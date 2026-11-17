"""
AnnotationEngine Desktop - Welcome Widget (embedded in stacked widget)
"""
import os
from pathlib import Path
from typing import Optional, List

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QFrame, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtGui import QIcon, QFont, QPixmap

from annotation_engine.config import (
    APP_NAME, APP_VERSION, PROJECTS_DIR, DEFAULT_SETTINGS
)
from annotation_engine.core.database import (
    get_database, get_all_projects, get_project, get_recent_projects, add_recent_project
)
from annotation_engine.ui.dialogs.project_dialog import ProjectDialog


# Project root for logo (go up 3 levels from annotation_engine/ui/welcome_widget.py)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Asset paths
ASSETS_DIR = PROJECT_ROOT / "annotation_engine" / "resources" / "assets"


class WelcomeWidget(QWidget):
    """Welcome widget shown when no project is loaded (embedded in stacked widget)."""
    
    projectSelected = Signal(int)
    createProjectRequested = Signal()
    openProjectRequested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.selected_project_id: Optional[int] = None
        self.selected_project_path: Optional[str] = None
        
        self.setupUI()
        self.loadRecentProjects()
    
    def setupUI(self):
        # Main layout - generous margins and spacing
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 30)
        layout.setSpacing(24)
        
        # ===== LOGO SECTION (own space) =====
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(160, 160)  # Large logo
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
            }
        """)
        logo_path = ASSETS_DIR / "logo.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled = pixmap.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled)
        else:
            self.logo_label.setStyleSheet("""
                QLabel {
                    background-color: #3b82f6;
                    border-radius: 80px;
                    color: white;
                    font-size: 56px;
                    font-weight: bold;
                }
            """)
            self.logo_label.setText("AE")
        
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setAlignment(Qt.AlignCenter)
        logo_layout.setContentsMargins(0, 20, 0, 20)
        logo_layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)
        layout.addWidget(logo_container)
        
        # ===== APP NAME SECTION (own space) =====
        app_name = QLabel(APP_NAME)
        app_name.setAlignment(Qt.AlignCenter)
        app_name.setStyleSheet("font-size: 28px; font-weight: 700; color: #111827;")
        layout.addWidget(app_name)
        
        # ===== VERSION/TAGLINE SECTION (own space) =====
        from annotation_engine.config import APP_VERSION
        version_tagline = QLabel(f"v{APP_VERSION}  •  Hybrid Image Annotation")
        version_tagline.setAlignment(Qt.AlignCenter)
        version_tagline.setStyleSheet("font-size: 14px; color: #6b7280;")
        layout.addWidget(version_tagline)
        
        # ===== SEPARATOR =====
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #e5e7eb;")
        layout.addWidget(separator)
        
        # ===== ACTION BUTTONS SECTION =====
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(14)
        actions_layout.setContentsMargins(60, 0, 60, 0)
        
        self.create_btn = QPushButton("Create New Project")
        self.create_btn.setFixedHeight(52)
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 17px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        self.create_btn.clicked.connect(self.onCreateClicked)
        actions_layout.addWidget(self.create_btn)
        
        self.open_btn = QPushButton("Open Existing Project")
        self.open_btn.setFixedHeight(52)
        self.open_btn.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6;
                color: #374151;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                font-size: 17px;
                font-weight: 500;
            }
            QPushButton:hover { background-color: #e5e7eb; border-color: #9ca3af; }
            QPushButton:pressed { background-color: #d1d5db; }
        """)
        self.open_btn.clicked.connect(self.onOpenClicked)
        actions_layout.addWidget(self.open_btn)
        
        layout.addLayout(actions_layout)
        
        # ===== SEPARATOR =====
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        separator2.setStyleSheet("color: #e5e7eb;")
        layout.addWidget(separator2)
        
        # ===== RECENT PROJECTS SECTION =====
        recent_label = QLabel("Recent Projects")
        recent_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #374151;")
        layout.addWidget(recent_label)
        
        self.recent_list = QListWidget()
        self.recent_list.setAlternatingRowColors(True)
        self.recent_list.setMinimumHeight(300)
        self.recent_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                background-color: white;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 14px 18px;
                border-bottom: 1px solid #f3f4f6;
            }
            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #1e40af;
            }
            QListWidget::item:hover {
                background-color: #f9fafb;
            }
        """)
        self.recent_list.itemDoubleClicked.connect(self.onRecentItemDoubleClicked)
        layout.addWidget(self.recent_list, 1)  # Stretch
        
        # ===== BOTTOM ACTIONS =====
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        settings_btn = QPushButton("Settings")
        settings_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6b7280;
                border: none;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { color: #3b82f6; }
        """)
        settings_btn.clicked.connect(self.openSettings)
        bottom_layout.addWidget(settings_btn)
        
        quit_btn = QPushButton("Quit")
        quit_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ef4444;
                border: none;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { color: #dc2626; }
        """)
        quit_btn.clicked.connect(self.quitApplication)
        bottom_layout.addWidget(quit_btn)
        
        layout.addLayout(bottom_layout)
    
    def loadRecentProjects(self):
        """Load recent projects from settings."""
        from annotation_engine.core.database import get_recent_projects, get_project
        recent_ids = get_recent_projects()
        self.recent_list.clear()
        
        if not recent_ids:
            item = QListWidgetItem("No recent projects")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item.setForeground(Qt.gray)
            self.recent_list.addItem(item)
            return
        
        for pid in recent_ids[:10]:
            project = get_project(pid)
            if project:
                item = QListWidgetItem()
                item.setData(Qt.UserRole, pid)
                
                widget = QWidget()
                widget_layout = QHBoxLayout(widget)
                widget_layout.setContentsMargins(18, 16, 18, 16)
                widget_layout.setSpacing(12)
                
                # Left side - project info
                info_widget = QWidget()
                info_layout = QVBoxLayout(info_widget)
                info_layout.setContentsMargins(0, 0, 0, 0)
                info_layout.setSpacing(6)
                info_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                info_widget.setMinimumWidth(400)
                
                name_label = QLabel(project['name'])
                name_label.setStyleSheet("font-weight: 600; color: #111827; font-size: 16px;")
                name_label.setWordWrap(True)
                name_label.setMinimumHeight(24)
                name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                info_layout.addWidget(name_label)
                
                path_label = QLabel(project['base_path'])
                path_label.setStyleSheet("color: #6b7280; font-size: 13px;")
                path_label.setWordWrap(True)
                path_label.setMinimumHeight(22)
                path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                info_layout.addWidget(path_label)
                
                widget_layout = QHBoxLayout()
                widget_layout.setContentsMargins(18, 16, 18, 16)
                widget_layout.setSpacing(12)
                
                info_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                info_widget.setMinimumWidth(400)
                
                info_layout = QVBoxLayout(info_widget)
                info_layout.setContentsMargins(0, 0, 0, 0)
                info_layout.setSpacing(6)
                info_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                info_widget.setMinimumWidth(400)
                
                name_label = QLabel(project['name'])
                name_label.setStyleSheet("font-weight: 600; color: #111827; font-size: 16px;")
                name_label.setWordWrap(True)
                name_label.setMinimumHeight(24)
                name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                info_layout.addWidget(name_label)
                
                path_label = QLabel(project['base_path'])
                path_label.setStyleSheet("color: #6b7280; font-size: 13px;")
                path_label.setWordWrap(True)
                path_label.setMinimumHeight(22)
                path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                info_layout.addWidget(path_label)
                
                widget_layout.addWidget(info_widget, 1)
                
                # Right side - delete button
                delete_btn = QPushButton("Delete")
                delete_btn.setFixedSize(80, 32)
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #fef2f2;
                        color: #dc2626;
                        border: 1px solid #fecaca;
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: 500;
                    }
                    QPushButton:hover { background-color: #fee2e2; border-color: #fca5a5; }
                    QPushButton:pressed { background-color: #fecaca; }
                """)
                delete_btn.clicked.connect(lambda checked, pid=pid: self.deleteProject(pid))
                widget_layout.addWidget(delete_btn)
                
                item.setSizeHint(QSize(0, 100))
                self.recent_list.addItem(item)
                self.recent_list.setItemWidget(item, widget)
    
    @Slot()
    def onCreateClicked(self):
        """Emit signal to create new project."""
        self.createProjectRequested.emit()
    
    @Slot()
    def onOpenClicked(self):
        """Emit signal to open existing project."""
        self.openProjectRequested.emit()
    
    @Slot(QListWidgetItem)
    def onRecentItemDoubleClicked(self, item: QListWidgetItem):
        """Handle double-click on recent project."""
        pid = item.data(Qt.UserRole)
        if pid:
            self.projectSelected.emit(pid)
    
    @Slot(int)
    def deleteProject(self, project_id: int):
        """Delete a project with confirmation."""
        from annotation_engine.core.database import get_project, delete_project
        project = get_project(project_id)
        if not project:
            return
        
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Delete Project",
            f"Are you sure you want to delete '{project['name']}'?\n\n"
            f"This will permanently delete the project folder:\n{project['base_path']}\n\n"
            f"This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if delete_project(project_id):
                self.loadRecentProjects()
                QMessageBox.information(self, "Deleted", "Project deleted successfully.")
            else:
                QMessageBox.critical(self, "Error", "Failed to delete project.")
    
    @Slot()
    def openSettings(self):
        """Open settings dialog."""
        from annotation_engine.ui.dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec()
    
    @Slot()
    def quitApplication(self):
        """Quit the application."""
        QApplication.quit()
    
    def getSelectedProjectId(self) -> Optional[int]:
        """Return selected project ID."""
        return self.selected_project_id