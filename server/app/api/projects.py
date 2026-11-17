import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.config import get_settings
from app.models import Project, Image, Annotation, Job
from app.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse, 
    ImageResponse, ImageImportResponse, AnnotationResponse,
    LabelMeAnnotation, PaginatedResponse
)

router = APIRouter(prefix="/projects", tags=["projects"])
settings = get_settings()


@router.get("", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    
    # Add image counts
    response = []
    for project in projects:
        img_count_result = await db.execute(
            select(func.count(Image.id)).where(Image.project_id == project.id)
        )
        img_count = img_count_result.scalar() or 0
        response.append(ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            base_path=project.base_path,
            created_at=project.created_at,
            updated_at=project.updated_at,
            image_count=img_count
        ))
    
    return response


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db)
):
    # Determine base path
    if project_data.base_path:
        base_path = project_data.base_path
    else:
        base_path = str(Path.home() / "Documents" / "AnnotationEngine" / "Projects")
    
    project_path = Path(base_path) / project_data.name
    
    # Create directory structure
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "images").mkdir(exist_ok=True)
    (project_path / "labels").mkdir(exist_ok=True)
    
    # Create project in DB
    project = Project(
        name=project_data.name,
        description=project_data.description,
        base_path=str(project_path)
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        base_path=project.base_path,
        created_at=project.created_at,
        updated_at=project.updated_at,
        image_count=0
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    img_count_result = await db.execute(
        select(func.count(Image.id)).where(Image.project_id == project.id)
    )
    img_count = img_count_result.scalar() or 0
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        base_path=project.base_path,
        created_at=project.created_at,
        updated_at=project.updated_at,
        image_count=img_count
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    update_data: ProjectUpdate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if update_data.name is not None:
        project.name = update_data.name
    if update_data.description is not None:
        project.description = update_data.description
    
    await db.commit()
    await db.refresh(project)
    
    img_count_result = await db.execute(
        select(func.count(Image.id)).where(Image.project_id == project.id)
    )
    img_count = img_count_result.scalar() or 0
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        base_path=project.base_path,
        created_at=project.created_at,
        updated_at=project.updated_at,
        image_count=img_count
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Delete project folder
    project_path = Path(project.base_path)
    if project_path.exists():
        shutil.rmtree(project_path)
    
    await db.delete(project)
    await db.commit()


@router.get("/{project_id}/images", response_model=PaginatedResponse)
async def list_images(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    split: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Build query
    query = select(Image).where(Image.project_id == project_id)
    if split:
        query = query.where(Image.split == split)
    
    # Count total
    count_result = await db.execute(
        select(func.count(Image.id)).where(Image.project_id == project_id)
    )
    total = count_result.scalar() or 0
    
    # Paginate
    query = query.order_by(Image.imported_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    images = result.scalars().all()
    
    # Check which have annotations
    image_ids = [img.id for img in images]
    ann_result = await db.execute(
        select(Annotation.image_id).where(Annotation.image_id.in_(image_ids))
    )
    annotated_ids = set(row[0] for row in ann_result.all())
    
    items = [
        ImageResponse(
            id=img.id,
            project_id=img.project_id,
            filename=img.filename,
            relative_path=img.relative_path,
            width=img.width,
            height=img.height,
            file_size=img.file_size,
            split=img.split,
            imported_at=img.imported_at,
            has_annotation=img.id in annotated_ids
        )
        for img in images
    ]
    
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


@router.post("/{project_id}/import-images", response_model=ImageImportResponse)
async def import_images(
    project_id: int,
    files: List[UploadFile] = File(...),
    split: str = Form(default="train"),
    db: AsyncSession = Depends(get_db)
):
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_path = Path(project.base_path)
    images_dir = project_path / "images"
    images_dir.mkdir(exist_ok=True)
    
    imported = 0
    skipped = 0
    imported_images = []
    
    for file in files:
        # Validate file type
        ext = Path(file.filename).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            skipped += 1
            continue
        
        # Validate file size
        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE:
            skipped += 1
            continue
        
        # Generate unique filename
        import uuid
        unique_name = f"{uuid.uuid4().hex}{ext}"
        save_path = images_dir / unique_name
        
        # Save file
        with open(save_path, "wb") as f:
            f.write(content)
        
        # Get image dimensions
        from PIL import Image as PILImage
        try:
            with PILImage.open(save_path) as img:
                width, height = img.size
        except Exception:
            width, height = None, None
        
        # Create DB record
        image = Image(
            project_id=project_id,
            filename=file.filename,
            original_path=str(save_path),
            relative_path=f"images/{unique_name}",
            width=width,
            height=height,
            file_size=len(content),
            split=split
        )
        db.add(image)
        await db.commit()
        await db.refresh(image)
        
        imported_images.append(ImageResponse(
            id=image.id,
            project_id=image.project_id,
            filename=image.filename,
            relative_path=image.relative_path,
            width=image.width,
            height=image.height,
            file_size=image.file_size,
            split=image.split,
            imported_at=image.imported_at,
            has_annotation=False
        ))
        imported += 1
    
    return ImageImportResponse(
        imported=imported,
        skipped=skipped,
        images=imported_images
    )


@router.post("/{project_id}/import-labels")
async def import_labels(
    project_id: int,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    imported = 0
    skipped = 0
    errors = []
    
    for file in files:
        if not file.filename.endswith(".json"):
            skipped += 1
            continue
        
        try:
            content = await file.read()
            import json
            labelme_data = json.loads(content)
            
            # Find matching image by filename
            image_filename = labelme_data.get("imagePath", "")
            if not image_filename:
                errors.append(f"{file.filename}: No imagePath in JSON")
                skipped += 1
                continue
            
            # Find image in project
            result = await db.execute(
                select(Image).where(
                    Image.project_id == project_id,
                    Image.filename == image_filename
                )
            )
            image = result.scalar_one_or_none()
            
            if not image:
                # Try to find by stem
                stem = Path(image_filename).stem
                result = await db.execute(
                    select(Image).where(
                        Image.project_id == project_id,
                        Image.filename.like(f"{stem}%")
                    )
                )
                image = result.scalar_one_or_none()
            
            if not image:
                errors.append(f"{file.filename}: No matching image found for {image_filename}")
                skipped += 1
                continue
            
            # Save annotation
            annotation = Annotation(
                image_id=image.id,
                data=json.dumps(labelme_data),
                version=1
            )
            db.add(annotation)
            await db.commit()
            imported += 1
            
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
            skipped += 1
    
    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors
    }


@router.get("/{project_id}/images/{image_id}", response_model=ImageResponse)
async def get_image(
    project_id: int,
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Image).where(Image.id == image_id, Image.project_id == project_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Check annotation
    ann_result = await db.execute(
        select(Annotation.id).where(Annotation.image_id == image_id)
    )
    has_ann = ann_result.scalar_one_or_none() is not None
    
    return ImageResponse(
        id=image.id,
        project_id=image.project_id,
        filename=image.filename,
        relative_path=image.relative_path,
        width=image.width,
        height=image.height,
        file_size=image.file_size,
        split=image.split,
        imported_at=image.imported_at,
        has_annotation=has_ann
    )


@router.delete("/{project_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    project_id: int,
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Image).where(Image.id == image_id, Image.project_id == project_id)
    )
    image = result.scalar_one_or_none()
    
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Delete file
    file_path = Path(image.original_path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete label file if exists
    labels_dir = Path(image.original_path).parent.parent / "labels"
    label_file = labels_dir / (Path(image.filename).stem + ".json")
    if label_file.exists():
        label_file.unlink()
    
    await db.delete(image)
    await db.commit()