"""
AnnotationEngine Desktop - Export Dialog
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QCheckBox, QRadioButton,
    QLineEdit, QProgressBar, QMessageBox, QApplication,
    QSpinBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal

from annotation_engine.core.database import get_project
from annotation_engine.services.export_service import ExportService


class ExportDialog(QDialog):
    """Dialog for exporting dataset."""
    
    # Emitted when the user chooses to export to the SSH server instead of a
    # local directory. The main window performs the work in the background.
    exportToServerRequested = Signal(dict)
    
    def __init__(self, parent=None, project_id=None, image_resolver=None):
        super().__init__(parent)
        
        self.project_id = project_id
        self.project = get_project(project_id) if project_id else None
        self.is_remote = bool(self.project and self.project.get('remote_host'))
        self.image_resolver = image_resolver
        
        self.setWindowTitle("Export Dataset")
        self.setModal(True)
        self.resize(500, 560)
        
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
        split_layout = QVBoxLayout(split_group)
        
        self.use_split = QCheckBox("Group by split (train/val/test)")
        self.use_split.setChecked(True)
        self.use_split.setToolTip(
            "Organize images and labels into train/val/test subfolders and "
            "write a data.yaml for YOLO. Uncheck for a flat labels/ output."
        )
        split_layout.addWidget(self.use_split)
        
        # Distribution applied to images that were imported without a split.
        dist_layout = QFormLayout()
        dist_layout.setContentsMargins(16, 4, 0, 0)
        
        self.split_train = QSpinBox()
        self.split_train.setRange(0, 100)
        self.split_train.setValue(70)
        self.split_train.setSuffix("%")
        dist_layout.addRow("Train:", self.split_train)
        
        self.split_val = QSpinBox()
        self.split_val.setRange(0, 100)
        self.split_val.setValue(20)
        self.split_val.setSuffix("%")
        dist_layout.addRow("Val:", self.split_val)
        
        self.split_test = QSpinBox()
        self.split_test.setRange(0, 100)
        self.split_test.setValue(10)
        self.split_test.setSuffix("%")
        dist_layout.addRow("Test:", self.split_test)
        
        dist_note = QLabel(
            "Percentage of unassigned images to place in each split."
        )
        dist_note.setStyleSheet("color: #6b7280; font-size: 12px;")
        dist_note.setWordWrap(True)
        dist_layout.addRow("", dist_note)
        
        split_layout.addLayout(dist_layout)
        
        self.use_split.toggled.connect(self._onUseSplitToggled)
        self._onUseSplitToggled(self.use_split.isChecked())
        
        layout.addWidget(split_group)
        
        # Include
        include_group = QGroupBox("Include")
        include_layout = QVBoxLayout(include_group)
        
        self.include_bbox = QCheckBox("Bounding Boxes")
        self.include_bbox.setChecked(True)
        include_layout.addWidget(self.include_bbox)
        
        self.include_obb = QCheckBox("Oriented Boxes")
        self.include_obb.setChecked(True)
        include_layout.addWidget(self.include_obb)
        
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
        
        # SSH-only: write the export straight to the server.
        self.output_server = QRadioButton("Save to server (SSH)")
        self.output_server.setToolTip(
            "Export locally into a temporary folder, then upload it to the "
            "remote path below."
        )
        output_layout.addWidget(self.output_server)
        
        server_path_layout = QHBoxLayout()
        self.server_path = QLineEdit()
        self.server_path.setEnabled(False)
        if self.is_remote:
            remote_dir = (self.project.get('remote_dir') or '').rstrip('/')
            self.server_path.setText(f"{remote_dir}/exports" if remote_dir else "/exports")
        server_path_layout.addWidget(self.server_path)
        output_layout.addLayout(server_path_layout)
        
        if self.is_remote:
            server_note = QLabel(
                "Remote path on the SSH server. Images are uploaded too."
            )
        else:
            server_note = QLabel(
                "Only available for SSH projects."
            )
            self.output_server.setEnabled(False)
            self.output_server.setVisible(False)
            self.server_path.setVisible(False)
        server_note.setStyleSheet("color: #6b7280; font-size: 12px;")
        server_note.setWordWrap(True)
        output_layout.addWidget(server_note)
        
        self.output_server.toggled.connect(self._onOutputModeChanged)
        self.output_custom.toggled.connect(self._onOutputModeChanged)
        
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

    def _onUseSplitToggled(self, checked: bool):
        """Enable the split-distribution spinboxes only when grouping."""
        for spin in (self.split_train, self.split_val, self.split_test):
            spin.setEnabled(checked)
    
    def _onOutputModeChanged(self, *args):
        """Enable the matching path field for the chosen output mode."""
        self.output_path.setEnabled(self.output_custom.isChecked())
        self.server_path.setEnabled(self.output_server.isChecked())
    
    def _exportOptions(self) -> dict:
        """Collect the format/split/include choices shared by both targets."""
        return {
            'want_yolo': self.format_yolo.isChecked(),
            'want_labelme': self.format_labelme.isChecked(),
            'use_split': self.use_split.isChecked(),
            'split_distribution': {
                'train': self.split_train.value() / 100,
                'val': self.split_val.value() / 100,
                'test': self.split_test.value() / 100,
            },
            'include_bboxes': self.include_bbox.isChecked(),
            'include_obb': self.include_obb.isChecked(),
            'include_polygons': self.include_polygon.isChecked(),
            'include_keypoints': self.include_keypoints.isChecked(),
        }
    
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

        # SSH projects may export straight to the server; the main window runs
        # that in the background and reports back through the progress bar.
        if self.is_remote and self.output_server.isChecked():
            remote_path = self.server_path.text().strip()
            if not remote_path:
                QMessageBox.warning(self, "Export", "Enter a remote path.")
                return
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.export_btn.setEnabled(False)
            self.exportToServerRequested.emit({
                **self._exportOptions(), 'remote_path': remote_path,
            })
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

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.export_btn.setEnabled(False)
        QApplication.processEvents()

        def report(percent, message):
            self.progress_bar.setValue(int(percent))
            self.progress_bar.setFormat(f"{message} (%p%)")
            QApplication.processEvents()

        service = ExportService(self.project_id, image_resolver=self.image_resolver)
        ok = True
        try:
            if want_yolo:
                ok = service.export_yolo(
                    output_dir / 'yolo',
                    use_split=self.use_split.isChecked(),
                    split_distribution={
                        'train': self.split_train.value() / 100,
                        'val': self.split_val.value() / 100,
                        'test': self.split_test.value() / 100,
                    },
                    include_bboxes=self.include_bbox.isChecked(),
                    include_obb=self.include_obb.isChecked(),
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
    
    # ------------------------------------------------------------------
    # Server export (driven by the main window)
    # ------------------------------------------------------------------
    def setServerProgress(self, percent: int, message: str = ""):
        """Update the progress bar while a server export runs."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(int(percent))
        if message:
            self.progress_bar.setFormat(f"{message} (%p%)")
    
    def finishServerExport(self, ok: bool, message: str, remote_path: str = ""):
        """Close out a server export, reporting success or failure."""
        self.progress_bar.setVisible(False)
        self.export_btn.setEnabled(True)
        if ok:
            QMessageBox.information(self, "Export", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Export", message)