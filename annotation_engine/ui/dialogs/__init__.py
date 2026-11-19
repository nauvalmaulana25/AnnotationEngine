"""
AnnotationEngine Desktop - Dialogs Package
"""
from .project_dialog import ProjectDialog
from .import_images import ImportImagesDialog
from .import_labels import ImportLabelsDialog
from .export_dialog import ExportDialog
from .settings_dialog import SettingsDialog
from .auto_annotate import AutoAnnotateDialog
from .progress_dialog import ProgressDialog
from .rename_label import RenameLabelDialog

__all__ = [
    'ProjectDialog',
    'ImportImagesDialog',
    'ImportLabelsDialog',
    'ExportDialog',
    'SettingsDialog',
    'AutoAnnotateDialog',
    'ProgressDialog',
    'RenameLabelDialog',
]