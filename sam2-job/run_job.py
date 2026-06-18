import base64
import json
import os
import shutil
import sys
import tempfile
from io import BytesIO
from pathlib import Path

# Setup SAM2 import paths
sys.path.insert(0, '/app/backend')
sys.path.insert(0, '/app/backend/segment-anything-2')

import boto3
from boto3.session import Config
import psycopg2
import redis
import cv2
import numpy as np

from sam2_segmenter import SAM2Segmenter, VideoObjectData
from utils import encode_mask


def env_or_raise(key: str):
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Required env var {key} is missing")
    return value


def get_storage_client():
    provider = os.getenv('STORAGE_PROVIDER', 'minio').lower()
    if provider == 'minio':
        return boto3.client(
            's3',
            endpoint_url=f"http://{env_or_raise('MINIO_ENDPOINT')}",
            aws_access_key_id=env_or_raise('MINIO_USER'),
            aws_secret_access_key=env_or_raise('MINIO_PASSWORD'),
            config=Config(signature_version='s3v4')
        )

    if provider == 'r2':
        return boto3.client(
            's3',
            endpoint_url=env_or_raise('R2_ENDPOINT'),
            aws_access_key_id=env_or_raise('R2_ACCESS_KEY'),
            aws_secret_access_key=env_or_raise('R2_SECRET_KEY'),
            config=Config(signature_version='s3v4')
        )

    raise RuntimeError(f"Unsupported storage provider: {provider}")


def publish_progress(redis_client, job_id, payload):
    channel = f"job:{job_id}:progress"
    redis_client.publish(channel, json.dumps(payload))


def download_input_video(storage_client, bucket, key, local_path):
    with open(local_path, 'wb') as f:
        storage_client.download_fileobj(bucket, key, f)


def upload_json(storage_client, bucket, key, data):
    storage_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data).encode('utf-8'),
        ContentType='application/json'
    )


def update_job_row(conn, job_id, status, result_path=None, error=None):
    with conn.cursor() as curs:
        curs.execute(
            "UPDATE inference_jobs SET status=%s, result_path=%s, completed_at=NOW(), error=%s WHERE id=%s",
            (status, result_path, error, job_id)
        )
        conn.commit()


def parse_video_objects(json_text, scale_factor):
    objects = json.loads(json_text)
    parsed = []

    for obj in objects:
        points_raw = obj.get('points')
        labels_raw = obj.get('labels')
        if not points_raw or not labels_raw or len(points_raw) != len(labels_raw):
            raise ValueError('Invalid video_objects data')

        points = np.array(points_raw, dtype=np.float32) * scale_factor
        labels = np.array(labels_raw, dtype=np.int32)

        parsed.append(
            VideoObjectData(
                points=points,
                labels=labels,
                ann_frame_idx=int(obj.get('ann_frame_idx', 0)),
                ann_obj_id=int(obj.get('ann_obj_id', 1)),
            )
        )

    return parsed


def serialize_masks(mask_map):
    serialized = {}
    for frame_idx, frame_data in mask_map.items():
        serialized_frame = {}
        for obj_id, mask in frame_data.items():
            if mask is None:
                continue

            serialized_frame[obj_id] = {
                'shape': mask.shape,
                'data': f"data:image/png;base64,{encode_mask(mask)}"
            }

        serialized[frame_idx] = serialized_frame
    return serialized


def main():
    job_id = env_or_raise('JOB_ID')
    input_key = env_or_raise('INPUT_VIDEO_KEY')
    provider = os.getenv('STORAGE_PROVIDER', 'minio').lower()
    scale_factor = float(os.getenv('SCALE_FACTOR', '0.5'))
    start_frame = int(os.getenv('START_FRAME', '0'))
    end_frame = int(os.getenv('END_FRAME', '-1'))
    video_objects_json = env_or_raise('VIDEO_OBJECTS_JSON')
    bucket_videos = os.getenv('R2_BUCKET_VIDEOS') or 'videos'
    bucket_outputs = os.getenv('R2_BUCKET_OUTPUTS') or 'outputs'

    redis_url = env_or_raise('REDIS_URL')
    database_url = env_or_raise('DATABASE_URL')

    redis_client = redis.from_url(redis_url)
    publish_progress(redis_client, job_id, {'status': 'downloading'})

    storage_client = get_storage_client()

    tmp_dir = tempfile.mkdtemp(prefix='sam2_job_')
    input_video_path = os.path.join(tmp_dir, 'input_video.mp4')
    try:
        download_input_video(storage_client, bucket_videos, input_key, input_video_path)

        publish_progress(redis_client, job_id, {'status': 'segmenting', 'frame': 0, 'total': 0})

        video_objects = parse_video_objects(video_objects_json, scale_factor)

        segmenter = SAM2Segmenter()
        mask_map = segmenter.generate_masks_for_video(
            video_path=input_video_path,
            video_objects_data=video_objects,
            output_dir=os.path.join(tmp_dir, 'frames'),
            scale_factor=scale_factor,
            start_frame=start_frame,
            end_frame=None if end_frame == -1 else end_frame,
            debug_points=False,
        )

        serialized = serialize_masks(mask_map)
        output_key = f"outputs/{job_id}/masks.json"
        upload_json(storage_client, bucket_outputs, output_key, serialized)

        conn = psycopg2.connect(database_url)
        update_job_row(conn, job_id, 'done', output_key, None)
        conn.close()

        publish_progress(redis_client, job_id, {'status': 'done'})
        print(f"Job {job_id} completed successfully")

    except Exception as exc:
        try:
            conn = psycopg2.connect(database_url)
            update_job_row(conn, job_id, 'failed', None, str(exc))
            conn.close()
        except Exception:
            pass
        publish_progress(redis_client, job_id, {'status': 'failed', 'error': str(exc)})
        print(f"Job failed: {exc}")
        sys.exit(1)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
