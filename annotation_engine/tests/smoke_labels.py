"""Headless smoke test for label persistence, rename, eye icons, coordinates."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_smoke_"))

# Redirect DB to a temp file before importing config-dependent modules.
import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtCore import QPointF, QPoint, Qt
from PySide6.QtGui import QPixmap, QColor, QContextMenuEvent
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


# ---------------------------------------------------------------- database
project_id = dbm.create_project("Smoke", TMP / "projects")
dbm.save_project_labels(project_id, [
    {"name": "cat", "color": "#ff0000", "visible": True},
    {"name": "dog", "color": "#00ff00", "visible": False},
])
rows = dbm.get_project_labels(project_id)
check("labels roundtrip", [r["name"] for r in rows] == ["cat", "dog"], rows)
check("label color persisted", rows[0]["color"] == "#ff0000", rows)
check("label visibility persisted", rows[1]["visible"] is False, rows)

img_id = dbm.add_image(project_id, "a.jpg", "images/a.jpg", 100, 100)
dbm.save_annotation(img_id, {
    "shapes": [
        {"label": "cat", "points": [[0, 0], [10, 10]], "shape_type": "rectangle"},
        {"label": "cat", "points": [[1, 1], [2, 2]], "shape_type": "point"},
    ],
    "imagePath": "a.jpg",
})
dbm.rename_label_in_project(project_id, "cat", "lion")
data = dbm.get_annotation(img_id)["data"]
check("annotation labels renamed",
      [s["label"] for s in data["shapes"]] == ["lion", "lion"], data)

# ------------------------------------------------------------ label list
from annotation_engine.ui.widgets.label_list import LabelListWidget
from annotation_engine.config import ICONS_DIR

check("eye icon exists", (ICONS_DIR / "eye.svg").exists())
check("eye-off icon exists", (ICONS_DIR / "eye-off.svg").exists())

ll = LabelListWidget()
emitted = []
ll.labelsChanged.connect(lambda: emitted.append(1))

ll.setLabels([
    {"name": "cat", "color": "#ef4444", "visible": True},
    {"name": "dog", "color": "#3b82f6", "visible": False},
])
check("setLabels bulk load", ll.getLabels() == ["cat", "dog"], ll.getLabels())
check("setLabels no persist noise", emitted == [], emitted)
check("state roundtrip", ll.getLabelState() == [
    {"name": "cat", "color": "#ef4444", "visible": True},
    {"name": "dog", "color": "#3b82f6", "visible": False},
], ll.getLabelState())

item = ll._findItem("dog")
widget = ll.list_widget.itemWidget(item, 0)
check("hidden label uses eye-off icon",
      widget.visible_cb.icon().isNull() is False)
check("hidden label tooltip",
      widget.visible_cb.toolTip() == "Show label shapes",
      widget.visible_cb.toolTip())

emitted.clear()
widget.visible_cb.setChecked(True)
check("visibility change persists", emitted == [1], emitted)
check("visibility state updated", ll.labels["dog"]["visible"] is True)
check("visible tooltip", widget.visible_cb.toolTip() == "Hide label shapes")

# rename (no collision) keeps color and row
emitted.clear()
color = ll.renameLabel("dog", "puppy")
check("rename keeps color", color == "#3b82f6", color)
check("rename updates state", "puppy" in ll.labels and "dog" not in ll.labels)
check("rename keeps row", ll._findItem("puppy") is not None)
check("rename emits persist", emitted == [1], emitted)
check("rename updates widget label",
      ll.list_widget.itemWidget(ll._findItem("puppy"), 0).label == "puppy")

# rename collision merges and keeps target color
color = ll.renameLabel("puppy", "cat")
check("merge keeps target color", color == "#ef4444", color)
check("merge removes old row", ll._findItem("puppy") is None)
check("merge keeps target only", ll.getLabels() == ["cat"], ll.getLabels())

# right-click anywhere on a row must open the row menu (buttons swallow it
# otherwise), so wire the row's forwarding through a stub.
from PySide6.QtCore import QPoint as _QPoint
from PySide6.QtGui import QContextMenuEvent

row_label_hits = []
ll.showLabelMenu = lambda label, gp: row_label_hits.append(label)
row_widget = ll.list_widget.itemWidget(ll._findItem("cat"), 0)
for target, target_name in (
    (row_widget.visible_cb, "eye button"),
    (row_widget.color_btn, "color button"),
    (row_widget.label_text, "label text"),
    (row_widget, "row body"),
):
    row_label_hits.clear()
    ev = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, _QPoint(6, 6),
        target.mapToGlobal(_QPoint(6, 6)),
    )
    app.sendEvent(target, ev)
    app.processEvents()
    check(f"right-click menus on {target_name}", row_label_hits == ["cat"],
          row_label_hits)

# ------------------------------------------------ per-layer instance rows
ll2 = LabelListWidget()
ll2.syncFromShapes([
    {"label": "cat", "shape_type": "rectangle", "points": [[0, 0], [10, 10]]},
    {"label": "dog", "shape_type": "rectangle", "points": [[0, 0], [10, 10]]},
    {"label": "cat", "shape_type": "rectangle", "points": [[20, 20], [30, 30]]},
    {"label": "cat", "shape_type": "polygon", "points": [[0, 0], [10, 0], [10, 10]]},
])
cat_item = ll2._findItem("cat")
check("overlapping label exposes instance children",
      cat_item.childCount() == 3, cat_item.childCount())
check("top layer is Layer 1 (top)",
      "Layer 1 (top)" in cat_item.child(0).text(0),
      cat_item.child(0).text(0))
check("top-first ordering by z-index",
      [cat_item.child(i).data(0, Qt.UserRole) for i in range(cat_item.childCount())]
      == [3, 2, 0],
      [cat_item.child(i).data(0, Qt.UserRole) for i in range(cat_item.childCount())])
dog_item = ll2._findItem("dog")
check("single instance gets one child", dog_item.childCount() == 1)

clicks = []
deletes = []
ll2.instanceClicked.connect(clicks.append)
ll2.instanceDeleteRequested.connect(deletes.append)
ll2.onItemClicked(cat_item.child(1), 0)
check("clicking an instance emits its index", clicks == [2], clicks)
ll2.instanceDeleteRequested.emit(2)
check("instance delete signal carries the index", deletes == [2], deletes)

# ---------------------------------------------------------------- canvas
from annotation_engine.ui.canvas import AnnotationCanvas

canvas = AnnotationCanvas()
pixmap = QPixmap(200, 150)
pixmap.fill(QColor("white"))
canvas.load_pixmap(pixmap=pixmap)
canvas.resize(200, 150)

rename_events = []
canvas.labelsRenamed.connect(rename_events.append)

check("shape context menu available",
      hasattr(canvas, "shape_context_menu")
      and any("Edit Label" in (a.text() or "")
              for a in canvas.shape_context_menu.actions()),
      [a.text() for a in getattr(canvas, "shape_context_menu", []).actions()])

menu_texts = [a.text() for a in canvas.shape_context_menu.actions()]
for expected in (
    "Duplicate Shapes", "Copy to Clipboard", "Delete Shapes",
    "Merge Shapes", "Lock Shapes", "Add Point to Edge",
    "Delete Selected Point",
):
    check(f"menu has {expected}", expected in menu_texts, menu_texts)
check("menu has Convert To submenu",
      any(a.menu() is not None for a in canvas.shape_context_menu.actions()),
      menu_texts)

canvas.loadShapes([
    {"label": "cat", "points": [[10, 10], [50, 50]], "shape_type": "rectangle"},
    {"label": "cat", "points": [[60, 60], [90, 90]], "shape_type": "rectangle"},
    {"label": "dog", "points": [[100, 100], [120, 120]], "shape_type": "rectangle"},
])
check("shapes loaded", len(canvas.shapes) == 3, len(canvas.shapes))

renamed = canvas.renameLabelCategory("cat", "lion")
check("category rename count", renamed == 2, renamed)
check("category rename labels",
      [s.label for s in canvas.shapes] == ["lion", "lion", "dog"],
      [s.label for s in canvas.shapes])
check("category rename undoable", canvas.canUndo())
check("labelsRenamed reports vacated", rename_events == [["cat"]], rename_events)

canvas.undo()
check("undo restores labels",
      [s.label for s in canvas.shapes] == ["cat", "cat", "dog"],
      [s.label for s in canvas.shapes])
canvas.redo()

# selected-shape rename
canvas.select_shapes(shapes=[canvas.shapes[2]])
selected = canvas.renameSelectedShapesLabel("wolf")
check("selected rename count", selected == 1, selected)
check("selected rename only target",
      [s.label for s in canvas.shapes] == ["lion", "lion", "wolf"],
      [s.label for s in canvas.shapes])
check("selected rename undoable", canvas.canUndo())

# Edit Label via the context menu action applies to the selection only.
edit_actions = [
    a for a in canvas.shape_context_menu.actions()
    if "Edit Label" in (a.text() or "")
]
check("single edit action", len(edit_actions) == 1, len(edit_actions))

shapes_changed = []
canvas.shapesChanged.connect(lambda: shapes_changed.append(1))
canvas.select_shapes(shapes=[canvas.shapes[0]])
canvas._askShapeFields = lambda shape, locked=(): {
    "label": "tiger", "flags": dict(shape.flags or {}),
    "group_id": shape.group_id, "description": shape.description or "",
}
edit_actions[0].trigger()
check("edit action renames selection",
      [s.label for s in canvas.shapes] == ["tiger", "lion", "wolf"],
      [s.label for s in canvas.shapes])
check("edit action emits shapesChanged", shapes_changed == [1], shapes_changed)
check("edit action undoable", canvas.canUndo())
canvas.undo()
check("edit undo restores label",
      [s.label for s in canvas.shapes] == ["lion", "lion", "wolf"],
      [s.label for s in canvas.shapes])

# menu duplicate / copy / paste / delete
canvas.select_shapes(shapes=[canvas.shapes[0]])
before = len(canvas.shapes)
canvas.duplicateSelectedShapes()
check("duplicate adds shapes", len(canvas.shapes) == before + 1, len(canvas.shapes))
check("duplicate selects copy", len(canvas.selected_shapes) == 1)
check("duplicate clears lock", all(not s.locked for s in canvas.selected_shapes))

check("copy fills clipboard", canvas.copySelectedShapes() == 1)
check("paste adds shapes",
      canvas.pasteShapes() == 1 and len(canvas.shapes) == before + 2,
      len(canvas.shapes))

canvas.select_shapes(shapes=[canvas.shapes[0]])
canvas.deleteSelected()
check("menu delete removes selection", len(canvas.shapes) == before + 1,
      len(canvas.shapes))

# convert rectangle -> polygon
canvas.loadShapes([
    {"label": "cat", "points": [[10, 10], [50, 50]], "shape_type": "rectangle"},
])
canvas.select_shapes(shapes=[canvas.shapes[0]])
check("convert to polygon", canvas.convertSelectedShapes("polygon"))
check("converted shape type", canvas.shapes[0].shape_type == "polygon",
      canvas.shapes[0].shape_type)
check("converted has 4 points", len(canvas.shapes[0].points) == 4)

# lock blocks deletion, unlock restores
canvas.select_shapes(shapes=list(canvas.shapes))
check("lock toggle", canvas.toggleSelectedShapesLock())
check("shapes locked", all(s.locked for s in canvas.selected_shapes))
locked_count = len(canvas.shapes)
canvas.deleteSelected()
check("locked shapes survive delete", len(canvas.shapes) == locked_count)
canvas.select_shapes(shapes=list(canvas.shapes))
canvas.toggleSelectedShapesLock()
check("unlock toggle", all(not s.locked for s in canvas.shapes))

# mouse_moved emits image coords
positions = []
canvas.mouse_moved.connect(lambda p: positions.append((p.x(), p.y())))
canvas.setTool("select")
canvas.show()
app.processEvents()
QTest.mouseMove(canvas, QPoint(40, 30))
app.processEvents()
check("mouse_moved emits", len(positions) > 0, positions)
check("mouse_moved not origin",
      any(x != 0 or y != 0 for x, y in positions), positions)
canvas.hide()

# ------------------------------------------------------------- main window
import annotation_engine.ui.main_window as mw

# The welcome dialog is modal; stub it so the window can be built headlessly.
mw.MainWindow.showWelcomeDialog = lambda self: None

window = mw.MainWindow()
window.current_project_id = project_id
window.current_image_id = None
window.status_bar.setCoordinates(0, 0)
window.onCanvasMouseMoved(QPointF(37.4, 88.6))
check("status bar coordinates",
      window.status_bar.coords_label.text() == "x: 37, y: 89",
      window.status_bar.coords_label.text())

window._suspend_label_persistence = True
window.label_list.setLabels([
    {"name": "cat", "color": "#ef4444", "visible": True},
])
window._suspend_label_persistence = False
window.onCanvasMouseMoved(QPointF(-5, -9))
check("negative coordinates",
      window.status_bar.coords_label.text() == "x: -5, y: -9",
      window.status_bar.coords_label.text())

# mouse_moved is wired to the status bar in setupConnections
window.canvas.mouse_moved.emit(QPointF(12.6, 34.2))
check("canvas->status bar wiring",
      window.status_bar.coords_label.text() == "x: 13, y: 34",
      window.status_bar.coords_label.text())

# label metadata persistence through the window
window.label_list.addLabel("bird", color="#a855f7")
saved = dbm.get_project_labels(project_id)
check("window persists labels",
      any(r["name"] == "bird" and r["color"] == "#a855f7" for r in saved), saved)

# ------------------------------------------------- color survives a "restart"
dbm.save_project_labels(project_id, [
    {"name": "cat", "color": "#123456", "visible": True},
    {"name": "dog", "color": "#abcdef", "visible": False},
])

restarted = mw.MainWindow()          # simulates a fresh app launch
restarted.loadProject(project_id)
reloaded = {r["name"]: r for r in dbm.get_project_labels(project_id)}
check("color survives reload", reloaded["cat"]["color"] == "#123456", reloaded)
check("visibility survives reload", reloaded["dog"]["visible"] is False, reloaded)
check("reload repopulates list",
      restarted.label_list.getLabelColors() == {
          "cat": "#123456", "dog": "#abcdef"},
      restarted.label_list.getLabelColors())
check("reload pushes colors to canvas",
      restarted.canvas.label_colors == {"cat": "#123456", "dog": "#abcdef"},
      restarted.canvas.label_colors)
restarted.close()

window.close()

# visibility is view state and must not pollute undo history
canvas.setTool("select")
canvas.setLabelVisibility("lion", False)
check("label hidden", all(not s.visible for s in canvas.shapes if s.label == "lion"))
history_before = list(canvas._undo_stack)
canvas.applyLabelVisibilities({"lion": True})
check("apply visibility restores", all(s.visible for s in canvas.shapes if s.label == "lion"))
check("apply visibility no new history", len(canvas._undo_stack) == len(history_before))

# ------------------------------------------------------------ rename dialog
from annotation_engine.ui.dialogs.rename_label import RenameLabelDialog

dlg = RenameLabelDialog(
    old_label="lion",
    existing_labels=["lion", "dog"],
    allow_scope=True,
    has_current_image=True,
)
check("dialog prefills name", dlg.newLabel() == "lion")
check("dialog default scope project", dlg.scope() == "project", dlg.scope())
check("dialog offers image scope", dlg.scope_combo.count() == 2)
dlg.name_edit.setText("dog")
check("dialog merge hint", "merge" in dlg.hint_label.text().lower(), dlg.hint_label.text())
dlg.name_edit.setText("  ")
check("dialog blank hint", "cannot be empty" in dlg.hint_label.text().lower())

shape_dlg = RenameLabelDialog(
    old_label="lion", existing_labels=["lion"], allow_scope=False
)
check("shape dialog hides scope", shape_dlg.scope_widget.isVisible() is False)
check("shape dialog scope is image", shape_dlg.scope() == "image", shape_dlg.scope())
shape_dlg.close()
dlg.close()

print()
if failures:
    print(f"FINAL_SMOKE_FAILED: {failures}")
    sys.exit(1)
print("FINAL_SMOKE_OK")
