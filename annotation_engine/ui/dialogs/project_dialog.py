"""
AnnotationEngine Desktop - Project Dialog
"""
import os
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QTextEdit,
    QHBoxLayout
)
from PySide6.QtCore import Qt


class ProjectDialog(QDialog):
    """Dialog for creating/editing projects."""
    
    def __init__(self, parent=None, mode="create", project_data=None):
        super().__init__(parent)
        
        self.mode = mode  # "create" or "edit"
        self.project_data = project_data
        
        self.setWindowTitle("Create Project" if mode == "create" else "Edit Project")
        self.setModal(True)
        self.resize(500, 400)
        
        self.setupUI()
        
        if mode == "edit" and project_data:
            self.loadProjectData()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # Form
        form = QFormLayout()
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("My Annotation Project")
        form.addRow("Project Name:", self.name_input)
        
        # Base path
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("~/Documents/AnnotationEngine/Projects/MyProject")
        path_layout.addWidget(self.path_input)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browsePath)
        path_layout.addWidget(browse_btn)
        
        form.addRow("Project Folder:", path_layout)
        
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        self.description_input.setPlaceholderText("Optional description...")
        form.addRow("Description:", self.description_input)
        
        layout.addLayout(form)
        
        # Info
        info_label = QLabel(
            "A project folder will be created with the following structure:\n"
            "  project_name/\n"
            "    ├── images/     (imported images)\n"
            "    ├── labels/     (LabelMe JSON annotations)\n"
            "    └── exports/    (exported datasets)"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #6b7280; font-size: 12px; padding: 8px; background: #f9fafb; border-radius: 4px;")
        layout.addWidget(info_label)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        self.ok_btn = QPushButton("Create Project" if self.mode == "create" else "Save Changes")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.validateAndAccept)
        buttons.addWidget(self.ok_btn)
        
        layout.addLayout(buttons)
    
    def browsePath(self):
        """Browse for project directory."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Project Directory", str(Path.home() / "Documents")
        )
        if path:
            self.path_input.setText(path)
    
    def loadProjectData(self):
        """Load existing project data."""
        if self.project_data:
            self.name_input.setText(self.project_data.get('name', ''))
            self.path_input.setText(self.project_data.get('base_path', ''))
            self.description_input.setPlainText(self.project_data.get('description', ''))
    
    def validateAndAccept(self):
        """Validate inputs and accept."""
        name = self.name_input.text().strip()
        path = self.path_input.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a project name.")
            return
        
        if not path:
            QMessageBox.warning(self, "Invalid Path", "Please select a project directory.")
            return
        
        # Check if path exists for create mode
        if self.mode == "create" and os.path.exists(os.path.join(path, name)):
            reply = QMessageBox.question(
                self, "Project Exists",
                f"A folder '{name}' already exists in the selected directory.\n"
                "Do you want to use it as the project folder?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        self.accept()
    
    def projectName(self) -> str:
        return self.name_input.text().strip()
    
    def basePath(self) -> str:
        return self.path_input.text().strip()
    
    def description(self) -> str:
        return self.description_input.toPlainText().strip()