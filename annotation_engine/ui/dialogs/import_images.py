"""
AnnotationEngine Desktop - Import Images Dialog
"""
import os
import shutil
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QComboBox, QCheckBox, QListWidget,
    QMessageBox
)
from PySide6.QtCore import Qt

from annotation_engine.config import SUPPORTED_IMAGE_FORMATS
from annotation_engine.core.database import get_database, get_project, add_image


class ImportImagesDialog(QDialog):
    """Dialog for importing images into a project."""
    
    def __init__(self, parent=None, project_id=None):
        super().__init__(parent)
        
        self.project_id = project_id
        self.selected_files: List[str] = []
        self.selected_folder: Optional[str] = None
        
        self.setWindowTitle("Import Images")
        self.setModal(True)
        self.resize(600, 500)
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # Source selection
        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        
        # Files
        files_layout = QHBoxLayout()
        files_btn = QPushButton("Select Files...")
        files_btn.clicked.connect(self.selectFiles)
        files_layout.addWidget(files_btn)
        
        self.files_label = QLabel("No files selected")
        files_layout.addWidget(self.files_label)
        files_layout.addStretch()
        source_layout.addLayout(files_layout)
        
        # Folder
        folder_layout = QHBoxLayout()
        folder_btn = QPushButton("Select Folder...")
        folder_btn.clicked.connect(self.selectFolder)
        folder_layout.addWidget(folder_btn)
        
        self.folder_label = QLabel("No folder selected")
        folder_layout.addWidget(self.folder_label)
        folder_layout.addStretch()
        source_layout.addLayout(folder_layout)
        
        layout.addWidget(source_group)
        
        # Options
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        
        self.split_combo = QComboBox()
        self.split_combo.addItems(["train", "val", "test"])
        options_layout.addRow("Default Split:", self.split_combo)
        
        self.recursive_check = QCheckBox("Include subfolders (for folder import)")
        self.recursive_check.setChecked(True)
        options_layout.addRow(self.recursive_check)
        
        layout.addWidget(options_group)
        
        # Preview
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_list = QListWidget()
        self.preview_list.setMaximumHeight(200)
        preview_layout.addWidget(self.preview_list)
        
        layout.addWidget(preview_group)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        self.import_btn = QPushButton("Import")
        self.import_btn.setDefault(True)
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.doImport)
        buttons.addWidget(self.import_btn)
        
        layout.addLayout(buttons)
    
    def selectFiles(self):
        """Select image files."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", str(Path.home()),
            f"Images ({' '.join(f'*{ext}' for ext in SUPPORTED_IMAGE_FORMATS)})"
        )
        if files:
            self.selected_files = files
            self.selected_folder = None
            self.updatePreview()
            self.import_btn.setEnabled(True)
    
    def selectFolder(self):
        """Select image folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", str(Path.home())
        )
        if folder:
            self.selected_folder = folder
            self.selected_files = []
            self.updatePreview()
            self.import_btn.setEnabled(True)
    
    def updatePreview(self):
        """Update preview list."""
        self.preview_list.clear()
        
        if self.selected_files:
            for f in self.selected_files[:50]:
                self.preview_list.addItem(f)
            if len(self.selected_files) > 50:
                self.preview_list.addItem(f"... and {len(self.selected_files) - 50} more")
        elif self.selected_folder:
            # Scan folder
            folder = Path(self.selected_folder)
            recursive = self.recursive_check.isChecked()
            pattern = "**/*" if recursive else "*"
            count = 0
            for ext in SUPPORTED_IMAGE_FORMATS:
                for f in folder.glob(f"{pattern}{ext}"):
                    if count < 50:
                        self.preview_list.addItem(str(f.relative_to(folder)))
                    count += 1
            if count > 50:
                self.preview_list.addItem(f"... and {count - 50} more")
            self.preview_list.addItem(f"Total: {count} images")
    
    def doImport(self):
        """Perform the import."""
        if not self.project_id:
            return
        
        project = get_project(self.project_id)
        if not project:
            return
        
        base_path = Path(project['base_path'])
        images_dir = base_path / 'images'
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Get files to import
        files_to_import = []
        if self.selected_files:
            files_to_import = [Path(f) for f in self.selected_files]
        elif self.selected_folder:
            folder = Path(self.selected_folder)
            recursive = self.recursive_check.isChecked()
            pattern = "**/*" if recursive else "*"
            for ext in SUPPORTED_IMAGE_FORMATS:
                files_to_import.extend(folder.glob(f"{pattern}{ext}"))
        
        if not files_to_import:
            return
        
        # Import each file
        split = self.split_combo.currentText()
        imported = 0
        
        for src_path in files_to_import:
            try:
                # Copy to project images folder
                rel_path = src_path.name
                dst_path = images_dir / rel_path
                
                # Handle duplicates
                counter = 1
                while dst_path.exists():
                    stem = src_path.stem
                    suffix = src_path.suffix
                    dst_path = images_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
                
                shutil.copy2(src_path, dst_path)
                
                # Add to database
                from PIL import Image
                with Image.open(dst_path) as img:
                    width, height = img.size
                
                file_size = dst_path.stat().st_size
                rel_path_str = dst_path.relative_to(base_path).as_posix()
                
                add_image(
                    self.project_id,
                    dst_path.name,
                    rel_path_str,
                    width, height, file_size, split
                )
                
                imported += 1
            except Exception as e:
                print(f"Failed to import {src_path}: {e}")
        
        QMessageBox.information(self, "Import Complete", f"Successfully imported {imported} images.")
        self.accept()