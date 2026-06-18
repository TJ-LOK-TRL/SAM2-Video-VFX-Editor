import os

import cv2
import torch
import base64
from typing import *

import numpy as np
import supervision as sv
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from PIL import Image
from pathlib import Path
from supervision.assets import download_assets, VideoAssets
from data_saver import DataSaver
from io import BytesIO
from dataclasses import dataclass

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
from sam2.build_sam import build_sam2_video_predictor

@dataclass
class VideoObjectData:
    points: Optional[np.ndarray] = None,
    labels: Optional[np.ndarray] = None,
    ann_frame_idx: int = 0,
    ann_obj_id: int = 1,

class SAM2Segmenter:
    HOME = os.path.join(os.path.dirname(__file__), 'segment-anything-2')
    MODEL_SIZE_BASE = 'base_plus'
    MODEL_SIZE_LARGE = 'large'
    MODEL_SIZE_SMALL = 'small'
    MODEL_SIZE_TINY = 'tiny'
    
    def __init__(self, model_size: str = MODEL_SIZE_TINY) -> None:
        # Set the device to GPU if available, otherwise fallback to CPU
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        if self.device.type == 'cuda':
            # Enable autocasting for CUDA with bfloat16 precision to optimize performance
            torch.autocast(device_type='cuda', dtype=torch.bfloat16).__enter__()

            # If the GPU supports TensorFloat-32 (e.g., Ampere or newer), enable it for better performance
            if torch.cuda.get_device_properties(0).major >= 8:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
        
        # Define the path to the SAM2 configuration file
        self.config = os.path.join(SAM2Segmenter.HOME, 'sam2', 'configs', 'sam2', 'sam2_hiera_t.yaml')
        
        # Define the path to the pre-trained model checkpoint based on the model size
        self.model_path = os.path.join(SAM2Segmenter.HOME, 'checkpoints', f'sam2_hiera_{model_size}.pt')
        
        # Load the base SAM2 model with the given configuration and checkpoint
        self.model = build_sam2('/' + os.path.abspath(self.config), self.model_path, 
                                device=self.device, apply_postprocessing=False)
        
        # Load the video prediction model (used for handling temporal context in video)
        self.video_model = build_sam2_video_predictor('/' + os.path.abspath(self.config), self.model_path,
                                                       device=self.device)
        
        # Initialize the automatic mask generator using the base SAM2 model
        self.mask_generator = SAM2AutomaticMaskGenerator(self.model)

    def generate_mask_for_image(self, img_path: str) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
        image_bgr = cv2.imread(img_path)
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

        sam2_result = self.mask_generator.generate(image_rgb)
        return image_bgr, image_rgb, sam2_result
    
    def generate_masks_for_video(
        self,
        video_path: Union[str, Path],
        video_objects_data: List[VideoObjectData],
        output_dir: Optional[Union[str, Path]] = None,
        scale_factor: float = 1.0,
        start_frame: int = 0,
        end_frame: Optional[int] = None,
        frame_pattern: str = "{:05d}.jpeg",
        overwrite: bool = False,
        debug_points: bool = False,
    ) -> Tuple[Dict, Path]:        
        """
        Generates segmentation masks for a given video using point-based annotations.

        Args:
            video_path (Union[str, Path]): Path to the input video file.
            video_objects_data (List[VideoObjectData]): A list of VideoObjectData instances,
                each containing point annotations, labels, object ID, and frame index.
            output_dir (Optional[Union[str, Path]], optional): Directory to store extracted frames 
                and intermediate results. If not provided, defaults to the same directory as the video.
            scale_factor (float, optional): Factor to scale frames during processing. 
                Useful for faster inference. Default is 1.0 (no scaling).
            start_frame (int, optional): Index of the frame to start processing from. Default is 0.
            end_frame (Optional[int], optional): Index of the last frame to process. 
                If None, processes until the end of the video. Default is None.
            frame_pattern (str, optional): Naming pattern for extracted frame images. 
                Default is "{:05d}.jpeg".
            overwrite (bool, optional): If True, re-extracts frames even if they already exist. 
                Default is False.
            debug_points (bool, optional): If True, displays visual feedback of added points 
                on frames for debugging. Default is False.

        Returns:
            Tuple[Dict, Path]: 
                - A dictionary mapping frame indices to object masks (as NumPy arrays).
                - The path to the directory containing the extracted frames.
        """
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract video frames and save them as individual images
        frame_paths = self._extract_frames(
            video_path,
            output_dir,
            scale_factor,
            start_frame,
            end_frame,
            frame_pattern,
            overwrite
        )
        
        print('Output dir is:', output_dir.as_posix())
        
        # Initialize model inference state using extracted frames
        self.inference_state = self.video_model.init_state(video_path=output_dir.as_posix())
        self.current_video_path = output_dir
        
        # Iterate through each annotated object
        for vod in video_objects_data:
            if vod.points is not None and vod.labels is not None:
                # Add user-provided points and labels to the model
                _, out_obj_ids, out_mask_logits = self.video_model.add_new_points_or_box(
                    inference_state=self.inference_state,
                    frame_idx=vod.ann_frame_idx - start_frame,
                    obj_id=vod.ann_obj_id,
                    points=vod.points,
                    labels=vod.labels
                )   
            
            # Optionally visualize debug information
            if debug_points:
                self.show_results_on_interacted_frame(vod.points, vod.labels, frame_paths[vod.ann_frame_idx], 
                                                      vod.ann_frame_idx, out_obj_ids, out_mask_logits)
                
            print(f"Pontos adicionados no frame {vod.ann_frame_idx} com obj_id {vod.ann_obj_id}.")
        
        # Propagate the segmentation masks throughout the video frames
        video_segments = {}
        for out_frame_idx, out_obj_ids, out_mask_logits in self.video_model.propagate_in_video(self.inference_state):
            video_segments[out_frame_idx] = {
                out_obj_id: (out_mask_logits[i] > 0.0).cpu().numpy()
                for i, out_obj_id in enumerate(out_obj_ids)
            }

        return video_segments
    
    def _extract_frames(
        self,
        video_path: Path,
        output_dir: Path,
        scale_factor: float,
        start_frame: int,
        end_frame: Optional[int],
        frame_pattern: str,
        overwrite: bool
    ) -> List[Path]:
        """Extract frames from video and save to output directory."""
        print(start_frame, end_frame)
        frames_generator = sv.get_video_frames_generator(
            video_path.as_posix(),
            start=start_frame,
            end=end_frame
        )
        
        images_sink = sv.ImageSink(
            target_dir_path=output_dir.as_posix(),
            overwrite=overwrite,
            image_name_pattern=frame_pattern
        )
        
        # Begin writing frames to the image sink (e.g., saving frames to disk)
        with images_sink:
            # Iterate over each frame from the generator, starting at the specified frame index
            for i, frame in enumerate(frames_generator, start=start_frame):
                # If a scaling factor is provided (not 1.0), resize the frame accordingly for efficiency
                if scale_factor != 1.0:
                    frame = sv.scale_image(frame, scale_factor)
                # Save the processed frame (scaled or original) using the sink
                images_sink.save_image(frame)
        
        return sorted(sv.list_files_with_extensions(output_dir.as_posix(), extensions=["jpeg"]))
    
    def show_sam_result(self, image_bgr: np.ndarray, image_sam_data: List[Dict]):
        mask_annotator = sv.MaskAnnotator(color_lookup=sv.ColorLookup.INDEX)
        detections = sv.Detections.from_sam(sam_result=image_sam_data)

        annotated_image = mask_annotator.annotate(scene=image_bgr.copy(), detections=detections)

        sv.plot_images_grid(
            images=[image_bgr, annotated_image],
            grid_size=(1, 2),
            titles=['source image', 'segmented image']
        )
    
    def show_results_on_interacted_frame(
        self, 
        points: np.ndarray, 
        labels: np.ndarray,
        frame_path: str,
        ann_frame_idx: int, 
        out_obj_ids: List,
        out_mask_logits: List,
    ) -> None:
        plt.figure(figsize=(9, 6))
        plt.title(f"frame {ann_frame_idx}")
        plt.imshow(Image.open(frame_path))
        self.show_points(points, labels, plt.gca())
        self.show_mask((out_mask_logits[0] > 0.0).cpu().numpy(), plt.gca(), obj_id=out_obj_ids[0])
        
    @staticmethod
    def show_mask(mask: np.ndarray, ax: Axes, obj_id: Optional[int] = None, random_color: bool = False) -> None:
        """
        Mostra uma máscara sobre um eixo matplotlib.

        Args:
            mask (np.ndarray): Máscara binária de segmentação (altura, largura).
            ax (Axes): Objeto matplotlib para renderizar a máscara.
            obj_id (Optional[int]): Identificador do objeto para escolher uma cor específica. Se None, usa cor padrão.
            random_color (bool): Se True, usa uma cor aleatória. Caso contrário, usa uma cor baseada no obj_id.
        """
        if random_color:
            color = np.concatenate([np.random.random(3), np.array([0.6])], axis=0)
        else:
            cmap = plt.get_cmap("tab10")
            cmap_idx = 0 if obj_id is None else obj_id
            color = np.array([*cmap(cmap_idx)[:3], 0.6])
        
        h, w = mask.shape[-2:]
        mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
        ax.imshow(mask_image)

    @staticmethod
    def show_points(coords: np.ndarray, labels: np.ndarray, ax: Axes, marker_size: int = 200) -> None:
        """
        Mostra pontos positivos e negativos sobre um eixo matplotlib.

        Args:
            coords (np.ndarray): Coordenadas dos pontos, shape (N, 2).
            labels (np.ndarray): Labels dos pontos, 1 para positivo, 0 para negativo.
            ax (Axes): Objeto matplotlib para renderizar os pontos.
            marker_size (int): Tamanho dos marcadores dos pontos.
        """
        pos_points = coords[labels == 1]
        neg_points = coords[labels == 0]

        ax.scatter(pos_points[:, 0], pos_points[:, 1], color='green', marker='*', s=marker_size,
                edgecolor='white', linewidth=1.25)
        ax.scatter(neg_points[:, 0], neg_points[:, 1], color='red', marker='*', s=marker_size,
                edgecolor='white', linewidth=1.25)

    @staticmethod
    def show_box(box: np.ndarray, ax: Axes) -> None:
        """
        Mostra uma caixa delimitadora sobre um eixo matplotlib.

        Args:
            box (np.ndarray): Coordenadas da caixa no formato [x0, y0, x1, y1].
            ax (Axes): Objeto matplotlib para renderizar a caixa.
        """
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        ax.add_patch(plt.Rectangle((x0, y0), w, h, edgecolor='green', facecolor=(0, 0, 0, 0), lw=2))
    
    @staticmethod
    def render_segmentation(video_segments: Dict, frames_dir: str, frame_stride: int = 30, start: int = 0) -> None:
        plt.close('all')
        frames_paths = os.listdir(frames_dir)
        for out_frame_idx in range(start, start+len(frames_paths), frame_stride):
            plt.figure(figsize=(6, 4))
            plt.title(f'frame {out_frame_idx}')
            plt.imshow(Image.open(os.path.join(frames_dir, frames_paths[out_frame_idx - start])))
            for out_obj_id, out_mask in video_segments[out_frame_idx].items():
                if isinstance(out_mask, np.ndarray):
                    SAM2Segmenter.show_mask(out_mask, plt.gca(), obj_id=out_obj_id)
                elif isinstance(out_mask, dict):
                    mask_base64 = out_mask['data']
                    
                    # Remove o prefixo "data:image/png;base64," se existir
                    if mask_base64.startswith('data:image'):
                        mask_base64 = mask_base64.split(',', 1)[1]
                    
                    mask_bytes = base64.b64decode(mask_base64)
                    mask_image = Image.open(BytesIO(mask_bytes)).convert('L')  # escala de cinza
                    mask_numpy = np.array(mask_image) > 0  # máscara binária (True / False)
                    
                    SAM2Segmenter.show_mask(mask_numpy, plt.gca(), obj_id=out_obj_id)
            plt.show()
    
if __name__ == '__main__':
    # Testar uma imagem
    sam2 = SAM2Segmenter()
    if 0:
        img_bgr, img_rgb, sam_result = sam2.generate_mask_for_image('images\\dog-2.jpeg')
        sam2.show_sam_result(img_bgr, sam_result)    
    
    # Testar com video
    if 1:
        print('Started')
        stage_name = '214703_tiny.mp4_track_masks'
        result = DataSaver.get_stage(stage_name)
        #if result == None:
        #    points = np.array([[250, 50], [250, 220]], dtype=np.float32)
        #    labels = np.array([1, 1], np.int32)
        #    
        #    result = sam2.generate_masks_for_video(
        #        'videos\\video1.mp4', 
        #        'videos\\video1_frames\\', 
        #        scale_factor=.5,
        #        points=points,
        #        labels=labels,
        #        ann_frame_idx=0,
        #        ann_obj_id=1,
        #        debug_points=True)
        #    DataSaver.add_stage(stage_name, result)
            
        print(type(result))
        print(len(result.items()))
        print(result.keys())
        #for mask in result.items():
        #    print(mask)
        SAM2Segmenter.render_segmentation(result, os.path.join('videos', 'frames', stage_name), frame_stride=1, start=0)