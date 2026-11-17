import httpx
import base64
from typing import List, Dict, Any
from PIL import Image
import io


class GroundingDINOService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api-inference.huggingface.co/models"
        self.model_id = "IDEA-Research/grounding-dino-tiny"
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = 60.0
    
    async def detect(
        self, 
        image_bytes: bytes, 
        text_prompt: str, 
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Detect objects using Grounding DINO via HF Inference API.
        
        Returns list of detections: [{label, score, box: [x1, y1, x2, y2]}, ...]
        """
        # Prepare image as base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        # Ensure prompt ends with period
        prompt = text_prompt.strip()
        if not prompt.endswith("."):
            prompt += "."
        
        payload = {
            "inputs": {
                "image": image_b64,
                "text": prompt
            },
            "parameters": {
                "threshold": threshold
            }
        }
        
        url = f"{self.base_url}/{self.model_id}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=self.headers, json=payload)
            
            if response.status_code == 401:
                raise ValueError("Invalid Hugging Face API key")
            elif response.status_code == 429:
                raise ValueError("Rate limited by Hugging Face API")
            elif response.status_code == 503:
                raise ValueError("Model is loading, please try again in a moment")
            elif response.status_code != 200:
                raise ValueError(f"HF API error: {response.status_code} - {response.text}")
            
            result = response.json()
            
            # Parse response
            detections = []
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and "box" in item:
                        box = item["box"]
                        # HF returns [xmin, ymin, xmax, ymax] normalized or absolute?
                        # The API typically returns normalized coordinates
                        detections.append({
                            "label": item.get("label", "object"),
                            "score": item.get("score", 0.0),
                            "box": [
                                box.get("xmin", 0),
                                box.get("ymin", 0),
                                box.get("xmax", 0),
                                box.get("ymax", 0)
                            ]
                        })
            
            return detections
    
    async def detect_with_image_info(
        self,
        image_bytes: bytes,
        text_prompt: str,
        threshold: float = 0.3,
        image_width: int = None,
        image_height: int = None
    ) -> List[Dict[str, Any]]:
        """Detect with optional image dimensions for coordinate conversion."""
        detections = await self.detect(image_bytes, text_prompt, threshold)
        
        # If we have image dimensions and boxes are normalized, convert to absolute
        if image_width and image_height:
            for det in detections:
                box = det["box"]
                # Check if normalized (all values <= 1)
                if all(0 <= v <= 1 for v in box):
                    det["box"] = [
                        box[0] * image_width,
                        box[1] * image_height,
                        box[2] * image_width,
                        box[3] * image_height
                    ]
        
        return detections