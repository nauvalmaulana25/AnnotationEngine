import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import Job, Settings
from app.core.websocket_manager import manager


class JobQueue:
    def __init__(self, max_workers: int = 2):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.max_workers = max_workers
        self.running = False
    
    async def start(self):
        if not self.running:
            self.running = True
            for i in range(self.max_workers):
                worker = asyncio.create_task(self._worker(f"worker-{i}"))
                self.workers.append(worker)
    
    async def stop(self):
        self.running = False
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
    
    async def enqueue(self, job: Job):
        await self.queue.put(job.id)
    
    async def _worker(self, name: str):
        while self.running:
            try:
                job_id = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self._process_job(job_id)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker {name} error: {e}")
    
    async def _process_job(self, job_id: int):
        async with async_session_maker() as db:
            # Load job
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                return
            
            # Update status to running
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.progress = 0
            await db.commit()
            
            # Notify via WebSocket
            await manager.send_progress(str(job_id), {
                "job_id": job_id,
                "status": "running",
                "progress": 0,
                "message": "Job started"
            })
            
            try:
                # Process based on job type
                if job.job_type == "grounding_dino":
                    await self._process_grounding_dino(job, db)
                elif job.job_type == "mobile_sam":
                    await self._process_mobile_sam(job, db)
                elif job.job_type == "dinov2_keypoint":
                    await self._process_dinov2_keypoint(job, db)
                elif job.job_type == "export":
                    await self._process_export(job, db)
                else:
                    raise ValueError(f"Unknown job type: {job.job_type}")
                
                # Mark completed
                job.status = "completed"
                job.progress = 100
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                
                await manager.send_progress(str(job_id), {
                    "job_id": job_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "Job completed successfully"
                })
                
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                
                await manager.send_progress(str(job_id), {
                    "job_id": job_id,
                    "status": "failed",
                    "progress": job.progress,
                    "message": f"Job failed: {str(e)}"
                })
    
    def _progress_callback(self, job_id: int, current: int, total: int, message: str = ""):
        """Create a progress callback for services."""
        async def callback():
            async with async_session_maker() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()
                if job:
                    job.progress = int((current / total) * 100) if total > 0 else 0
                    await db.commit()
                    await manager.send_progress(str(job_id), {
                        "job_id": job_id,
                        "status": "running",
                        "progress": job.progress,
                        "current": current,
                        "total": total,
                        "message": message
                    })
        # Schedule the async callback
        asyncio.create_task(callback())
    
    async def _get_hf_api_key(self, db: AsyncSession) -> str:
        """Get HF API key from settings."""
        result = await db.execute(select(Settings))
        settings = result.scalar_one_or_none()
        if not settings or not settings.hf_api_key_encrypted:
            raise ValueError("Hugging Face API key not configured in settings")
        from app.core.security import decrypt_api_key
        return decrypt_api_key(settings.hf_api_key_encrypted)
    
    async def _process_grounding_dino(self, job: Job, db: AsyncSession):
        from app.services.grounding_dino import GroundingDINOService
        from app.models import Image
        
        payload = json.loads(job.payload)
        image_ids = payload["image_ids"]
        text_prompt = payload["text_prompt"]
        conf_threshold = payload["conf_threshold"]
        
        # Get HF API key from settings
        hf_api_key = await self._get_hf_api_key(db)
        service = GroundingDINOService(hf_api_key)
        
        results = []
        total = len(image_ids)
        
        for i, image_id in enumerate(image_ids):
            result = await db.execute(select(Image).where(Image.id == image_id))
            image = result.scalar_one_or_none()
            if not image:
                continue
            
            # Read image file
            import aiofiles
            async with aiofiles.open(image.original_path, "rb") as f:
                image_bytes = await f.read()
            
            # Detect objects
            detections = await service.detect(image_bytes, text_prompt, conf_threshold)
            
            results.append({
                "image_id": image_id,
                "filename": image.filename,
                "detections": detections
            })
            
            # Update progress
            await self._progress_callback(job.id, i + 1, total, f"Processed {image.filename}")
        
        # Save results
        job.result = json.dumps({"results": results})
    
    async def _process_mobile_sam(self, job: Job, db: AsyncSession):
        from app.services.mobile_sam import MobileSAMService
        from app.models import Image
        import numpy as np
        from PIL import Image as PILImage
        import cv2
        
        payload = json.loads(job.payload)
        image_ids = payload["image_ids"]
        boxes = payload["boxes"]  # List of boxes per image
        
        service = MobileSAMService()
        results = []
        total = len(image_ids)
        
        for i, image_id in enumerate(image_ids):
            result = await db.execute(select(Image).where(Image.id == image_id))
            image = result.scalar_one_or_none()
            if not image:
                continue
            
            # Load image
            img = PILImage.open(image.original_path).convert("RGB")
            img_array = np.array(img)
            
            # Get boxes for this image
            image_boxes = boxes[i] if i < len(boxes) else []
            
            # Segment
            masks = service.segment(img_array, image_boxes)
            
            # Convert masks to polygons
            polygons = []
            for mask in masks:
                contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for contour in contours:
                    if len(contour) >= 3:
                        # Simplify polygon
                        epsilon = 0.005 * cv2.arcLength(contour, True)
                        approx = cv2.approxPolyDP(contour, epsilon, True)
                        polygon = approx.reshape(-1, 2).tolist()
                        polygons.append(polygon)
            
            results.append({
                "image_id": image_id,
                "filename": image.filename,
                "polygons": polygons
            })
            
            await self._progress_callback(job.id, i + 1, total, f"Segmented {image.filename}")
        
        job.result = json.dumps({"results": results})
    
    async def _process_dinov2_keypoint(self, job: Job, db: AsyncSession):
        from app.services.dinov2 import DINOv2KeypointService
        from app.models import Image, Annotation
        from PIL import Image as PILImage
        
        payload = json.loads(job.payload)
        target_image_ids = payload["target_image_ids"]
        reference_image_ids = payload["reference_image_ids"]
        similarity_threshold = payload["similarity_threshold"]
        consensus_votes = payload["consensus_votes"]
        nms_dist_pct = payload["nms_dist_pct"]
        
        service = DINOv2KeypointService()
        
        # Load reference data
        ref_data_list = []
        for ref_id in reference_image_ids:
            result = await db.execute(select(Image).where(Image.id == ref_id))
            ref_image = result.scalar_one_or_none()
            if not ref_image:
                continue
            
            # Get annotation with keypoints
            ann_result = await db.execute(select(Annotation).where(Annotation.image_id == ref_id))
            ann = ann_result.scalar_one_or_none()
            if not ann:
                continue
            
            import json
            ann_data = json.loads(ann.data)
            keypoints = []
            for shape in ann_data.get("shapes", []):
                if shape.get("shape_type") == "point" and shape.get("points"):
                    x, y = shape["points"][0]
                    keypoints.append((x, y, shape.get("label", "keypoint")))
            
            if keypoints:
                ref_data_list.append({
                    "image_path": ref_image.original_path,
                    "keypoints": keypoints
                })
        
        if not ref_data_list:
            raise ValueError("No valid reference images with keypoints")
        
        results = []
        total = len(target_image_ids)
        
        for i, target_id in enumerate(target_image_ids):
            result = await db.execute(select(Image).where(Image.id == target_id))
            target_image = result.scalar_one_or_none()
            if not target_image:
                continue
            
            # Transfer keypoints
            keypoints = service.transfer_keypoints(
                target_image.original_path,
                ref_data_list,
                similarity_threshold,
                consensus_votes,
                nms_dist_pct
            )
            
            # Convert to LabelMe shapes
            shapes = []
            for kp in keypoints:
                shapes.append({
                    "label": kp["label"],
                    "points": [[kp["x"], kp["y"]]],
                    "group_id": None,
                    "description": "",
                    "shape_type": "point",
                    "flags": {},
                    "mask": None
                })
            
            results.append({
                "image_id": target_id,
                "filename": target_image.filename,
                "shapes": shapes
            })
            
            await self._progress_callback(job.id, i + 1, total, f"Processed {target_image.filename}")
        
        job.result = json.dumps({"results": results})
    
    async def _process_export(self, job: Job, db: AsyncSession):
        from app.services.export_service import ExportService
        from app.models import Project
        
        payload = json.loads(job.payload)
        format = payload["format"]
        split_ratios = payload.get("split_ratios")
        include_bboxes = payload["include_bboxes"]
        include_polygons = payload["include_polygons"]
        include_keypoints = payload["include_keypoints"]
        
        result = await db.execute(select(Project).where(Project.id == job.project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")
        
        service = ExportService()
        output_path = await service.export(
            project_id=job.project_id,
            format=format,
            split_ratios=split_ratios,
            include_bboxes=include_bboxes,
            include_polygons=include_polygons,
            include_keypoints=include_keypoints,
            progress_callback=lambda c, t, m: self._progress_callback(job.id, c, t, m)
        )
        
        job.result = json.dumps({"output_path": output_path})


job_queue = JobQueue(max_workers=2)