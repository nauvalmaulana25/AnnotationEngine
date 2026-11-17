import json
import base64
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models import Image, Annotation
from app.schemas import AnnotationResponse, LabelMeAnnotation, AnnotationCreate, AnnotationUpdate

router = APIRouter(prefix="/annotations", tags=["annotations"])


@router.get("/images/{image_id}", response_model=AnnotationResponse)
async def get_annotation(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    # Verify image exists
    result = await db.execute(
        select(Image).where(Image.id == image_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Get annotation
    result = await db.execute(
        select(Annotation).where(Annotation.image_id == image_id)
    )
    annotation = result.scalar_one_or_none()
    
    if not annotation:
        # Return empty annotation structure
        empty_annotation = LabelMeAnnotation(
            version="5.4.1",
            flags={},
            shapes=[],
            imagePath=image.filename,
            imageData=None,
            imageHeight=image.height or 0,
            imageWidth=image.width or 0
        )
        return AnnotationResponse(
            id=0,
            image_id=image_id,
            data=empty_annotation,
            version=0,
            created_at=image.imported_at,
            updated_at=image.imported_at
        )
    
    # Parse stored JSON
    try:
        data = json.loads(annotation.data)
    except json.JSONDecodeError:
        data = {"version": "5.4.1", "flags": {}, "shapes": [], "imagePath": image.filename, "imageData": None, "imageHeight": image.height or 0, "imageWidth": image.width or 0}
    
    return AnnotationResponse(
        id=annotation.id,
        image_id=annotation.image_id,
        data=LabelMeAnnotation(**data),
        version=annotation.version,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at
    )


@router.put("/images/{image_id}", response_model=AnnotationResponse)
async def save_annotation(
    image_id: int,
    annotation_data: AnnotationCreate,
    db: AsyncSession = Depends(get_db)
):
    # Verify image exists
    result = await db.execute(
        select(Image).where(Image.id == image_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Get or create annotation
    result = await db.execute(
        select(Annotation).where(Annotation.image_id == image_id)
    )
    annotation = result.scalar_one_or_none()
    
    # Convert to JSON string
    data_json = annotation_data.data.model_dump_json()
    
    if annotation:
        annotation.data = data_json
        annotation.version += 1
    else:
        annotation = Annotation(
            image_id=image_id,
            data=data_json,
            version=1
        )
        db.add(annotation)
    
    await db.commit()
    await db.refresh(annotation)
    
    # Also save to labels folder (LabelMe format)
    labels_dir = Path(image.original_path).parent.parent / "labels"
    labels_dir.mkdir(exist_ok=True)
    label_file = labels_dir / (Path(image.filename).stem + ".json")
    
    # Write LabelMe JSON with base64 image data
    labelme_data = json.loads(data_json)
    # Optionally include image data
    try:
        with open(image.original_path, "rb") as f:
            image_bytes = f.read()
        labelme_data["imageData"] = base64.b64encode(image_bytes).decode("utf-8")
    except Exception:
        labelme_data["imageData"] = None
    
    with open(label_file, "w") as f:
        json.dump(labelme_data, f, indent=2)
    
    return AnnotationResponse(
        id=annotation.id,
        image_id=annotation.image_id,
        data=annotation_data.data,
        version=annotation.version,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at
    )


@router.patch("/images/{image_id}", response_model=AnnotationResponse)
async def update_annotation(
    image_id: int,
    annotation_data: AnnotationUpdate,
    db: AsyncSession = Depends(get_db)
):
    # Same as PUT for now - full replace
    return await save_annotation(image_id, AnnotationCreate(data=annotation_data.data), db)


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    # Verify image exists
    result = await db.execute(
        select(Image).where(Image.id == image_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Delete annotation
    result = await db.execute(
        select(Annotation).where(Annotation.image_id == image_id)
    )
    annotation = result.scalar_one_or_none()
    
    if annotation:
        await db.delete(annotation)
        await db.commit()
    
    # Delete label file
    labels_dir = Path(image.original_path).parent.parent / "labels"
    label_file = labels_dir / (Path(image.filename).stem + ".json")
    if label_file.exists():
        label_file.unlink()