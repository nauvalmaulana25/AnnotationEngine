"""
AnnotationEngine Desktop - Rename Label Dialog
"""
from typing import List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QComboBox,
    QDialogButtonBox, QMessageBox, QWidget
)


class RenameLabelDialog(QDialog):
    """Dialog for renaming a label, optionally across the whole project."""

    def __init__(
        self,
        parent=None,
        old_label: str = "",
        existing_labels: List[str] = None,
        allow_scope: bool = True,
        has_current_image: bool = True,
        title: str = "Rename Label",
    ):
        super().__init__(parent)

        self.old_label = old_label
        self.existing_labels = set(existing_labels or [])
        self.allow_scope = allow_scope

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel(f"Rename label '<b>{old_label}</b>' to:"))

        self.name_edit = QLineEdit(old_label)
        self.name_edit.selectAll()
        self.name_edit.textChanged.connect(self._updateHint)
        layout.addWidget(self.name_edit)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self.hint_label)

        self.scope_widget = QWidget()
        scope_layout = QVBoxLayout(self.scope_widget)
        scope_layout.setContentsMargins(0, 6, 0, 0)
        scope_layout.setSpacing(4)
        scope_layout.addWidget(QLabel("Apply to:"))
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("All images in this project", "project")
        if has_current_image:
            self.scope_combo.addItem("Current image only", "image")
        scope_layout.addWidget(self.scope_combo)
        self.scope_widget.setVisible(allow_scope)
        layout.addWidget(self.scope_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._updateHint(self.name_edit.text())
        self.name_edit.setFocus()

    def _updateHint(self, text: str):
        name = (text or "").strip()
        if not name:
            self.hint_label.setText("Label name cannot be empty.")
        elif name == self.old_label:
            self.hint_label.setText("")
        elif name in self.existing_labels:
            self.hint_label.setText(
                "This label already exists; shapes will be merged into it "
                "and its color will be kept."
            )
        else:
            self.hint_label.setText("")

    def _accept(self):
        if not self.newLabel():
            QMessageBox.warning(self, "Invalid Label", "Label name cannot be empty.")
            return
        self.accept()

    def newLabel(self) -> str:
        return (self.name_edit.text() or "").strip()

    def scope(self) -> str:
        if not self.allow_scope:
            return "image"
        return self.scope_combo.currentData() or "project"
