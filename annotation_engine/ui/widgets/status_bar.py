"""
AnnotationEngine Desktop - Status Bar
"""
from PySide6.QtWidgets import QStatusBar, QLabel, QProgressBar
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont


class AnnotationStatusBar(QStatusBar):
    """Custom status bar with annotation info."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setSizeGripEnabled(False)
        
        # Permanent widgets (right side)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.addPermanentWidget(self.zoom_label)
        
        # Coordinates
        self.coords_label = QLabel("x: 0, y: 0")
        self.coords_label.setMinimumWidth(120)
        self.addPermanentWidget(self.coords_label)
        
        # Shape count
        self.shapes_label = QLabel("Shapes: 0")
        self.shapes_label.setMinimumWidth(100)
        self.addPermanentWidget(self.shapes_label)
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.addPermanentWidget(self.progress_bar)
        
        # Message area
        self.message_label = QLabel("Ready")
        self.addWidget(self.message_label, 1)
    
    def setZoom(self, zoom: float):
        """Set zoom level display."""
        self.zoom_label.setText(f"{int(zoom * 100)}%")
    
    def setCoordinates(self, x: float, y: float):
        """Set mouse coordinates (image pixels, rounded like LabelMe)."""
        self.coords_label.setText(f"x: {round(x)}, y: {round(y)}")
    
    def setShapeCount(self, count: int):
        """Set shape count."""
        self.shapes_label.setText(f"Shapes: {count}")
    
    def setProject(self, project: dict):
        """Set project info."""
        self.showMessage(f"Project: {project['name']}", 3000)
    
    def clearProject(self):
        """Clear project info."""
        self.showMessage("No project loaded")
        self.shapes_label.setText("Shapes: 0")
    
    def setImage(self, image: dict):
        """Set current image info."""
        self.showMessage(f"Image: {image['filename']} ({image.get('width', '?')}x{image.get('height', '?')})", 3000)
    
    def showProgress(self, visible: bool, value: int = 0, message: str = ""):
        """Show/hide progress bar."""
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setValue(value)
            if message:
                self.showMessage(message)
    
    def showMessage(self, message: str, timeout: int = 0):
        """Show temporary message."""
        self.message_label.setText(message)
        super().showMessage(message, timeout)