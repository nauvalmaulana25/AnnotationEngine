"""
AnnotationEngine Desktop - Hybrid Image Annotation Application
"""
__version__ = "1.0.0"
__author__ = "AnnotationEngine Team"
__license__ = "GPL-3.0-only"

from .config import (
    APP_NAME,
    APP_VERSION,
    APP_DATA_DIR,
    MODELS_DIR,
    PROJECTS_DIR,
    DATABASE_PATH,
    DEFAULT_SETTINGS,
    SUPPORTED_IMAGE_FORMATS,
    EXPORT_FORMATS,
    TOOL_NAMES,
    SHORTCUTS,
)

__all__ = [
    'APP_NAME',
    'APP_VERSION',
    'APP_DATA_DIR',
    'MODELS_DIR',
    'PROJECTS_DIR',
    'DATABASE_PATH',
    'DEFAULT_SETTINGS',
    'SUPPORTED_IMAGE_FORMATS',
    'EXPORT_FORMATS',
    'TOOL_NAMES',
    'SHORTCUTS',
]