"""
AnnotationEngine Desktop - Annotation Toolbar
"""
from typing import Optional

from PySide6.QtWidgets import (
    QToolBar, QWidget, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QSpinBox, QWidgetAction, QSizePolicy
)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QIcon, QAction

from annotation_engine.config import TOOL_NAMES, SHORTCUTS, COLORS, ICONS_DIR


def _icon(name: str) -> QIcon:
    """Load a toolbar icon, or an empty one when the resource is missing."""
    icon_path = ICONS_DIR / name
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


class AnnotationToolbar(QToolBar):
    """Main annotation toolbar with tools and actions."""
    
    # Signals
    toolChanged = Signal(str)
    importImagesRequested = Signal()
    importLabelsRequested = Signal()
    exportRequested = Signal()
    autoAnnotateRequested = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    deleteRequested = Signal()
    welcomeRequested = Signal()
    
    def __init__(self, parent=None):
        super().__init__("Annotation Toolbar", parent)
        
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(24, 24))
        
        self.current_tool = "select"
        self.project_loaded = False
        
        self.setupUI()
    
    def setupUI(self):
        # Tool group
        self.tool_actions = {}
        
        tools = [
            ("select", "Select", "V", "mouse-pointer"),
            ("bbox", "Bounding Box", "B", "square"),
            ("polygon", "Polygon", "P", "polygon"),
            ("keypoint", "Keypoint", "K", "map-pin"),
        ]
        
        for tool_id, label, shortcut, icon_name in tools:
            action = QAction(_icon(f"{icon_name}.svg"), label, self)
            # The Tools menu owns the shortcut; duplicating it here makes Qt
            # report an ambiguous shortcut overload and fires neither action.
            action.setCheckable(True)
            action.setToolTip(f"{label} ({shortcut})")
            action.setData(tool_id)
            action.triggered.connect(lambda checked, t=tool_id: self.onToolAction(t))
            self.addAction(action)
            self.tool_actions[tool_id] = action
        
        self.tool_actions["select"].setChecked(True)
        
        # Auto-annotate: it creates shapes like the tools above, so it belongs
        # in the tool group rather than between Export and Save.
        auto_annotate_action = QAction(_icon("sparkles.svg"), "Auto Annotate", self)
        auto_annotate_action.setToolTip("Auto Annotate (Ctrl+Shift+A)")
        auto_annotate_action.triggered.connect(self.autoAnnotateRequested)
        self.addAction(auto_annotate_action)
        
        self.addSeparator()
        
        # Import/Export actions
        import_images_action = QAction(_icon("image-plus.svg"), "Import Images", self)
        import_images_action.setToolTip("Import Images (Ctrl+I)")
        import_images_action.triggered.connect(self.importImagesRequested)
        self.addAction(import_images_action)
        
        import_labels_action = QAction(_icon("tags.svg"), "Import Labels", self)
        import_labels_action.setToolTip("Import Labels")
        import_labels_action.triggered.connect(self.importLabelsRequested)
        self.addAction(import_labels_action)
        
        self.addSeparator()
        
        export_action = QAction(_icon("download.svg"), "Export Dataset", self)
        export_action.setToolTip("Export Dataset (Ctrl+E)")
        export_action.triggered.connect(self.exportRequested)
        self.addAction(export_action)
        
        self.addSeparator()
        
        # Undo/Redo (menu actions own the keyboard shortcuts)
        self.undo_action = QAction(_icon("undo.svg"), "Undo", self)
        self.undo_action.setToolTip("Undo (Ctrl+Z)")
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undoRequested)
        self.addAction(self.undo_action)
        
        self.redo_action = QAction(_icon("redo.svg"), "Redo", self)
        self.redo_action.setToolTip("Redo (Ctrl+Shift+Z)")
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self.redoRequested)
        self.addAction(self.redo_action)

        self.delete_action = QAction(_icon("trash.svg"), "Delete", self)
        self.delete_action.setToolTip("Delete selected shapes (Del)")
        self.delete_action.setEnabled(False)
        self.delete_action.triggered.connect(self.deleteRequested)
        self.addAction(self.delete_action)
        
        self.addSeparator()
        
        # Selection count label
        self.selection_label = QLabel("0 selected")
        self.selection_label.setMinimumWidth(100)
        self.addWidget(self.selection_label)
        
        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)
        
        # Current image info
        self.image_info_label = QLabel("No image")
        self.addWidget(self.image_info_label)
        
        self.addSeparator()
        
        # Welcome / Project screen action
        self.welcome_action = QAction(_icon("home.svg"), "Welcome Screen", self)
        self.welcome_action.setToolTip("Return to Welcome Screen (Ctrl+Shift+W)")
        self.welcome_action.triggered.connect(self.welcomeRequested)
        self.addAction(self.welcome_action)
    
    def onToolAction(self, tool_id: str):
        """Handle tool action triggered."""
        # Update checked state
        for tid, action in self.tool_actions.items():
            action.setChecked(tid == tool_id)
        
        self.toolChanged.emit(tool_id)
    
    def setTool(self, tool_id: str):
        """Set current tool programmatically."""
        if tool_id not in self.tool_actions:
            return
        # The tools are exclusive, so clear the siblings here too: menu items
        # and shortcuts reach this path without going through onToolAction.
        for tid, action in self.tool_actions.items():
            action.setChecked(tid == tool_id)
    
    def setProjectLoaded(self, loaded: bool):
        """Update UI for project loaded state."""
        self.project_loaded = loaded
        
        # Enable/disable actions based on project state. Undo/redo stay under
        # the canvas history signal so they cannot be wrongly re-enabled.
        for action in self.actions():
            if action.data() in TOOL_NAMES:
                action.setEnabled(loaded)
        if not loaded:
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)
            self.delete_action.setEnabled(False)
    
    def setSelectionCount(self, count: int):
        """Update selection count label."""
        if count > 0:
            self.selection_label.setText(f"{count} selected")
            self.selection_label.setStyleSheet("color: #3b82f6; font-weight: 500;")
        else:
            self.selection_label.setText("0 selected")
            self.selection_label.setStyleSheet("color: #9ca3af;")
    
    def setUndoRedoEnabled(self, can_undo: bool, can_redo: bool):
        """Update undo/redo enabled state."""
        self.undo_action.setEnabled(can_undo and self.project_loaded)
        self.redo_action.setEnabled(can_redo and self.project_loaded)

    def setDeleteEnabled(self, enabled: bool):
        """Enable or disable the Delete action."""
        self.delete_action.setEnabled(enabled and self.project_loaded)
    
    def setImageInfo(self, text: str):
        """Set current image info label."""
        self.image_info_label.setText(text)