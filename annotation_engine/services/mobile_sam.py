"""
AnnotationEngine Desktop - MobileSAM Service
"""
import os
import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple


class MobileSAMService:
    """MobileSAM instance segmentation via ONNX Runtime."""
    
    def __init__(self, model_path: str = ""):
        """
        Initialize MobileSAM service.
        
        Args:
            model_path: Path to mobile_sam.onnx file
        """
        if not model_path:
            # Default to models directory
            from annotation_engine.config import MODELS_DIR
            model_path = MODELS_DIR / "mobile_sam.onnx"
        
        self.model_path = str(model_path)
        self.session = None
        self._initialize_session()
    
    def _initialize_session(self):
        """Initialize ONNX Runtime session."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"MobileSAM model not found at {self.model_path}. "
                "Please run scripts/export_mobile_sam.py to generate it."
            )
        
        # Use CPU execution provider
        self.session = ort.InferenceSession(
            self.model_path,
            providers=['CPUExecutionProvider']
        )
        
        # Get input/output names
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [out.name for out in self.session.get_outputs()]
        
        print(f"MobileSAM loaded: {self.model_path}")
        print(f"Input: {self.input_name}")
        print(f"Outputs: {self.output_names}")
    
    def preprocess(self, image: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
        """
        Preprocess image for MobileSAM encoder.
        
        Returns:
            (preprocessed_tensor, original_size)
        """
        h, w = image.shape[:2]
        
        # Resize to 1024x1024 maintaining aspect ratio
        scale = 1024 / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        
        # Resize
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # Pad to 1024x1024
        padded = np.zeros((1024, 1024, 3), dtype=np.uint8)
        padded[:new_h, :new_w] = resized
        
        # Normalize (ImageNet stats)
        normalized = padded.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (normalized - mean) / std
        
        # HWC to CHW, add batch dimension
        tensor = np.transpose(normalized, (2, 0, 1))
        tensor = np.expand_dims(tensor, 0).astype(np.float32)
        
        return tensor, (h, w)
    
    def encode_image(self, image: np.ndarray) -> np.ndarray:
        """
        Run image encoder to get image embeddings.
        
        Args:
            image: BGR image as numpy array
            
        Returns:
            Image embeddings from encoder
        """
        # Convert BGR to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Preprocess
        input_tensor, original_size = self.preprocess(image_rgb)
        
        # Run encoder
        outputs = self.session.run(
            self.output_names,
            {self.input_name: input_tensor}
        )
        
        # First output is typically image embeddings
        image_embeddings = outputs[0]
        
        return image_embeddings, original_size
    
    def segment_from_boxes(
        self,
        image: np.ndarray,
        boxes: List[List[float]],
        image_embeddings: np.ndarray = None,
        original_size: Tuple[int, int] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[np.ndarray]:
        """
        Generate segmentation masks from bounding boxes.
        
        Args:
            image: Input image (BGR)
            boxes: List of [x1, y1, x2, y2] in original image coordinates
            image_embeddings: Pre-computed embeddings (optional)
            original_size: Original image size (h, w) (optional)
            progress_callback: Optional progress callback
            
        Returns:
            List of binary masks (H, W) as boolean arrays
        """
        if image_embeddings is None or original_size is None:
            image_embeddings, original_size = self.encode_image(image)
        
        h, w = original_size
        masks = []
        
        for i, box in enumerate(boxes):
            if progress_callback:
                progress_callback(
                    int((i / len(boxes)) * 100),
                    f"Segmenting box {i+1}/{len(boxes)}"
                )
            
            # Convert box to 1024 scale
            x1, y1, x2, y2 = box
            scale_x, scale_y = 1024 / w, 1024 / h
            box_1024 = np.array([
                x1 * scale_x, y1 * scale_y,
                x2 * scale_x, y2 * scale_y
            ], dtype=np.float32)
            
            # Run decoder with box prompt
            # Note: This depends on the specific ONNX export structure
            # The decoder typically takes: image_embeddings, box_prompts
            mask = self._run_decoder(image_embeddings, box_1024)
            
            # Resize mask to original image size
            mask = cv2.resize(mask.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
            mask = (mask > 0.5).astype(np.bool_)
            
            masks.append(mask)
        
        if progress_callback:
            progress_callback(100, f"Generated {len(masks)} masks")
        
        return masks
    
    def _run_decoder(self, image_embeddings: np.ndarray, box_prompt: np.ndarray) -> np.ndarray:
        """
        Run MobileSAM decoder with box prompt.
        
        Note: This is a simplified implementation. The actual decoder inputs
        depend on how the ONNX model was exported.
        """
        # This is a placeholder - actual implementation depends on ONNX structure
        # MobileSAM decoder typically needs:
        # - image_embeddings
        # - sparse_embeddings (from box/point prompts)
        # - dense_embeddings (from image)
        
        # For now, return a dummy mask matching the box
        # In production, this would call the actual decoder session
        return np.ones((1024, 1024), dtype=np.float32)
    
    def segment(
        self,
        image_path: str,
        boxes: List[List[float]],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[np.ndarray]:
        """
        Segment image from file using boxes.
        
        Args:
            image_path: Path to image file
            boxes: List of [x1, y1, x2, y2] in image coordinates
            progress_callback: Optional progress callback
            
        Returns:
            List of binary masks
        """
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Failed to load image: {image_path}")
        
        return self.segment_from_boxes(image, boxes, progress_callback=progress_callback)
    
    def batch_segment(
        self,
        image_paths: List[str],
        boxes_list: List[List[List[float]]],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, List[np.ndarray]]:
        """
        Segment multiple images.
        
        Args:
            image_paths: List of image file paths
            boxes_list: List of box lists for each image
            progress_callback: Optional progress callback
            
        Returns:
            Dict mapping image_path -> list of masks
        """
        results = {}
        total = len(image_paths)
        
        for i, (img_path, boxes) in enumerate(zip(image_paths, boxes_list)):
            if progress_callback:
                progress_callback(
                    int((i / total) * 100),
                    f"Processing {i+1}/{total}: {os.path.basename(img_path)}"
                )
            
            try:
                masks = self.segment(img_path, boxes)
                results[img_path] = masks
            except Exception as e:
                print(f"Error segmenting {img_path}: {e}")
                results[img_path] = []
        
        if progress_callback:
            progress_callback(100, f"Completed {total} images")
        
        return results