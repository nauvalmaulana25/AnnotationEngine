from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AnnotationEngine"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./annotation_engine.db"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ENCRYPTION_KEY: str = "your-encryption-key-32-chars-long!!"
    
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    
    # File upload
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    UPLOAD_DIR: str = "./uploads"
    
    # Models
    MOBILE_SAM_MODEL_PATH: str = "./models/mobile_sam.onnx"
    DINOV2_MODEL_NAME: str = "facebook/dinov2-small"
    
    # Hugging Face
    HF_API_BASE_URL: str = "https://api-inference.huggingface.co/models"
    GROUNDING_DINO_MODEL: str = "IDEA-Research/grounding-dino-tiny"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()