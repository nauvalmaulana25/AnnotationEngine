import os
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import FileResponse
from app.core.database import get_db, engine
from app.core.config import get_settings
from app.services.job_queue import job_queue

router = APIRouter(prefix="/database", tags=["database"])


@router.get("/export")
async def export_database():
    """Export the SQLite database file."""
    settings = get_settings()
    db_path = Path(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", ""))
    
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    
    # Create a copy to avoid locking issues
    export_path = db_path.with_name(f"{db_path.stem}_export{db_path.suffix}")
    shutil.copy2(db_path, export_path)
    
    return FileResponse(
        path=export_path,
        filename="annotation_engine.db",
        media_type="application/x-sqlite3",
        headers={"Content-Disposition": 'attachment; filename="annotation_engine.db"'}
    )


@router.post("/import")
async def import_database(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Import and replace the SQLite database file."""
    if not file.filename.endswith(".db") and not file.filename.endswith(".sqlite") and not file.filename.endswith(".sqlite3"):
        raise HTTPException(status_code=400, detail="File must be a SQLite database (.db, .sqlite, .sqlite3)")
    
    settings = get_settings()
    db_path = Path(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", ""))
    
    # Read uploaded file
    content = await file.read()
    
    # Validate it's a SQLite database by checking header
    if not content[:16] == b"SQLite format 3\x00":
        raise HTTPException(status_code=400, detail="Invalid SQLite database file")
    
    # Backup current database
    backup_path = db_path.with_name(f"{db_path.stem}_backup{db_path.suffix}")
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
    
    # Write new database
    with open(db_path, "wb") as f:
        f.write(content)
    
    # Dispose engine to close connections
    await engine.dispose()
    
    # Reinitialize database (tables should already exist)
    from app.core.database import init_db
    await init_db()
    
    return {"message": "Database imported successfully. Please restart the application for changes to take full effect."}