"""
AnnotationEngine Desktop - Custom Annotation Canvas (extends LabelMe Canvas)
"""
import os
import typing
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QPixmap
from PySide6.QtWidgets import QInputDialog, QMenu

from annotation_engine.config import ANNOTATION_COLORS, ANNOTATION_SETTINGS
from annotation_engine.ui.colors import resolve_label_color

# Import LabelMe components. LabelMe >= 7 uses the private package layout and a
# numpy based Shape model; the fallback keeps old (vendored) LabelMe working.
try:
    from labelme._widgets._canvas import Canvas as LabelMeCanvas
    from labelme._shape._model import Shape as LabelMeShape
    from labelme._widgets._label_dialog import LabelDialog as LabelMeLabelDialog
    from labelme._shape import (
        can_merge_shapes,
        conversion_needs_detail,
        convert_blocker,
        convert_shape,
        merge_masks,
    )
    from labelme._widgets import ConversionDetailDialog
    from labelme._shape_clipboard import ShapeClipboard
except ImportError:
    try:
        from labelme._widgets._zoom_widget import ZoomWidget as LabelMeZoomWidget  # noqa: F401
        from labelme._widgets._canvas import Canvas as LabelMeCanvas
        from labelme._shape._model import Shape as LabelMeShape

        LabelMeLabelDialog = None
        can_merge_shapes = conversion_needs_detail = convert_blocker = None
        convert_shape = merge_masks = ConversionDetailDialog = None
        ShapeClipboard = None
    except ImportError:
        from PySide6.QtWidgets import QWidget

        LabelMeCanvas = QWidget
        LabelMeShape = object
        LabelMeLabelDialog = None
        can_merge_shapes = conversion_needs_detail = convert_blocker = None
        convert_shape = merge_masks = ConversionDetailDialog = None
        ShapeClipboard = None

# Shape fields the label dialog can edit, mirroring LabelMe's Edit Label.
# Kept as a tuple so a LabelMe build without the type alias still works.
try:
    from labelme._widgets._label_dialog import LabelDialogField
except ImportError:  # pragma: no cover - older LabelMe
    LabelDialogField = str  # type: ignore[assignment]

# Conversion targets offered by the "Convert To" submenu, in LabelMe's order.
CONVERT_TARGETS = (
    ("polygon", "Polygon"),
    ("rectangle", "Rectangle"),
    ("oriented_rectangle", "Oriented Rectangle"),
    ("circle", "Circle"),
    ("line", "Line"),
    ("point", "Point"),
    ("linestrip", "LineStrip"),
    ("mask", "Mask"),
)


class AnnotationCanvas(LabelMeCanvas):
    """
    Extended LabelMe Canvas with custom signals and AnnotationEngine integration.
    """

    # Custom signals
    shapeCreated = Signal(dict)           # shape data
    shapeModified = Signal(dict)          # shape data
    shapeDeleted = Signal(int)            # shape index (-1 when unknown)
    selectionChanged = Signal(list)       # list of selected indices
    zoomChanged = Signal(float)           # zoom level (1.0 == 100%)
    historyChanged = Signal(bool, bool)   # (can_undo, can_redo)
    shapesChanged = Signal()              # shape list structurally changed
    labelsRenamed = Signal(list)          # labels that may be vacated

    def __init__(self, parent=None):
        super().__init__(parent)

        # State
        self.current_tool = "select"  # rect, polygon, point, line, circle, select, pan
        self.selected_label = ""
        self.label_colors: Dict[str, str] = {}
        self._color_resolver_installed = False

        self._panning = False
        self._pan_last_global: Optional[QPointF] = None

        self._shape_count = 0
        self._undo_stack: List[List[Any]] = []
        self._redo_stack: List[List[Any]] = []
        self._last_snapshot: List[Any] = []
        self._history_limit = int(
            ANNOTATION_SETTINGS.get("max_undo_steps", 50)
        )
        self._label_provider: Callable[[], List[str]] = lambda: []
        self._label_dialog = None
        self._edge_selected = False
        self._conversion_detail = 60  # LabelMe's default polygon detail
        self._shape_clipboard = (
            ShapeClipboard(parent=self) if ShapeClipboard is not None else None
        )

        self._init_label_dialog()
        self._connect_labelme_signals()
        self._init_context_menus()

        # Pan/scroll/zoom are handled internally. The canvas must live inside a
        # QScrollArea for these to have a viewport to act on.
        if hasattr(self, "pan_request"):
            self.pan_request.connect(self._onPanRequest)
        if hasattr(self, "scroll_request"):
            self.scroll_request.connect(self._onScrollRequest)
        if hasattr(self, "zoom_request"):
            self.zoom_request.connect(self._onZoomRequest)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _init_label_dialog(self):
        if LabelMeLabelDialog is None:
            return
        try:
            self._label_dialog = LabelMeLabelDialog(
                parent=self,
                labels=[],
                sort_labels=True,
                completion="startswith",
                show_text_field=True,
            )
        except Exception:  # pragma: no cover - defensive against API drift
            self._label_dialog = None

    def _connect_labelme_signals(self):
        """Connect LabelMe 7.x snake_case signals."""
        try:
            self.new_shape.connect(self._onNewShape)
            self.shape_moved.connect(self._onShapeMoved)
            self.selection_changed.connect(self._onSelectionChanged)
        except (AttributeError, TypeError):
            pass
        if hasattr(self, "edge_selected"):
            self.edge_selected.connect(self._onEdgeSelected)

    def _onEdgeSelected(self, selected: bool):
        self._edge_selected = bool(selected)

    def _init_context_menus(self):
        """Populate LabelMe's context menus with its full shape action set.

        LabelMe builds these menus in its own application layer, which we do not
        use, so the canvas would otherwise show an empty menu on right-click.
        """
        menu = getattr(self, "shape_context_menu", None)
        if menu is not None:
            self._buildShapeContextMenu(menu)

        canvas_menu = getattr(self, "canvas_context_menu", None)
        if canvas_menu is not None:
            self._buildCanvasContextMenu(canvas_menu)

    def _newAction(self, text: str, slot, *, tip: str = "") -> QAction:
        action = QAction(text, self)
        action.triggered.connect(lambda checked=False: slot())
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        return action

    def _buildShapeContextMenu(self, menu: QMenu):
        menu.setToolTipsVisible(True)

        self._act_edit = self._newAction(
            "&Edit Label\u2026",
            self.editSelectedShapes,
            tip="Modify the label of the selected shapes",
        )
        self._act_duplicate = self._newAction(
            "Duplicate Shapes",
            self.duplicateSelectedShapes,
            tip="Create a duplicate of the selected shapes",
        )
        self._act_copy = self._newAction(
            "Copy to Clipboard",
            self.copySelectedShapes,
            tip="Place the selected shapes on the clipboard",
        )
        self._act_delete = self._newAction(
            "Delete Shapes",
            self.deleteSelected,
            tip="Delete the selected shapes (Del)",
        )
        self._act_merge = self._newAction(
            "Merge Shapes",
            self.mergeSelectedShapes,
            tip="Merge the selected mask shapes into one",
        )

        self._convert_actions: Dict[str, QAction] = {}
        self._convert_menu = QMenu("Convert To", self)
        self._convert_menu.setToolTipsVisible(True)
        for target, label in CONVERT_TARGETS:
            action = self._newAction(
                label,
                lambda t=target: self.convertSelectedShapes(t),
                tip=f"Convert the selected shapes to {label.lower()}s",
            )
            action.setCheckable(True)
            self._convert_menu.addAction(action)
            self._convert_actions[target] = action

        self._act_lock = self._newAction(
            "Lock Shapes",
            self.toggleSelectedShapesLock,
            tip="Lock the selected shapes against editing, or unlock them",
        )
        self._act_add_point = self._newAction(
            "Add Point to Edge",
            self.addPointToHoveredEdge,
            tip="Insert a new point at the hovered polygon edge",
        )
        self._act_remove_point = self._newAction(
            "Delete Selected Point",
            self.removeHoveredPoint,
            tip="Delete the hovered point from the polygon or LineStrip",
        )

        menu.addAction(self._act_edit)
        menu.addAction(self._act_duplicate)
        menu.addAction(self._act_copy)
        menu.addAction(self._act_delete)
        menu.addAction(self._act_merge)
        menu.addMenu(self._convert_menu)
        menu.addAction(self._act_lock)
        menu.addSeparator()
        menu.addAction(self._act_add_point)
        menu.addAction(self._act_remove_point)

        menu.aboutToShow.connect(self._refreshShapeContextMenu)

    def _buildCanvasContextMenu(self, menu: QMenu):
        menu.setToolTipsVisible(True)
        edit_mode = self._newAction(
            "Edit Shapes", lambda: self.setTool("select"),
            tip="Move and edit the selected shapes",
        )
        self._act_undo = self._newAction(
            "Undo", self.undo, tip="Undo the last shape change (Ctrl+Z)"
        )
        self._act_paste = self._newAction(
            "Paste from Clipboard",
            self.pasteShapes,
            tip="Insert the clipboard shapes into this image",
        )
        menu.addAction(edit_mode)
        menu.addSeparator()
        menu.addAction(self._act_undo)
        menu.addSeparator()
        menu.addAction(self._act_paste)
        menu.aboutToShow.connect(self._refreshCanvasContextMenu)

    def _refreshCanvasContextMenu(self):
        if hasattr(self, "_act_undo"):
            self._act_undo.setEnabled(self.canUndo())
        if hasattr(self, "_act_paste"):
            self._act_paste.setEnabled(
                self._shape_clipboard is not None
                and bool(self._shape_clipboard.paste())
            )

    def _imageSize(self) -> Optional[tuple]:
        if self.pixmap.isNull():
            return None
        return (self.pixmap.width(), self.pixmap.height())

    def _hoveredShapeAndVertex(self):
        hover = getattr(self, "_last_hover", None)
        shape = getattr(hover, "shape", None)
        vertex = getattr(hover, "vertex", None)
        return shape, vertex

    def _refreshShapeContextMenu(self):
        """Enable menu entries to match the current selection, like LabelMe."""
        selected = list(getattr(self, "selected_shapes", []) or [])
        unlocked = [shape for shape in selected if not shape.locked]
        busy = bool(getattr(self, "is_busy", False))

        self._act_edit.setEnabled(not busy and bool(unlocked))
        self._act_duplicate.setEnabled(not busy and bool(selected))
        self._act_copy.setEnabled(bool(selected))
        self._act_delete.setEnabled(not busy and bool(unlocked))
        self._act_lock.setEnabled(not busy and bool(selected))
        self._act_lock.setText(
            "Unlock Shapes"
            if selected and all(shape.locked for shape in selected)
            else "Lock Shapes"
        )

        if can_merge_shapes is not None:
            try:
                mergeable = can_merge_shapes(shapes=selected)
            except Exception:
                mergeable = False
            self._act_merge.setEnabled(not busy and mergeable)
        else:
            self._act_merge.setEnabled(False)

        image_size = self._imageSize()
        for target, action in self._convert_actions.items():
            if convert_blocker is None:
                action.setEnabled(False)
                action.setChecked(False)
                continue
            try:
                blocker = convert_blocker(
                    shapes=selected, target=target, image_size=image_size
                )
            except Exception:
                blocker = "error"
            action.setEnabled(not busy and blocker is None)
            sources = [shape for shape in selected if shape.shape_type != target]
            action.setChecked(bool(selected) and not sources)

        self._act_add_point.setEnabled(self._edge_selected)
        hovered_shape, hovered_vertex = self._hoveredShapeAndVertex()
        self._act_remove_point.setEnabled(
            hovered_shape is not None
            and hovered_vertex is not None
            and not hovered_shape.locked
            and hovered_shape.can_remove_point()
        )

    def setLabelProvider(self, provider: Callable[[], List[str]]):
        """Set a callback returning labels available for the label dialog."""
        self._label_provider = provider

    # ------------------------------------------------------------------
    # Tool handling
    # ------------------------------------------------------------------
    def setTool(self, tool_name: str):
        """Set current annotation tool."""
        tool_name = (tool_name or "select").lower()

        # LabelMe 7.11 create modes.
        create_mode_map = {
            "rect": "rectangle",
            "bbox": "rectangle",
            "rectangle": "rectangle",
            "polygon": "polygon",
            "point": "point",
            "keypoint": "point",
            "line": "line",
            "circle": "circle",
            "oriented_rectangle": "oriented_rectangle",
        }

        try:
            if tool_name in ("select", "pan"):
                # EDIT mode: select / move shapes. Middle-mouse pan and
                # Ctrl+wheel zoom are handled by the canvas itself.
                self.set_editing(value=True)
            else:
                mode = create_mode_map.get(tool_name, "polygon")
                self.set_editing(value=False, create_mode=mode)
        except (AttributeError, TypeError):
            # Old LabelMe fallback.
            try:
                self._set_create_mode(value=create_mode_map.get(tool_name, "polygon"))
            except (AttributeError, TypeError):
                pass

        self.current_tool = tool_name
        self._stop_pan()
        if tool_name == "pan":
            try:
                self._release_cursor()
            except AttributeError:
                pass
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()

    def setSelectedLabel(self, label: str):
        """Set the label pre-filled in the label dialog for new shapes."""
        self.selected_label = label or ""
        # Old LabelMe API.
        if hasattr(self, "setLabel"):
            try:
                self.setLabel(self.selected_label)
            except (AttributeError, TypeError):
                pass

    def _setLabelVisibility(self, label: str, visible: bool) -> bool:
        """Apply visibility to one label's shapes; return True if it changed."""
        changed = False
        for shape in self.shapes:
            if (getattr(shape, "label", "") or "") != label:
                continue
            if getattr(shape, "visible", True) == visible:
                continue
            try:
                self.set_shape_visible(shape=shape, value=visible)
            except (AttributeError, TypeError):
                shape.visible = visible
            changed = True
        return changed

    def setLabelVisibility(self, label: str, visible: bool):
        """Show/hide shapes with a specific label.

        Visibility is view state, so it is not an undoable edit. The history
        baseline is refreshed instead, keeping undo focused on real changes.
        """
        if self._setLabelVisibility(label, bool(visible)):
            self._last_snapshot = self._snapshot()
            self.update()

    # ------------------------------------------------------------------
    # Shape colors
    # ------------------------------------------------------------------
    def setLabelColors(self, colors: Dict[str, str]):
        """Use the label-list colors when rendering shapes."""
        self.label_colors = dict(colors or {})

        if not self._color_resolver_installed and hasattr(self, "set_color_resolver"):
            try:
                self.set_color_resolver(resolver=self._resolveShapeColor)
                self._color_resolver_installed = True
            except (AttributeError, TypeError):
                self._color_resolver_installed = False

        self.refreshShapeColors()

    def applyLabelVisibilities(self, visibility: Dict[str, bool]):
        """Apply per-label visibility without touching undo history."""
        changed = False
        for label, visible in (visibility or {}).items():
            if self._setLabelVisibility(label, bool(visible)):
                changed = True
        if changed:
            # Visibility is view state, not an edit: keep the history baseline
            # in sync so a later undo does not flip shapes back to the old value.
            self._last_snapshot = self._snapshot()
            self.update()

    def refreshShapeColors(self):
        """Drop cached palettes so color edits show up immediately."""
        cache = getattr(self, "_palette_cache", None)
        if cache is not None:
            cache.clear()
        self.update()

    def _resolveShapeColor(self, label: str) -> tuple:
        qcolor = resolve_label_color(label, self.label_colors)
        return (qcolor.red(), qcolor.green(), qcolor.blue())

    # ------------------------------------------------------------------
    # Image loading / view transform
    # ------------------------------------------------------------------
    def loadImage(self, image_path: str) -> bool:
        """Load image from file path."""
        if not os.path.exists(image_path):
            print(f"[Canvas] Image not found: {image_path}")
            return False

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            print(f"[Canvas] Failed to load pixmap: {image_path}")
            return False

        try:
            self.load_pixmap(pixmap=pixmap)
        except (AttributeError, TypeError) as e:
            print(f"[Canvas] load_pixmap error: {e}")
            return False

        self._shape_count = len(self.shapes)
        self._resetHistory()
        self._stop_pan()
        # The scroll area has not laid out yet; fit on the next event loop turn.
        QTimer.singleShot(0, self.zoomFit)
        return True

    def zoomFit(self):
        """Fit image to the scroll area viewport."""
        area = self._find_scroll_area()
        if area is None or self.pixmap.isNull():
            return

        available = area.maximumViewportSize()
        if available.width() <= 0 or available.height() <= 0:
            return

        scale = min(
            available.width() / max(1, self.pixmap.width()),
            available.height() / max(1, self.pixmap.height()),
        )
        self._applyScale(max(scale, 1e-6))
        self.reset_view_offset()
        self._center_view()
        self.zoomChanged.emit(self.scale)

    def _applyScale(self, scale: float):
        """Set the zoom scale and refresh the layout it affects.

        The canvas size hint follows the scaled pixmap, so scrollbar ranges and
        the pan gate would otherwise lag one layout pass behind a zoom change.
        """
        self.scale = scale
        self.updateGeometry()
        self.update()

    def zoomIn(self):
        """Zoom in around the viewport center."""
        self._zoom_steps(1.0, anchor=None)

    def zoomOut(self):
        """Zoom out around the viewport center."""
        self._zoom_steps(-1.0, anchor=None)

    def setZoom(self, scale: float):
        """Set absolute zoom scale (1.0 == 100%)."""
        if scale <= 0:
            return
        self._zoom_to(scale, anchor=None)

    def _zoom_steps(self, steps: float, anchor: Optional[QPointF]):
        # 1.1 per wheel notch, matching LabelMe.
        self._zoom_to(self.scale * (1.1 ** steps), anchor=anchor)

    def _zoom_to(self, scale: float, anchor: Optional[QPointF]):
        new_scale = max(0.01, min(40.0, scale))
        area = self._find_scroll_area()
        if area is None:
            self._applyScale(new_scale)
            self.zoomChanged.emit(self.scale)
            return

        viewport = area.viewport()
        if anchor is None:
            anchor = QPointF(self.mapFrom(viewport, viewport.rect().center()))

        try:
            image_pos = self.transform_widget_point_to_image(point=anchor)
            viewport_pos = QPointF(self.mapTo(viewport, anchor.toPoint()))
        except (AttributeError, TypeError):
            self._applyScale(new_scale)
            self.zoomChanged.emit(self.scale)
            return

        self._applyScale(new_scale)

        try:
            target = self.transform_image_point_to_widget(
                point=image_pos, area=self.sizeHint()
            )
            current = QPointF(self.mapFrom(viewport, viewport_pos.toPoint()))
            self._move_view(step=current - target, constrain_to_center=False)
        except (AttributeError, TypeError):
            self._center_view()

        self.zoomChanged.emit(self.scale)

    def _center_view(self):
        area = self._find_scroll_area()
        if area is None:
            return
        h_bar = area.horizontalScrollBar()
        v_bar = area.verticalScrollBar()
        h_bar.setValue((h_bar.minimum() + h_bar.maximum()) // 2)
        v_bar.setValue((v_bar.minimum() + v_bar.maximum()) // 2)

    def _move_view(self, step: QPointF, constrain_to_center: bool = False):
        area = self._find_scroll_area()
        if area is None:
            return

        h_bar = area.horizontalScrollBar()
        v_bar = area.verticalScrollBar()
        h_old = h_bar.value()
        v_old = v_bar.value()

        h_bar.setValue(int(h_bar.value() - step.x()))
        v_bar.setValue(int(v_bar.value() - step.y()))

        try:
            self.pan_view(
                step=QPointF(
                    step.x() + h_bar.value() - h_old,
                    step.y() + v_bar.value() - v_old,
                ),
                constrain_to_center=constrain_to_center,
            )
        except (AttributeError, TypeError):
            pass

    def _onPanRequest(self, step: QPoint):
        self._move_view(
            step=QPointF(step.x(), step.y()), constrain_to_center=True
        )

    def _onScrollRequest(self, delta: int, orientation: Qt.Orientation):
        area = self._find_scroll_area()
        if area is None:
            return
        bar = (
            area.horizontalScrollBar()
            if orientation == Qt.Orientation.Horizontal
            else area.verticalScrollBar()
        )
        units = -delta * 0.1
        bar.setValue(int(bar.value() + bar.singleStep() * units))

    def _onZoomRequest(self, delta: int, pos: QPointF):
        # 120 is one wheel notch; trackpads send smaller deltas.
        self._zoom_steps(delta / 120.0, anchor=pos)

    # ------------------------------------------------------------------
    # Pan tool and wheel zoom
    # ------------------------------------------------------------------
    def _hasImage(self) -> bool:
        return not getattr(self, "pixmap", QPixmap()).isNull()

    def _can_pan(self) -> bool:
        """Whether middle-mouse drag may pan (LabelMe's own rule)."""
        try:
            return self._hasImage() and (
                self._is_image_overflowing_viewport()
                or not self.get_view_offset().isNull()
            )
        except (AttributeError, TypeError):
            return False

    def _can_pan_with_tool(self) -> bool:
        """Whether the Pan tool may start a drag.

        An image that fits the viewport has no scrollbars, but panning it is
        still meaningful: LabelMe's pan_view clamps to half the image, so the
        user can recenter slack around a fitted image.
        """
        return self._hasImage()

    def _stop_pan(self):
        self._panning = False
        self._pan_last_global = None

    def _start_pan(self, event):
        self._panning = True
        self._pan_last_global = QPointF(event.globalPosition())
        self.setCursor(Qt.ClosedHandCursor)

    def _pan_to(self, event):
        if not self._panning or self._pan_last_global is None:
            return
        pos = QPointF(event.globalPosition())
        delta = pos - self._pan_last_global
        self._pan_last_global = pos
        if delta.isNull():
            return
        step = QPoint(int(delta.x()), int(delta.y()))
        if hasattr(self, "pan_request"):
            self.pan_request.emit(step)
        else:
            self._move_view(
                step=QPointF(step.x(), step.y()), constrain_to_center=True
            )

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self.current_tool == "select" and event.button() == Qt.MouseButton.LeftButton:
            # Select-mode integrated pan: an empty-area left press pans the view
            # and clears the selection; a press on a shape (body, vertex, edge,
            # rotation handle) still selects/drags it. Hit-test first so a shape
            # always wins over the pan.
            shape = None
            try:
                pos = self.transform_widget_point_to_image(point=event.position())
                self._refresh_hover_state(pos=pos)
                shape = self._find_pointed_shape(point=pos)
            except (AttributeError, TypeError):
                pass
            if shape is None:
                self.deselect_shape()
                self._start_pan(event)
                event.accept()
                return
        if self.current_tool == "pan" and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
        ):
            # The Pan tool may drag any loaded image; middle-mouse keeps
            # LabelMe's rule of only panning when the view can move.
            can_start = (
                self._can_pan_with_tool()
                if event.button() == Qt.MouseButton.LeftButton
                else self._can_pan()
            )
            if can_start:
                self._start_pan(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def _emitMousePosition(self, widget_pos: QPointF):
        try:
            image_pos = self.transform_widget_point_to_image(point=widget_pos)
        except (AttributeError, TypeError):
            return
        self.mouse_moved.emit(image_pos)

    def mouseMoveEvent(self, event):
        if self._panning:
            self._pan_to(event)
            self._emitMousePosition(event.position())
            event.accept()
            return
        if self.current_tool == "pan":
            self.setCursor(Qt.OpenHandCursor)
            self._emitMousePosition(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
        ):
            self._stop_pan()
            self.setCursor(
                Qt.OpenHandCursor if self.current_tool == "pan" else Qt.ArrowCursor
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta()
        if delta.isNull():
            event.accept()
            return
        # Ctrl+wheel and Shift+wheel keep LabelMe's zoom/scroll behavior.
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier or (
            modifiers & Qt.KeyboardModifier.ShiftModifier
        ):
            super().wheelEvent(event)
            return
        if delta.y() != 0:
            self._zoom_steps(delta.y() / 120.0, anchor=event.position())
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------
    # Shape <-> LabelMe JSON conversion
    # ------------------------------------------------------------------
    def _shapeToDict(self, shape) -> dict:
        """Convert a LabelMe Shape to a LabelMe JSON-compatible dictionary."""
        if hasattr(shape, "to_dict"):
            try:
                return shape.to_dict()
            except Exception:
                pass

        points = []
        raw_points = getattr(shape, "points", [])
        for point in raw_points:
            try:
                points.append([float(point[0]), float(point[1])])
            except (IndexError, TypeError, ValueError):
                continue

        return {
            "label": getattr(shape, "label", "") or "",
            "points": points,
            "group_id": getattr(shape, "group_id", None),
            "description": getattr(shape, "description", "") or "",
            "shape_type": getattr(shape, "shape_type", "polygon"),
            "flags": dict(getattr(shape, "flags", None) or {}),
            "mask": None,
        }

    def _dictToShape(self, shape_data: dict):
        """Build a LabelMe 7.x Shape from LabelMe JSON shape data."""
        points = shape_data.get("points") or []
        points_array = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        kwargs: Dict[str, Any] = {
            "label": shape_data.get("label"),
            "group_id": shape_data.get("group_id"),
            "shape_type": shape_data.get("shape_type", "polygon"),
            "flags": dict(shape_data.get("flags") or {}),
            "description": shape_data.get("description") or "",
            "points": points_array,
        }
        if "locked" in shape_data:
            kwargs["locked"] = bool(shape_data.get("locked"))
        if shape_data.get("other_data"):
            kwargs["other_data"] = dict(shape_data["other_data"])
        return LabelMeShape(**kwargs)

    # ------------------------------------------------------------------
    # Undo / redo history
    # ------------------------------------------------------------------
    def _snapshot(self) -> List[Any]:
        """Return an independent copy of the current shapes."""
        snapshot = []
        for shape in self.shapes:
            copy_method = getattr(shape, "copy", None)
            snapshot.append(copy_method() if callable(copy_method) else shape)
        return snapshot

    def _emitHistoryState(self):
        self.historyChanged.emit(bool(self._undo_stack), bool(self._redo_stack))

    def _resetHistory(self):
        """Forget history and treat the current shapes as the clean state."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_snapshot = self._snapshot()
        self._emitHistoryState()

    def _recordHistory(self):
        """Push the previous state before applying a shape edit."""
        if self._history_limit <= 0:
            return
        self._undo_stack.append(self._last_snapshot)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._last_snapshot = self._snapshot()
        self._emitHistoryState()

    def _applyHistoryState(self, shapes: List[Any]):
        try:
            self.load_shapes(shapes=list(shapes), replace=True)
        except (AttributeError, TypeError):
            self.shapes = list(shapes)
        self.selected_shapes = []
        self._shape_count = len(self.shapes)
        self.selectionChanged.emit([])
        self.update()

    def canUndo(self) -> bool:
        return bool(self._undo_stack)

    def canRedo(self) -> bool:
        return bool(self._redo_stack)

    def loadShapes(self, shapes_data: List[dict]):
        """Load shapes from LabelMe JSON data."""
        shapes = []
        for shape_data in shapes_data or []:
            try:
                shapes.append(self._dictToShape(shape_data))
            except Exception as e:
                print(f"[Canvas] Failed to load shape: {e}")

        try:
            self.load_shapes(shapes=shapes, replace=True)
        except (AttributeError, TypeError):
            self.shapes = shapes
            self.update()

        self.selected_shapes = []
        self._shape_count = len(self.shapes)
        self._resetHistory()
        self.selectionChanged.emit([])
        self.update()

    def getShapesData(self) -> List[dict]:
        """Get all shapes as LabelMe JSON format."""
        return [self._shapeToDict(shape) for shape in self.shapes]

    def appendShapes(self, shapes_data: List[dict]) -> int:
        """Append LabelMe shape dicts as a single undoable edit.

        Unlike :meth:`loadShapes`, this keeps the undo history, so generated
        shapes (for example MobileSAM masks) can be undone with Ctrl+Z.
        """
        new_shapes = []
        for shape_data in shapes_data or []:
            try:
                new_shapes.append(self._dictToShape(shape_data))
            except Exception as e:
                print(f"[Canvas] Failed to append shape: {e}")
        if not new_shapes:
            return 0
        self._commitShapes(list(self.shapes) + new_shapes, select=new_shapes)
        return len(new_shapes)

    def applyShapes(self, shapes_data: List[dict]) -> int:
        """Replace the whole shape list as a single undoable edit.

        Generated batches need this rather than :meth:`appendShapes` because
        they may also *remove* the prompts that produced them.
        """
        shapes = []
        for shape_data in shapes_data or []:
            try:
                shapes.append(self._dictToShape(shape_data))
            except Exception as e:
                print(f"[Canvas] Failed to apply shape: {e}")
        self._commitShapes(shapes, select=[])
        return len(shapes)

    def clear(self):
        """Clear all shapes and image."""
        try:
            self.load_pixmap(pixmap=QPixmap())
        except (AttributeError, TypeError):
            pass
        try:
            self.load_shapes(shapes=[], replace=True)
        except (AttributeError, TypeError):
            self.shapes = []
        self.selected_shapes = []
        self._shape_count = 0
        self._resetHistory()
        self._stop_pan()
        self.selectionChanged.emit([])
        self.update()

    # ------------------------------------------------------------------
    # LabelMe signal handlers
    # ------------------------------------------------------------------
    def _onNewShape(self):
        """A shape has just been committed; ask for its label."""
        if not self.shapes:
            return

        prefill = self.selected_label
        if not prefill and self._label_dialog is not None:
            prefill = self._label_dialog.last_label

        entry = self._askNewShapeLabel(prefill=prefill)
        if entry is None:
            # Mirror LabelMe: discard the shape that was just committed, then
            # fully cancel the draft it reopens instead of leaving the user
            # stuck with a half-drawn shape.
            try:
                if self.shape_backups:
                    self.shape_backups.pop()
                self.undo_last_line()
            except (AttributeError, TypeError):
                pass
            try:
                self._cancel_current_shape()
            except (AttributeError, TypeError):
                pass
            self._shape_count = len(self.shapes)
            self.update()
            return

        try:
            new_shapes = self.set_last_label(
                text=entry["label"], flags=entry.get("flags") or {}
            )
        except (AttributeError, TypeError):
            new_shapes = self.shapes[-1:]

        for shape in new_shapes:
            if entry.get("group_id") is not None or getattr(shape, "group_id", None) is None:
                shape.group_id = entry.get("group_id")
            shape.description = entry.get("description") or ""

        self.selected_label = entry["label"]
        if self._label_dialog is not None:
            try:
                self._label_dialog.add_label_history(label=entry["label"])
                self._label_dialog.remember_label(label=entry["label"])
            except (AttributeError, TypeError):
                pass

        # The label dialog runs after LabelMe snapshotted the unlabeled shape.
        # Retake that snapshot so undo/redo restores the labeled state.
        try:
            if self.shape_backups:
                self.shape_backups.pop()
                self.shape_backups.append(
                    [shape.copy() for shape in self.shapes]
                )
        except (AttributeError, TypeError):
            pass

        self._shape_count = len(self.shapes)
        self._recordHistory()
        for shape in new_shapes:
            self.shapeCreated.emit(self._shapeToDict(shape))
        self.update()

    def _askNewShapeLabel(self, prefill: str = "") -> Optional[dict]:
        if self._label_dialog is not None:
            try:
                labels = list(self._label_provider() or [])
                self._label_dialog.set_predefined_labels(labels=labels)
                entry = self._label_dialog.popup(text=prefill or None)
            except (AttributeError, TypeError):
                entry = None
            if entry is not None:
                return {
                    "label": entry.label,
                    "flags": entry.flags,
                    "group_id": entry.group_id,
                    "description": entry.description,
                }
            return None

        # Fallback for LabelMe builds without LabelDialog.
        text, ok = QInputDialog.getText(
            self, "Shape Label", "Label:", text=prefill or ""
        )
        if not ok or not text.strip():
            return None
        return {
            "label": text.strip(),
            "flags": {},
            "group_id": None,
            "description": "",
        }

    def _onShapeMoved(self):
        """Handle shape moved (LabelMe 7.x signal has no arguments)."""
        shapes = list(getattr(self, "selected_shapes", []) or [])
        if not shapes and self.shapes:
            shapes = self.shapes[-1:]
        for shape in shapes:
            self.shapeModified.emit(self._shapeToDict(shape))
        self._recordHistory()

    def _onSelectionChanged(self, selected_shapes):
        """Track the selection and detect deletions."""
        # LabelMe leaves this to the host app. Without assigning it here the
        # canvas has no selected shapes to drag or delete.
        self.selected_shapes = list(selected_shapes or [])

        if len(self.shapes) < self._shape_count:
            self.shapeDeleted.emit(-1)
        self._shape_count = len(self.shapes)

        indices = []
        for i, shape in enumerate(self.shapes):
            if shape in self.selected_shapes:
                indices.append(i)
        self.selectionChanged.emit(indices)

    # ------------------------------------------------------------------
    # Edit actions
    # ------------------------------------------------------------------
    def undo(self) -> bool:
        """Undo the last shape change."""
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot())
        if len(self._redo_stack) > self._history_limit:
            self._redo_stack.pop(0)
        state = self._undo_stack.pop()
        self._applyHistoryState(state)
        self._last_snapshot = self._snapshot()
        self._emitHistoryState()
        return True

    def redo(self) -> bool:
        """Redo the last undone shape change."""
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        state = self._redo_stack.pop()
        self._applyHistoryState(state)
        self._last_snapshot = self._snapshot()
        self._emitHistoryState()
        return True

    def selectAll(self):
        """Select all shapes."""
        try:
            self.select_shapes(shapes=list(self.shapes))
        except (AttributeError, TypeError):
            pass

    def deleteSelected(self):
        """Delete selected shapes."""
        try:
            removed = self.delete_selected()
        except (AttributeError, TypeError):
            return
        if not removed:
            return
        self._shape_count = len(self.shapes)
        self._recordHistory()
        self.shapeDeleted.emit(-1)
        self.selectionChanged.emit(self.getSelectedIndices())
        self.update()

    def _commitShapes(self, shapes: List[Any], select: Optional[List[Any]] = None):
        """Replace the shape list as one undoable edit."""
        try:
            self.load_shapes(shapes=list(shapes), replace=True)
        except (AttributeError, TypeError):
            self.shapes = list(shapes)
        self._shape_count = len(self.shapes)
        self._recordHistory()
        if select is not None:
            try:
                self.select_shapes(shapes=list(select))
            except (AttributeError, TypeError):
                self.selected_shapes = list(select)
        self.selectionChanged.emit(self.getSelectedIndices())
        self.shapesChanged.emit()
        self.update()

    # ------------------------------------------------------------------
    # Shape context menu actions (LabelMe parity)
    # ------------------------------------------------------------------
    def _unlockedSelection(self) -> List[Any]:
        return [
            shape
            for shape in (getattr(self, "selected_shapes", []) or [])
            if not getattr(shape, "locked", False)
        ]

    def editSelectedShapes(self) -> bool:
        """Edit label/flags/group/description of the selected shapes."""
        shapes = self._unlockedSelection()
        if not shapes:
            return False

        first = shapes[0]
        # A field that differs across the selection has no single value to
        # show, so it is locked in the dialog and left untouched, as LabelMe
        # does. "label" stays editable so this doubles as Rename.
        locked = {
            field
            for field in typing.get_args(LabelDialogField)
            if any(
                getattr(shape, field) != getattr(first, field)
                for shape in shapes[1:]
            )
        }
        entry = self._askShapeFields(first, locked)
        if entry is None:
            return False

        fields = ["label", "flags", "group_id", "description"]
        editable = [field for field in fields if field not in locked]
        changed = any(
            getattr(shape, field) != entry.get(field)
            for shape in shapes
            for field in editable
        )
        if not changed:
            return False

        old_labels = {shape.label or "" for shape in shapes}
        for shape in shapes:
            for field in editable:
                setattr(shape, field, entry.get(field))
        self._recordHistory()
        if self.selected_label in old_labels:
            self.selected_label = entry.get("label") or ""
        self.labelsRenamed.emit(sorted(label for label in old_labels if label))
        self.shapesChanged.emit()
        self.update()
        return True

    def _askShapeFields(self, shape, locked=()) -> Optional[dict]:
        """Open the label dialog prefilled with the shape's current fields."""
        if self._label_dialog is not None:
            try:
                self._label_dialog.set_predefined_labels(
                    labels=list(self._label_provider() or [])
                )
                entry = self._label_dialog.popup(
                    text=shape.label,
                    flags=dict(shape.flags or {}),
                    group_id=shape.group_id,
                    description=shape.description,
                    locked=locked,
                )
            except (AttributeError, TypeError):
                entry = None
            if entry is not None:
                return {
                    "label": entry.label,
                    "flags": entry.flags,
                    "group_id": entry.group_id,
                    "description": entry.description,
                }
            return None

        text, ok = QInputDialog.getText(
            self, "Edit Label", "Label:", text=shape.label or ""
        )
        if not ok or not text.strip():
            return None
        return {
            "label": text.strip(),
            "flags": dict(shape.flags or {}),
            "group_id": shape.group_id,
            "description": shape.description or "",
        }

    def duplicateSelectedShapes(self) -> int:
        """Append editable copies of the selected shapes."""
        shapes = list(getattr(self, "selected_shapes", []) or [])
        if not shapes:
            return 0
        copies = [shape.copy() for shape in shapes]
        for copy in copies:
            copy.locked = False
        self._commitShapes(list(self.shapes) + copies, select=copies)
        return len(copies)

    def copySelectedShapes(self) -> int:
        """Copy the selected shapes to the canvas clipboard."""
        shapes = list(getattr(self, "selected_shapes", []) or [])
        if self._shape_clipboard is None or not shapes:
            return 0
        self._shape_clipboard.store(shapes=shapes)
        return len(shapes)

    def pasteShapes(self) -> int:
        """Insert the clipboard shapes into this image."""
        if self._shape_clipboard is None:
            return 0
        shapes = self._shape_clipboard.paste()
        if not shapes:
            return 0
        for shape in shapes:
            shape.locked = False
        self._commitShapes(list(self.shapes) + shapes, select=shapes)
        return len(shapes)

    def mergeSelectedShapes(self) -> bool:
        """Merge the selected mask shapes into one, keeping its slot."""
        shapes = list(getattr(self, "selected_shapes", []) or [])
        if can_merge_shapes is None or not can_merge_shapes(shapes=shapes):
            return False
        merged = merge_masks(shapes=shapes)
        new_shapes = [
            merged if shape is shapes[0] else shape
            for shape in self.shapes
            if shape is shapes[0] or shape not in shapes
        ]
        self._commitShapes(new_shapes, select=[merged])
        return True

    def convertSelectedShapes(self, target: str) -> bool:
        """Convert the selected shapes to another shape type."""
        if convert_shape is None or convert_blocker is None:
            return False
        selected = list(getattr(self, "selected_shapes", []) or [])
        sources = [shape for shape in selected if shape.shape_type != target]
        if not sources:
            return False
        image_size = self._imageSize()
        try:
            if convert_blocker(
                shapes=selected, target=target, image_size=image_size
            ):
                return False
        except Exception:
            return False

        detail = None
        if (
            conversion_needs_detail is not None
            and ConversionDetailDialog is not None
            and conversion_needs_detail(shapes=sources, target=target)
        ):
            detail = self._askConversionDetail(target, sources, image_size)
            if detail is None:
                return False

        replacements: Dict[int, List[Any]] = {}
        for shape in sources:
            try:
                replacements[id(shape)] = convert_shape(
                    shape=shape, target=target, image_size=image_size,
                    detail=detail,
                )
            except Exception:
                return False

        new_shapes: List[Any] = []
        for shape in self.shapes:
            converted = replacements.get(id(shape))
            if converted is None:
                new_shapes.append(shape)
            else:
                new_shapes.extend(converted)

        converted_shapes = [
            shape for shapes in replacements.values() for shape in shapes
        ]
        self._commitShapes(new_shapes, select=converted_shapes)
        return True

    def _askConversionDetail(self, target: str, sources, image_size) -> Optional[int]:
        """Ask for the polygon detail a lossy conversion needs."""
        def preview(detail: int) -> None:
            shapes = []
            for shape in sources:
                try:
                    shapes.extend(convert_shape(
                        shape=shape, target=target, image_size=image_size,
                        detail=detail,
                    ))
                except Exception:
                    continue
            try:
                self.set_conversion_preview(shapes=shapes)
            except AttributeError:
                pass

        dialog = ConversionDetailDialog(
            title="Convert to Polygon",
            detail=self._conversion_detail,
            on_detail_changed=preview,
            parent=self,
        )
        accepted = dialog.exec() == dialog.DialogCode.Accepted
        try:
            self.set_conversion_preview(shapes=[])
        except AttributeError:
            pass
        if not accepted:
            return None
        self._conversion_detail = int(dialog.detail)
        return self._conversion_detail

    def toggleSelectedShapesLock(self) -> bool:
        """Lock or unlock the selected shapes."""
        shapes = list(getattr(self, "selected_shapes", []) or [])
        if not shapes:
            return False
        value = any(not shape.locked for shape in shapes)
        if self.is_drawing:
            return False
        for shape in shapes:
            shape.locked = value
        # Reloading drops hover state so no handle stays grabbable.
        self._commitShapes(list(self.shapes), select=shapes)
        return True

    def addPointToHoveredEdge(self) -> bool:
        """Insert a point at the hovered polygon edge."""
        if not hasattr(self, "add_point_to_edge"):
            return False
        before = sum(len(shape.points) for shape in self.shapes)
        try:
            self.add_point_to_edge()
        except (AttributeError, TypeError):
            return False
        after = sum(len(shape.points) for shape in self.shapes)
        if after == before:
            return False
        self._recordHistory()
        self.shapesChanged.emit()
        self.update()
        return True

    def removeHoveredPoint(self) -> bool:
        """Delete the hovered vertex from a polygon or LineStrip."""
        if not hasattr(self, "remove_selected_point"):
            return False
        try:
            removed = self.remove_selected_point()
        except (AttributeError, TypeError):
            return False
        if not removed:
            return False
        self._recordHistory()
        self.shapesChanged.emit()
        self.update()
        return True

    def _shapesWithLabel(self, label: str) -> List[Any]:
        return [
            shape
            for shape in self.shapes
            if (getattr(shape, "label", "") or "") == label
        ]

    def selectShapesByLabel(self, label: str) -> int:
        """Select every shape carrying the given label."""
        shapes = [
            shape
            for shape in self._shapesWithLabel(label)
            if getattr(shape, "visible", True)
        ]
        if not shapes:
            return 0
        try:
            self.select_shapes(shapes=shapes)
        except (AttributeError, TypeError):
            self.selected_shapes = shapes
        self.update()
        return len(shapes)

    def deleteShapesByLabel(self, label: str) -> int:
        """Delete every visible, unlocked shape carrying the given label."""
        shapes = [
            shape
            for shape in self._shapesWithLabel(label)
            if getattr(shape, "visible", True)
            and not getattr(shape, "locked", False)
        ]
        if not shapes:
            return 0
        try:
            self.select_shapes(shapes=shapes)
            removed = self.delete_selected()
        except (AttributeError, TypeError):
            return 0
        if not removed:
            return 0
        self._shape_count = len(self.shapes)
        self._recordHistory()
        self.shapeDeleted.emit(-1)
        self.selectionChanged.emit(self.getSelectedIndices())
        self.update()
        return len(removed)

    def renameLabelCategory(self, old: str, new: str) -> int:
        """Rename every unlocked shape carrying the old label."""
        if not old or not new or old == new:
            return 0
        shapes = [
            shape
            for shape in self._shapesWithLabel(old)
            if not getattr(shape, "locked", False)
        ]
        if not shapes:
            return 0

        for shape in shapes:
            shape.label = new
        self._shape_count = len(self.shapes)
        if self.selected_label == old:
            self.selected_label = new
        self._recordHistory()
        self.labelsRenamed.emit([old])
        self.shapesChanged.emit()
        self.update()
        return len(shapes)

    def renameSelectedShapesLabel(self, new: str) -> int:
        """Rename the currently selected, unlocked shapes."""
        if not new:
            return 0
        shapes = self._unlockedSelection()
        if not shapes:
            return 0

        old_labels = {getattr(shape, "label", "") or "" for shape in shapes}
        for shape in shapes:
            shape.label = new
        self._shape_count = len(self.shapes)
        if self.selected_label in old_labels:
            self.selected_label = new
        self._recordHistory()
        self.labelsRenamed.emit(sorted(label for label in old_labels if label))
        self.shapesChanged.emit()
        self.update()
        return len(shapes)

    def selectedLabels(self) -> List[str]:
        """Return the labels of the currently selected shapes."""
        return [
            getattr(shape, "label", "") or ""
            for shape in (getattr(self, "selected_shapes", []) or [])
        ]

    def getSelectedIndices(self) -> List[int]:
        """Get indices of selected shapes."""
        selected = getattr(self, "selected_shapes", []) or []
        return [i for i, shape in enumerate(self.shapes) if shape in selected]

    def setSelectedIndices(self, indices: List[int]):
        """Set selected shapes by indices."""
        shapes = [self.shapes[i] for i in indices if 0 <= i < len(self.shapes)]
        try:
            self.select_shapes(shapes=shapes)
        except (AttributeError, TypeError):
            self.selected_shapes = shapes
