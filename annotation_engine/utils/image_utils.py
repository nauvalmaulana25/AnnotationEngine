"""
AnnotationEngine Desktop - Image Utilities
"""
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Tuple, Optional, List
import hashlib


def load_image(image_path: Path) -> Optional[np.ndarray]:
    """Load image as numpy array (BGR)."""
    try:
        image = cv2.imread(str(image_path))
        return image
    except Exception:
        return None


def load_image_pil(image_path: Path) -> Optional[Image.Image]:
    """Load image as PIL Image."""
    try:
        return Image.open(image_path).convert('RGB')
    except Exception:
        return None


def save_image(image: np.ndarray, output_path: Path) -> bool:
    """Save numpy array as image."""
    try:
        cv2.imwrite(str(output_path), image)
        return True
    except Exception:
        return False


def resize_image(image: np.ndarray, max_dimension: int = 1024) -> np.ndarray:
    """Resize image maintaining aspect ratio."""
    h, w = image.shape[:2]
    if max(h, w) <= max_dimension:
        return image
    
    scale = max_dimension / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)


def normalize_image(image: np.ndarray, mean=None, std=None) -> np.ndarray:
    """Normalize image for model input."""
    if mean is None:
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    if std is None:
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    
    normalized = image.astype(np.float32) / 255.0
    normalized = (normalized - mean) / std
    return normalized


def denormalize_image(image: np.ndarray, mean=None, std=None) -> np.ndarray:
    """Denormalize image for visualization."""
    if mean is None:
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    if std is None:
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    
    denorm = image * std + mean
    denorm = np.clip(denorm * 255, 0, 255).astype(np.uint8)
    return denorm


def bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    """Convert BGR to RGB."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def rgb_to_bgr(image: np.ndarray) -> np.ndarray:
    """Convert RGB to BGR."""
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
    """Convert PIL Image to OpenCV BGR."""
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv2_image: np.ndarray) -> Image.Image:
    """Convert OpenCV BGR to PIL Image."""
    return Image.fromarray(cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB))


def get_image_hash(image_path: Path) -> str:
    """Compute SHA256 hash of image file."""
    hasher = hashlib.sha256()
    with open(image_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_image_pyramid(image: np.ndarray, levels: int = 4) -> List[np.ndarray]:
    """Create image pyramid for multi-scale processing."""
    pyramid = [image]
    for i in range(1, levels):
        h, w = pyramid[-1].shape[:2]
        if h < 32 or w < 32:
            break
        pyramid.append(cv2.resize(pyramid[-1], (w // 2, h // 2)))
    return pyramid


def non_max_suppression(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float = 0.5
) -> np.ndarray:
    """Apply Non-Maximum Suppression to boxes."""
    if len(boxes) == 0:
        return np.array([], dtype=np.int32)
    
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        
        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]
    
    return np.array(keep, dtype=np.int32)