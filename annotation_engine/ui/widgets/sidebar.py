"""
AnnotationEngine Desktop - Sidebar Widget
"""
from typing import List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QToolBar, QMenu
)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QIcon, QAction

from annotation_engine.ui.widgets.image_grid import ImageGridWidget


class SidebarWidget(QWidget):
    """Main sidebar containing image grid and controls."""
    
    imageSelected = Signal(int)
    imageDoubleClicked = Signal(int)
    selectionChanged = Signal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Image grid
        self.image_grid = ImageGridWidget(self)
        self.image_grid.imageSelected.connect(self.imageSelected)
        self.image_grid.imageDoubleClicked.connect(self.imageDoubleClicked)
        self.image_grid.selectionChanged.connect(self.selectionChanged)
        
        layout.addWidget(self.image_grid)
    
    def setImages(self, images: List[Dict]):
        """Set images in grid."""
        self.image_grid.setImages(images)
    
    def clear(self):
        """Clear images."""
        self.image_grid.clear()
    
    def getSelectedImageIds(self) -> List[int]:
        """Get selected image IDs."""
        return self.image_grid.getSelectedImageIds()
    
    def setSelectedIndices(self, indices: List[int]):
        """Set selected indices."""
        self.image_grid.setSelectedIndices(indices)