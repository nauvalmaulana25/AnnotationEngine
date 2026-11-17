"""
AnnotationEngine Desktop - Sidebar Widget (Image Grid)
"""
import os
from pathlib import Path
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem, QLabel, QPushButton,
    QComboBox, QLineEdit, QToolBar, QMenu
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QSize, QRect, QModelIndex, QSortFilterProxyModel,
    QAbstractListModel, QMimeData
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QFont, QIcon, QCursor,
    QStandardItemModel, QStandardItem, QAction
)

from annotation_engine.config import SUPPORTED_IMAGE_FORMATS, COLORS


class ImageGridModel(QAbstractListModel):
    """Model for image grid with thumbnails."""
    
    def __init__(self, images: List[Dict] = None, parent=None):
        super().__init__(parent)
        self.images = images or []
        self.thumbnails = {}  # Cache for thumbnails
        self.thumbnail_size = QSize(200, 200)
    
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.images)
    
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.images):
            return None
        
        image = self.images[index.row()]
        
        if role == Qt.DisplayRole:
            return image['filename']
        
        elif role == Qt.DecorationRole:
            # Return thumbnail
            thumb = self.getThumbnail(image)
            if thumb:
                return QIcon(thumb)
            return QIcon()
        
        elif role == Qt.ToolTipRole:
            return f"{image['filename']}\n{image.get('width', '?')}x{image.get('height', '?')}"
        
        elif role == Qt.UserRole:
            return image
        
        elif role == Qt.CheckStateRole:
            return Qt.Checked if image.get('_selected', False) else Qt.Unchecked
        
        return None
    
    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if role == Qt.CheckStateRole and index.isValid():
            image = self.images[index.row()]
            image['_selected'] = (value == Qt.Checked)
            self.dataChanged.emit(index, index, [role])
            return True
        return False
    
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return super().flags(index) | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
    
    def getThumbnail(self, image: Dict) -> Optional[QPixmap]:
        """Get or create thumbnail for image."""
        image_id = image['id']
        if image_id in self.thumbnails:
            return self.thumbnails[image_id]
        
        # Generate thumbnail path
        project = get_project(image['project_id']) if 'project_id' in image else None
        if project:
            image_path = os.path.join(project['base_path'], image['relative_path'])
        else:
            return None
        
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                thumb = pixmap.scaled(
                    self.thumbnail_size, 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                self.thumbnails[image_id] = thumb
                return thumb
        
        return None
    
    def setImages(self, images: List[Dict]):
        """Update images list."""
        self.beginResetModel()
        self.images = images
        self.thumbnails.clear()
        self.endResetModel()
    
    def getImage(self, row: int) -> Optional[Dict]:
        """Get image data by row."""
        if 0 <= row < len(self.images):
            return self.images[row]
        return None


class ImageThumbnailDelegate(QStyledItemDelegate):
    """Custom delegate for rendering image thumbnails in grid view."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumb_size = 180
        self.padding = 8
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # Get image data
        image = index.data(Qt.UserRole)
        if not image:
            return
        
        rect = option.rect
        
        # Background
        if option.state & QStyleOptionViewItem.State_Selected:
            painter.fillRect(rect, QColor(COLORS['primary_100']))
            painter.setPen(QColor(COLORS['primary_500']))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        elif option.state & QStyleOptionViewItem.State_MouseOver:
            painter.fillRect(rect, QColor(COLORS['gray_100']))
        
        # Thumbnail area
        thumb_rect = QRect(
            rect.x() + self.padding,
            rect.y() + self.padding,
            self.thumb_size,
            self.thumb_size
        )
        
        # Draw thumbnail
        icon = index.data(Qt.DecorationRole)
        if icon:
            pixmap = icon.pixmap(QSize(self.thumb_size, self.thumb_size))
            painter.drawPixmap(thumb_rect, pixmap)
        else:
            # Placeholder
            painter.fillRect(thumb_rect, QColor(COLORS['gray_200']))
            painter.setPen(QColor(COLORS['gray_400']))
            painter.drawText(thumb_rect, Qt.AlignCenter, "No Preview")
        
        # Filename
        text_rect = QRect(
            rect.x() + self.padding,
            thumb_rect.bottom() + 4,
            self.thumb_size,
            40
        )
        painter.setPen(QColor(COLORS['gray_900']))
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.TextWordWrap, image['filename'])
        
        # Dimensions
        if image.get('width') and image.get('height'):
            dim_text = f"{image['width']}x{image['height']}"
            painter.setPen(QColor(COLORS['gray_500']))
            painter.drawText(text_rect.adjusted(0, 20, 0, 0), Qt.AlignHCenter, dim_text)
        
        # Split badge
        if image.get('split'):
            split_colors = {'train': COLORS['green_500'], 'val': COLORS['blue_500'], 'test': COLORS['purple_500']}
            color = split_colors.get(image['split'], COLORS['gray_500'])
            badge_rect = QRect(
                rect.right() - 60,
                rect.top() + 8,
                52, 20
            )
            painter.fillRect(badge_rect, QColor(color))
            painter.setPen(Qt.white)
            painter.drawText(badge_rect, Qt.AlignCenter, image['split'].upper())
        
        # Annotation indicator
        if image.get('has_annotation'):
            painter.setPen(QColor(COLORS['primary_500']))
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            painter.drawText(
                QRect(thumb_rect.x(), thumb_rect.y(), 20, 20),
                Qt.AlignCenter, "✓"
            )
    
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(self.thumb_size + self.padding * 2, self.thumb_size + self.padding * 2 + 60)


class ImageGridWidget(QWidget):
    """Sidebar widget with image grid/list view."""
    
    imageSelected = Signal(int)          # image_id
    imageDoubleClicked = Signal(int)     # image_id
    selectionChanged = Signal(list)      # list of selected image_ids
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.project_id: Optional[int] = None
        self.view_mode = "grid"  # "grid" or "list"
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        
        # View mode toggle
        self.grid_btn = QPushButton()
        self.grid_btn.setCheckable(True)
        self.grid_btn.setChecked(True)
        self.grid_btn.setToolTip("Grid View")
        self.grid_btn.setIcon(QIcon.fromTheme("view-grid"))
        self.grid_btn.clicked.connect(lambda: self.setViewMode("grid"))
        
        self.list_btn = QPushButton()
        self.list_btn.setCheckable(True)
        self.list_btn.setToolTip("List View")
        self.list_btn.setIcon(QIcon.fromTheme("view-list"))
        self.list_btn.clicked.connect(lambda: self.setViewMode("list"))
        
        header_layout.addWidget(QLabel("Images"))
        header_layout.addStretch()
        header_layout.addWidget(self.grid_btn)
        header_layout.addWidget(self.list_btn)
        
        layout.addWidget(header)
        
        # Filter/Search
        filter_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search images...")
        self.search_input.textChanged.connect(self.filterImages)
        filter_layout.addWidget(self.search_input)
        
        self.split_filter = QComboBox()
        self.split_filter.addItems(["All", "train", "val", "test"])
        self.split_filter.currentTextChanged.connect(self.filterImages)
        filter_layout.addWidget(self.split_filter)
        
        layout.addLayout(filter_layout)
        
        # Image list view
        self.list_view = QListView()
        self.list_view.setViewMode(QListView.IconMode)
        self.list_view.setMovement(QListView.Static)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setSpacing(8)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_view.setItemDelegate(ImageThumbnailDelegate())
        
        # Model
        self.model = ImageGridModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.list_view.setModel(self.proxy_model)
        
        # Connect signals
        self.list_view.clicked.connect(self.onItemClicked)
        self.list_view.doubleClicked.connect(self.onItemDoubleClicked)
        self.list_view.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        
        layout.addWidget(self.list_view)
    
    def setImages(self, images: List[Dict]):
        """Set images to display."""
        self.model.setImages(images)
        self.project_id = images[0]['project_id'] if images else None
    
    def clear(self):
        """Clear all images."""
        self.model.setImages([])
        self.project_id = None
    
    def setViewMode(self, mode: str):
        """Set view mode (grid or list)."""
        self.view_mode = mode
        self.grid_btn.setChecked(mode == "grid")
        self.list_btn.setChecked(mode == "list")
        
        if mode == "grid":
            self.list_view.setViewMode(QListView.IconMode)
            self.list_view.setFlow(QListView.LeftToRight)
            self.list_view.setWrapping(True)
        else:
            self.list_view.setViewMode(QListView.ListMode)
            self.list_view.setFlow(QListView.TopToBottom)
            self.list_view.setWrapping(False)
    
    def filterImages(self):
        """Filter images by search text and split."""
        search_text = self.search_input.text().lower()
        split_filter = self.split_filter.currentText()
        
        def filter_func(index):
            image = index.data(Qt.UserRole)
            if not image:
                return False
            
            if search_text and search_text not in image['filename'].lower():
                return False
            
            if split_filter != "All" and image.get('split') != split_filter.lower():
                return False
            
            return True
        
        self.proxy_model.setFilterFixedString(search_text)
        # Custom filtering would need a custom proxy model
    
    def onItemClicked(self, index: QModelIndex):
        """Handle single click."""
        proxy_index = self.proxy_model.mapToSource(index)
        image = self.model.getImage(proxy_index.row())
        if image:
            self.imageSelected.emit(image['id'])
    
    def onItemDoubleClicked(self, index: QModelIndex):
        """Handle double click."""
        proxy_index = self.proxy_model.mapToSource(index)
        image = self.model.getImage(proxy_index.row())
        if image:
            self.imageDoubleClicked.emit(image['id'])
    
    def onSelectionChanged(self):
        """Handle selection change."""
        selected = self.list_view.selectionModel().selectedRows()
        image_ids = []
        for idx in selected:
            proxy_idx = self.proxy_model.mapToSource(idx)
            image = self.model.getImage(proxy_idx.row())
            if image:
                image_ids.append(image['id'])
        self.selectionChanged.emit(image_ids)
    
    def getSelectedImageIds(self) -> List[int]:
        """Get currently selected image IDs."""
        selected = self.list_view.selectionModel().selectedRows()
        image_ids = []
        for idx in selected:
            proxy_idx = self.proxy_model.mapToSource(idx)
            image = self.model.getImage(proxy_idx.row())
            if image:
                image_ids.append(image['id'])
        return image_ids
    
    def setSelectedIndices(self, indices: List[int]):
        """Set selected indices."""
        self.list_view.selectionModel().clearSelection()
        for i, image in enumerate(self.model.images):
            if image['id'] in indices:
                proxy_idx = self.proxy_model.mapFromSource(self.model.index(i))
                self.list_view.selectionModel().select(
                    proxy_idx, 
                    self.list_view.selectionModel().Select | self.list_view.selectionModel().Rows
                )