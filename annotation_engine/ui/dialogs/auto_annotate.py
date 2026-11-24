"""
AnnotationEngine Desktop - Auto Annotate Dialog
"""
import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QDoubleSpinBox,
    QTabWidget, QWidget, QProgressBar, QHBoxLayout,
    QSpinBox, QCheckBox, QMessageBox, QFrame, QScrollArea,
    QFileDialog
)
from PySide6.QtCore import Qt, QSettings, Signal, Slot

from annotation_engine.services.device import (
    DEVICE_AUTO,
    describe_device,
    list_devices,
    resolve_device,
)
from annotation_engine.services.model_manager import (
    list_yolo_models,
    mobile_sam_status,
)
from annotation_engine.services.grounding_dino import grounding_dino_mode

# Box sources offered on the MobileSAM tab.
BOX_SOURCE_EXISTING = "existing"
BOX_SOURCE_ALL = "all"

# Image scope offered on the YOLO tab.
YOLO_SCOPE_CURRENT = "current"
YOLO_SCOPE_ALL = "all"

# Height cap for the label checklist; projects can have many labels.
LABEL_LIST_MAX_HEIGHT = 130

# Settings key holding the last chosen inference device.
DEVICE_SETTING_KEY = "auto_annotate/device"


class AutoAnnotateDialog(QDialog):
    """Dialog for auto-annotation (Grounding DINO, MobileSAM, DINOv2)."""
    
    # Signals
    runGroundingDINO = Signal(dict)
    runMobileSAM = Signal(dict)
    downloadMobileSAM = Signal()
    runDINOv2 = Signal(dict)
    runYolo = Signal(dict)
    loadYoloModel = Signal(dict)
    
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
        self._refreshYoloModels()
    
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
        """Rebuild the label checklist, keeping existing ticks where possible.

        A label the user has not seen before starts checked, so newly imported
        labels are included without an explicit "all labels" entry.
        """
        self.labels = list(labels or [])
        known = getattr(self, "sam_label_boxes", {}) or {}
        previously = {label for label, box in known.items() if box.isChecked()}

        # Drop the old rows before rebuilding.
        while self.sam_label_layout.count():
            item = self.sam_label_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.sam_label_boxes = {}

        for label in self.labels:
            box = QCheckBox(label)
            # Known labels keep their tick; brand-new ones start selected.
            box.setChecked(label in previously if label in known else True)
            box.stateChanged.connect(self._updateLabelSummary)
            self.sam_label_layout.addWidget(box)
            self.sam_label_boxes[label] = box

        self.sam_label_layout.addStretch(1)
        self._updateLabelSummary()

    def selectedLabels(self) -> List[str]:
        """Labels currently ticked in the checklist."""
        boxes = getattr(self, "sam_label_boxes", {}) or {}
        return [label for label, box in boxes.items() if box.isChecked()]

    def _updateLabelSummary(self):
        """Show how many labels are selected next to the checklist."""
        boxes = getattr(self, "sam_label_boxes", {}) or {}
        if not boxes:
            self.sam_label_summary.setText("No labels in this project yet")
            return
        chosen = len(self.selectedLabels())
        self.sam_label_summary.setText(
            f"{chosen} of {len(boxes)} label(s) selected"
        )
    
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
        
        # Inference mode is fixed by the hardware: local on a big GPU, else cloud.
        self.gdino_mode = grounding_dino_mode()
        mode_text = (
            "Local (GPU)" if self.gdino_mode == "local"
            else "Cloud (Hugging Face API)"
        )
        self.gdino_mode_label = QLabel(f"Mode: {mode_text}")
        self.gdino_mode_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        gdino_layout.addRow("", self.gdino_mode_label)
        
        self.gdino_prompt = QLineEdit()
        self.gdino_prompt.setPlaceholderText(
            "e.g., person, car, dog, cat (comma-separated)"
        )
        gdino_layout.addRow("Prompts:", self.gdino_prompt)
        
        self.gdino_threshold = QDoubleSpinBox()
        self.gdino_threshold.setRange(0.0, 1.0)
        self.gdino_threshold.setValue(0.3)
        self.gdino_threshold.setSingleStep(0.05)
        gdino_layout.addRow("Confidence:", self.gdino_threshold)
        
        self.gdino_scope = QComboBox()
        self.gdino_scope.addItem("Current image", YOLO_SCOPE_CURRENT)
        self.gdino_scope.addItem("All images", YOLO_SCOPE_ALL)
        if self.gdino_mode == "cloud":
            # Cloud offloads one image at a time.
            self.gdino_scope.setEnabled(False)
            self.gdino_scope.setCurrentIndex(0)
        gdino_layout.addRow("Images:", self.gdino_scope)
        
        self.gdino_device_note = QLabel(
            "Cloud mode processes one image at a time."
            if self.gdino_mode == "cloud"
            else "Local mode (GPU with at least 4 GB VRAM)."
        )
        self.gdino_device_note.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.gdino_device_note.setWordWrap(True)
        gdino_layout.addRow("", self.gdino_device_note)
        
        gdino_btn = QPushButton("Run Grounding DINO")
        gdino_btn.setDefault(True)
        gdino_btn.clicked.connect(self._emitGroundingDino)
        self.gdino_btn = gdino_btn
        gdino_layout.addRow(gdino_btn)
        
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
        
        # The labels decide which boxes are used as prompts, and the resulting
        # masks inherit them. A checklist allows segmenting several classes in
        # one run; ticking everything is the equivalent of "all labels".
        self.sam_label_boxes = {}
        self.sam_label_container = QWidget()
        self.sam_label_layout = QVBoxLayout(self.sam_label_container)
        self.sam_label_layout.setContentsMargins(0, 0, 0, 0)
        self.sam_label_layout.setSpacing(2)

        self.sam_label_scroll = QScrollArea()
        self.sam_label_scroll.setWidgetResizable(True)
        self.sam_label_scroll.setFrameShape(QFrame.NoFrame)
        self.sam_label_scroll.setMaximumHeight(LABEL_LIST_MAX_HEIGHT)
        self.sam_label_scroll.setWidget(self.sam_label_container)

        self.sam_label_summary = QLabel("")
        self.sam_label_summary.setStyleSheet("color: #6b7280; font-size: 12px;")

        sam_layout.addRow("Labels:", self.sam_label_scroll)
        sam_layout.addRow("", self.sam_label_summary)
        self.setLabels(self.labels)
        
        # This is a mask-confidence floor, not an IoU threshold: masks scoring
        # below it are skipped. 0.25 matches Ultralytics' own default, so a box
        # that Ultralytics would drop is also reported as skipped here.
        self.sam_iou = QDoubleSpinBox()
        self.sam_iou.setRange(0.0, 1.0)
        self.sam_iou.setValue(0.25)
        self.sam_iou.setSingleStep(0.05)
        self.sam_iou.setToolTip(
            "Masks whose confidence is below this value are skipped. "
            "Lower it to segment weak or ambiguous boxes."
        )
        sam_layout.addRow("Min mask confidence:", self.sam_iou)
        
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
        
        # YOLO tab
        yolo_tab = QWidget()
        yolo_layout = QFormLayout(yolo_tab)
        
        model_row = QWidget()
        model_row_layout = QHBoxLayout(model_row)
        model_row_layout.setContentsMargins(0, 0, 0, 0)
        
        self.yolo_model_combo = QComboBox()
        self.yolo_model_combo.setMinimumWidth(240)
        model_row_layout.addWidget(self.yolo_model_combo, 1)
        
        self.yolo_browse_btn = QPushButton("Browse…")
        self.yolo_browse_btn.clicked.connect(self._onYoloBrowse)
        model_row_layout.addWidget(self.yolo_browse_btn)
        
        self.yolo_load_btn = QPushButton("Load")
        self.yolo_load_btn.clicked.connect(self._emitLoadYoloModel)
        model_row_layout.addWidget(self.yolo_load_btn)
        
        yolo_layout.addRow("Model:", model_row)
        
        self.yolo_task_label = QLabel("Not loaded")
        self.yolo_task_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        yolo_layout.addRow("", self.yolo_task_label)
        
        self.yolo_label_boxes = {}
        self.yolo_label_container = QWidget()
        self.yolo_label_layout = QVBoxLayout(self.yolo_label_container)
        self.yolo_label_layout.setContentsMargins(0, 0, 0, 0)
        self.yolo_label_layout.setSpacing(2)
        
        self.yolo_label_scroll = QScrollArea()
        self.yolo_label_scroll.setWidgetResizable(True)
        self.yolo_label_scroll.setFrameShape(QFrame.NoFrame)
        self.yolo_label_scroll.setMaximumHeight(LABEL_LIST_MAX_HEIGHT)
        self.yolo_label_scroll.setWidget(self.yolo_label_container)
        
        self.yolo_label_summary = QLabel("")
        self.yolo_label_summary.setStyleSheet("color: #6b7280; font-size: 12px;")
        
        yolo_layout.addRow("Labels:", self.yolo_label_scroll)
        yolo_layout.addRow("", self.yolo_label_summary)
        
        self.yolo_conf = QDoubleSpinBox()
        self.yolo_conf.setRange(0.0, 1.0)
        self.yolo_conf.setValue(0.25)
        self.yolo_conf.setSingleStep(0.05)
        yolo_layout.addRow("Confidence:", self.yolo_conf)
        
        self.yolo_iou = QDoubleSpinBox()
        self.yolo_iou.setRange(0.0, 1.0)
        self.yolo_iou.setValue(0.45)
        self.yolo_iou.setSingleStep(0.05)
        yolo_layout.addRow("IoU:", self.yolo_iou)
        
        self.yolo_scope = QComboBox()
        self.yolo_scope.addItem("Current image", YOLO_SCOPE_CURRENT)
        self.yolo_scope.addItem("All project images", YOLO_SCOPE_ALL)
        yolo_layout.addRow("Images:", self.yolo_scope)
        
        self.yolo_btn = QPushButton("Run YOLO")
        self.yolo_btn.setEnabled(False)
        self.yolo_btn.clicked.connect(self._emitRunYolo)
        yolo_layout.addRow(self.yolo_btn)
        
        tabs.addTab(yolo_tab, "YOLO")
        
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
            'labels': self.selectedLabels(),
            'iou_threshold': self.sam_iou.value(),
            'remove_boxes': self.sam_remove_boxes.isChecked(),
            'image_ids': self.selected_images
        }))
    
    def sam_model_present(self) -> bool:
        """Whether the checkpoint is available locally."""
        return bool(mobile_sam_status()['present'])
    
    def _emitGroundingDino(self):
        """Collect the Grounding DINO options and ask the window to run them."""
        prompts = [
            p.strip() for p in self.gdino_prompt.text().split(',') if p.strip()
        ]
        if not prompts:
            QMessageBox.warning(
                self, "Grounding DINO", "Enter at least one prompt (comma-separated)."
            )
            return
        self.runGroundingDINO.emit(self._payload({
            'prompts': prompts,
            'threshold': self.gdino_threshold.value(),
            'scope': self.gdino_scope.currentData(),
            'image_ids': self.selected_images,
            'mode': self.gdino_mode,
        }))
    
    def setMobileSamRunning(self, running: bool):
        """Disable the MobileSAM controls while a run is in flight."""
        self.sam_btn.setEnabled(not running)
        self.sam_source.setEnabled(not running)
        self.sam_label_scroll.setEnabled(not running)
    
    # ------------------------------------------------------------------
    # YOLO tab
    # ------------------------------------------------------------------
    def _refreshYoloModels(self):
        """Populate the YOLO model dropdown from the models directory."""
        current = self.yolo_model_combo.currentData()
        self.yolo_model_combo.clear()
        for path in list_yolo_models():
            self.yolo_model_combo.addItem(os.path.basename(path), path)
        if current:
            index = self.yolo_model_combo.findData(current)
            if index >= 0:
                self.yolo_model_combo.setCurrentIndex(index)
    
    def _onYoloBrowse(self):
        """Pick an arbitrary ``.pt`` file and add it to the dropdown."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select YOLO model", "", "PyTorch models (*.pt);;All files (*)"
        )
        if not path:
            return
        index = self.yolo_model_combo.findData(path)
        if index < 0:
            self.yolo_model_combo.addItem(os.path.basename(path), path)
            index = self.yolo_model_combo.count() - 1
        self.yolo_model_combo.setCurrentIndex(index)
        # A freshly picked model has no loaded weights yet.
        self.yolo_task_label.setText("Not loaded")
        self.yolo_btn.setEnabled(False)
    
    def _currentYoloModelPath(self) -> str:
        return self.yolo_model_combo.currentData() or ""
    
    def _emitLoadYoloModel(self):
        path = self._currentYoloModelPath()
        if not path:
            QMessageBox.warning(
                self, "YOLO", "Pick a model file first (or browse for a .pt)."
            )
            return
        self.yolo_load_btn.setEnabled(False)
        self.yolo_task_label.setText("Loading…")
        self.loadYoloModel.emit(self._payload({'model_path': path}))
    
    def setYoloModelInfo(self, task: str, names: dict):
        """Populate the task line and label checklist after a model load."""
        self.yolo_load_btn.setEnabled(True)
        if task == "classify":
            self.yolo_task_label.setText(
                "Classify models are image-level and are not supported yet"
            )
            self.yolo_task_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
            self.yolo_btn.setEnabled(False)
            return
        self.yolo_task_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        
        if isinstance(names, dict):
            name_list = [names[k] for k in sorted(names)]
        else:
            name_list = list(names or [])
        
        # Rebuild the label checklist, re-using the previous selection.
        previous = set(self.selectedYoloLabels())
        while self.yolo_label_layout.count():
            item = self.yolo_label_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.yolo_label_boxes = {}
        for name in name_list:
            box = QCheckBox(name)
            box.setChecked(name in previous if previous else True)
            box.stateChanged.connect(self._updateYoloLabelSummary)
            self.yolo_label_layout.addWidget(box)
            self.yolo_label_boxes[name] = box
        self.yolo_label_layout.addStretch(1)
        
        self.yolo_task_label.setText(f"Task: {task} · {len(name_list)} classes")
        self.yolo_btn.setEnabled(bool(name_list))
        self._updateYoloLabelSummary()
    
    def selectedYoloLabels(self) -> List[str]:
        """Labels currently ticked in the YOLO checklist."""
        return [
            name for name, box in self.yolo_label_boxes.items()
            if box.isChecked()
        ]
    
    def _updateYoloLabelSummary(self):
        boxes = self.yolo_label_boxes
        if not boxes:
            self.yolo_label_summary.setText("No labels loaded")
            return
        chosen = len(self.selectedYoloLabels())
        self.yolo_label_summary.setText(
            f"{chosen} of {len(boxes)} label(s) selected"
        )
    
    def _emitRunYolo(self):
        labels = self.selectedYoloLabels()
        if not labels:
            QMessageBox.warning(
                self, "YOLO", "Tick at least one label to run."
            )
            return
        self.runYolo.emit(self._payload({
            'model_path': self._currentYoloModelPath(),
            'labels': labels,
            'conf': self.yolo_conf.value(),
            'iou': self.yolo_iou.value(),
            'scope': self.yolo_scope.currentData(),
            'image_ids': self.selected_images,
        }))
    
    def setYoloRunning(self, running: bool):
        """Disable the YOLO controls while a load or run is in flight."""
        self.yolo_btn.setEnabled(not running and bool(self.yolo_label_boxes))
        self.yolo_load_btn.setEnabled(not running)
        self.yolo_browse_btn.setEnabled(not running)
        self.yolo_model_combo.setEnabled(not running)
    
    def setGroundingDinoRunning(self, running: bool):
        """Disable the Grounding DINO controls while a run is in flight."""
        self.gdino_btn.setEnabled(not running)
    
    @Slot(int, str)
    def setProgress(self, value: int, message: str = ""):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(value)
        if message:
            self.progress_label.setText(message)