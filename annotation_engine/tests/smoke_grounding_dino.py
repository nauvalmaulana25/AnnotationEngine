"""Headless smoke test for Grounding DINO (local/cloud) integration."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_gdino_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {extra}")
        failures.append(name)


def wait(ms=300):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ------------------------------------------------------- mode detection logic
from annotation_engine.services import grounding_dino as gd

# grounding_dino_mode reads the module-level can_run_local_grounding_dino.
_real_runner = gd.can_run_local_grounding_dino
gd.can_run_local_grounding_dino = lambda *a, **k: True
check("mode = local when hardware allows", gd.grounding_dino_mode() == "local")
gd.can_run_local_grounding_dino = lambda *a, **k: False
check("mode = cloud when hardware disallows", gd.grounding_dino_mode() == "cloud")
gd.can_run_local_grounding_dino = _real_runner


# ------------------------------------------------------- local service detect
import torch

class _Inputs:
    def __init__(self):
        self.input_ids = torch.tensor([[1, 2, 3]])
    def to(self, device):
        return self
    def keys(self):
        return ["input_ids"]
    def __getitem__(self, key):
        return getattr(self, key)


class FakeProcessor:
    def __init__(self, boxes, scores):
        self.boxes = torch.tensor(boxes, dtype=torch.float32)
        self.scores = torch.tensor(scores, dtype=torch.float32)
    def __call__(self, images=None, text=None, return_tensors=None):
        return _Inputs()
    def post_process_grounded_object_detection(
        self, outputs, input_ids, threshold=None, target_sizes=None
    ):
        return [{"boxes": self.boxes, "scores": self.scores}]


class FakeModel:
    def __call__(self, **inputs):
        return "outputs"
    def eval(self):
        pass


img = TMP / "gdino_test.png"
px = QPixmap(100, 80)
px.fill(QColor("white"))
px.save(str(img))

service = gd.LocalGroundingDINOService(device="cpu")
service._processor = FakeProcessor([[10, 20, 30, 40], [50, 60, 70, 80]], [0.9, 0.5])
service._model = FakeModel()
dets = service.detect(str(img), ["cat"], 0.3)
check("local detect returns boxes", len(dets) == 2, dets)
check("local detect labels prompt",
      [d["label"] for d in dets] == ["cat", "cat"],
      [d["label"] for d in dets])
check("local detect box format",
      dets[0]["box"] == [10.0, 20.0, 30.0, 40.0], dets)
check("local detect keeps score",
      abs(dets[1]["score"] - 0.5) < 1e-5, dets[1]["score"])

# Each prompt gets its own label.
service._processor = FakeProcessor([[10, 20, 30, 40]], [0.9])
dets = service.detect(str(img), ["cat", "dog"], 0.3)
check("local detect labels each prompt",
      [d["label"] for d in dets] == ["cat", "dog"],
      [d["label"] for d in dets])


# ------------------------------------------------------- result application
import annotation_engine.ui.main_window as mw

mw.MainWindow.showWelcomeDialog = lambda self: None
mw.MainWindow._prewarmAutoAnnotate = lambda self: None

_messages = []


def _record(kind):
    def handler(parent, title, text, *a, **k):
        _messages.append((kind, text))
        return 0
    return handler


mw.QMessageBox.warning = staticmethod(_record("warning"))
mw.QMessageBox.critical = staticmethod(_record("critical"))
mw.QMessageBox.information = staticmethod(_record("info"))

pid = dbm.create_project("GDINO", TMP / "projects")
base = Path(dbm.get_project(pid)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)
image_ids = []
for name in ("a.png", "b.png"):
    path = base / "images" / name
    pixmap = QPixmap(320, 240)
    pixmap.fill(QColor("white"))
    pixmap.save(str(path))
    image_ids.append(dbm.add_image(pid, name, f"images/{name}", 320, 240))

window = mw.MainWindow()
window.current_project_id = pid
window.loadImage(image_ids[0])
app.processEvents()

grid_refreshes = []
window._syncGridAnnotations = lambda: grid_refreshes.append(1)

window._applyGroundingDinoResult({"results": {
    image_ids[0]: [{"label": "cat", "score": 0.9, "box": [1, 2, 20, 30]}],
    image_ids[1]: [{"label": "dog", "score": 0.8, "box": [5, 6, 40, 50]}],
}, "mode": "cloud"})

canvas_shapes = window.canvas.getShapesData()
check("current image gets rectangle", len(canvas_shapes) == 1
      and canvas_shapes[0]["shape_type"] == "rectangle"
      and canvas_shapes[0]["label"] == "cat", canvas_shapes)
check("current image result undoable", window.canvas.canUndo())
other = dbm.get_annotation(image_ids[1])["data"]["shapes"]
check("other image written directly",
      len(other) == 1 and other[0]["label"] == "dog", other)
check("grid refreshed for others", len(grid_refreshes) == 1, grid_refreshes)

# Malformed box is skipped without crashing.
window._applyGroundingDinoResult({"results": {
    image_ids[0]: [{"label": "bad", "score": 0.9, "box": []}],
}, "mode": "local"})
check("empty box is skipped", len(window.canvas.getShapesData()) == 1)


# ------------------------------------------------- cloud forces single image
class FakeSync:
    calls = []

    def __init__(self, api_key):
        self.api_key = api_key

    def detect(self, image_path, text_prompt, threshold, progress_callback=None):
        FakeSync.calls.append({"path": str(image_path), "prompt": text_prompt})
        return [{"label": "cat", "score": 0.9, "box": [1, 1, 9, 9]}]


original_sync = mw.GroundingDINOSync
mw.GroundingDINOSync = FakeSync
FakeSync.calls = []
window._grounding_dino_mode = "cloud"
window._hfApiKey = lambda: "test-key"
window._local_grounding_dino = {}

window.runGroundingDINO({
    "prompts": ["cat"], "threshold": 0.3, "scope": "all", "mode": "cloud",
    "device": "cpu",
})
wait(700)
app.processEvents()

# Cloud forces the current image only: one call, and it's the open image.
check("cloud processes a single image", len(FakeSync.calls) == 1, FakeSync.calls)
if FakeSync.calls:
    check("cloud processes the current image",
          FakeSync.calls[0]["path"].endswith("a.png"), FakeSync.calls[0]["path"])

mw.GroundingDINOSync = original_sync

window.annotations_dirty = False
window.close()


# ----------------------------------------------------------- dialog scope gate
import annotation_engine.ui.dialogs.auto_annotate as aa

aa.grounding_dino_mode = lambda: "cloud"
dialog = aa.AutoAnnotateDialog()
check("cloud mode disables all-images scope", not dialog.gdino_scope.isEnabled())
check("cloud mode scope is current", dialog.gdino_scope.currentData() == "current")
dialog.close()

aa.grounding_dino_mode = lambda: "local"
dialog = aa.AutoAnnotateDialog()
check("local mode enables all-images scope", dialog.gdino_scope.isEnabled())
dialog.close()

# Prompt parsing + emission
dialog = aa.AutoAnnotateDialog()
emitted = []
dialog.runGroundingDINO.connect(emitted.append)
dialog.gdino_prompt.setText("person,  car , dog")
dialog._emitGroundingDino()
check("prompts are split and trimmed",
      emitted and emitted[0]["prompts"] == ["person", "car", "dog"], emitted)
check("emit carries threshold", emitted and "threshold" in emitted[0])
check("emit carries scope", emitted and "scope" in emitted[0])
check("emit carries mode", emitted and "mode" in emitted[0])
dialog.close()

print()
if failures:
    print(f"FINAL_GROUNDING_DINO_FAILED: {failures}")
    sys.exit(1)
print("FINAL_GROUNDING_DINO_OK")