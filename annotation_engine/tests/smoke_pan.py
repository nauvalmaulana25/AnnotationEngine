"""Headless smoke test for panning at fit and right after loading an image."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_pan_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget
from PySide6.QtTest import QTest

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {extra}")
        failures.append(name)


def build_canvas(width, height):
    host = QWidget()
    host.resize(600, 400)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    area = QScrollArea()
    area.setWidgetResizable(True)
    layout.addWidget(area)

    from annotation_engine.ui.canvas import AnnotationCanvas

    canvas = AnnotationCanvas()
    area.setWidget(canvas)
    host.show()
    app.processEvents()
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("white"))
    canvas.load_pixmap(pixmap=pixmap)
    app.processEvents()
    return host, area, canvas


# ---------------------------------------------------------------- fit to image
host, area, canvas = build_canvas(1600, 1200)
canvas.zoomFit()
app.processEvents()

check("fit does not overflow", not canvas._is_image_overflowing_viewport())
check("fit has no scroll range",
      area.horizontalScrollBar().maximum() == 0
      and area.verticalScrollBar().maximum() == 0)
check("middle drag still blocked at fit", not canvas._can_pan())

canvas.setTool("select")
start = canvas.get_view_offset()
QTest.mousePress(canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, QPoint(300, 200))
QTest.mouseMove(canvas, QPoint(360, 240))
QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton,
                   Qt.KeyboardModifier.NoModifier, QPoint(360, 240))
app.processEvents()

moved = canvas.get_view_offset()
check("left drag pans at fit", moved != start, (start, moved))
check("pan moved in both axes", moved.x() != 0 and moved.y() != 0, moved)

# The drawn image really shifted under the cursor.
from PySide6.QtCore import QPointF

canvas.reset_view_offset()
before = canvas.transform_widget_point_to_image(point=QPointF(0, 0))
canvas.pan_view(step=QPointF(40, 30))
after = canvas.transform_widget_point_to_image(point=QPointF(0, 0))
check("pan changes image coordinates under cursor", before != after, (before, after))

# Middle drag is still refused at fit (kept by request).
canvas.reset_view_offset()
QTest.mousePress(canvas, Qt.MouseButton.MiddleButton,
                 Qt.KeyboardModifier.NoModifier, QPoint(300, 200))
check("middle press does not start pan at fit", not canvas._panning)
QTest.mouseRelease(canvas, Qt.MouseButton.MiddleButton,
                   Qt.KeyboardModifier.NoModifier, QPoint(300, 200))

# After zooming past the viewport, middle drag works again.
canvas.zoomIn()
canvas.zoomIn()
app.processEvents()
check("zoomed image overflows", canvas._is_image_overflowing_viewport())
check("middle drag allowed when zoomed", canvas._can_pan())

host.close()


# ----------------------------------------------- select-mode integrated pan
host, area, canvas = build_canvas(1600, 1200)
canvas.zoomFit()
app.processEvents()

import numpy as np

shape = canvas._dictToShape({
    "label": "box",
    "shape_type": "rectangle",
    "points": [[100, 100], [300, 200]],
})
canvas.load_shapes(shapes=[shape], replace=True)
app.processEvents()

canvas.setTool("select")
app.processEvents()

# 1) Empty-area left-drag pans the view and clears the selection.
canvas.select_shapes(shapes=[shape])
app.processEvents()
check("select: box selected initially", len(canvas.selected_shapes) == 1)

empty = canvas.transform_image_point_to_widget(point=QPointF(1400, 1000))
press = empty.toPoint()
offset_before = canvas.get_view_offset()
QTest.mousePress(canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, press)
QTest.mouseMove(canvas, press + QPoint(40, 30))
QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton,
                   Qt.KeyboardModifier.NoModifier, press + QPoint(40, 30))
app.processEvents()
check("select: empty drag pans at fit",
      canvas.get_view_offset() != offset_before,
      (offset_before, canvas.get_view_offset()))
check("select: empty click clears selection",
      len(canvas.selected_shapes) == 0)

# 2) Left-drag on a shape moves the shape, not the view.
canvas.reset_view_offset()
app.processEvents()
box_center = canvas.transform_image_point_to_widget(point=QPointF(200, 150))
p = box_center.toPoint()
pts_before = canvas.shapes[0].points.copy()
offset_before = canvas.get_view_offset()
QTest.mousePress(canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, p)
QTest.mouseMove(canvas, p + QPoint(30, 20))
QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton,
                   Qt.KeyboardModifier.NoModifier, p + QPoint(30, 20))
app.processEvents()
pts_after = canvas.shapes[0].points
check("select: drag on shape moves shape",
      not np.array_equal(pts_before, pts_after))
check("select: shape drag does not pan",
      canvas.get_view_offset() == offset_before,
      (offset_before, canvas.get_view_offset()))
check("select: shape becomes selected",
      len(canvas.selected_shapes) == 1)

# 3) Middle-drag stays blocked at fit in select mode (standing decision).
canvas.reset_view_offset()
app.processEvents()
QTest.mousePress(canvas, Qt.MouseButton.MiddleButton,
                 Qt.KeyboardModifier.NoModifier, QPoint(300, 200))
check("select: middle press does not pan at fit", not canvas._panning)
QTest.mouseRelease(canvas, Qt.MouseButton.MiddleButton,
                   Qt.KeyboardModifier.NoModifier, QPoint(300, 200))

host.close()


# ------------------------------------------------- pan right after image load
import annotation_engine.ui.main_window as mw

mw.MainWindow.showWelcomeDialog = lambda self: None

project_id = dbm.create_project("Pan", TMP / "projects")
base = Path(dbm.get_project(project_id)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)
image_ids = []
for name, (w, h) in (("a.png", (1600, 1200)), ("b.png", (900, 700))):
    path = base / "images" / name
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor("white"))
    pixmap.save(str(path))
    image_ids.append(dbm.add_image(project_id, name, f"images/{name}", w, h))

window = mw.MainWindow()
window.current_project_id = project_id
window.resize(1000, 700)
window.show()
app.processEvents()

for index, image_id in enumerate(image_ids, start=1):
    window.loadImage(image_id)
    app.processEvents()
    app.processEvents()
    canvas = window.canvas
    check(f"image {index}: select tool active",
          canvas.current_tool == "select")
    check(f"image {index}: loaded image fits",
          not canvas._is_image_overflowing_viewport())
    offset = canvas.get_view_offset()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(200, 150))
    QTest.mouseMove(canvas, QPoint(250, 190))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, QPoint(250, 190))
    app.processEvents()
    check(f"image {index}: drag pans immediately", canvas.get_view_offset() != offset,
          (offset, canvas.get_view_offset()))

window.annotations_dirty = False
window.close()

print()
if failures:
    print(f"FINAL_PAN_FAILED: {failures}")
    sys.exit(1)
print("FINAL_PAN_OK")
