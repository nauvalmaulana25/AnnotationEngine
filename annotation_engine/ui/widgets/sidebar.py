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

    def setImageFetcher(self, fetcher):
        """Set an on-demand image fetch callback for remote (SSH) projects."""
        self.image_grid.setImageFetcher(fetcher)

    def setPrefetchRequest(self, request):
        """Set a background prefetch callback so painting never blocks."""
        self.image_grid.setPrefetchRequest(request)

    def invalidateThumbnail(self, image_id: int):
        """Drop a cached thumbnail so it is regenerated from the local file."""
        self.image_grid.invalidateThumbnail(image_id)

    def setAnnotationData(
        self,
        annotations: Dict[int, List[dict]] = None,
        label_colors: Dict[str, str] = None,
        label_visibility: Dict[str, bool] = None,
    ):
        """Feed annotation shapes and label metadata into the grid."""
        self.image_grid.setAnnotationData(
            annotations=annotations,
            label_colors=label_colors,
            label_visibility=label_visibility,
        )

    def invalidateOverlay(self, image_id: int):
        """Refresh a single image's overlay."""
        self.image_grid.invalidateOverlay(image_id)
    
    def clear(self):
        """Clear images."""
        self.image_grid.clear()
    
    def getSelectedImageIds(self) -> List[int]:
        """Get selected image IDs."""
        return self.image_grid.getSelectedImageIds()
    
    def setSelectedIndices(self, indices: List[int]):
        """Set selected indices."""
        self.image_grid.setSelectedIndices(indices)

    def visibleImageIds(self) -> List[int]:
        """Image ids in display order, honouring the active filter."""
        return self.image_grid.visibleImageIds()

    def revealImage(self, image_id: int):
        """Select an image and scroll it into view."""
        self.image_grid.revealImage(image_id)

    def setLastSeen(self, image_id: int):
        """Mark which image the project reopens on."""
        self.image_grid.setLastSeen(image_id)