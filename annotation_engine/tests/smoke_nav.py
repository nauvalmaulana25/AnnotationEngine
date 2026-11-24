"""Headless smoke test for image navigation and the last-seen state."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_nav_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {extra}")
        failures.append(name)


import annotation_engine.ui.main_window as mw

mw.MainWindow.showWelcomeDialog = lambda self: None

project_id = dbm.create_project("Nav", TMP / "projects")
base = Path(dbm.get_project(project_id)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)

names = ["apple.png", "banana.png", "apricot.png", "cherry.png"]
image_ids = []
for name in names:
    path = base / "images" / name
    pixmap = QPixmap(320, 240)
    pixmap.fill(QColor("white"))
    pixmap.save(str(path))
    image_ids.append(dbm.add_image(project_id, name, f"images/{name}", 320, 240))


def new_window():
    window = mw.MainWindow()
    window.resize(1100, 800)
    window.show()
    # Activating matters: focus transfer (and therefore key delivery) needs an
    # active window, and the navigation filter keys off the focused widget.
    window.activateWindow()
    app.processEvents()
    return window


def focus_and_press(window, widget, key=Qt.Key.Key_Right, reset=True):
    """Move focus to a widget, then send it a key as a user would."""
    if reset and window.current_image_id not in (None, image_ids[0]):
        window.loadImage(image_ids[0])
        app.processEvents()
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    app.processEvents()
    current = window.current_image_id
    QTest.keyClick(widget, key)
    app.processEvents()
    return window.current_image_id != current


def press(canvas, key):
    canvas.setFocus()
    QTest.keyClick(canvas, key)
    app.processEvents()


# ------------------------------------------------------- last-seen storage
check("no last image before any load",
      dbm.get_last_image_id(project_id) is None,
      dbm.get_last_image_id(project_id))

dbm.set_last_image_id(project_id, image_ids[2])
check("last image round-trips",
      dbm.get_last_image_id(project_id) == image_ids[2],
      dbm.get_last_image_id(project_id))
dbm.set_last_image_id(project_id, None)
check("setting None does not overwrite",
      dbm.get_last_image_id(project_id) == image_ids[2],
      dbm.get_last_image_id(project_id))
# Start the rest of the test from a clean slate.
dbm.set_setting(f"last_image:{project_id}", None)

# ---------------------------------------------------------- arrow keys
window = new_window()
window.loadProject(project_id)
app.processEvents()
app.processEvents()

check("project opens with nothing loaded",
      window.current_image_id is None, window.current_image_id)

press(window.canvas, Qt.Key.Key_Right)
check("first Right opens the first image",
      window.current_image_id == image_ids[0], window.current_image_id)

press(window.canvas, Qt.Key.Key_Right)
check("Right advances to the second image",
      window.current_image_id == image_ids[1], window.current_image_id)

press(window.canvas, Qt.Key.Key_Left)
check("Left returns to the first image",
      window.current_image_id == image_ids[0], window.current_image_id)

for _ in range(5):
    press(window.canvas, Qt.Key.Key_Left)
check("navigation clamps at the first image",
      window.current_image_id == image_ids[0], window.current_image_id)

for _ in range(8):
    press(window.canvas, Qt.Key.Key_Right)
check("navigation clamps at the last image",
      window.current_image_id == image_ids[-1], window.current_image_id)

# A selected shape keeps the arrow keys for nudging.
window.canvas.loadShapes([
    {"label": "box", "points": [[10, 10], [60, 60]], "shape_type": "rectangle"},
])
window.canvas.select_shapes(shapes=list(window.canvas.shapes))
app.processEvents()
before = [list(map(float, p)) for p in window.canvas.shapes[0].points]
current = window.current_image_id
press(window.canvas, Qt.Key.Key_Right)
after = [list(map(float, p)) for p in window.canvas.shapes[0].points]
check("arrow with a selection does not navigate",
      window.current_image_id == current, window.current_image_id)
check("arrow with a selection nudges the shape", before != after, (before, after))

# Explicit navigation still works with a selection.
window.navigateImage(-1)
check("navigateImage works with a selection",
      window.current_image_id == image_ids[-2], window.current_image_id)

# Mid-draw, arrows must not navigate.
window.canvas.select_shapes(shapes=[])
window.canvas.loadShapes([])
window.canvas._drawing_override = True
_original_is_drawing = type(window.canvas).is_drawing


class _DrawingStub:
    """Pretend a shape is being drawn without touching the real canvas."""

    def __get__(self, obj, objtype=None):
        return True


type(window.canvas).is_drawing = _DrawingStub()
try:
    current = window.current_image_id
    press(window.canvas, Qt.Key.Key_Right)
    check("arrow does nothing mid-draw",
          window.current_image_id == current, window.current_image_id)
finally:
    type(window.canvas).is_drawing = _original_is_drawing

# ------------------------------------------------- filtered navigation
window.sidebar.image_grid.search_input.setText("ap")
app.processEvents()
visible = window.sidebar.visibleImageIds()
check("filter narrows the visible set",
      visible == [image_ids[0], image_ids[2]], visible)

window.loadImage(image_ids[0])
app.processEvents()
press(window.canvas, Qt.Key.Key_Right)
check("navigation follows the filtered set",
      window.current_image_id == image_ids[2], window.current_image_id)
press(window.canvas, Qt.Key.Key_Right)
check("navigation clamps inside the filtered set",
      window.current_image_id == image_ids[2], window.current_image_id)
window.sidebar.image_grid.search_input.setText("")
app.processEvents()

# ------------------------------------------- focus-independent navigation
# Regression: navigation used to require clicking the canvas first, because
# the filter lived on the canvas and Qt only sends keys to the focused widget.
grid = window.sidebar.image_grid
window.loadImage(image_ids[0])
app.processEvents()

check("canvas takes focus after loading an image",
      window.canvas.hasFocus(), app.focusWidget())

check("arrow navigates from a toolbar button",
      focus_and_press(window, grid.grid_btn), window.current_image_id)
check("arrow navigates from the image grid",
      focus_and_press(window, grid.list_view), window.current_image_id)
check("arrow navigates from the zoom widget",
      focus_and_press(window, window.zoom_widget), window.current_image_id)
check("arrow navigates from the canvas",
      focus_and_press(window, window.canvas), window.current_image_id)

# Widgets that own the arrow keys must keep them.
grid.search_input.clear()
check("arrow does not navigate from the search box",
      not focus_and_press(window, grid.search_input), window.current_image_id)
check("search box keeps its caret",
      grid.search_input.cursorPosition() == 0, grid.search_input.cursorPosition())
check("arrow does not navigate from a combo box",
      not focus_and_press(window, grid.split_filter), window.current_image_id)
check("arrow does not navigate from the labels list",
      not focus_and_press(window, window.label_list.list_widget),
      window.current_image_id)

# A modal dialog blocks navigation, so the image cannot change behind it.
from PySide6.QtWidgets import QDialog, QPushButton, QVBoxLayout

_dialog = QDialog(window)
_layout = QVBoxLayout(_dialog)
_button = QPushButton("OK")
_layout.addWidget(_button)
_dialog.setModal(True)
_dialog.show()
_button.setFocus()
app.processEvents()
_current = window.current_image_id
QTest.keyClick(_button, Qt.Key.Key_Right)
app.processEvents()
check("arrow does not navigate while a dialog is open",
      window.current_image_id == _current, window.current_image_id)
_dialog.close()
app.processEvents()

# ------------------------------------------------------ last-seen persist
window.loadImage(image_ids[1])
app.processEvents()
check("loading an image records it",
      dbm.get_last_image_id(project_id) == image_ids[1],
      dbm.get_last_image_id(project_id))
check("grid marks the last-seen image",
      window.sidebar.image_grid.model.last_seen_id == image_ids[1],
      window.sidebar.image_grid.model.last_seen_id)
check("last-seen exposes a model role",
      window.sidebar.image_grid.model.data(
          window.sidebar.image_grid.model.index(1, 0), Qt.UserRole + 2) is True,
      "role not set")

window.annotations_dirty = False
window.close()

# Reopening restores the same image.
restored = new_window()
restored.loadProject(project_id)
app.processEvents()
app.processEvents()
check("reopening restores the last image",
      restored.current_image_id == image_ids[1], restored.current_image_id)
check("restored image is marked",
      restored.sidebar.image_grid.model.last_seen_id == image_ids[1],
      restored.sidebar.image_grid.model.last_seen_id)
restored.annotations_dirty = False
restored.close()

# A stale id must not break opening a project.
dbm.set_last_image_id(project_id, 999999)
stale = new_window()
stale.loadProject(project_id)
app.processEvents()
app.processEvents()
check("stale last image still opens the project",
      stale.current_project_id == project_id, stale.current_project_id)
check("stale last image leaves no image open",
      stale.current_image_id is None, stale.current_image_id)
check("stale last image clears the marker",
      stale.sidebar.image_grid.model.last_seen_id is None,
      stale.sidebar.image_grid.model.last_seen_id)
stale.annotations_dirty = False
stale.close()

# ------------------------------------------------- reveal scroll (startup order)
# The real startup loads the project from MainWindow.__init__ (via the welcome
# dialog) *before* the window is shown. Reproduce that ordering and assert the
# sidebar still scrolls to the last-seen image once shown. Use enough images
# that the target sits well past the first batch of a deferred (Batched) layout.
pid2 = dbm.create_project("ScrollNav", TMP / "projects")
base2 = Path(dbm.get_project(pid2)["base_path"])
(base2 / "images").mkdir(parents=True, exist_ok=True)
many_ids = []
for i in range(200):
    path = base2 / "images" / f"{i:03d}.png"
    pixmap = QPixmap(60, 40)
    pixmap.fill(QColor("white"))
    pixmap.save(str(path))
    many_ids.append(dbm.add_image(pid2, f"{i:03d}.png", f"images/{i:03d}.png", 60, 40))
dbm.set_last_image_id(pid2, many_ids[-1])

win = mw.MainWindow()      # no show() yet
win.resize(1100, 800)
win.loadProject(pid2)      # reveal happens here, before the window is shown
win.show()
app.processEvents()
app.processEvents()

lv = win.sidebar.image_grid.list_view
check("sidebar scrolls to the last-seen image",
      lv.verticalScrollBar().value() > 0,
      (lv.verticalScrollBar().value(), lv.verticalScrollBar().maximum()))
check("current index points at the last image",
      lv.currentIndex().row() == len(many_ids) - 1, lv.currentIndex().row())

win.annotations_dirty = False
win.close()

print()
if failures:
    print(f"FINAL_NAV_FAILED: {failures}")
    sys.exit(1)
print("FINAL_NAV_OK")
