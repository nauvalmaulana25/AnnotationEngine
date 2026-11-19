"""Headless smoke test for canvas right-click rename and window rename flows."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_smoke2_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
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


from annotation_engine.ui.canvas import AnnotationCanvas

canvas = AnnotationCanvas()
pixmap = QPixmap(300, 300)
pixmap.fill(QColor("white"))
canvas.load_pixmap(pixmap=pixmap)
canvas.resize(300, 300)
canvas.setTool("select")
canvas.show()
app.processEvents()

canvas.loadShapes([
    {"label": "cat", "points": [[10, 10], [80, 80]], "shape_type": "rectangle"},
    {"label": "cat", "points": [[120, 120], [200, 200]], "shape_type": "rectangle"},
])
canvas.zoomFit()
app.processEvents()

menu_shown = {"count": 0, "texts": []}

# Right-click inside the second shape: LabelMe should select it and then open
# the shape context menu, where our actions live.
target = canvas.transform_image_point_to_widget(
    point=QPointF(160, 160), area=canvas.size()
)
target_point = QPoint(int(target.x()), int(target.y()))


def fake_exec(*args, **kwargs):
    menu_shown["count"] += 1
    menu_shown["texts"] = [a.text() for a in canvas.shape_context_menu.actions()]
    return None


canvas.shape_context_menu.exec = fake_exec

QTest.mousePress(canvas, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, target_point)
QTest.mouseRelease(canvas, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, target_point)
app.processEvents()

check("shape menu opened on right-click", menu_shown["count"] == 1, menu_shown)
check("shape menu has delete",
      "Delete Shapes" in menu_shown["texts"], menu_shown["texts"])
check("shape menu has edit label",
      any("Edit Label" in (t or "") for t in menu_shown["texts"]), menu_shown["texts"])
check("right-click selected the shape", len(canvas.selected_shapes) == 1,
      [getattr(s, 'label', None) for s in canvas.selected_shapes])

# Delete the right-clicked shape through the menu, then undo it.
delete_action = [a for a in canvas.shape_context_menu.actions()
                 if a.text() == "Delete Shapes"][0]
delete_action.trigger()
check("menu delete removes right-clicked shape", len(canvas.shapes) == 1,
      [s.label for s in canvas.shapes])
canvas.undo()
check("undo restores deleted shape", len(canvas.shapes) == 2)

# Edit Label only touches the selection, not both shapes.
canvas.select_shapes(shapes=[canvas.shapes[0]])
canvas._askShapeFields = lambda shape, locked=(): {
    "label": "dog", "flags": dict(shape.flags or {}),
    "group_id": shape.group_id, "description": shape.description or "",
}
edit_action = [a for a in canvas.shape_context_menu.actions()
               if "Edit Label" in (a.text() or "")][0]
edit_action.trigger()
check("only selected shape renamed",
      sorted(s.label for s in canvas.shapes) == ["cat", "dog"],
      [s.label for s in canvas.shapes])

# ------------------------------------------------- window-level rename flows
import annotation_engine.ui.main_window as mw
mw.MainWindow.showWelcomeDialog = lambda self: None

project_id = dbm.create_project("Smoke2", TMP / "projects")
img_id = dbm.add_image(project_id, "a.jpg", "images/a.jpg", 300, 300)
dbm.save_annotation(img_id, {
    "shapes": [
        {"label": "cat", "points": [[0, 0], [10, 10]], "shape_type": "rectangle"},
        {"label": "dog", "points": [[5, 5], [9, 9]], "shape_type": "rectangle"},
    ],
    "imagePath": "a.jpg",
})
dbm.save_project_labels(project_id, [
    {"name": "cat", "color": "#111111", "visible": True},
    {"name": "dog", "color": "#222222", "visible": True},
])

# Build the window without touching the welcome dialog.
window = mw.MainWindow()
window.current_project_id = project_id
window.current_image_id = None
window._suspend_label_persistence = True
window.label_list.setLabels(dbm.get_project_labels(project_id))
window._suspend_label_persistence = False
window.canvas.loadShapes([
    {"label": "cat", "points": [[0, 0], [10, 10]], "shape_type": "rectangle"},
    {"label": "dog", "points": [[5, 5], [9, 9]], "shape_type": "rectangle"},
])


class FakeDialog:
    """Stands in for the modal rename dialog."""

    def __init__(self, *args, new_label="", scope="project", **kwargs):
        self._new = new_label
        self._scope = scope

    def exec(self):
        return 1

    def newLabel(self):
        return self._new

    def scope(self):
        return self._scope


# Sidebar rename, project scope, merging into an existing label.
mw.RenameLabelDialog = lambda *a, **k: FakeDialog(new_label="dog", scope="project")
window.onLabelRename("cat")
check("merge removed old label row", "cat" not in window.label_list.getLabels(),
      window.label_list.getLabels())
check("merge kept target color",
      window.label_list.labelColor("dog") == "#222222",
      window.label_list.labelColor("dog"))
check("merge updated canvas",
      [s.label for s in window.canvas.shapes] == ["dog", "dog"],
      [s.label for s in window.canvas.shapes])
saved = dbm.get_annotation(img_id)["data"]
check("merge updated saved annotations",
      [s["label"] for s in saved["shapes"]] == ["dog", "dog"], saved["shapes"])
check("merge persisted labels",
      [r["name"] for r in dbm.get_project_labels(project_id)] == ["dog"],
      dbm.get_project_labels(project_id))

# Rename to a brand-new name keeps the original color.
window._suspend_label_persistence = True
window.label_list.setLabels([
    {"name": "dog", "color": "#222222", "visible": True},
    {"name": "cat", "color": "#111111", "visible": True},
])
window._suspend_label_persistence = False
window.canvas.loadShapes([
    {"label": "dog", "points": [[0, 0], [10, 10]], "shape_type": "rectangle"},
    {"label": "cat", "points": [[5, 5], [9, 9]], "shape_type": "rectangle"},
])
mw.RenameLabelDialog = lambda *a, **k: FakeDialog(new_label="lion", scope="project")
window.onLabelRename("cat")
check("rename preserves color",
      window.label_list.labelColor("lion") == "#111111",
      window.label_list.labelColor("lion"))
check("rename kept other label", "dog" in window.label_list.getLabels())

# Current-image-only scope must not rewrite saved annotations for other images.
other_id = dbm.add_image(project_id, "b.jpg", "images/b.jpg", 300, 300)
dbm.save_annotation(other_id, {
    "shapes": [{"label": "lion", "points": [[0, 0], [4, 4]], "shape_type": "rect"}],
    "imagePath": "b.jpg",
})
window.current_image_id = img_id
window.canvas.loadShapes([
    {"label": "lion", "points": [[0, 0], [10, 10]], "shape_type": "rectangle"},
])
mw.RenameLabelDialog = lambda *a, **k: FakeDialog(new_label="tiger", scope="image")
window.onLabelRename("lion")
check("image scope updates canvas",
      [s.label for s in window.canvas.shapes] == ["tiger"],
      [s.label for s in window.canvas.shapes])
check("image scope leaves other image alone",
      dbm.get_annotation(other_id)["data"]["shapes"][0]["label"] == "lion",
      dbm.get_annotation(other_id)["data"]["shapes"])

# Repeated renames through the canvas Edit Label must not leave stale labels.
window.canvas.loadShapes([
    {"label": "tiger", "points": [[0, 0], [10, 10]], "shape_type": "rectangle"},
])
window._label_counts = {}
window.syncLabelsFromShapes()
print("labels after loading tiger:", window.label_list.getLabels())

for new_label in ("zebra", "horse", "cow"):
    window.canvas.select_shapes(shapes=[window.canvas.shapes[0]])
    window.canvas._askShapeFields = (
        lambda shape, locked=(), _name=new_label: {
            "label": _name,
            "flags": dict(shape.flags or {}),
            "group_id": shape.group_id,
            "description": shape.description or "",
        }
    )
    window.canvas.editSelectedShapes()
    print(f"after rename -> {new_label}: {window.label_list.getLabels()}")

check("repeated rename keeps one label",
      [l for l in window.label_list.getLabels() if l in ("tiger", "zebra", "horse")] == [],
      window.label_list.getLabels())
check("repeated rename ends on final label",
      "cow" in window.label_list.getLabels(), window.label_list.getLabels())
check("repeated rename pruned from db",
      [r["name"] for r in dbm.get_project_labels(project_id)
       if r["name"] in ("tiger", "zebra", "horse")] == [],
      dbm.get_project_labels(project_id))

# The label kept for the other image survives, with its color.
check("label used by other image kept", "lion" in window.label_list.getLabels(),
      window.label_list.getLabels())
check("kept label keeps its color",
      window.label_list.labelColor("lion") == "#111111",
      window.label_list.labelColor("lion"))

window.annotations_dirty = False  # avoid the modal save prompt on close
window.close()

print()
if failures:
    print(f"FINAL_RENAME_FAILED: {failures}")
    sys.exit(1)
print("FINAL_RENAME_OK")
