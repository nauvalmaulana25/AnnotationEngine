"""
AnnotationEngine Desktop - Zoom Widget
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QIcon


class ZoomWidget(QWidget):
    """Zoom control widget for canvas."""
    
    zoomChanged = Signal(float)
    
    def __init__(self, canvas=None, parent=None):
        super().__init__(parent)
        
        self.canvas = canvas
        self.setupUI()
    
    def setupUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        # Style
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }
            QPushButton {
                background: transparent;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
            }
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 2px 8px;
                min-width: 80px;
            }
        """)
        
        # Zoom out button
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setFixedSize(28, 28)
        self.zoom_out_btn.setToolTip("Zoom Out (Ctrl+-)")
        self.zoom_out_btn.clicked.connect(self.zoomOut)
        layout.addWidget(self.zoom_out_btn)
        
        # Zoom combo box
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.addItems([
            "12.5%", "25%", "33%", "50%", "67%", 
            "75%", "100%", "150%", "200%", "300%", "400%"
        ])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.lineEdit().returnPressed.connect(self.onZoomTextEntered)
        layout.addWidget(self.zoom_combo)
        
        # Zoom in button
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedSize(28, 28)
        self.zoom_in_btn.setToolTip("Zoom In (Ctrl++)")
        self.zoom_in_btn.clicked.connect(self.zoomIn)
        layout.addWidget(self.zoom_in_btn)
        
        # Fit button
        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setFixedSize(44, 28)
        self.fit_btn.setToolTip("Fit to Window (Ctrl+0)")
        self.fit_btn.clicked.connect(self.zoomFit)
        layout.addWidget(self.fit_btn)
    
    def setZoom(self, zoom: float):
        """Set zoom level."""
        text = f"{int(zoom * 100)}%"
        index = self.zoom_combo.findText(text)
        if index >= 0:
            self.zoom_combo.setCurrentIndex(index)
        else:
            self.zoom_combo.setCurrentText(text)
    
    def zoomIn(self):
        """Zoom in."""
        if self.canvas:
            self.canvas.zoomIn()
    
    def zoomOut(self):
        """Zoom out."""
        if self.canvas:
            self.canvas.zoomOut()
    
    def zoomFit(self):
        """Fit to window."""
        if self.canvas:
            self.canvas.zoomFit()
    
    @Slot()
    def onZoomTextEntered(self):
        """Handle manual zoom text entry."""
        text = self.zoom_combo.currentText()
        try:
            if text.endswith('%'):
                zoom = float(text[:-1]) / 100.0
            else:
                zoom = float(text)
            
            if self.canvas:
                # Would need to implement setZoom on canvas
                pass
        except ValueError:
            pass