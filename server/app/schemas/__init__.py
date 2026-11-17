from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# Project schemas
class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    base_path: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime
    image_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)


# Image schemas
class ImageResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    relative_path: str
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]
    split: str
    imported_at: datetime
    has_annotation: bool = False
    
    model_config = ConfigDict(from_attributes=True)


class ImageImportResponse(BaseModel):
    imported: int
    skipped: int
    images: List[ImageResponse]


# Annotation schemas (LabelMe format)
class LabelMePoint(BaseModel):
    x: float
    y: float


class LabelMeShape(BaseModel):
    label: str
    points: List[List[float]]
    group_id: Optional[int] = None
    description: str = ""
    shape_type: str  # rectangle, polygon, point, circle, line
    flags: dict = {}
    mask: Optional[Any] = None


class LabelMeAnnotation(BaseModel):
    version: str = "5.4.1"
    flags: dict = {}
    shapes: List[LabelMeShape]
    imagePath: str
    imageData: Optional[str] = None
    imageHeight: int
    imageWidth: int


class AnnotationCreate(BaseModel):
    data: LabelMeAnnotation


class AnnotationUpdate(BaseModel):
    data: LabelMeAnnotation


class AnnotationResponse(BaseModel):
    id: int
    image_id: int
    data: LabelMeAnnotation
    version: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Job schemas
class JobBase(BaseModel):
    job_type: str
    payload: dict


class JobCreate(JobBase):
    project_id: int


class JobStatusResponse(BaseModel):
    id: int
    project_id: int
    job_type: str
    status: str
    progress: int
    payload: dict
    result: Optional[dict]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


# Export schemas
class ExportRequest(BaseModel):
    format: str = Field(pattern="^(yolo|coco|both)$")
    split_ratios: Optional[dict] = None
    include_bboxes: bool = True
    include_polygons: bool = True
    include_keypoints: bool = True


# Auto-annotate schemas
class GroundingDinoRequest(BaseModel):
    project_id: int
    image_ids: List[int]
    text_prompt: str
    conf_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class MobileSamRequest(BaseModel):
    project_id: int
    image_ids: List[int]
    boxes: List[List[float]]


class DinoV2KeypointRequest(BaseModel):
    project_id: int
    target_image_ids: List[int]
    reference_image_ids: List[int]
    similarity_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    consensus_votes: int = Field(default=2, ge=1)
    nms_dist_pct: float = Field(default=0.025, ge=0.0, le=0.1)


# Pagination
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# Settings schemas
class SettingsResponse(BaseModel):
    id: int
    hf_api_key_set: bool
    default_project_path: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    hf_api_key: Optional[str] = None
    default_project_path: Optional[str] = None


# Database schemas
class DatabaseExportResponse(BaseModel):
    message: str
    filename: str