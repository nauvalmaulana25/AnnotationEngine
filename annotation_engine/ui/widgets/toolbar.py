"""
AnnotationEngine Desktop - Annotation Toolbar
"""
from typing import Optional

from PySide6.QtWidgets import (
    QToolBar, QWidget, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QSpinBox, QWidgetAction, QSizePolicy
)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QIcon, QKeySequence, QAction

from annotation_engine.config import TOOL_NAMES, SHORTCUTS, COLORS


class AnnotationToolbar(QToolBar):
    """Main annotation toolbar with tools and actions."""
    
    # Signals
    toolChanged = Signal(str)
    importImagesRequested = Signal()
    importLabelsRequested = Signal()
    exportRequested = Signal()
    autoAnnotateRequested = Signal()
    saveRequested = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    welcomeRequested = Signal()
    
    def __init__(self, parent=None):
        super().__init__("Annotation Toolbar", parent)
        
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(24, 24))
        
        self.current_tool = "select"
        self.project_loaded = False
        self.save_enabled = False
        
        self.setupUI()
    
    def setupUI(self):
        # Tool group
        self.tool_actions = {}
        
        tools = [
            ("select", "Select", "V", "mouse-pointer"),
            ("bbox", "Bounding Box", "B", "square"),
            ("polygon", "Polygon", "P", "polygon"),
            ("keypoint", "Keypoint", "K", "map-pin"),
            ("pan", "Pan", "H", "move"),
        ]
        
        for tool_id, label, shortcut, icon_name in tools:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(shortcut))
            action.setCheckable(True)
            action.setToolTip(f"{label} ({shortcut})")
            action.setData(tool_id)
            action.triggered.connect(lambda checked, t=tool_id: self.onToolAction(t))
            self.addAction(action)
            self.tool_actions[tool_id] = action
        
        self.tool_actions["select"].setChecked(True)
        
        self.addSeparator()
        
        # Import/Export actions
        import_images_action = QAction("Import Images", self)
        import_images_action.setShortcut(QKeySequence("Ctrl+I"))
        import_images_action.setToolTip("Import Images (Ctrl+I)")
        import_images_action.triggered.connect(self.importImagesRequested)
        self.addAction(import_images_action)
        
        import_labels_action = QAction("Import Labels", self)
        import_labels_action.setToolTip("Import Labels")
        import_labels_action.triggered.connect(self.importLabelsRequested)
        self.addAction(import_labels_action)
        
        self.addSeparator()
        
        export_action = QAction("Export Dataset", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.setToolTip("Export Dataset (Ctrl+E)")
        export_action.triggered.connect(self.exportRequested)
        self.addAction(export_action)
        
        self.addSeparator()
        
        # Auto-annotate
        auto_annotate_action = QAction("Auto Annotate", self)
        auto_annotate_action.setShortcut(QKeySequence("Ctrl+A"))
        auto_annotate_action.setToolTip("Auto Annotate (Ctrl+A)")
        auto_annotate_action.triggered.connect(self.autoAnnotateRequested)
        self.addAction(auto_annotate_action)
        
        self.addSeparator()
        
        # Save action
        self.save_action = QAction("Save Annotation", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.setToolTip("Save Annotation (Ctrl+S)")
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.saveRequested)
        self.addAction(self.save_action)
        
        self.addSeparator()
        
        # Undo/Redo
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setToolTip("Undo (Ctrl+Z)")
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undoRequested)
        self.addAction(self.undo_action)
        
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setToolTip("Redo (Ctrl+Shift+Z)")
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self.redoRequested)
        self.addAction(self.redo_action)
        
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
        self.welcome_action = QAction("Welcome Screen", self)
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
        if tool_id in self.tool_actions:
            self.tool_actions[tool_id].setChecked(True)
    
    def setProjectLoaded(self, loaded: bool):
        """Update UI for project loaded state."""
        self.project_loaded = loaded
        
        # Enable/disable actions based on project state
        for action in self.actions():
            if action.data() in TOOL_NAMES or action in [
                self.save_action, self.undo_action, self.redo_action
            ]:
                action.setEnabled(loaded)
    
    def setSaveEnabled(self, enabled: bool):
        """Enable/disable save action."""
        self.save_enabled = enabled
        self.save_action.setEnabled(enabled and self.project_loaded)
    
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
    
    def setImageInfo(self, text: str):
        """Set current image info label."""
        self.image_info_label.setText(text)