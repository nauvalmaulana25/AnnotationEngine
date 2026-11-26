"""
AnnotationEngine Desktop - Sidebar Widget (Image Grid)
"""
import os
import math
from pathlib import Path
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem, QLabel, QPushButton,
    QComboBox, QLineEdit, QToolBar, QMenu
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QSize, QRect, QModelIndex, QSortFilterProxyModel,
    QAbstractListModel, QMimeData, QPoint
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QFont, QIcon, QCursor,
    QStandardItemModel, QStandardItem, QAction, QPen, QPolygon
)
from PySide6.QtWidgets import QStyle

from annotation_engine.config import SUPPORTED_IMAGE_FORMATS, COLORS, ICONS_DIR
from annotation_engine.core.database import get_project
from annotation_engine.ui.colors import resolve_label_color


class ImageGridModel(QAbstractListModel):
    """Model for image grid with thumbnails."""
    
    def __init__(self, images: List[Dict] = None, parent=None):
        super().__init__(parent)
        self.images = images or []
        self.thumbnails = {}  # Cache for base thumbnails (no overlays)
        self.overlays = {}    # Cache for overlay-composited thumbnails
        self.thumbnail_size = QSize(180, 180)
        # Label overlay state, fed by the main window.
        self.annotations: Dict[int, List[dict]] = {}
        self.label_colors: Dict[str, str] = {}
        self.label_visibility: Dict[str, bool] = {}
        self.show_overlays: bool = True
        # Image the project should reopen on; marked in the delegates.
        self.last_seen_id: Optional[int] = None
        # Optional callback(image) -> local path, used to fetch remote (SSH)
        # images on demand when the local cache file is missing.
        self.image_fetcher = None
        # Optional callback(image) -> bool, used to enqueue a background fetch
        # so painting never blocks on network I/O.
        self.prefetch_request = None
    
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
            if self.show_overlays:
                return self.getOverlayThumbnail(image)
            return self.getThumbnail(image)
        
        elif role == Qt.ToolTipRole:
            return f"{image['filename']}\n{image.get('width', '?')}x{image.get('height', '?')}"
        
        elif role == Qt.UserRole:
            return image
        
        elif role == Qt.UserRole + 1:
            # 1-based index number (position in the ordered image list).
            return index.row() + 1
        
        elif role == Qt.UserRole + 2:
            # Whether this is the image the project last opened on.
            return self.last_seen_id is not None and image.get('id') == self.last_seen_id
        
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
    
    def setImages(self, images: List[Dict]):
        """Update images list."""
        self.beginResetModel()
        self.images = images
        self.thumbnails.clear()
        self.overlays.clear()
        self.endResetModel()

    def setAnnotationData(
        self,
        annotations: Optional[Dict[int, List[dict]]] = None,
        label_colors: Optional[Dict[str, str]] = None,
        label_visibility: Optional[Dict[str, bool]] = None,
    ):
        """Feed annotation shapes and label metadata for overlay rendering."""
        if annotations is not None:
            self.annotations = annotations
        if label_colors is not None:
            self.label_colors = label_colors
        if label_visibility is not None:
            self.label_visibility = label_visibility
        self.overlays.clear()

    def setShowOverlays(self, show: bool):
        """Toggle label overlays on/off and refresh the view."""
        if show == self.show_overlays:
            return
        self.show_overlays = show
        # Only the DecorationRole thumbnails changed — signal a data change,
        # not a layout reset (layoutChanged mid-event crashes the view).
        if self.images:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.images) - 1, 0),
                [Qt.DecorationRole],
            )

    def setLastSeen(self, image_id: Optional[int]):
        """Mark which image the project should reopen on."""
        if self.last_seen_id == image_id:
            return
        self.last_seen_id = image_id
        if self.images:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.images) - 1, 0),
                [Qt.UserRole + 2],
            )

    def invalidateOverlay(self, image_id: int):
        """Drop a single image's cached overlay so it is recomposed next paint."""
        self.overlays.pop(image_id, None)

    def invalidateThumbnail(self, image_id: int):
        """Drop a single image's cached thumbnail (e.g. after a remote fetch)."""
        self.thumbnails.pop(image_id, None)
        self.overlays.pop(image_id, None)

    def getThumbnail(self, image: Dict) -> Optional[QPixmap]:
        """Get or create the base (unannotated) thumbnail for an image."""
        image_id = image['id']
        if image_id in self.thumbnails:
            return self.thumbnails[image_id]
        
        # Generate thumbnail path
        project = get_project(image['project_id']) if 'project_id' in image else None
        if project:
            image_path = os.path.join(project['base_path'], image['relative_path'])
        else:
            return None
        
        if not os.path.exists(image_path):
            # Never fetch inside paintEvent: a network round-trip per visible
            # tile would freeze the UI. Enqueue a background fetch instead and
            # let the delegate show its placeholder until it lands.
            if self.prefetch_request is not None:
                try:
                    self.prefetch_request(image)
                except Exception:
                    pass
                return None
            # No prefetcher configured: fall back to the blocking fetcher.
            if self.image_fetcher is not None:
                try:
                    fetched = self.image_fetcher(image)
                except Exception:
                    fetched = None
                if fetched:
                    image_path = fetched
        
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

    def setImageFetcher(self, fetcher):
        """Set a callback(image) -> local path for on-demand (SSH) images."""
        self.image_fetcher = fetcher

    def setPrefetchRequest(self, request):
        """Set a callback(image) -> bool that enqueues a background fetch."""
        self.prefetch_request = request

    def getOverlayThumbnail(self, image: Dict) -> Optional[QPixmap]:
        """Return the thumbnail with saved annotation shapes drawn on top."""
        image_id = image['id']
        if image_id in self.overlays:
            return self.overlays[image_id]

        base = self.getThumbnail(image)
        if base is None:
            return None

        shapes = self.annotations.get(image_id) or []
        composed = self._composeOverlay(base, shapes, image)
        self.overlays[image_id] = composed
        return composed

    def _composeOverlay(self, base: QPixmap, shapes: List[dict], image: Dict) -> QPixmap:
        """Paint annotation shapes onto a copy of the base thumbnail."""
        if not shapes:
            return base

        composed = QPixmap(base)
        painter = QPainter(composed)
        painter.setRenderHint(QPainter.Antialiasing)

        img_w = image.get('width') or 1
        img_h = image.get('height') or 1
        sx = base.width() / img_w
        sy = base.height() / img_h

        for shape in shapes:
            label = shape.get('label') or ''
            if label and self.label_visibility.get(label) is False:
                continue
            color = resolve_label_color(label, self.label_colors)

            shape_type = shape.get('shape_type') or 'polygon'
            points = shape.get('points') or []
            pts = []
            for p in points:
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    continue
                x = self._scaledCoord(p[0], sx)
                y = self._scaledCoord(p[1], sy)
                if x is None or y is None:
                    continue
                pts.append(QPoint(int(x), int(y)))
            if not pts:
                continue

            if shape_type == 'mask':
                self._paintMaskShape(painter, color, shape, img_w, img_h, sx, sy)
                continue

            fill = QColor(color)
            fill.setAlpha(60)
            pen = QPen(QColor(color))
            pen.setWidth(max(1, round(1.5 * sx)))
            painter.setPen(pen)

            if shape_type == 'point':
                # A plain 2px dot is nearly invisible at thumbnail scale; draw a
                # small filled dot with a contrasting outline instead.
                painter.setBrush(QColor(color))
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawEllipse(pts[0], 3, 3)
            elif shape_type == 'line':
                painter.setBrush(Qt.NoBrush)
                painter.drawLine(pts[0], pts[-1])
            elif shape_type in ('linestrip', 'polyline'):
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(pts)
            elif shape_type == 'circle' and len(pts) >= 2:
                painter.setBrush(fill)
                center = pts[0]
                radius = int(((pts[1].x() - center.x()) ** 2 +
                              (pts[1].y() - center.y()) ** 2) ** 0.5)
                painter.drawEllipse(center, radius, radius)
            elif shape_type == 'rectangle' and len(pts) >= 2:
                # LabelMe stores a rectangle as two corner points; expand them
                # into a real box (normalized in case the corners are inverted).
                painter.setBrush(fill)
                painter.drawRect(QRect(pts[0], pts[1]).normalized())
            else:
                # polygon, rectangle, oriented_rectangle
                painter.setBrush(fill)
                painter.drawPolygon(QPolygon(pts))

        painter.end()
        return composed

    @staticmethod
    def _scaledCoord(coord, scale, limit: float = 1_000_000.0):
        """Scale one coordinate, rejecting non-finite values and clamping huge ones.

        A non-numeric or non-finite coordinate (NaN/inf) would otherwise be fed
        into ``QPoint(int(...))``, which can overflow and crash the C++ painter.
        """
        try:
            value = float(coord) * scale
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        return max(-limit, min(limit, value))

    def _paintMaskShape(self, painter: QPainter, color: QColor, shape: dict,
                        img_w: int, img_h: int, sx: float, sy: float):
        """Draw a mask shape, falling back to its bounding box outline."""
        mask = shape.get('mask')
        if isinstance(mask, (list, tuple)):
            fill = QColor(color)
            fill.setAlpha(70)
            pen = QPen(QColor(color))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(fill)
            for rect in mask:
                if not isinstance(rect, (list, tuple)) or len(rect) < 4:
                    continue
                x0 = self._scaledCoord(rect[0], sx)
                y0 = self._scaledCoord(rect[1], sy)
                x1 = self._scaledCoord(rect[2], sx)
                y1 = self._scaledCoord(rect[3], sy)
                if None in (x0, y0, x1, y1):
                    continue
                painter.drawRect(
                    QRect(int(x0), int(y0), int(x1 - x0) + 1, int(y1 - y0) + 1)
                )
        else:
            points = shape.get('points') or []
            xs, ys = [], []
            for p in points:
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    continue
                x = self._scaledCoord(p[0], sx)
                y = self._scaledCoord(p[1], sy)
                if x is None or y is None:
                    continue
                xs.append(x)
                ys.append(y)
            if not xs:
                return
            pen = QPen(QColor(color))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(
                QRect(int(min(xs)), int(min(ys)),
                      int(max(xs) - min(xs)) + 1,
                      int(max(ys) - min(ys)) + 1)
            )
    
    def getImage(self, row: int) -> Optional[Dict]:
        """Get image data by row."""
        if 0 <= row < len(self.images):
            return self.images[row]
        return None

    def labelCounts(self, image_id: int) -> Dict[str, int]:
        """Return ``{label: count}`` for one image's saved shapes."""
        counts: Dict[str, int] = {}
        for shape in self.annotations.get(image_id) or []:
            label = (shape or {}).get('label') or ''
            if label:
                counts[label] = counts.get(label, 0) + 1
        return counts

    def annotationState(self, image_id: int) -> str:
        """Classify an image: 'none', 'has', or 'duplicate'."""
        counts = self.labelCounts(image_id)
        if not counts:
            return 'none'
        if any(n >= 2 for n in counts.values()):
            return 'duplicate'
        return 'has'


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

        # "Last seen" marker: the image the project reopens on.
        if index.data(Qt.UserRole + 2):
            badge_rect = QRect(
                rect.x() + self.padding,
                rect.y() + self.padding + 24,
                62, 18
            )
            painter.fillRect(badge_rect, QColor(COLORS['primary_500']))
            painter.setPen(Qt.white)
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(badge_rect, Qt.AlignCenter, "LAST SEEN")
    
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

        # "Last seen" marker: the image the project reopens on.
        if index.data(Qt.UserRole + 2):
            badge_rect = QRect(
                rect.right() - 78,
                rect.y() + 3,
                72, self.row_height - 6
            )
            painter.fillRect(badge_rect, QColor(COLORS['primary_500']))
            painter.setPen(Qt.white)
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(badge_rect, Qt.AlignCenter, "LAST SEEN")

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, self.row_height)


class ImageFilterProxyModel(QSortFilterProxyModel):
    """Filter by filename, 1-based index number, and split."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search = ""
        self._split = "All"
        self._annotation = "all"  # "all" | "has" | "none" | "duplicate"
        self._label = None        # a specific label name, or None for "Any"

    def setSearch(self, text: str):
        self._search = (text or "").strip().lower()
        self.invalidateFilter()

    def setSplit(self, split: str):
        self._split = split or "All"
        self.invalidateFilter()

    def setAnnotationFilter(self, category: str):
        self._annotation = category or "all"
        self.invalidateFilter()

    def setLabelFilter(self, label: Optional[str]):
        self._label = label or None
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

        if self._annotation != "all":
            state = model.annotationState(image['id'])
            if self._annotation == "none" and state != "none":
                return False
            if self._annotation == "has" and state == "none":
                return False
            if self._annotation == "duplicate" and state != "duplicate":
                return False

        if self._label is not None:
            counts = model.labelCounts(image['id'])
            needed = 2 if self._annotation == "duplicate" else 1
            if counts.get(self._label, 0) < needed:
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
        self._current_image_id: Optional[int] = None
        
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
        self.split_filter.currentTextChanged.connect(self._onFilterComboChanged)
        filter_layout.addWidget(self.split_filter)
        
        self.overlay_check = QPushButton()
        self.overlay_check.setCheckable(True)
        self.overlay_check.setChecked(True)
        self.overlay_check.setToolTip("Show Labels")
        self.overlay_check.setText("Show Labels")
        self.overlay_check.toggled.connect(self._onOverlayToggled)
        filter_layout.addWidget(self.overlay_check)
        
        layout.addLayout(filter_layout)
        
        # Annotation-state filter (has / no / duplicate labels, per-label)
        annot_layout = QHBoxLayout()
        
        self.annotation_filter = QComboBox()
        self.annotation_filter.addItem("All images", "all")
        self.annotation_filter.addItem("Has labels", "has")
        self.annotation_filter.addItem("No labels", "none")
        self.annotation_filter.addItem("Duplicate labels", "duplicate")
        self.annotation_filter.currentIndexChanged.connect(self._onAnnotationFilterChanged)
        annot_layout.addWidget(self.annotation_filter)
        
        self.label_filter = QComboBox()
        self.label_filter.addItem("Any label", None)
        self.label_filter.setEnabled(False)
        self.label_filter.currentIndexChanged.connect(self._onFilterComboChanged)
        annot_layout.addWidget(self.label_filter)
        
        layout.addLayout(annot_layout)
        
        # Image list view
        self.list_view = QListView()
        self.list_view.setViewMode(QListView.IconMode)
        self.list_view.setMovement(QListView.Static)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setSpacing(8)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
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
        self._current_image_id = None

    def setImageFetcher(self, fetcher):
        """Set an on-demand image fetch callback for remote projects."""
        self.model.setImageFetcher(fetcher)

    def setPrefetchRequest(self, request):
        """Set a background prefetch callback so painting never blocks."""
        self.model.setPrefetchRequest(request)

    def invalidateThumbnail(self, image_id: int):
        """Drop a cached thumbnail and repaint that row (after a fetch)."""
        self.model.invalidateThumbnail(image_id)
        for row in range(self.proxy_model.rowCount()):
            proxy_idx = self.proxy_model.index(row, 0)
            source_idx = self.proxy_model.mapToSource(proxy_idx)
            image = self.model.getImage(source_idx.row())
            if image and image['id'] == image_id:
                self.model.dataChanged.emit(
                    source_idx, source_idx, [Qt.DecorationRole]
                )
                return

    def setAnnotationData(
        self,
        annotations: Optional[Dict[int, List[dict]]] = None,
        label_colors: Optional[Dict[str, str]] = None,
        label_visibility: Optional[Dict[str, bool]] = None,
    ):
        """Feed annotation shapes and label metadata into the grid model."""
        self.model.setAnnotationData(
            annotations=annotations,
            label_colors=label_colors,
            label_visibility=label_visibility,
        )
        if label_colors is not None:
            self._refreshLabelFilter()
        self.proxy_model.invalidateFilter()
        # Re-select the current image: annotation changes (save/import/auto) also
        # reset the view's current index via the re-filter above.
        if self._current_image_id is not None:
            self.revealImage(self._current_image_id)
        self.list_view.viewport().update()

    def _refreshLabelFilter(self):
        """Populate the per-label filter from the project's labels."""
        current = self.label_filter.currentData()
        self.label_filter.blockSignals(True)
        self.label_filter.clear()
        self.label_filter.addItem("Any label", None)
        for label in sorted(self.model.label_colors.keys()):
            self.label_filter.addItem(label, label)
        if current is not None:
            index = self.label_filter.findData(current)
            if index >= 0:
                self.label_filter.setCurrentIndex(index)
        self.label_filter.blockSignals(False)
        category = self.annotation_filter.currentData()
        self.label_filter.setEnabled(category in ("has", "duplicate"))

    def _onAnnotationFilterChanged(self, *args):
        """Enable the label filter only for 'has'/'duplicate', then re-filter."""
        self._refreshLabelFilter()
        self.filterImages()
        self.list_view.setFocus()

    def _onFilterComboChanged(self, *args):
        """Re-filter after a split/label combo change and return arrow keys to."""
        self.filterImages()
        self.list_view.setFocus()

    def _onOverlayToggled(self, checked: bool):
        self.model.setShowOverlays(checked)

    def invalidateOverlay(self, image_id: int):
        """Refresh a single image's overlay (e.g. after saving its annotation)."""
        self.model.invalidateOverlay(image_id)
        self.list_view.viewport().update()
    
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
        """Filter images by search text, split, and annotation state."""
        self.proxy_model.setSearch(self.search_input.text())
        self.proxy_model.setSplit(self.split_filter.currentText())
        self.proxy_model.setAnnotationFilter(self.annotation_filter.currentData())
        self.proxy_model.setLabelFilter(self.label_filter.currentData())
        # Keep the current image selected: a filter change resets the view's
        # current index, which would otherwise leave no image highlighted.
        if self._current_image_id is not None:
            self.revealImage(self._current_image_id)
    
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

    def visibleImageIds(self) -> List[int]:
        """Image ids in display order, honouring the active filter."""
        ids = []
        for row in range(self.proxy_model.rowCount()):
            proxy_idx = self.proxy_model.index(row, 0)
            source_idx = self.proxy_model.mapToSource(proxy_idx)
            image = self.model.getImage(source_idx.row())
            if image:
                ids.append(image['id'])
        return ids

    def revealImage(self, image_id: int):
        """Select an image and scroll it into view."""
        self._current_image_id = image_id
        for row in range(self.proxy_model.rowCount()):
            proxy_idx = self.proxy_model.index(row, 0)
            source_idx = self.proxy_model.mapToSource(proxy_idx)
            image = self.model.getImage(source_idx.row())
            if image and image['id'] == image_id:
                self.list_view.setCurrentIndex(proxy_idx)
                self.list_view.scrollTo(
                    proxy_idx, self.list_view.ScrollHint.EnsureVisible
                )
                return

    def setLastSeen(self, image_id: Optional[int]):
        """Mark which image the project reopens on."""
        self.model.setLastSeen(image_id)
        self.list_view.viewport().update()