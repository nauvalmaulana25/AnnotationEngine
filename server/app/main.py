from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db, close_db
from app.services.job_queue import job_queue
from app.api import projects, images, annotations, auto_annotate, settings as settings_router, database

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await job_queue.start()
    
    # Create upload directories
    import os
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(settings.MOBILE_SAM_MODEL_PATH), exist_ok=True)
    
    yield
    
    # Shutdown
    await job_queue.stop()
    await close_db()


app = FastAPI(
    title="AnnotationEngine API",
    description="Hybrid Image Annotation Web Application",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router, prefix=settings.API_V1_PREFIX)
app.include_router(images.router, prefix=settings.API_V1_PREFIX)
app.include_router(annotations.router, prefix=settings.API_V1_PREFIX)
app.include_router(auto_annotate.router, prefix=settings.API_V1_PREFIX)
app.include_router(settings_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(database.router, prefix=settings.API_V1_PREFIX)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "annotation-engine-api"}

# Root
@app.get("/")
async def root():
    return {"message": "AnnotationEngine API", "version": "1.0.0", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )