"""
AnnotationEngine Desktop - Settings Dialog
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QCheckBox,
    QTabWidget, QWidget, QHBoxLayout, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt

from PySide6.QtCore import QSettings

from annotation_engine.core.database import (
    clean_database, get_setting, set_setting,
)
from annotation_engine.utils.encryption import EncryptionManager


class SettingsDialog(QDialog):
    """Settings dialog."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(500, 400)
        
        self.encryption = EncryptionManager()
        self.setupUI()
        self.loadSettings()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        tabs = QTabWidget()
        
        # General tab
        general = QWidget()
        general_layout = QFormLayout(general)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        general_layout.addRow("Theme:", self.theme_combo)
        
        self.auto_save = QSpinBox()
        self.auto_save.setRange(0, 300)
        self.auto_save.setValue(30)
        self.auto_save.setSuffix(" seconds (0 = disabled)")
        general_layout.addRow("Auto-save interval:", self.auto_save)
        
        tabs.addTab(general, "General")
        
        # API Keys tab
        api = QWidget()
        api_layout = QFormLayout(api)
        
        self.hf_api_key = QLineEdit()
        self.hf_api_key.setEchoMode(QLineEdit.Password)
        self.hf_api_key.setPlaceholderText("Enter Hugging Face API key")
        api_layout.addRow("Hugging Face API Key:", self.hf_api_key)
        
        self.show_key = QCheckBox("Show key")
        self.show_key.toggled.connect(lambda checked: self.hf_api_key.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        ))
        api_layout.addRow(self.show_key)
        
        tabs.addTab(api, "API Keys")
        
        # Advanced tab
        advanced = QWidget()
        advanced_layout = QFormLayout(advanced)
        
        self.models_dir = QLineEdit()
        self.models_dir.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.models_dir)
        dir_layout.addWidget(browse_btn)
        advanced_layout.addRow("Models Directory:", dir_layout)
        
        # Danger zone - Clean Database
        danger_group = QWidget()
        danger_layout = QVBoxLayout(danger_group)
        danger_layout.setContentsMargins(0, 0, 0, 0)
        danger_layout.setSpacing(8)
        
        danger_label = QLabel("⚠️ Danger Zone")
        danger_label.setStyleSheet("color: #dc2626; font-weight: 600; font-size: 13px;")
        danger_layout.addWidget(danger_label)
        
        clean_desc = QLabel("This will permanently delete ALL projects, their folders, and reset the database to empty state. This action cannot be undone.")
        clean_desc.setWordWrap(True)
        clean_desc.setStyleSheet("color: #6b7280; font-size: 12px;")
        danger_layout.addWidget(clean_desc)
        
        self.clean_db_btn = QPushButton("Clean Database (Reset to Empty)")
        self.clean_db_btn.setStyleSheet("""
            QPushButton {
                background-color: #fef2f2;
                color: #dc2626;
                border: 1px solid #fecaca;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #fee2e2;
                border-color: #fca5a5;
            }
            QPushButton:pressed {
                background-color: #fecaca;
            }
        """)
        self.clean_db_btn.clicked.connect(self.cleanDatabase)
        danger_layout.addWidget(self.clean_db_btn)
        
        advanced_layout.addRow(danger_group)
        
        tabs.addTab(advanced, "Advanced")
        
        layout.addWidget(tabs)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.saveSettings)
        buttons.addWidget(save_btn)
        
        layout.addLayout(buttons)
    
    def loadSettings(self):
        settings = QSettings()
        self.theme_combo.setCurrentText(settings.value("theme", "Light"))
        self.auto_save.setValue(settings.value("auto_save", 30, type=int))
        
        # Models directory
        from annotation_engine.config import MODELS_DIR
        self.models_dir.setText(str(MODELS_DIR))
        
        # Hugging Face API key (stored encrypted)
        self.hf_api_key.setText(
            self.encryption.decrypt(get_setting('hf_api_key_encrypted', ''))
        )
    
    def saveSettings(self):
        settings = QSettings()
        settings.setValue("theme", self.theme_combo.currentText().lower())
        settings.setValue("auto_save", self.auto_save.value())
        
        # Hugging Face API key (stored encrypted)
        key = self.hf_api_key.text().strip()
        set_setting(
            'hf_api_key_encrypted',
            self.encryption.encrypt(key) if key else '',
        )
        self.accept()
    
    def cleanDatabase(self):
        """Clean the entire database with confirmation."""
        reply = QMessageBox.question(
            self, "⚠️ Clean Database",
            "This will PERMANENTLY DELETE:\n\n"
            "• ALL projects\n"
            "• ALL project folders on disk\n"
            "• ALL images, annotations, and jobs\n"
            "• Recent projects history\n\n"
            "The database will be reset to empty state (AUTOINCREMENT reset to 1).\n\n"
            "THIS ACTION CANNOT BE UNDONE.\n\n"
            "Are you absolutely sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Double confirmation
            reply2 = QMessageBox.question(
                self, "Final Confirmation",
                "This is your LAST CHANCE to cancel.\n\n"
                "Type 'DELETE' in the text field below to confirm:",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply2 == QMessageBox.Yes:
                # Show text input for final confirmation
                from PySide6.QtWidgets import QInputDialog
                text, ok = QInputDialog.getText(
                    self, "Final Confirmation",
                    "Type 'DELETE' to confirm:",
                    text=""
                )
                
                if ok and text == "DELETE":
                    try:
                        from annotation_engine.core.database import clean_database
                        clean_database()
                        QMessageBox.information(self, "Done", "Database cleaned successfully. AUTOINCREMENT reset to 1.")
                        self.accept()
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to clean database: {e}")