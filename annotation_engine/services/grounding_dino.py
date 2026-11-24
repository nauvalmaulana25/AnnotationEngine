"""
AnnotationEngine Desktop - Grounding DINO Service

Two backends:

* ``LocalGroundingDINOService`` runs ``IDEA-Research/grounding-dino-tiny``
  locally via ``transformers`` when a CUDA GPU with enough VRAM is available.
* ``GroundingDINOService`` / ``GroundingDINOSync`` offload to the Hugging Face
  Inference API (used when local inference is not possible).

:func:`grounding_dino_mode` picks the backend from the hardware.
"""
import base64
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

import httpx

from annotation_engine.services.device import (
    DEVICE_AUTO,
    DEVICE_CPU,
    can_run_local_grounding_dino,
    describe_device,
    resolve_device,
)

# Hugging Face model backing the local path (public; no token required).
GROUNDING_DINO_MODEL_ID = "IDEA-Research/grounding-dino-tiny"


def grounding_dino_mode() -> str:
    """Return ``"local"`` when a GPU with enough VRAM is available, else ``"cloud"``."""
    return "local" if can_run_local_grounding_dino() else "cloud"


class LocalGroundingDINOService:
    """Grounding DINO object detection running locally via transformers."""

    def __init__(self, model_id: str = GROUNDING_DINO_MODEL_ID,
                 device: str = DEVICE_AUTO):
        self.model_id = model_id
        self.device_preference = device
        self.device = resolve_device(device)
        self._processor = None
        self._model = None

    @property
    def device_description(self) -> str:
        return describe_device(self.device)

    def load(self, progress_callback: Optional[Callable[[int, str], None]] = None):
        """Load the transformers model, deferring the (slow) imports."""
        if self._model is not None:
            return
        if progress_callback:
            progress_callback(
                0, f"Loading {self.model_id} on {self.device_description}"
            )
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
            self.model_id
        )
        try:
            self._model.to(self.device)
        except Exception:  # a device that vanished mid-run
            self.device = DEVICE_CPU
            self._model.to(DEVICE_CPU)
        self._model.eval()
        if progress_callback:
            progress_callback(100, "Grounding DINO loaded")

    def detect(
        self,
        image_path: str,
        prompts: List[str],
        threshold: float = 0.3,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Detect ``prompts`` and return ``[{label, score, box}]`` entries."""
        import torch
        from PIL import Image

        self.load(progress_callback)
        image = Image.open(image_path).convert("RGB")
        height, width = image.height, image.width

        detections: List[Dict[str, Any]] = []
        total = max(len(prompts), 1)
        for i, prompt in enumerate(prompts):
            if progress_callback:
                progress_callback(
                    int((i / total) * 100), f"Detecting '{prompt}'"
                )
            text = f"{prompt}."
            inputs = self._processor(
                images=image, text=text, return_tensors="pt"
            ).to(self.device)
            with torch.no_grad():
                outputs = self._model(**inputs)
            results = self._processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                threshold=threshold,
                target_sizes=[(height, width)],
            )
            if not results:
                continue
            result = results[0]
            boxes = result.get("boxes")
            if boxes is None or len(boxes) == 0:
                continue
            boxes = boxes.cpu().tolist()
            scores = result.get("scores")
            score_list = (
                scores.cpu().tolist() if scores is not None else [1.0] * len(boxes)
            )
            for box, score in zip(boxes, score_list):
                x1, y1, x2, y2 = box
                detections.append({
                    'label': prompt,
                    'score': float(score),
                    'box': [float(x1), float(y1), float(x2), float(y2)],
                })

        if progress_callback:
            progress_callback(100, f"Found {len(detections)} objects")
        return detections

    def unload(self):
        self._model = None
        self._processor = None


class GroundingDINOService:
    """Grounding DINO object detection via Hugging Face Inference API."""
    
    def __init__(self, api_key: str = ""):
        self.api_url = "https://api-inference.huggingface.co/models/IDEA-Research/grounding-dino-tiny"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.AsyncClient(timeout=120.0)
    
    def set_api_key(self, api_key: str):
        """Update API key."""
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    
    async def detect(
        self, 
        image_path: str, 
        text_prompt: str, 
        threshold: float = 0.3,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Run Grounding DINO detection on an image.
        
        Returns:
            List of detections: [{label, score, box: [x1, y1, x2, y2]}, ...]
        """
        if progress_callback:
            progress_callback(10, "Loading image...")
        
        # Read image
        try:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
        except Exception as e:
            raise RuntimeError(f"Failed to read image: {e}")
        
        if progress_callback:
            progress_callback(30, "Sending to Grounding DINO...")
        
        # Prepare request
        files = {"file": ("image.jpg", image_bytes, "image/jpeg")}
        data = {
            "text_prompt": text_prompt,
            "threshold": str(threshold)
        }
        
        try:
            response = await self.client.post(
                self.api_url,
                headers=self.headers,
                files=files,
                data=data
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RuntimeError("Invalid or missing Hugging Face API key")
            elif e.response.status_code == 429:
                raise RuntimeError("Rate limited. Please wait and try again.")
            elif e.response.status_code == 503:
                raise RuntimeError("Model loading. Please try again in a moment.")
            else:
                raise RuntimeError(f"API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error: {e}")
        
        if progress_callback:
            progress_callback(80, "Processing results...")
        
        # Parse results
        results = response.json()
        
        detections = []
        for det in results:
            if det.get('score', 0) >= threshold:
                box = det.get('box', {})
                detections.append({
                    'label': det.get('label', 'unknown'),
                    'score': det.get('score', 0),
                    'box': [
                        box.get('xmin', 0),
                        box.get('ymin', 0),
                        box.get('xmax', 0),
                        box.get('ymax', 0)
                    ]
                })
        
        if progress_callback:
            progress_callback(100, f"Found {len(detections)} objects")
        
        return detections
    
    async def detect_batch(
        self,
        image_paths: List[str],
        text_prompt: str,
        threshold: float = 0.3,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Run detection on multiple images.
        
        Returns:
            Dict mapping image_path -> list of detections
        """
        results = {}
        total = len(image_paths)
        
        for i, image_path in enumerate(image_paths):
            if progress_callback:
                progress_callback(
                    int((i / total) * 100),
                    f"Processing {i+1}/{total}: {os.path.basename(image_path)}"
                )
            
            try:
                detections = await self.detect(image_path, text_prompt, threshold)
                results[image_path] = detections
            except Exception as e:
                results[image_path] = []
                print(f"Error processing {image_path}: {e}")
        
        if progress_callback:
            progress_callback(100, f"Completed {total} images")
        
        return results
    
    def close(self):
        """Close HTTP client."""
        import asyncio
        asyncio.create_task(self.client.aclose())


class GroundingDINOSync:
    """Synchronous wrapper for Grounding DINO service."""
    
    def __init__(self, api_key: str = ""):
        self.service = GroundingDINOService(api_key)
    
    def detect(
        self, 
        image_path: str, 
        text_prompt: str, 
        threshold: float = 0.3,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """Synchronous detection."""
        import asyncio
        return asyncio.run(self.service.detect(image_path, text_prompt, threshold, progress_callback))
    
    def detect_batch(
        self,
        image_paths: List[str],
        text_prompt: str,
        threshold: float = 0.3,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, List[Dict]]:
        """Synchronous batch detection."""
        import asyncio
        return asyncio.run(self.service.detect_batch(image_paths, text_prompt, threshold, progress_callback))
    
    def set_api_key(self, api_key: str):
        self.service.set_api_key(api_key)
