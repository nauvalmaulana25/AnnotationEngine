"""
AnnotationEngine Desktop - Import Labels Dialog
"""
import os
import json
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QComboBox, QCheckBox, QFormLayout,
    QMessageBox
)
from PySide6.QtCore import Qt


class ImportLabelsDialog(QDialog):
    """Dialog for importing LabelMe JSON annotations."""
    
    def __init__(self, parent=None, project_id=None):
        super().__init__(parent)
        
        self.project_id = project_id
        self.selected_files: List[str] = []
        self.selected_folder: Optional[str] = None
        
        self.setWindowTitle("Import Labels")
        self.setModal(True)
        self.resize(600, 400)
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # Source selection
        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        
        files_btn = QPushButton("Select LabelMe JSON Files...")
        files_btn.clicked.connect(self.selectFiles)
        source_layout.addWidget(files_btn)
        
        folder_btn = QPushButton("Select Folder...")
        folder_btn.clicked.connect(self.selectFolder)
        source_layout.addWidget(folder_btn)
        
        layout.addWidget(source_group)
        
        # Options
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        
        self.match_by = QComboBox()
        self.match_by.addItems(["Filename", "Filename (no extension)", "Image ID in JSON"])
        options_layout.addRow("Match by:", self.match_by)
        
        self.overwrite_check = QCheckBox("Overwrite existing annotations")
        options_layout.addRow(self.overwrite_check)
        
        layout.addWidget(options_group)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        import_btn = QPushButton("Import")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self.doImport)
        buttons.addWidget(import_btn)
        
        layout.addLayout(buttons)
    
    def selectFiles(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select LabelMe JSON Files", str(Path.home()),
            "JSON Files (*.json)"
        )
        if files:
            self.selected_files = files
            self.selected_folder = None
    
    def selectFolder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", str(Path.home())
        )
        if folder:
            self.selected_folder = folder
            self.selected_files = []
    
    def doImport(self):
        # Import logic here
        QMessageBox.information(self, "Import", "Label import functionality not yet implemented.")
        self.accept()