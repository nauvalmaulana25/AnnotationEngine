"""
AnnotationEngine Desktop - UI Package
"""
from .main_window import MainWindow
from .canvas import AnnotationCanvas
from .styles import get_application_stylesheet, get_dark_stylesheet, get_light_stylesheet

from .widgets import (
    ImageGridWidget,
    SidebarWidget,
    AnnotationToolbar,
    AnnotationStatusBar,
    ZoomWidget,
    LabelListWidget,
)

from .dialogs import (
    ProjectDialog,
    ImportImagesDialog,
    ImportLabelsDialog,
    ExportDialog,
    SettingsDialog,
    AutoAnnotateDialog,
    ProgressDialog,
)

__all__ = [
    'MainWindow',
    'AnnotationCanvas',
    'get_application_stylesheet',
    'get_dark_stylesheet',
    'get_light_stylesheet',
    'ImageGridWidget',
    'SidebarWidget',
    'AnnotationToolbar',
    'AnnotationStatusBar',
    'ZoomWidget',
    'LabelListWidget',
    'ProjectDialog',
    'ImportImagesDialog',
    'ImportLabelsDialog',
    'ExportDialog',
    'SettingsDialog',
    'AutoAnnotateDialog',
    'ProgressDialog',
]