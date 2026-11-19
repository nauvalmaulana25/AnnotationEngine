"""
AnnotationEngine Desktop - Export Dialog
"""
from pathlib import Path
from typing import Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QCheckBox, QSpinBox, QRadioButton,
    QLineEdit, QProgressBar, QFormLayout, QMessageBox, QApplication
)
from PySide6.QtCore import Qt

from annotation_engine.core.database import get_project
from annotation_engine.services.export_service import ExportService


class ExportDialog(QDialog):
    """Dialog for exporting dataset."""
    
    def __init__(self, parent=None, project_id=None):
        super().__init__(parent)
        
        self.project_id = project_id
        
        self.setWindowTitle("Export Dataset")
        self.setModal(True)
        self.resize(500, 500)
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # Format
        format_group = QGroupBox("Format")
        format_layout = QVBoxLayout(format_group)
        
        self.format_yolo = QCheckBox("YOLO (.txt + data.yaml)")
        self.format_yolo.setChecked(True)
        format_layout.addWidget(self.format_yolo)
        
        self.format_labelme = QCheckBox("LabelMe (.json)")
        format_layout.addWidget(self.format_labelme)
        
        layout.addWidget(format_group)
        
        # Split
        split_group = QGroupBox("Data Split")
        split_layout = QFormLayout(split_group)
        
        self.split_train = QSpinBox()
        self.split_train.setRange(0, 100)
        self.split_train.setValue(70)
        self.split_train.setSuffix("%")
        split_layout.addRow("Train:", self.split_train)
        
        self.split_val = QSpinBox()
        self.split_val.setRange(0, 100)
        self.split_val.setValue(20)
        self.split_val.setSuffix("%")
        split_layout.addRow("Val:", self.split_val)
        
        self.split_test = QSpinBox()
        self.split_test.setRange(0, 100)
        self.split_test.setValue(10)
        self.split_test.setSuffix("%")
        split_layout.addRow("Test:", self.split_test)
        
        layout.addWidget(split_group)
        
        # Include
        include_group = QGroupBox("Include")
        include_layout = QVBoxLayout(include_group)
        
        self.include_bbox = QCheckBox("Bounding Boxes")
        self.include_bbox.setChecked(True)
        include_layout.addWidget(self.include_bbox)
        
        self.include_polygon = QCheckBox("Polygons")
        include_layout.addWidget(self.include_polygon)
        
        self.include_keypoints = QCheckBox("Keypoints")
        include_layout.addWidget(self.include_keypoints)
        
        layout.addWidget(include_group)
        
        # Output
        output_group = QGroupBox("Output Location")
        output_layout = QVBoxLayout(output_group)
        
        self.output_project = QRadioButton("Save to project folder")
        self.output_project.setChecked(True)
        output_layout.addWidget(self.output_project)
        
        self.output_custom = QRadioButton("Custom location")
        output_layout.addWidget(self.output_custom)
        
        path_layout = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setEnabled(False)
        path_layout.addWidget(self.output_path)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browseOutput)
        path_layout.addWidget(browse_btn)
        
        output_layout.addLayout(path_layout)
        
        layout.addWidget(output_group)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        self.export_btn = QPushButton("Export")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self.doExport)
        buttons.addWidget(self.export_btn)
        
        layout.addLayout(buttons)
    
    def browseOutput(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.output_path.setText(path)
    
    def doExport(self):
        """Run the selected export(s) into the chosen output directory."""
        if not self.project_id:
            QMessageBox.warning(self, "Export", "No project is open.")
            return

        want_yolo = self.format_yolo.isChecked()
        want_labelme = self.format_labelme.isChecked()
        if not want_yolo and not want_labelme:
            QMessageBox.warning(self, "Export", "Select at least one format.")
            return

        if self.output_custom.isChecked():
            target = self.output_path.text().strip()
            if not target:
                QMessageBox.warning(self, "Export", "Choose an output folder.")
                return
            output_dir = Path(target)
        else:
            project = get_project(self.project_id)
            if not project:
                QMessageBox.warning(self, "Export", "Project not found.")
                return
            output_dir = Path(project['base_path']) / 'exports'

        ratios = {
            'train': self.split_train.value() / 100,
            'val': self.split_val.value() / 100,
            'test': self.split_test.value() / 100,
        }

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.export_btn.setEnabled(False)
        QApplication.processEvents()

        def report(percent, message):
            self.progress_bar.setValue(int(percent))
            self.progress_bar.setFormat(f"{message} (%p%)")
            QApplication.processEvents()

        service = ExportService(self.project_id)
        ok = True
        try:
            if want_yolo:
                ok = service.export_yolo(
                    output_dir / 'yolo',
                    ratios,
                    include_bboxes=self.include_bbox.isChecked(),
                    include_polygons=self.include_polygon.isChecked(),
                    include_keypoints=self.include_keypoints.isChecked(),
                    progress_callback=report,
                ) and ok
            if want_labelme:
                ok = service.export_labelme(
                    output_dir / 'labelme',
                    copy_images=True,
                    progress_callback=report,
                ) and ok
        finally:
            self.progress_bar.setVisible(False)
            self.export_btn.setEnabled(True)

        if ok:
            QMessageBox.information(
                self, "Export", f"Export finished:\n{output_dir}"
            )
            self.accept()
        else:
            QMessageBox.critical(
                self, "Export", "Export failed. Check the log for details."
            )