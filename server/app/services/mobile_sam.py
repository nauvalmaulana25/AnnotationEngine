import numpy as np
import onnxruntime as ort
from typing import List, Tuple
from PIL import Image


class MobileSAMService:
    def __init__(self, model_path: str = None):
        from app.core.config import get_settings
        settings = get_settings()
        self.model_path = model_path or settings.MOBILE_SAM_MODEL_PATH
        
        # Initialize ONNX Runtime session
        self.session = ort.InferenceSession(
            self.model_path,
            providers=['CPUExecutionProvider']
        )
        
        # Get input/output names
        self.input_names = [inp.name for inp in self.session.get_inputs()]
        self.output_names = [out.name for out in self.session.get_outputs()]
        
        # Image encoder expects 1024x1024
        self.input_size = 1024
        self.mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
        self.std = np.array([58.395, 57.12, 57.375], dtype=np.float32)
    
    def _preprocess_image(self, image: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
        """Preprocess image for MobileSAM encoder."""
        h, w = image.shape[:2]
        
        # Resize to 1024x1024 maintaining aspect ratio
        scale = self.input_size / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        
        # Resize
        resized = cv2.resize(image, (new_w, new_h))
        
        # Pad to 1024x1024
        padded = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        padded[:new_h, :new_w] = resized
        
        # Normalize
        normalized = (padded.astype(np.float32) - self.mean) / self.std
        # HWC to CHW
        normalized = normalized.transpose(2, 0, 1)
        # Add batch dimension
        normalized = np.expand_dims(normalized, axis=0)
        
        return normalized, (new_h, new_w), (h, w), scale
    
    def _encode_image(self, image: np.ndarray) -> np.ndarray:
        """Run image encoder to get embeddings."""
        preprocessed, _, _, _ = self._preprocess_image(image)
        
        # Run encoder
        outputs = self.session.run(
            self.output_names,
            {self.input_names[0]: preprocessed}
        )
        
        # First output is typically image embeddings
        return outputs[0]
    
    def segment(
        self, 
        image: np.ndarray, 
        boxes: List[List[float]]
    ) -> List[np.ndarray]:
        """
        Segment image using box prompts.
        
        Args:
            image: Input image as numpy array (H, W, 3) RGB
            boxes: List of [x1, y1, x2, y2] in original image coordinates
            
        Returns:
            List of binary masks (H, W) for each box
        """
        if not boxes:
            return []
        
        # Get original dimensions
        orig_h, orig_w = image.shape[:2]
        
        # Preprocess and encode image once
        preprocessed, (new_h, new_w), _, scale = self._preprocess_image(image)
        image_embeddings = self._encode_image(image)
        
        masks = []
        
        for box in boxes:
            x1, y1, x2, y2 = box
            
            # Convert box to resized coordinates
            box_resized = [
                x1 * scale,
                y1 * scale,
                x2 * scale,
                y2 * scale
            ]
            
            # Prepare prompt inputs (box coordinates)
            # MobileSAM expects specific format for box prompts
            # This is simplified - actual implementation depends on exported ONNX model structure
            prompt_input = self._prepare_box_prompt(box_resized, new_w, new_h)
            
            # Run decoder with image embeddings and prompt
            decoder_outputs = self.session.run(
                ["masks", "iou_predictions", "low_res_logits"],
                {
                    "image_embeddings": image_embeddings,
                    "point_coords": prompt_input["point_coords"],
                    "point_labels": prompt_input["point_labels"],
                    "boxes": prompt_input["boxes"]
                }
            )
            
            mask = decoder_outputs[0][0, 0]  # Take first mask
            
            # Resize mask back to original size
            mask = cv2.resize(mask, (orig_w, orig_h))
            mask = (mask > 0.5).astype(np.uint8)
            
            masks.append(mask)
        
        return masks
    
    def _prepare_box_prompt(self, box: List[float], w: int, h: int) -> dict:
        """Prepare box prompt for MobileSAM decoder."""
        x1, y1, x2, y2 = box
        
        # Normalize to 0-1
        box_norm = np.array([[
            [x1 / w, y1 / h],
            [x2 / w, y2 / h]
        ]], dtype=np.float32)
        
        # Point coords (dummy for box-only)
        point_coords = np.zeros((1, 1, 2), dtype=np.float32)
        point_labels = np.zeros((1, 1), dtype=np.float32)
        
        return {
            "boxes": box_norm,
            "point_coords": point_coords,
            "point_labels": point_labels
        }


# For now, provide a fallback implementation that works with ultralytics SAM
# if ONNX model is not available
class MobileSAMServiceFallback:
    """Fallback using ultralytics SAM if ONNX not available."""
    
    def __init__(self, model_path: str = None):
        try:
            from ultralytics import SAM
            self.model = SAM("mobile_sam.pt")  # Will download if not present
            self.use_ultralytics = True
        except ImportError:
            self.use_ultralytics = False
            raise RuntimeError("Neither ONNX nor ultralytics SAM available")
    
    def segment(self, image: np.ndarray, boxes: List[List[float]]) -> List[np.ndarray]:
        if not boxes:
            return []
        
        from PIL import Image as PILImage
        pil_img = PILImage.fromarray(image)
        
        masks = []
        for box in boxes:
            x1, y1, x2, y2 = box
            # Ultralytics SAM expects [x, y, w, h] or similar
            results = self.model(pil_img, bboxes=[[x1, y1, x2 - x1, y2 - y1]])
            
            if results and len(results) > 0:
                for r in results:
                    if r.masks is not None:
                        for mask in r.masks.data:
                            mask_np = mask.cpu().numpy()
                            mask_resized = cv2.resize(mask_np, (image.shape[1], image.shape[0]))
                            masks.append((mask_resized > 0.5).astype(np.uint8))
        
        return masks


# Try to import cv2, use fallback if not available
try:
    import cv2
except ImportError:
    cv2 = None
    print("Warning: opencv-python-headless not installed, MobileSAM will use fallback")