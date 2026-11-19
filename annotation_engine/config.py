"""
AnnotationEngine Desktop - Configuration and Constants
"""
import os
from pathlib import Path

# Application metadata
APP_NAME = "AnnotationEngine"
APP_VERSION = "1.0.0"
ORG_NAME = "AnnotationEngine"

# Paths
def get_app_data_dir() -> Path:
    """Get platform-appropriate app data directory."""
    if os.name == 'nt':  # Windows
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    elif os.name == 'posix' and 'darwin' in os.sys.platform:  # macOS
        base = Path.home() / 'Library' / 'Application Support'
    else:  # Linux
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / APP_NAME

APP_DATA_DIR = get_app_data_dir()
MODELS_DIR = APP_DATA_DIR / 'models'
PROJECTS_DIR = Path.home() / 'Documents' / 'AnnotationEngine' / 'Projects'
LOGS_DIR = APP_DATA_DIR / 'logs'
ICONS_DIR = Path(__file__).parent / 'resources' / 'icons'

# Ensure directories exist
for d in [APP_DATA_DIR, MODELS_DIR, PROJECTS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_PATH = APP_DATA_DIR / 'annotation_engine.db'

# Model URLs
MOBILE_SAM_ONNX_URL = "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.onnx"
DINOV2_MODEL_NAME = "facebook/dinov2-small"

# Default settings
DEFAULT_SETTINGS = {
    'hf_api_key': '',
    'hf_api_key_encrypted': '',
    'recent_projects': [],
    'window_geometry': None,
    'window_state': None,
    'sidebar_width': 300,
    'theme': 'light',  # 'light' or 'dark'
    'auto_save_interval': 30,  # seconds
    'max_recent_projects': 10,
}

# Color palette for annotations (Tailwind-inspired)
COLORS = {
    'primary_50': '#eff6ff', 'primary_100': '#dbeafe', 'primary_200': '#bfdbfe',
    'primary_300': '#93c5fd', 'primary_400': '#60a5fa', 'primary_500': '#3b82f6',
    'primary_600': '#2563eb', 'primary_700': '#1d4ed8', 'primary_800': '#1e40af',
    'primary_900': '#1e3a8a', 'primary_950': '#172554',
    
    'gray_50': '#f9fafb', 'gray_100': '#f3f4f6', 'gray_200': '#e5e7eb',
    'gray_300': '#d1d5db', 'gray_400': '#9ca3af', 'gray_500': '#6b7280',
    'gray_600': '#4b5563', 'gray_700': '#374151', 'gray_800': '#1f2937',
    'gray_900': '#111827', 'gray_950': '#030712',
    
    'success': '#22c55e', 'warning': '#f59e0b', 'error': '#ef4444',
    'info': '#06b6d4',
    
    'green_500': '#22c55e', 'blue_500': '#3b82f6', 'purple_500': '#a855f7',
}

# High-contrast palette used for annotation shapes (cycled per label)
ANNOTATION_COLORS = [
    '#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#a855f7',
    '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#6366f1',
    '#14b8a6', '#eab308',
]

# Annotation settings
ANNOTATION_SETTINGS = {
    'max_undo_steps': 50,
    'default_stroke_width': 2,
    'default_fill_opacity': 0.1,
    'vertex_size': 8,
    'handle_size': 10,
}

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'
}

# Export formats
EXPORT_FORMATS = {
    'yolo': 'YOLO (.txt + data.yaml)',
    'coco': 'COCO (.json)',
}

# Job types
JOB_TYPES = [
    'grounding_dino',
    'mobile_sam', 
    'dinov2_keypoint',
    'export'
]

JOB_STATUSES = [
    'pending',
    'running',
    'completed',
    'failed'
]

# Tool names (LabelMe compatible)
TOOL_NAMES = {
    'select': 'select',
    'bbox': 'rect',
    'polygon': 'polygon',
    'keypoint': 'point',
}

# Keyboard shortcuts
SHORTCUTS = {
    'tool_select': 'V',
    'tool_bbox': 'B',
    'tool_polygon': 'P',
    'tool_keypoint': 'K',
    'delete': 'Del',
    'escape': 'Esc',
    'undo': 'Ctrl+Z',
    'redo': 'Ctrl+Shift+Z',
    'save': 'Ctrl+S',
    'zoom_in': 'Ctrl++',
    'zoom_out': 'Ctrl+-',
    'zoom_fit': 'Ctrl+0',
}