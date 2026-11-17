"""
AnnotationEngine Desktop - Progress Dialog
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
)
from PySide6.QtCore import Qt, Signal, Slot


class ProgressDialog(QDialog):
    """Progress dialog for long-running operations."""
    
    cancelled = Signal()
    
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.resize(400, 150)
        
        layout = QVBoxLayout(self)
        
        self.message_label = QLabel(message)
        layout.addWidget(self.message_label)
        
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self.detail_label)
        
        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.onCancel)
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignRight)
    
    @Slot()
    def onCancel(self):
        self.cancelled.emit()
        self.reject()
    
    @Slot(int, str)
    def setProgress(self, value: int, message: str = ""):
        self.progress_bar.setValue(value)
        if message:
            self.detail_label.setText(message)