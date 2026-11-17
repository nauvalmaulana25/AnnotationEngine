"""
AnnotationEngine Desktop - Grounding DINO Service
"""
import httpx
import base64
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable


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