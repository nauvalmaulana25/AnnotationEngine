"""
AnnotationEngine Desktop - Label List Widget
"""
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QLineEdit, QColorDialog, QMenu, QInputDialog
)
from PySide6.QtCore import Signal, Slot, Qt, QSize, QSignalBlocker, QPoint, QEvent
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush
from PySide6.QtWidgets import QGraphicsOpacityEffect

from annotation_engine.config import ANNOTATION_COLORS, ICONS_DIR


class LabelItemWidget(QWidget):
    """Widget for a single label in the list."""

    colorChanged = Signal(str, str)
    visibilityChanged = Signal(str, bool)
    contextMenuRequested = Signal(str, QPoint)

    def __init__(self, label: str, color: str, visible: bool = True, parent=None):
        super().__init__(parent)
        
        self.label = label
        self.color = color
        self.visible = visible
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)
        
        # Visibility toggle (eye icon)
        self.visible_cb = QPushButton()
        self.visible_cb.setCheckable(True)
        self.visible_cb.setFlat(True)
        self.visible_cb.setFixedSize(22, 22)
        self.visible_cb.setIconSize(QSize(16, 16))
        # Override the global flat-button padding so the icon is not clipped.
        self.visible_cb.setStyleSheet(
            "QPushButton { padding: 0; border: none; background: transparent;"
            " min-height: 0; min-width: 0; }"
            "QPushButton:hover { background-color: rgba(127, 127, 127, 0.18);"
            " border-radius: 4px; }"
        )
        self.visible_cb.setChecked(visible)
        self._updateVisibilityIcon()
        self.visible_cb.toggled.connect(self.onVisibilityChanged)
        layout.addWidget(self.visible_cb)
        
        # Color indicator
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(20, 20)
        self.color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: 1px solid #d1d5db;
                border-radius: 3px;
            }}
        """)
        self.color_btn.clicked.connect(self.onColorClicked)
        layout.addWidget(self.color_btn)
        
        # Label name (wrap instead of hard-clipping long names)
        self.label_text = QLabel(label)
        self.label_text.setTextFormat(Qt.TextFormat.PlainText)
        self.label_text.setWordWrap(True)
        self.label_text.setStyleSheet("font-weight: 500;")
        self.label_text.setToolTip(label)
        self.label_text.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.label_text, 1)
        
        # Shape count
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.count_label)

        # Right-clicking any child (including the buttons, which swallow
        # context menu events) still opens the row's context menu.
        for child in (
            self.visible_cb, self.color_btn, self.label_text, self.count_label
        ):
            child.installEventFilter(self)

        # Dimming (labels absent from the current image) via opacity.
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ContextMenu:
            self.contextMenuRequested.emit(self.label, event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def contextMenuEvent(self, event):
        self.contextMenuRequested.emit(self.label, event.globalPos())
        event.accept()
    
    def _updateVisibilityIcon(self):
        """Swap the eye icon to match the current visibility."""
        icon_name = "eye.svg" if self.visible else "eye-off.svg"
        icon_path = ICONS_DIR / icon_name
        self.visible_cb.setIcon(
            QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        )
        self.visible_cb.setToolTip(
            "Hide label shapes" if self.visible else "Show label shapes"
        )

    def onVisibilityChanged(self, checked: bool):
        """Handle visibility toggle."""
        self.visible = checked
        self._updateVisibilityIcon()
        self.visibilityChanged.emit(self.label, checked)

    def onColorClicked(self):
        """Handle color change."""
        color = QColorDialog.getColor(QColor(self.color), self, "Choose Label Color")
        if color.isValid():
            self.color = color.name()
            self.color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.color};
                    border: 1px solid #d1d5db;
                    border-radius: 3px;
                }}
            """)
            self.colorChanged.emit(self.label, self.color)
    
    def setCount(self, count: int):
        """Update shape count and dim the row when the label is absent."""
        self.count_label.setText(str(count))
        self.setDimmed(count == 0)

    def setDimmed(self, dimmed: bool):
        """Dim the row when its label has no shapes in the current image."""
        self._opacity.setOpacity(0.4 if dimmed else 1.0)


class LabelListWidget(QWidget):
    """Widget for managing annotation labels."""
    
    labelSelected = Signal(str)
    labelVisibilityChanged = Signal(str, bool)
    labelColorChanged = Signal(str, str)
    selectShapesRequested = Signal(str)
    deleteShapesRequested = Signal(str)
    removeLabelRequested = Signal(str)
    renameLabelRequested = Signal(str)
    labelsChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.labels: Dict[str, Dict] = {}  # label -> {color, visible, count}
        self._color_memory: Dict[str, str] = {}  # survives removal (undo, rename)
        self._loading = False
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_layout.addWidget(QLabel("Labels"))
        header_layout.addStretch()
        
        self.add_label_btn = QPushButton("+ Add Label")
        # clicked(bool) would otherwise pass its checked flag as the label.
        self.add_label_btn.clicked.connect(lambda checked=False: self.addLabel())
        header_layout.addWidget(self.add_label_btn)
        
        layout.addWidget(header)
        
        # Label list
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setWordWrap(True)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._onContextMenu)
        self.list_widget.itemClicked.connect(self.onItemClicked)
        layout.addWidget(self.list_widget, 1)
    
    def addLabel(
        self, label: str = None, color: str = None, visible: bool = True
    ):
        """Add a new label to the list."""
        # Defensive: some Qt signals pass a bool as the first argument.
        if label is not None and not isinstance(label, str):
            label = None
        if label is None:
            label, ok = QInputDialog.getText(self, "New Label", "Label name:")
            if not ok:
                return None
            label = label.strip()
        else:
            label = label.strip()
        if not label:
            return None
        
        if label in self.labels:
            return label
        
        if color is None:
            # A label that comes back after a rename or undo keeps its color.
            color = self._color_memory.get(label) or ANNOTATION_COLORS[
                len(self.labels) % len(ANNOTATION_COLORS)
            ]
        self._color_memory[label] = color
        
        self.labels[label] = {
            'color': color,
            'visible': bool(visible),
            'count': 0
        }
        
        self._addLabelToList(label, color, bool(visible))
        if not self._loading:
            self.labelsChanged.emit()
        return label
    
    def _addLabelToList(self, label: str, color: str, visible: bool):
        """Add label widget to list."""
        label = str(label)
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 44))
        item.setData(Qt.UserRole, label)
        item.setToolTip(label)
        
        widget = LabelItemWidget(label, color, visible)
        widget.setCount(0)
        widget.visibilityChanged.connect(self._onLabelVisibilityChanged)
        widget.colorChanged.connect(self._onLabelColorChanged)
        widget.contextMenuRequested.connect(self.showLabelMenu)
        
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)
    
    def _onLabelColorChanged(self, label: str, color: str):
        if label in self.labels:
            self.labels[label]['color'] = color
        self._color_memory[label] = color
        self.labelColorChanged.emit(label, color)
        if not self._loading:
            self.labelsChanged.emit()

    def _onLabelVisibilityChanged(self, label: str, visible: bool):
        if label in self.labels:
            self.labels[label]['visible'] = bool(visible)
        self.labelVisibilityChanged.emit(label, visible)
        if not self._loading:
            self.labelsChanged.emit()

    def setLabels(self, labels: List[dict]):
        """Bulk load persisted label metadata."""
        self._loading = True
        try:
            self.clear()
            for data in labels or []:
                name = (data.get('name') or '').strip()
                if not name:
                    continue
                self.addLabel(
                    name,
                    color=data.get('color'),
                    visible=data.get('visible', True),
                )
        finally:
            self._loading = False

    def getLabelState(self) -> List[dict]:
        """Return label metadata for persistence."""
        return [
            {
                'name': label,
                'color': data.get('color', ''),
                'visible': bool(data.get('visible', True)),
            }
            for label, data in self.labels.items()
        ]

    def renameLabel(self, old: str, new: str) -> Optional[str]:
        """Rename or merge a label; returns the resulting label color."""
        if old not in self.labels or old == new:
            return self.labels.get(old, {}).get('color')

        old_data = self.labels.pop(old)
        if new in self.labels:
            color = self.labels[new].get('color', old_data.get('color', ''))
            self._color_memory[old] = old_data.get('color', '')
            self._removeRow(old)
            if not self._loading:
                self.labelsChanged.emit()
            return color

        self.labels[new] = old_data
        self._color_memory[new] = old_data.get('color', '')
        item = self._findItem(old)
        if item is not None:
            item.setData(Qt.UserRole, new)
            item.setToolTip(new)
            widget = self.list_widget.itemWidget(item)
            if widget is not None:
                widget.label = new
                widget.label_text.setText(new)
                widget.label_text.setToolTip(new)
        if not self._loading:
            self.labelsChanged.emit()
        return old_data.get('color', '')
    
    def syncFromShapes(self, shapes: List[dict]):
        """Add labels found in shapes and refresh per-label counts."""
        counts: Dict[str, int] = {}
        for shape in shapes or []:
            label = shape.get('label') or ''
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
            if label not in self.labels:
                self.addLabel(label)
        
        for label in self.labels:
            self.setLabelCount(label, counts.get(label, 0))
    
    def setSelectedLabels(self, labels: List[str]):
        """Highlight the list rows for the given labels."""
        labels = set(labels or [])
        self.list_widget.clearSelection()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.UserRole) in labels:
                item.setSelected(True)
    
    def getLabels(self) -> List[str]:
        """Return all known label names."""
        return list(self.labels.keys())
    
    def getLabelColors(self) -> Dict[str, str]:
        """Return a label -> color mapping for the canvas."""
        return {label: data.get('color', '') for label, data in self.labels.items()}
    
    def labelColor(self, label: str) -> str:
        """Return the configured color for a label."""
        return self.labels.get(label, {}).get('color', '')
    
    def currentLabel(self) -> str:
        """Return the currently highlighted label, if any."""
        items = self.list_widget.selectedItems()
        if not items:
            return ""
        return items[0].data(Qt.UserRole) or ""
    
    def setLabelCount(self, label: str, count: int):
        """Update shape count for label."""
        if label not in self.labels:
            return
        self.labels[label]['count'] = count
        item = self._findItem(label)
        widget = self.list_widget.itemWidget(item) if item else None
        if widget is not None:
            widget.setCount(count)
    
    def setLabelVisibility(self, label: str, visible: bool):
        """Reflect an externally applied visibility state in the row UI."""
        if label not in self.labels:
            return
        self.labels[label]['visible'] = bool(visible)

        item = self._findItem(label)
        widget = self.list_widget.itemWidget(item) if item else None
        if widget is not None:
            blocker = QSignalBlocker(widget.visible_cb)
            widget.visible_cb.setChecked(bool(visible))
            del blocker
            widget.visible = bool(visible)
            widget._updateVisibilityIcon()
    
    def onItemClicked(self, item: QListWidgetItem):
        """Handle label item click."""
        widget = self.list_widget.itemWidget(item)
        if widget:
            self.labelSelected.emit(widget.label)

    def _onContextMenu(self, pos):
        """Show actions for the label under the cursor (list background)."""
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        label = item.data(Qt.UserRole)
        if not label:
            return
        self.showLabelMenu(label, self.list_widget.viewport().mapToGlobal(pos))

    def showLabelMenu(self, label: str, global_pos: QPoint):
        """Show the label context menu at a global position."""
        if not label:
            return
        menu = QMenu(self)
        select_action = menu.addAction("Select Shapes")
        delete_action = menu.addAction("Delete Shapes")
        menu.addSeparator()
        rename_action = menu.addAction("Rename Label...")
        remove_action = menu.addAction("Remove Label")

        chosen = menu.exec(global_pos)
        if chosen is select_action:
            self.selectShapesRequested.emit(label)
        elif chosen is delete_action:
            self.deleteShapesRequested.emit(label)
        elif chosen is rename_action:
            self.renameLabelRequested.emit(label)
        elif chosen is remove_action:
            self.removeLabelRequested.emit(label)

    def labelCount(self, label: str) -> int:
        """Return the recorded shape count for a label."""
        return int(self.labels.get(label, {}).get('count', 0))

    def _findItem(self, label: str) -> Optional[QListWidgetItem]:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.UserRole) == label:
                return item
        return None

    def _removeRow(self, label: str) -> None:
        for i in range(self.list_widget.count() - 1, -1, -1):
            item = self.list_widget.item(i)
            if item and item.data(Qt.UserRole) == label:
                self.list_widget.takeItem(i)

    def removeLabel(self, label: str) -> bool:
        """Remove a label row and its stored metadata."""
        if label not in self.labels:
            return False
        del self.labels[label]
        self._removeRow(label)
        if not self._loading:
            self.labelsChanged.emit()
        return True
    
    def clear(self):
        """Clear all labels (and the remembered colors of another project)."""
        self.labels.clear()
        self._color_memory.clear()
        self.list_widget.clear()