"""
AnnotationEngine Desktop - Label List Widget
"""
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QLineEdit, QColorDialog, QMenu
)
from PySide6.QtCore import Signal, Slot, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush

from annotation_engine.config import COLORS


class LabelItemWidget(QWidget):
    """Widget for a single label in the list."""
    
    def __init__(self, label: str, color: str, visible: bool = True, parent=None):
        super().__init__(parent)
        
        self.label = label
        self.color = color
        self.visible = visible
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)
        
        # Visibility checkbox
        self.visible_cb = QPushButton()
        self.visible_cb.setCheckable(True)
        self.visible_cb.setChecked(visible)
        self.visible_cb.setFixedSize(20, 20)
        self.visible_cb.setStyleSheet(f"""
            QPushButton {{
                border: 2px solid {color};
                border-radius: 3px;
                background-color: {'white' if visible else 'transparent'};
            }}
            QPushButton:checked {{
                background-color: {color};
            }}
        """)
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
        
        # Label name
        self.label_text = QLabel(label)
        self.label_text.setStyleSheet("font-weight: 500;")
        layout.addWidget(self.label_text, 1)
        
        # Shape count
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(self.count_label)
    
    def onVisibilityChanged(self, checked: bool):
        """Handle visibility toggle."""
        self.visible = checked
        # Update style
        if checked:
            self.visible_cb.setStyleSheet(f"""
                QPushButton {{
                    border: 2px solid {self.color};
                    border-radius: 3px;
                    background-color: {self.color};
                }}
            """)
        else:
            self.visible_cb.setStyleSheet(f"""
                QPushButton {{
                    border: 2px solid {self.color};
                    border-radius: 3px;
                    background-color: transparent;
                }}
            """)
    
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
            if self.visible_cb.isChecked():
                self.visible_cb.setStyleSheet(f"""
                    QPushButton {{
                        border: 2px solid {self.color};
                        border-radius: 3px;
                        background-color: {self.color};
                    }}
                """)
    
    def setCount(self, count: int):
        """Update shape count."""
        self.count_label.setText(str(count))


class LabelListWidget(QWidget):
    """Widget for managing annotation labels."""
    
    labelSelected = Signal(str)
    labelVisibilityChanged = Signal(str, bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.labels: Dict[str, Dict] = {}  # label -> {color, visible, count}
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
        self.add_label_btn.clicked.connect(self.addLabel)
        header_layout.addWidget(self.add_label_btn)
        
        layout.addWidget(header)
        
        # Label list
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemClicked.connect(self.onItemClicked)
        layout.addWidget(self.list_widget, 1)
    
    def addLabel(self, label: str = None, color: str = None):
        """Add a new label to the list."""
        if label is None:
            label, ok = QInputDialog.getText(self, "New Label", "Label name:")
            if not ok or not label.strip():
                return
            label = label.strip()
        
        if label in self.labels:
            return
        
        if color is None:
            # Auto-assign color
            color = COLORS[len(self.labels) % len(COLORS)]
        
        self.labels[label] = {
            'color': color,
            'visible': True,
            'count': 0
        }
        
        self._addLabelToList(label, color, True)
    
    def _addLabelToList(self, label: str, color: str, visible: bool):
        """Add label widget to list."""
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 32))
        
        widget = LabelItemWidget(label, color, visible)
        widget.count_label.setText("0")
        
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)
    
    def setLabelCount(self, label: str, count: int):
        """Update shape count for label."""
        if label in self.labels:
            self.labels[label]['count'] = count
            
            # Update widget
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                widget = self.list_widget.itemWidget(item)
                if widget and widget.label == label:
                    widget.setCount(count)
                    break
    
    def setLabelVisibility(self, label: str, visible: bool):
        """Set label visibility."""
        if label in self.labels:
            self.labels[label]['visible'] = visible
            
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                widget = self.list_widget.itemWidget(item)
                if widget and widget.label == label:
                    widget.visible_cb.setChecked(visible)
                    break
    
    def onItemClicked(self, item: QListWidgetItem):
        """Handle label item click."""
        widget = self.list_widget.itemWidget(item)
        if widget:
            self.labelSelected.emit(widget.label)
    
    def clear(self):
        """Clear all labels."""
        self.labels.clear()
        self.list_widget.clear()