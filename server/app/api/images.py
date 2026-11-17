from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.responses import FileResponse

from app.core.database import get_db
from app.models import Image

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/{image_id}/file")
async def serve_image(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Image).where(Image.id == image_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    file_path = Path(image.original_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")
    
    return FileResponse(file_path)


@router.get("/{image_id}/thumbnail")
async def serve_thumbnail(
    image_id: int,
    size: int = 256,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Image).where(Image.id == image_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    file_path = Path(image.original_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")
    
    # For now, return original image. In production, generate/cache thumbnails.
    return FileResponse(file_path)


@router.get("/{image_id}/info")
async def get_image_info(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Image).where(Image.id == image_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    return {
        "id": image.id,
        "filename": image.filename,
        "width": image.width,
        "height": image.height,
        "file_size": image.file_size,
        "split": image.split,
        "relative_path": image.relative_path
    }