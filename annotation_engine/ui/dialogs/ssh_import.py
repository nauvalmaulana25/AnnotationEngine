"""
AnnotationEngine Desktop - SSH Import Dialog

Connects to a remote server over SSH/SFTP, lists its images, and creates a
local "remote project" whose images are fetched on demand. The remote
connection details are stored on the project row so later image fetches and
"Sync to Server" reuse them.
"""
import time
from pathlib import Path
from typing import List, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QSpinBox, QPushButton, QFileDialog, QCheckBox, QHBoxLayout,
    QMessageBox, QProgressBar, QApplication
)
from PySide6.QtCore import Qt

from annotation_engine.config import SSH_CACHE_DIR
from annotation_engine.core.database import add_image, create_remote_project
from annotation_engine.services.ssh_client import (
    SSHClient, SSHConnectionError, encode_secret,
)


def _safe_name(name: str) -> str:
    cleaned = "".join(
        c if (c.isalnum() or c in "-_.") else "_" for c in (name or "")
    ).strip("._")
    return cleaned or "project"


class SSHImportDialog(QDialog):
    """Create a remote project by importing an image listing over SSH."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_id = None
        self._images: List[Tuple[str, int]] = []

        self.setWindowTitle("Connect via SSH")
        self.setModal(True)
        self.resize(560, 560)
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)

        # Connection
        connection_group = QGroupBox("Connection")
        form = QFormLayout(connection_group)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("192.168.1.10 or hostname")
        form.addRow("Host:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        form.addRow("Port:", self.port_spin)

        self.user_edit = QLineEdit()
        form.addRow("Username:", self.user_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self.password_edit)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("Optional private key file")
        key_btn = QPushButton("Browse…")
        key_btn.clicked.connect(self.browseKey)
        key_row.addWidget(self.key_edit)
        key_row.addWidget(key_btn)
        form.addRow("Private key:", key_row)

        layout.addWidget(connection_group)

        # Remote images
        source_group = QGroupBox("Remote images")
        source_layout = QFormLayout(source_group)
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("/data/images")
        source_layout.addRow("Remote directory:", self.dir_edit)

        self.recursive_check = QCheckBox("Include subfolders")
        self.recursive_check.setChecked(True)
        source_layout.addRow(self.recursive_check)
        layout.addWidget(source_group)

        # Local project
        project_group = QGroupBox("Local project")
        project_layout = QFormLayout(project_group)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Project name")
        project_layout.addRow("Project name:", self.name_edit)
        layout.addWidget(project_group)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.testConnection)
        buttons.addWidget(self.test_btn)
        buttons.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        self.import_btn = QPushButton("Create Project && Import")
        self.import_btn.setDefault(True)
        self.import_btn.clicked.connect(self.doImport)
        buttons.addWidget(self.import_btn)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def browseKey(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Private Key")
        if path:
            self.key_edit.setText(path)

    def _make_client(self) -> SSHClient:
        return SSHClient(
            self.host_edit.text().strip(),
            self.port_spin.value(),
            self.user_edit.text().strip(),
            self.password_edit.text(),
            self.key_edit.text().strip(),
        )

    def _remote_dir(self) -> str:
        return self.dir_edit.text().strip()

    def _validate(self, require_name: bool) -> bool:
        if not self.host_edit.text().strip():
            QMessageBox.warning(self, "Missing", "Host is required.")
            return False
        if not self.user_edit.text().strip():
            QMessageBox.warning(self, "Missing", "Username is required.")
            return False
        if not self._remote_dir():
            QMessageBox.warning(self, "Missing", "Remote directory is required.")
            return False
        if require_name and not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing", "Project name is required.")
            return False
        return True

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def testConnection(self):
        if not self._validate(require_name=False):
            return
        self.status_label.setText("Connecting…")
        self.test_btn.setEnabled(False)
        QApplication.processEvents()
        client = self._make_client()
        try:
            client.connect()
            self._images = client.list_images(
                self._remote_dir(), self.recursive_check.isChecked()
            )
            self.status_label.setText(
                f"Connected — {len(self._images)} image(s) found."
            )
        except SSHConnectionError as exc:
            self.status_label.setText(f"Connection failed: {exc}")
        except Exception as exc:
            self.status_label.setText(f"Connection failed: {exc}")
        finally:
            client.close()
            self.test_btn.setEnabled(True)

    def doImport(self):
        if not self._validate(require_name=True):
            return
        self.import_btn.setEnabled(False)
        self.status_label.setText("Connecting…")
        QApplication.processEvents()
        client = self._make_client()
        try:
            client.connect()
            self.status_label.setText("Listing images…")
            QApplication.processEvents()
            images = client.list_images(
                self._remote_dir(), self.recursive_check.isChecked()
            )
            if not images:
                QMessageBox.warning(
                    self, "No Images",
                    "No supported images were found in that directory.",
                )
                return

            name = self.name_edit.text().strip()
            cache = SSH_CACHE_DIR / f"{_safe_name(name)}_{int(time.time())}"
            project_id = create_remote_project(
                name=name,
                cache_path=cache,
                remote_host=self.host_edit.text().strip(),
                remote_port=self.port_spin.value(),
                remote_user=self.user_edit.text().strip(),
                remote_dir=self._remote_dir(),
                remote_secret=encode_secret(
                    self.password_edit.text(), self.key_edit.text().strip()
                ),
            )
            for relative_path, size in images:
                add_image(
                    project_id,
                    Path(relative_path).name,
                    relative_path,
                    None, None, size, None,
                )
            self.project_id = project_id
            QMessageBox.information(
                self, "Import Complete",
                f"Created project '{name}' with {len(images)} image(s).\n"
                "Images are fetched on demand as you open them.",
            )
            self.accept()
        except SSHConnectionError as exc:
            QMessageBox.critical(self, "Connection Failed", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))
        finally:
            client.close()
            self.import_btn.setEnabled(True)
