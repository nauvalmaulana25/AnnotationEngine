"""
AnnotationEngine Desktop - Auto Annotate Dialog
"""
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QDoubleSpinBox,
    QTabWidget, QWidget, QProgressBar, QHBoxLayout,
    QSpinBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot


class AutoAnnotateDialog(QDialog):
    """Dialog for auto-annotation (Grounding DINO, MobileSAM, DINOv2)."""
    
    # Signals
    runGroundingDINO = Signal(dict)
    runMobileSAM = Signal(dict)
    runDINOv2 = Signal(dict)
    
    def __init__(self, parent=None, project_id=None, selected_images=None):
        super().__init__(parent)
        
        self.project_id = project_id
        self.selected_images = selected_images or []
        
        self.setWindowTitle("Auto Annotate")
        self.setModal(True)
        self.resize(800, 600)
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        tabs = QTabWidget()
        
        # Grounding DINO tab
        gdino_tab = QWidget()
        gdino_layout = QFormLayout(gdino_tab)
        
        self.gdino_prompt = QLineEdit()
        self.gdino_prompt.setPlaceholderText("e.g., person, car, dog, cat")
        gdino_layout.addRow("Text Prompt:", self.gdino_prompt)
        
        self.gdino_threshold = QDoubleSpinBox()
        self.gdino_threshold.setRange(0.1, 1.0)
        self.gdino_threshold.setValue(0.3)
        self.gdino_threshold.setSingleStep(0.05)
        gdino_layout.addRow("Confidence:", self.gdino_threshold)
        
        self.gdino_images_label = QLabel(f"Images: {len(self.selected_images)} selected")
        gdino_layout.addRow(self.gdino_images_label)
        
        gdino_btn = QPushButton("Run Grounding DINO")
        gdino_btn.setDefault(True)
        gdino_btn.clicked.connect(lambda: self.runGroundingDINO.emit({
            'text_prompt': self.gdino_prompt.text(),
            'threshold': self.gdino_threshold.value(),
            'image_ids': self.selected_images
        }))
        gdino_layout.addRow(gdino_btn)
        
        tabs.addTab(gdino_tab, "Grounding DINO")
        
        # MobileSAM tab
        sam_tab = QWidget()
        sam_layout = QFormLayout(sam_tab)
        
        self.sam_mode = QComboBox()
        self.sam_mode.addItems(["From GDINO boxes", "From manual boxes", "From all annotations"])
        sam_layout.addRow("Box Source:", self.sam_mode)
        
        self.sam_iou = QDoubleSpinBox()
        self.sam_iou.setRange(0.1, 1.0)
        self.sam_iou.setValue(0.7)
        sam_layout.addRow("IoU Threshold:", self.sam_iou)
        
        sam_btn = QPushButton("Run MobileSAM")
        sam_btn.clicked.connect(lambda: self.runMobileSAM.emit({
            'mode': self.sam_mode.currentText(),
            'iou_threshold': self.sam_iou.value(),
            'image_ids': self.selected_images
        }))
        sam_layout.addRow(sam_btn)
        
        tabs.addTab(sam_tab, "MobileSAM")
        
        # DINOv2 tab
        dinov2_tab = QWidget()
        dinov2_layout = QFormLayout(dinov2_tab)
        
        self.dinov2_ref_label = QLabel("Reference images with keypoints:")
        dinov2_layout.addRow(self.dinov2_ref_label)
        
        self.dinov2_threshold = QDoubleSpinBox()
        self.dinov2_threshold.setRange(0.1, 1.0)
        self.dinov2_threshold.setValue(0.4)
        dinov2_layout.addRow("Similarity:", self.dinov2_threshold)
        
        self.dinov2_consensus = QSpinBox()
        self.dinov2_consensus.setRange(1, 10)
        self.dinov2_consensus.setValue(2)
        dinov2_layout.addRow("Consensus Votes:", self.dinov2_consensus)
        
        dinov2_btn = QPushButton("Run DINOv2 Keypoint")
        dinov2_btn.clicked.connect(lambda: self.runDINOv2.emit({
            'similarity_threshold': self.dinov2_threshold.value(),
            'consensus_votes': self.dinov2_consensus.value(),
            'image_ids': self.selected_images
        }))
        dinov2_layout.addRow(dinov2_btn)
        
        tabs.addTab(dinov2_tab, "DINOv2 Keypoint")
        
        layout.addWidget(tabs)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        
        layout.addLayout(buttons)
    
    @Slot(int, str)
    def setProgress(self, value: int, message: str = ""):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(value)
        if message:
            self.progress_label.setText(message)