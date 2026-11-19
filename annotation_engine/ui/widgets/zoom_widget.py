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
        self._updating = False
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
        self.zoom_combo.activated.connect(self.onZoomComboActivated)
        self.zoom_combo.lineEdit().editingFinished.connect(self.onZoomTextEntered)
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
        """Set the displayed zoom level without re-applying it."""
        self._updating = True
        try:
            text = f"{int(round(zoom * 100))}%"
            index = self.zoom_combo.findText(text)
            if index >= 0:
                self.zoom_combo.setCurrentIndex(index)
            else:
                self.zoom_combo.setCurrentText(text)
        finally:
            self._updating = False
    
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
    
    @Slot(int)
    def onZoomComboActivated(self, index: int):
        """Apply a zoom level chosen from the dropdown."""
        if self._updating:
            return
        self._applyZoomText(self.zoom_combo.itemText(index))

    @Slot()
    def onZoomTextEntered(self):
        """Handle manual zoom text entry."""
        if self._updating:
            return
        self._applyZoomText(self.zoom_combo.currentText())

    def _applyZoomText(self, text: str):
        zoom = self._parseZoom(text)
        if zoom is None:
            if self.canvas:
                self.setZoom(self.canvas.scale)
            return

        if self.canvas:
            self.canvas.setZoom(zoom)
        else:
            self.setZoom(zoom)
        self.zoomChanged.emit(zoom)

    @staticmethod
    def _parseZoom(text: str) -> float | None:
        text = (text or "").strip()
        if not text:
            return None
        try:
            if text.endswith('%'):
                zoom = float(text[:-1]) / 100.0
            else:
                value = float(text)
                # Treat bare values above 10 as percentages ("150" -> 1.5).
                zoom = value / 100.0 if value > 10 else value
        except ValueError:
            return None
        return zoom if zoom > 0 else None
