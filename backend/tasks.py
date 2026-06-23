"""
Celery tasks for SAM2 Video VFX Editor.
Handles lightweight async tasks like status updates, file prep, post-processing effects.
"""

import json
import os
import shutil
import sys
import tempfile
from typing import Optional

import numpy as np
import redis
import requests
from celery import Celery, Task
from kombu import Exchange, Queue

segment_anything_path = os.path.join(os.path.dirname(__file__), 'segment-anything-2')
if segment_anything_path not in sys.path:
    sys.path.append(segment_anything_path)

import storage
from data_saver import DataSaver
from sam2_segmenter import SAM2Segmenter, VideoObjectData
from utils import encode_mask, unique_filename

# Initialize Celery app
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)

celery_app = Celery("sam2_tasks", broker=CELERY_BROKER_URL, backend=REDIS_URL)

_redis_client = redis.from_url(REDIS_URL)


def publish_job_progress(job_id: str, payload: dict) -> None:
    """Publishes progress to Redis pub/sub; backend/ws_listener.py forwards it to SocketIO clients."""
    try:
        _redis_client.publish(f"job:{job_id}:progress", json.dumps(payload))
    except Exception as exc:
        print(f"[{job_id}] Failed to publish progress: {exc}")


def send_telegram(message: str) -> None:
    """Best-effort Telegram notification; never raises so it can't fail a job."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
        )
    except Exception as exc:
        print(f"Failed to send Telegram notification: {exc}")

# Celery config
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    default_queue="default",
    queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("priority", Exchange("priority"), routing_key="priority"),
    ),
)


class CallbackTask(Task):
    """Task with callbacks for progress tracking via Redis pub/sub."""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Success callback."""
        print(f"Task {task_id} succeeded: {retval}")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Failure callback."""
        print(f"Task {task_id} failed: {exc}")


def _parse_video_objects(video_objects_json: str, scale_factor: float):
    """Parse the JSON list of points/labels sent by the frontend into VideoObjectData."""
    objects = json.loads(video_objects_json)
    parsed = []

    for idx, obj in enumerate(objects):
        points_raw = obj.get("points")
        labels_raw = obj.get("labels")

        if not points_raw or not labels_raw or len(points_raw) != len(labels_raw):
            raise ValueError(f"Points and labels invalid for object index {idx}")

        parsed.append(VideoObjectData(
            points=np.array(points_raw, dtype=np.float32) * scale_factor,
            labels=np.array(labels_raw, dtype=np.int32),
            ann_frame_idx=int(obj.get("ann_frame_idx", 0)),
            ann_obj_id=int(obj.get("ann_obj_id", 1)),
        ))

    return parsed


@celery_app.task(name="generate_video_masks", base=CallbackTask, bind=True)
def generate_video_masks(self, video_key: str, video_objects_json: str, scale_factor: float,
                          start_frame: int, end_frame: int, stage_name: Optional[str] = None):
    """
    Run SAM2 inference for a video that was uploaded to MinIO/R2, and store the
    serialized masks back in MinIO/R2 under a stage so /download can reuse them.

    Args:
        video_key: Object key of the input video in the videos bucket.
        video_objects_json: JSON-encoded list of {points, labels, ann_frame_idx, ann_obj_id}.
        scale_factor: Scale applied to the video (and to the points) before inference.
        start_frame: First frame to process.
        end_frame: Last frame to process, or -1 for the end of the video.
        stage_name: Optional existing stage name to reuse/overwrite.

    Returns:
        dict with the serialized per-frame masks and the stage name (track_id).
    """
    job_id = self.request.id
    tmp_path = None
    output_dir = None

    try:
        self.update_state(state='PROGRESS', meta={'stage': 'downloading'})
        publish_job_progress(job_id, {'status': 'pending', 'stage': 'downloading'})

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
            tmp_path = tmp.name
        storage.download_file(storage.VIDEOS_BUCKET, video_key, tmp_path)

        video_objects = _parse_video_objects(video_objects_json, scale_factor)
        output_dir = tempfile.mkdtemp(prefix=f'sam2_frames_{job_id}_')

        self.update_state(state='PROGRESS', meta={'stage': 'segmenting'})
        publish_job_progress(job_id, {'status': 'pending', 'stage': 'segmenting'})

        def on_frame_progress(frame, total):
            publish_job_progress(job_id, {
                'status': 'pending', 'stage': 'segmenting', 'frame': frame, 'total': total,
            })

        segmenter = SAM2Segmenter()
        result = segmenter.generate_masks_for_video(
            video_path=tmp_path,
            video_objects_data=video_objects,
            output_dir=output_dir,
            scale_factor=scale_factor,
            start_frame=start_frame,
            end_frame=None if end_frame == -1 else end_frame,
            debug_points=False,
            on_frame_progress=on_frame_progress,
        )

        self.update_state(state='PROGRESS', meta={'stage': 'finishing'})
        publish_job_progress(job_id, {'status': 'pending', 'stage': 'finishing'})

        serialized_result = {}
        for frame_idx, frame_data in result.items():
            frame_idx = frame_idx + start_frame
            serialized_frame = {}
            for obj_id, mask in frame_data.items():
                if mask is None or mask.size == 0:
                    continue
                serialized_frame[obj_id] = {
                    "shape": mask.shape,
                    "data": f"data:image/png;base64,{encode_mask(mask)}",
                }
            serialized_result[frame_idx] = serialized_frame

        final_stage_name = stage_name or unique_filename('stages', prefix='track_masks_stage_', ext='')
        DataSaver.add_stage(final_stage_name, serialized_result)

        publish_job_progress(job_id, {'status': 'done', 'track_id': final_stage_name})
        send_telegram(f"✅ SAM2 job {job_id} completed successfully!")
        # Não devolver serialized_result aqui: iria para o result backend do Celery (Redis),
        # que não é feito para blobs grandes. Já está gravado no MinIO via DataSaver.add_stage;
        # quem precisar dele lê de lá (ver /video/mask/status em app.py).
        return {"track_id": final_stage_name}

    except Exception as exc:
        publish_job_progress(job_id, {'status': 'failed', 'error': str(exc)})
        send_telegram(f"❌ SAM2 job {job_id} failed: {exc}")
        raise

    finally:
        # A limpeza não deve mascarar um resultado/erro real da task
        try:
            storage.delete_object(storage.VIDEOS_BUCKET, video_key)
        except Exception as cleanup_exc:
            print(f"[{job_id}] Failed to delete uploaded video {video_key}: {cleanup_exc}")
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        if output_dir and os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)


@celery_app.task(name="prepare_video", base=CallbackTask)
def prepare_video(job_id: str, input_video_url: str):
    """
    Prepare video for inference: download, validate, extract frames.
    
    Args:
        job_id: Unique job identifier
        input_video_url: S3/MinIO URL of input video
    
    Returns:
        dict with status and frame info
    """
    try:
        print(f"[{job_id}] Preparing video from {input_video_url}")
        # TODO: Download from MinIO/S3, validate video, extract metadata
        return {"status": "prepared", "frames": 0}
    except Exception as e:
        print(f"[{job_id}] Error preparing video: {e}")
        raise


@celery_app.task(name="post_process_effect", base=CallbackTask)
def post_process_effect(job_id: str, effect_type: str, mask_frames_url: str):
    """
    Post-process effect frames after SAM2 inference completes.
    Apply color correction, blending, animations, etc.
    
    Args:
        job_id: Unique job identifier
        effect_type: Type of effect (color, blend, overlay, etc.)
        mask_frames_url: S3/MinIO URL prefix for mask frames
    
    Returns:
        dict with output URL
    """
    try:
        print(f"[{job_id}] Post-processing effect: {effect_type}")
        # TODO: Load masks, apply effects, upload result
        return {"status": "processed", "output_url": ""}
    except Exception as e:
        print(f"[{job_id}] Error post-processing: {e}")
        raise


@celery_app.task(name="cleanup_temp_files", base=CallbackTask)
def cleanup_temp_files(job_id: str, frame_prefix: str):
    """
    Clean up temporary frame files from MinIO after job completes.
    
    Args:
        job_id: Unique job identifier
        frame_prefix: Prefix in MinIO for frames to delete
    
    Returns:
        dict with deleted count
    """
    try:
        print(f"[{job_id}] Cleaning up frames: {frame_prefix}")
        # TODO: Delete frames from MinIO
        return {"status": "cleaned", "deleted_count": 0}
    except Exception as e:
        print(f"[{job_id}] Error cleaning up: {e}")
        raise


@celery_app.task(name="update_job_status", base=CallbackTask)
def update_job_status(job_id: str, status: str, progress: int = 0, error_msg: str = None):
    """
    Update job status in database and publish to Redis for WebSocket updates.
    
    Args:
        job_id: Unique job identifier
        status: Job status (queued, running, completed, failed)
        progress: Progress percentage (0-100)
        error_msg: Optional error message if failed
    
    Returns:
        dict with updated status
    """
    try:
        print(f"[{job_id}] Updating status: {status} ({progress}%)")
        # TODO: Update Postgres, publish to Redis pub/sub
        return {"status": status, "progress": progress}
    except Exception as e:
        print(f"[{job_id}] Error updating status: {e}")
        raise


if __name__ == "__main__":
    celery_app.start()
