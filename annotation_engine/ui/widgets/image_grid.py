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
from PySide6.QtWidgets import QStyle

from annotation_engine.config import SUPPORTED_IMAGE_FORMATS, COLORS, ICONS_DIR
from annotation_engine.core.database import get_project


class ImageGridModel(QAbstractListModel):
    """Model for image grid with thumbnails."""
    
    def __init__(self, images: List[Dict] = None, parent=None):
        super().__init__(parent)
        self.images = images or []
        self.thumbnails = {}  # Cache for thumbnails
        self.thumbnail_size = QSize(180, 180)
    
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.images)
    
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.images):
            return None
        
        image = self.images[index.row()]
        
        if role == Qt.DisplayRole:
            return image['filename']
        
        elif role == Qt.DecorationRole:
            # Return the cached thumbnail pixmap directly (no QIcon wrapping).
            return self.getThumbnail(image)
        
        elif role == Qt.ToolTipRole:
            return f"{image['filename']}\n{image.get('width', '?')}x{image.get('height', '?')}"
        
        elif role == Qt.UserRole:
            return image
        
        elif role == Qt.UserRole + 1:
            # 1-based index number (position in the ordered image list).
            return index.row() + 1
        
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
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor(COLORS['primary_100']))
            painter.setPen(QColor(COLORS['primary_500']))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(COLORS['gray_100']))
        
        # Thumbnail area
        thumb_rect = QRect(
            rect.x() + self.padding,
            rect.y() + self.padding,
            self.thumb_size,
            self.thumb_size
        )
        
        # Draw thumbnail at its native (cached) size, centered, so painting
        # never re-scales the pixmap — this is the main grid-scroll cost.
        pixmap = index.data(Qt.DecorationRole)
        if pixmap and not pixmap.isNull():
            x = thumb_rect.x() + (thumb_rect.width() - pixmap.width()) // 2
            y = thumb_rect.y() + (thumb_rect.height() - pixmap.height()) // 2
            painter.drawPixmap(x, y, pixmap)
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
        
        # Index badge (top-left, mirroring the split badge top-right)
        number = index.data(Qt.UserRole + 1)
        if number is not None:
            index_badge = QRect(
                rect.x() + self.padding,
                rect.y() + self.padding,
                28, 20
            )
            painter.fillRect(index_badge, QColor(COLORS['gray_600']))
            painter.setPen(Qt.white)
            painter.drawText(index_badge, Qt.AlignCenter, str(number))
        
        # Annotation indicator (bottom-right of the thumbnail)
        if image.get('has_annotation'):
            painter.setPen(QColor(COLORS['primary_500']))
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            painter.drawText(
                QRect(thumb_rect.right() - 20, thumb_rect.bottom() - 20, 20, 20),
                Qt.AlignCenter, "✓"
            )
    
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(self.thumb_size + self.padding * 2, self.thumb_size + self.padding * 2 + 60)


class ImageListDelegate(QStyledItemDelegate):
    """Compact text-only delegate for the list view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row_height = 26
        self.padding = 6

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        image = index.data(Qt.UserRole)
        if not image:
            return

        rect = option.rect
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor(COLORS['primary_100']))
            painter.setPen(QColor(COLORS['primary_500']))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(COLORS['gray_100']))

        number = index.data(Qt.UserRole + 1)
        text = f"{number}. {image['filename']}"
        painter.setPen(QColor(COLORS['gray_900']))
        text_rect = QRect(
            rect.x() + self.padding,
            rect.y(),
            rect.width() - self.padding * 2,
            self.row_height,
        )
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, self.row_height)


class ImageFilterProxyModel(QSortFilterProxyModel):
    """Filter by filename, 1-based index number, and split."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search = ""
        self._split = "All"

    def setSearch(self, text: str):
        self._search = (text or "").strip().lower()
        self.invalidateFilter()

    def setSplit(self, split: str):
        self._split = split or "All"
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        image = model.data(index, Qt.UserRole)
        if not image:
            return False

        if self._split != "All" and image.get('split') != self._split.lower():
            return False

        if self._search:
            filename = (image.get('filename') or "").lower()
            if self._search in filename:
                return True
            # A numeric query matches the 1-based index number.
            if self._search.isdigit() and self._search == str(source_row + 1):
                return True
            return False

        return True


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
        grid_icon = ICONS_DIR / "grid.svg"
        if grid_icon.exists():
            self.grid_btn.setIcon(QIcon(str(grid_icon)))
        self.grid_btn.clicked.connect(lambda: self.setViewMode("grid"))
        
        self.list_btn = QPushButton()
        self.list_btn.setCheckable(True)
        self.list_btn.setToolTip("List View")
        list_icon = ICONS_DIR / "list.svg"
        if list_icon.exists():
            self.list_btn.setIcon(QIcon(str(list_icon)))
        self.list_btn.clicked.connect(lambda: self.setViewMode("list"))
        
        header_layout.addWidget(QLabel("Images"))
        header_layout.addStretch()
        header_layout.addWidget(self.grid_btn)
        header_layout.addWidget(self.list_btn)
        
        layout.addWidget(header)
        
        # Filter/Search
        filter_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or index...")
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
        self.list_view.setLayoutMode(QListView.Batched)
        # ScrollPerPixel keeps a stable pixel-based wheel step after the
        # grid <-> list delegate swap. ScrollPerItem collapses singleStep to 1
        # when uniformItemSizes is re-applied, making wheel scrolling crawl.
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.grid_delegate = ImageThumbnailDelegate()
        self.list_delegate = ImageListDelegate()
        self.list_view.setItemDelegate(self.grid_delegate)
        
        # Model
        self.model = ImageGridModel()
        self.proxy_model = ImageFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
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
            self.list_view.setSpacing(8)
            self.list_view.setUniformItemSizes(True)
            self.list_view.setItemDelegate(self.grid_delegate)
        else:
            self.list_view.setViewMode(QListView.ListMode)
            self.list_view.setFlow(QListView.TopToBottom)
            self.list_view.setWrapping(False)
            self.list_view.setSpacing(2)
            self.list_view.setUniformItemSizes(True)
            self.list_view.setItemDelegate(self.list_delegate)

    def filterImages(self):
        """Filter images by search text (name or index) and split."""
        self.proxy_model.setSearch(self.search_input.text())
        self.proxy_model.setSplit(self.split_filter.currentText())
    
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