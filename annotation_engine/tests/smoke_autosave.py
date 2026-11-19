"""Headless smoke test for autosave and standard LabelMe JSON output."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_autosave_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

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

project_id = dbm.create_project("Auto", TMP / "projects")
base = Path(dbm.get_project(project_id)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)
image_ids = []
for name in ("a.png", "b.png"):
    path = base / "images" / name
    pixmap = QPixmap(640, 480)
    pixmap.fill(QColor("white"))
    pixmap.save(str(path))
    image_ids.append(dbm.add_image(project_id, name, f"images/{name}", 640, 480))

window = mw.MainWindow()
window.resize(1100, 800)
window.show()
app.processEvents()
window.current_project_id = project_id
window.loadImage(image_ids[0])
app.processEvents()
app.processEvents()

canvas = window.canvas

# ---------------------------------------------------------------- toolbar
toolbar_texts = [a.text() for a in window.toolbar.actions() if not a.isSeparator()]
check("toolbar has no Save action",
      not any("Save" in (t or "") for t in toolbar_texts), toolbar_texts)
check("toolbar has no saveRequested signal",
      not hasattr(window.toolbar, "saveRequested"))
check("toolbar has no setSaveEnabled",
      not hasattr(window.toolbar, "setSaveEnabled"))

# File menu keeps a manual Save with Ctrl+S
file_menu = window.menuBar().actions()[0].menu()
save_actions = [a for a in file_menu.actions()
                if "Save" in (a.text() or "")]
check("file menu has manual Save", len(save_actions) == 1,
      [a.text() for a in file_menu.actions()])
check("manual Save keeps Ctrl+S",
      save_actions[0].shortcut().toString() == "Ctrl+S",
      save_actions[0].shortcut().toString())


# ------------------------------------------------------------ autosave fires
def load_shapes(shapes):
    canvas.loadShapes(shapes)
    canvas._last_snapshot = canvas._snapshot()
    canvas._undo_stack.clear()
    canvas._redo_stack.clear()


load_shapes([
    {"label": "eye", "points": [[10, 10], [60, 60]], "shape_type": "rectangle"},
    {"label": "eye", "points": [[80, 80], [130, 130]], "shape_type": "rectangle"},
    {"label": "nose", "points": [[150, 150], [200, 200]], "shape_type": "rectangle"},
])

canvas.select_shapes(shapes=[canvas.shapes[0]])
canvas.deleteSelected()
app.processEvents()

check("edit marks dirty", window.annotations_dirty)
check("edit schedules autosave", window._autosave_timer.isActive())

# Wait for the debounce to elapse without sleeping the UI.
window._flushAutosave()
app.processEvents()

check("autosave clears dirty", not window.annotations_dirty)
check("autosave wrote the database",
      len(dbm.get_annotation(image_ids[0])["data"]["shapes"]) == 2,
      dbm.get_annotation(image_ids[0])["data"]["shapes"])

# ------------------------------------------------------- labelme json output
label_path = base / "labels" / "a.json"
check("autosave wrote a label file", label_path.exists(), label_path)

payload = json.loads(label_path.read_text())
check("label file has LabelMe keys",
      list(payload.keys()) == ["version", "flags", "shapes", "imagePath",
                               "imageData", "imageHeight", "imageWidth"],
      list(payload.keys()))
check("label file version", payload["version"] == "5.4.1", payload["version"])
check("label file shape count", len(payload["shapes"]) == 2,
      len(payload["shapes"]))
check("label file imagePath points at images",
      payload["imagePath"] == "../images/a.png", payload["imagePath"])
check("label file image size",
      (payload["imageWidth"], payload["imageHeight"]) == (640, 480),
      (payload["imageWidth"], payload["imageHeight"]))
check("label file shape fields",
      set(payload["shapes"][0].keys()) == {
          "label", "points", "group_id", "description",
          "shape_type", "flags", "mask"},
      payload["shapes"][0].keys())
check("label file is indented",
      '\n  "' in label_path.read_text(), "not indented")

# LabelMe itself must be able to resolve the image path.
check("imagePath resolves from labels dir",
      (label_path.parent / payload["imagePath"]).resolve()
      == (base / "images" / "a.png").resolve())

# ------------------------------------------------- undo/redo keep working
check("undo available after edit", canvas.canUndo())
before_history = (len(canvas._undo_stack), len(canvas._redo_stack),
                  canvas.canUndo(), canvas.canRedo())

window.undo()
app.processEvents()
window._flushAutosave()
app.processEvents()
check("undo restores shape", len(canvas.shapes) == 3, len(canvas.shapes))
check("undo autosaved to db",
      len(dbm.get_annotation(image_ids[0])["data"]["shapes"]) == 3,
      dbm.get_annotation(image_ids[0])["data"]["shapes"])
check("undo autosaved to label file",
      len(json.loads(label_path.read_text())["shapes"]) == 3)

window.redo()
app.processEvents()
window._flushAutosave()
app.processEvents()
check("redo removes shape again", len(canvas.shapes) == 2, len(canvas.shapes))
check("redo autosaved to db",
      len(dbm.get_annotation(image_ids[0])["data"]["shapes"]) == 2)

# Saving repeatedly must not disturb the history stacks.
before = (len(canvas._undo_stack), len(canvas._redo_stack),
          canvas.canUndo(), canvas.canRedo())
for _ in range(10):
    window.annotations_dirty = True
    window.saveAnnotation(silent=True)
after = (len(canvas._undo_stack), len(canvas._redo_stack),
         canvas.canUndo(), canvas.canRedo())
check("history unchanged across saves", before == after, (before, after))

# ------------------------------------------------- switching images flushes
window._markDirty()
check("dirty before switch", window.annotations_dirty)
window.loadImage(image_ids[1])
app.processEvents()
check("switch flushed previous image",
      len(dbm.get_annotation(image_ids[0])["data"]["shapes"]) == 2)
check("switch cleared dirty", not window.annotations_dirty)
check("switch did not queue autosave",
      not window._autosave_timer.isActive())
check("new image has no shapes", len(window.canvas.shapes) == 0,
      len(window.canvas.shapes))
check("new image not written yet",
      not (base / "labels" / "b.json").exists())

# ------------------------------------------------------ manual save is loud
window.canvas.loadShapes(
    [{"label": "cat", "points": [[1, 1], [9, 9]], "shape_type": "rectangle"}]
)
window._markDirty()
window.saveAnnotation(silent=False)
app.processEvents()
check("manual save persists",
      len(dbm.get_annotation(image_ids[1])["data"]["shapes"]) == 1)
check("manual save wrote b.json", (base / "labels" / "b.json").exists())

window.annotations_dirty = False
window.close()

print()
if failures:
    print(f"FINAL_AUTOSAVE_FAILED: {failures}")
    sys.exit(1)
print("FINAL_AUTOSAVE_OK")
