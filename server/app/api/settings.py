from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.config import get_settings
from app.models import Settings
from app.schemas import SettingsResponse, SettingsUpdate
from app.core.security import encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/settings", tags=["settings"])


async def get_or_create_settings(db: AsyncSession) -> Settings:
    result = await db.execute(select(Settings))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = Settings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.get("", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    settings = await get_or_create_settings(db)
    return SettingsResponse(
        id=settings.id,
        hf_api_key_set=bool(settings.hf_api_key_encrypted),
        default_project_path=settings.default_project_path,
        created_at=settings.created_at,
        updated_at=settings.updated_at
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    update_data: SettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    settings = await get_or_create_settings(db)
    
    if update_data.hf_api_key is not None:
        if update_data.hf_api_key.strip():
            settings.hf_api_key_encrypted = encrypt_api_key(update_data.hf_api_key.strip())
        else:
            settings.hf_api_key_encrypted = None
    
    if update_data.default_project_path is not None:
        settings.default_project_path = update_data.default_project_path.strip() if update_data.default_project_path.strip() else None
    
    await db.commit()
    await db.refresh(settings)
    
    return SettingsResponse(
        id=settings.id,
        hf_api_key_set=bool(settings.hf_api_key_encrypted),
        default_project_path=settings.default_project_path,
        created_at=settings.created_at,
        updated_at=settings.updated_at
    )


@router.get("/hf-api-key")
async def get_hf_api_key(db: AsyncSession = Depends(get_db)):
    """Get decrypted HF API key for internal use by services."""
    settings = await get_or_create_settings(db)
    if not settings.hf_api_key_encrypted:
        raise HTTPException(status_code=404, detail="HF API key not configured")
    return {"api_key": decrypt_api_key(settings.hf_api_key_encrypted)}