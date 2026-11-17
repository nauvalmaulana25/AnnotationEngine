import json
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.config import get_settings
from app.core.websocket_manager import manager
from app.models import Project, Image, Job, Settings
from app.schemas import (
    JobCreate, JobStatusResponse, GroundingDinoRequest, 
    MobileSamRequest, DinoV2KeypointRequest, ExportRequest
)
from app.services.job_queue import job_queue

router = APIRouter(prefix="/auto-annotate", tags=["auto-annotate"])
settings = get_settings()


@router.websocket("/ws/jobs/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: str):
    await manager.connect(job_id, websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id, websocket)


async def create_job(
    db: AsyncSession,
    project_id: int,
    job_type: str,
    payload: dict
) -> Job:
    job = Job(
        project_id=project_id,
        job_type=job_type,
        status="pending",
        progress=0,
        payload=json.dumps(payload),
        created_at=datetime.now(timezone.utc)
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_hf_api_key(db: AsyncSession) -> str:
    """Get HF API key from settings."""
    result = await db.execute(select(Settings))
    settings = result.scalar_one_or_none()
    if not settings or not settings.hf_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Hugging Face API key not configured in settings")
    from app.core.security import decrypt_api_key
    return decrypt_api_key(settings.hf_api_key_encrypted)


@router.post("/grounding-dino", response_model=JobStatusResponse)
async def start_grounding_dino(
    request: GroundingDinoRequest,
    db: AsyncSession = Depends(get_db)
):
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify images belong to project
    result = await db.execute(
        select(Image).where(Image.id.in_(request.image_ids), Image.project_id == request.project_id)
    )
    images = result.scalars().all()
    if len(images) != len(request.image_ids):
        raise HTTPException(status_code=400, detail="Some images not found in project")
    
    # Get HF API key from settings
    hf_api_key = await get_hf_api_key(db)
    
    # Create job
    payload = {
        "image_ids": request.image_ids,
        "text_prompt": request.text_prompt,
        "conf_threshold": request.conf_threshold,
        "hf_api_key": hf_api_key
    }
    job = await create_job(db, request.project_id, "grounding_dino", payload)
    
    # Enqueue
    await job_queue.enqueue(job)
    
    return JobStatusResponse(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        payload=json.loads(job.payload),
        result=json.loads(job.result) if job.result else None,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@router.post("/mobile-sam", response_model=JobStatusResponse)
async def start_mobile_sam(
    request: MobileSamRequest,
    db: AsyncSession = Depends(get_db)
):
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify images belong to project
    result = await db.execute(
        select(Image).where(Image.id.in_(request.image_ids), Image.project_id == request.project_id)
    )
    images = result.scalars().all()
    if len(images) != len(request.image_ids):
        raise HTTPException(status_code=400, detail="Some images not found in project")
    
    # Create job
    payload = {
        "image_ids": request.image_ids,
        "boxes": request.boxes
    }
    job = await create_job(db, request.project_id, "mobile_sam", payload)
    
    # Enqueue
    await job_queue.enqueue(job)
    
    return JobStatusResponse(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        payload=json.loads(job.payload),
        result=json.loads(job.result) if job.result else None,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@router.post("/dinov2-keypoint", response_model=JobStatusResponse)
async def start_dinov2_keypoint(
    request: DinoV2KeypointRequest,
    db: AsyncSession = Depends(get_db)
):
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify images belong to project
    all_image_ids = request.target_image_ids + request.reference_image_ids
    result = await db.execute(
        select(Image).where(Image.id.in_(all_image_ids), Image.project_id == request.project_id)
    )
    images = result.scalars().all()
    if len(images) != len(all_image_ids):
        raise HTTPException(status_code=400, detail="Some images not found in project")
    
    # Verify reference images have annotations with keypoints
    from app.models import Annotation
    ref_images = [img for img in images if img.id in request.reference_image_ids]
    for ref_img in ref_images:
        result = await db.execute(
            select(Annotation).where(Annotation.image_id == ref_img.id)
        )
        ann = result.scalar_one_or_none()
        if not ann:
            raise HTTPException(status_code=400, detail=f"Reference image {ref_img.filename} has no annotation")
    
    # Create job
    payload = {
        "target_image_ids": request.target_image_ids,
        "reference_image_ids": request.reference_image_ids,
        "similarity_threshold": request.similarity_threshold,
        "consensus_votes": request.consensus_votes,
        "nms_dist_pct": request.nms_dist_pct
    }
    job = await create_job(db, request.project_id, "dinov2_keypoint", payload)
    
    # Enqueue
    await job_queue.enqueue(job)
    
    return JobStatusResponse(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        payload=json.loads(job.payload),
        result=json.loads(job.result) if job.result else None,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        payload=json.loads(job.payload),
        result=json.loads(job.result) if job.result else None,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@router.get("/jobs/{job_id}/results")
async def get_job_results(
    job_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    
    return json.loads(job.result) if job.result else {}


@router.post("/export", response_model=JobStatusResponse)
async def start_export(
    project_id: int,
    request: ExportRequest,
    db: AsyncSession = Depends(get_db)
):
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Create job
    payload = {
        "format": request.format,
        "split_ratios": request.split_ratios,
        "include_bboxes": request.include_bboxes,
        "include_polygons": request.include_polygons,
        "include_keypoints": request.include_keypoints
    }
    job = await create_job(db, project_id, "export", payload)
    
    # Enqueue
    await job_queue.enqueue(job)
    
    return JobStatusResponse(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        payload=json.loads(job.payload),
        result=json.loads(job.result) if job.result else None,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )