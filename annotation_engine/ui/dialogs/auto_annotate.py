"""
AnnotationEngine Desktop - Auto Annotate Dialog
"""
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QDoubleSpinBox,
    QTabWidget, QWidget, QProgressBar, QHBoxLayout,
    QSpinBox, QCheckBox, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QSettings, Signal, Slot

from annotation_engine.services.device import (
    DEVICE_AUTO,
    describe_device,
    list_devices,
    resolve_device,
)
from annotation_engine.services.model_manager import mobile_sam_status

# Box sources offered on the MobileSAM tab.
BOX_SOURCE_EXISTING = "existing"
BOX_SOURCE_ALL = "all"

# Dropdown entry that segments every label instead of one.
ALL_LABELS = "__all__"

# Settings key holding the last chosen inference device.
DEVICE_SETTING_KEY = "auto_annotate/device"


class AutoAnnotateDialog(QDialog):
    """Dialog for auto-annotation (Grounding DINO, MobileSAM, DINOv2)."""
    
    # Signals
    runGroundingDINO = Signal(dict)
    runMobileSAM = Signal(dict)
    downloadMobileSAM = Signal()
    runDINOv2 = Signal(dict)
    
    def __init__(self, parent=None, project_id=None, selected_images=None,
                 labels=None, annotated_count=None):
        super().__init__(parent)
        
        self.project_id = project_id
        self.selected_images = selected_images or []
        self.labels = list(labels or [])
        self.annotated_count = annotated_count
        
        self.setWindowTitle("Auto Annotate")
        self.setModal(True)
        self.resize(800, 620)
        
        self.setupUI()
        self.refreshModelStatus()
    
    # ------------------------------------------------------------------
    # Device selection
    # ------------------------------------------------------------------
    def setupDeviceRow(self, layout: QVBoxLayout):
        """Add the shared device selector used by every tab."""
        frame = QFrame()
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 4, 0, 4)
        
        row.addWidget(QLabel("Device:"))
        
        self.device_combo = QComboBox()
        for option in list_devices():
            self.device_combo.addItem(option.label, option.id)
        self.device_combo.setMinimumWidth(260)
        row.addWidget(self.device_combo)
        
        self.device_detail = QLabel("")
        self.device_detail.setStyleSheet("color: #6b7280; font-size: 12px;")
        row.addWidget(self.device_detail)
        row.addStretch(1)
        
        layout.addWidget(frame)
        
        self.restoreDevicePreference()
        self.device_combo.currentIndexChanged.connect(self._onDeviceChanged)
        self._onDeviceChanged()
    
    def restoreDevicePreference(self):
        """Select the device saved by a previous session."""
        saved = QSettings().value(DEVICE_SETTING_KEY, DEVICE_AUTO)
        index = self.device_combo.findData(saved)
        self.device_combo.setCurrentIndex(max(index, 0))
    
    def selectedDevice(self) -> str:
        """The device preference id currently chosen."""
        return self.device_combo.currentData() or DEVICE_AUTO
    
    def _onDeviceChanged(self, *args):
        """Persist the choice and refresh the descriptive label."""
        preference = self.selectedDevice()
        QSettings().setValue(DEVICE_SETTING_KEY, preference)
        self.device_detail.setText(describe_device(preference))
    
    def _payload(self, extra: dict) -> dict:
        """Attach the shared device choice to a tab's options."""
        return {**extra, 'device': self.selectedDevice()}
    
    def setLabels(self, labels: List[str]):
        """Populate the label dropdown, keeping the current choice if possible."""
        self.labels = list(labels or [])
        current = self.sam_label.currentData()
        
        self.sam_label.blockSignals(True)
        self.sam_label.clear()
        self.sam_label.addItem("All labels", ALL_LABELS)
        for label in self.labels:
            self.sam_label.addItem(label, label)
        
        index = self.sam_label.findData(current) if current else 0
        self.sam_label.setCurrentIndex(max(index, 0))
        self.sam_label.blockSignals(False)
    
    def refreshModelStatus(self):
        """Show whether the MobileSAM checkpoint is available locally."""
        status = mobile_sam_status()
        if status['present']:
            size_mb = status['size'] / (1024 * 1024)
            self.sam_model_label.setText(
                f"Model ready ({size_mb:.0f} MB)"
            )
            self.sam_model_label.setStyleSheet("color: #22c55e;")
            self.sam_model_path_label.setText(str(status['path']))
            self.sam_download_btn.setVisible(False)
        else:
            self.sam_model_label.setText("Model not downloaded")
            self.sam_model_label.setStyleSheet("color: #f59e0b;")
            self.sam_model_path_label.setText(
                f"Will be saved to: {status['path']}"
            )
            self.sam_download_btn.setVisible(True)
    
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
        gdino_btn.clicked.connect(lambda: self.runGroundingDINO.emit(self._payload({
            'text_prompt': self.gdino_prompt.text(),
            'threshold': self.gdino_threshold.value(),
            'image_ids': self.selected_images
        })))
        gdino_layout.addRow(gdino_btn)
        
        # Grounding DINO currently runs on Hugging Face servers, so the device
        # choice does not apply until a local build replaces it.
        self.gdino_device_note = QLabel(
            "Runs on Hugging Face servers; the device setting does not apply."
        )
        self.gdino_device_note.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.gdino_device_note.setWordWrap(True)
        gdino_layout.addRow("", self.gdino_device_note)
        
        tabs.addTab(gdino_tab, "Grounding DINO")
        
        # MobileSAM tab
        sam_tab = QWidget()
        sam_layout = QFormLayout(sam_tab)
        
        self.sam_source = QComboBox()
        self.sam_source.addItem("Boxes in the current image", BOX_SOURCE_EXISTING)
        self.sam_source.addItem(self._allImagesText(), BOX_SOURCE_ALL)
        self.sam_source.setToolTip(
            "Which images supply the box prompts that MobileSAM segments"
        )
        sam_layout.addRow("Source:", self.sam_source)
        
        # The label decides which boxes are used as prompts, and the resulting
        # masks inherit it.
        self.sam_label = QComboBox()
        self.sam_label.setToolTip("Segment only boxes carrying this label")
        sam_layout.addRow("Label:", self.sam_label)
        self.setLabels(self.labels)
        
        self.sam_iou = QDoubleSpinBox()
        self.sam_iou.setRange(0.1, 1.0)
        self.sam_iou.setValue(0.7)
        sam_layout.addRow("IoU Threshold:", self.sam_iou)
        
        # A bbox exists only to prompt the model; once the mask exists it is
        # redundant. Only rectangles are removed, since a hand-drawn polygon
        # may carry detail the mask does not reproduce.
        self.sam_remove_boxes = QCheckBox(
            "Remove source boxes after segmentation"
        )
        self.sam_remove_boxes.setChecked(True)
        self.sam_remove_boxes.setToolTip(
            "Delete the rectangle prompts once their masks exist. Undoable on "
            "the current image only."
        )
        sam_layout.addRow("", self.sam_remove_boxes)
        
        self.sam_model_label = QLabel("")
        sam_layout.addRow("Model:", self.sam_model_label)
        
        self.sam_model_path_label = QLabel("")
        self.sam_model_path_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.sam_model_path_label.setWordWrap(True)
        sam_layout.addRow("", self.sam_model_path_label)
        
        self.sam_download_btn = QPushButton("Download MobileSAM model (39 MB)")
        self.sam_download_btn.setToolTip(
            "Fetch the checkpoint into the application models folder"
        )
        self.sam_download_btn.clicked.connect(self.downloadMobileSAM)
        sam_layout.addRow("", self.sam_download_btn)
        
        self.sam_btn = QPushButton("Run MobileSAM")
        self.sam_btn.clicked.connect(self._emitMobileSAM)
        sam_layout.addRow(self.sam_btn)
        
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
        dinov2_btn.clicked.connect(lambda: self.runDINOv2.emit(self._payload({
            'similarity_threshold': self.dinov2_threshold.value(),
            'consensus_votes': self.dinov2_consensus.value(),
            'image_ids': self.selected_images
        })))
        dinov2_layout.addRow(dinov2_btn)
        
        tabs.addTab(dinov2_tab, "DINOv2 Keypoint")
        
        layout.addWidget(tabs)
        
        # One device selector for every tab: the services share the hardware.
        self.setupDeviceRow(layout)
        
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
    
    def _allImagesText(self) -> str:
        """Label for the all-images source, showing how many will run."""
        if self.annotated_count is None:
            return "All annotated images"
        return f"All annotated images ({self.annotated_count})"
    
    def _emitMobileSAM(self):
        """Collect the MobileSAM options and ask the window to run them."""
        if not self.sam_model_present():
            reply = QMessageBox.question(
                self, "MobileSAM Model Missing",
                "The MobileSAM model is not downloaded yet.\n"
                "Download it now (about 39 MB)?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.downloadMobileSAM.emit()
            return
        
        self.runMobileSAM.emit(self._payload({
            'source': self.sam_source.currentData(),
            'label': self.sam_label.currentData(),
            'iou_threshold': self.sam_iou.value(),
            'remove_boxes': self.sam_remove_boxes.isChecked(),
            'image_ids': self.selected_images
        }))
    
    def sam_model_present(self) -> bool:
        """Whether the checkpoint is available locally."""
        return bool(mobile_sam_status()['present'])
    
    def setMobileSamRunning(self, running: bool):
        """Disable the MobileSAM controls while a run is in flight."""
        self.sam_btn.setEnabled(not running)
        self.sam_source.setEnabled(not running)
        self.sam_label.setEnabled(not running)
    
    @Slot(int, str)
    def setProgress(self, value: int, message: str = ""):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(value)
        if message:
            self.progress_label.setText(message)