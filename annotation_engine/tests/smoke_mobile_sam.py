"""Headless smoke test for the MobileSAM tab, model manager and wiring."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_sam_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer
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


def wait(ms=300):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ---------------------------------------------------------------- devices
import subprocess

_import_probe = subprocess.run(
    [sys.executable, "-c",
     "import sys, annotation_engine.services;"
     "print('torch' in sys.modules, 'transformers' in sys.modules)"],
    capture_output=True, text=True,
    cwd=str(Path(__file__).resolve().parent.parent.parent),
)
check("services package imports without torch/transformers",
      _import_probe.stdout.strip() == "False False",
      (_import_probe.stdout.strip(), _import_probe.stderr[-300:]))

from annotation_engine.services import device as dev

options = dev.list_devices()
check("auto is the first device option",
      options[0].id == dev.DEVICE_AUTO, [o.id for o in options])
check("cpu is always offered",
      any(o.id == dev.DEVICE_CPU for o in options), [o.id for o in options])
check("auto resolves to a real device",
      dev.resolve_device(dev.DEVICE_AUTO) in
      {o.id for o in options} | {"cuda:0", "mps", "cpu"},
      dev.resolve_device(dev.DEVICE_AUTO))
check("explicit cpu resolves to cpu", dev.resolve_device("cpu") == "cpu")
check("unknown device falls back to a usable one",
      dev.resolve_device("bogus") == dev.auto_device_id(),
      dev.resolve_device("bogus"))
check("impossible cuda index falls back to cpu",
      dev.resolve_device("cuda:99") == "cpu", dev.resolve_device("cuda:99"))
check("description names the device",
      "CPU" in dev.describe_device("cpu"), dev.describe_device("cpu"))
check("ultralytics device is a name for cpu",
      not isinstance(dev.ultralytics_device("cpu"), int),
      dev.ultralytics_device("cpu"))

# --------------------------------------------- CUDA out-of-memory fallback
from annotation_engine.services.mobile_sam import MobileSAMService


class _FakeCudaOOM(RuntimeError):
    pass


class _OomModel:
    """Predictor that fails once on CUDA, then succeeds on CPU."""

    def __init__(self):
        self.devices = []

        class _Inner:
            def to(self, device):
                pass

        self.model = _Inner()

    def predict(self, source=None, bboxes=None, device=None, verbose=False):
        self.devices.append(device)
        if device == 0:
            raise _FakeCudaOOM("CUDA out of memory. Tried to allocate 2.00 GiB")

        class _Masks:
            data = type("_T", (), {
                "cpu": lambda s: s,
                "numpy": lambda s: np.ones((1, 64, 64), np.float32),
            })()

            def __len__(self):
                return 1

        class _Result:
            masks = _Masks()

        return [_Result()]


_oom_service = MobileSAMService(device="cuda:0")
_oom_service._model = _OomModel()
_masks = _oom_service.segment_from_boxes(
    np.zeros((64, 64, 3), np.uint8), [[4, 4, 32, 32]]
)
check("oom retries on cpu", _oom_service._model.devices == [0, "cpu"],
      _oom_service._model.devices)
check("oom fallback switches the device", _oom_service.device == "cpu",
      _oom_service.device)
check("oom fallback still returns masks", len(_masks) == 1, len(_masks))


class _BoomModel(_OomModel):
    def predict(self, **kwargs):
        raise ValueError("something unrelated")


_boom_service = MobileSAMService(device="cuda:0")
_boom_service._model = _BoomModel()
try:
    _boom_service.segment_from_boxes(
        np.zeros((64, 64, 3), np.uint8), [[4, 4, 32, 32]]
    )
    check("non-oom errors propagate", False, "no exception raised")
except ValueError:
    check("non-oom errors propagate", True)

# ------------------------------------------------------------ model manager
from annotation_engine.services import model_manager as mm

status = mm.mobile_sam_status()
check("model path lives in MODELS_DIR",
      status["path"].parent == Path(config.MODELS_DIR), status["path"])
check("model filename", status["path"].name == "mobile_sam.pt",
      status["path"].name)
check("status reports expected size",
      status["expected_size"] == 40_728_226, status["expected_size"])
check("status present matches file",
      status["present"] == status["path"].is_file(), status)

# A truncated file must not be accepted as ready.
target = mm.mobile_sam_path()
backup = None
if target.exists():
    backup = target.read_bytes()
target.write_bytes(b"not a model")
check("truncated model is not present", not mm.mobile_sam_status()["present"])
if backup is not None:
    target.write_bytes(backup)

# ---------------------------------------------------------- mask to polygon
from annotation_engine.services.mobile_sam import mask_to_polygon

mask = np.zeros((100, 100), dtype=bool)
mask[20:60, 30:70] = True
polygon = mask_to_polygon(mask)
check("mask converts to polygon", len(polygon) >= 3, polygon)
xs = [p[0] for p in polygon]
ys = [p[1] for p in polygon]
check("polygon bounds match mask",
      (min(xs), max(xs), min(ys), max(ys)) == (30, 69, 20, 59),
      (min(xs), max(xs), min(ys), max(ys)))
check("empty mask yields no polygon",
      mask_to_polygon(np.zeros((50, 50), dtype=bool)) == [])
check("tiny speckle is dropped",
      mask_to_polygon(np.zeros((50, 50), dtype=bool)) == [])

# ---------------------------------------------------------------- dialog
from annotation_engine.ui.dialogs.auto_annotate import (
    ALL_LABELS, BOX_SOURCE_ALL, BOX_SOURCE_EXISTING, AutoAnnotateDialog,
)

dialog = AutoAnnotateDialog(labels=["bucket", "arm"], annotated_count=7)
check("label dropdown has All labels first",
      dialog.sam_label.itemData(0) == ALL_LABELS,
      [dialog.sam_label.itemText(i) for i in range(dialog.sam_label.count())])
check("label dropdown lists project labels",
      [dialog.sam_label.itemText(i) for i in range(1, dialog.sam_label.count())]
      == ["bucket", "arm"],
      [dialog.sam_label.itemText(i) for i in range(dialog.sam_label.count())])
check("source offers both options",
      [dialog.sam_source.itemData(i) for i in range(dialog.sam_source.count())]
      == [BOX_SOURCE_EXISTING, BOX_SOURCE_ALL])
check("all-images source shows the count",
      "(7)" in dialog.sam_source.itemText(1), dialog.sam_source.itemText(1))

# The device selector is shared by every tab and persisted.
check("dialog has a device selector", hasattr(dialog, "device_combo"))
check("device selector lists real devices",
      dialog.device_combo.count() >= 2,
      [dialog.device_combo.itemData(i) for i in range(dialog.device_combo.count())])
check("device selector defaults to auto",
      dialog.selectedDevice() == dev.DEVICE_AUTO, dialog.selectedDevice())
check("device detail names the device", bool(dialog.device_detail.text()),
      dialog.device_detail.text())

from PySide6.QtCore import QSettings
dialog.device_combo.setCurrentIndex(dialog.device_combo.findData(dev.DEVICE_CPU))
check("device choice is persisted",
      QSettings().value("auto_annotate/device") == dev.DEVICE_CPU,
      QSettings().value("auto_annotate/device"))
reopened = AutoAnnotateDialog(labels=["bucket"])
check("device choice is restored",
      reopened.selectedDevice() == dev.DEVICE_CPU, reopened.selectedDevice())
reopened.close()
# Leave the saved preference clean for other runs.
QSettings().setValue("auto_annotate/device", dev.DEVICE_AUTO)
dialog.device_combo.setCurrentIndex(dialog.device_combo.findData(dev.DEVICE_AUTO))

check("remove-boxes option defaults on", dialog.sam_remove_boxes.isChecked())

dialog.setLabels(["bucket", "arm", "tracks"])
check("setLabels keeps selection", dialog.sam_label.currentData() == ALL_LABELS)
dialog.sam_label.setCurrentIndex(dialog.sam_label.findData("arm"))
dialog.setLabels(["arm", "bucket"])
check("setLabels preserves chosen label",
      dialog.sam_label.currentData() == "arm", dialog.sam_label.currentData())

# Model status reflects the filesystem.
dialog.refreshModelStatus()
if mm.mobile_sam_status()["present"]:
    check("model status says ready", "ready" in dialog.sam_model_label.text(),
          dialog.sam_model_label.text())
    check("download button hidden when present",
          not dialog.sam_download_btn.isVisibleTo(dialog))
else:
    check("model status says missing",
          "not downloaded" in dialog.sam_model_label.text(),
          dialog.sam_model_label.text())
    check("download button shown when missing",
          dialog.sam_download_btn.isVisibleTo(dialog))

# Emitted options carry source and label.
emitted = []
dialog.runMobileSAM.connect(emitted.append)
dialog.sam_source.setCurrentIndex(1)
dialog.sam_label.setCurrentIndex(dialog.sam_label.findData("arm"))
dialog._emitMobileSAM()
check("run emits once", len(emitted) == 1, emitted)
if emitted:
    check("run emits source", emitted[0]["source"] == BOX_SOURCE_ALL, emitted[0])
    check("run emits label", emitted[0]["label"] == "arm", emitted[0])
    check("run emits device", "device" in emitted[0], emitted[0])
    check("run emits remove_boxes", "remove_boxes" in emitted[0], emitted[0])
    check("run emits image ids", "image_ids" in emitted[0], emitted[0])

dialog.close()

# ------------------------------------------------------- window integration
import annotation_engine.ui.main_window as mw

mw.MainWindow.showWelcomeDialog = lambda self: None

# Modal message boxes would block a headless run; record them instead.
_message_boxes = []


def _record_message(kind):
    def handler(parent, title, text, *args, **kwargs):
        _message_boxes.append((kind, title, text))
        return 0
    return handler


mw.QMessageBox.information = staticmethod(_record_message("info"))
mw.QMessageBox.warning = staticmethod(_record_message("warning"))
mw.QMessageBox.critical = staticmethod(_record_message("critical"))

project_id = dbm.create_project("SAM", TMP / "projects")
base = Path(dbm.get_project(project_id)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)
image_ids = []
for name in ("a.png", "b.png"):
    path = base / "images" / name
    pixmap = QPixmap(320, 240)
    pixmap.fill(QColor("white"))
    pixmap.save(str(path))
    image_ids.append(dbm.add_image(project_id, name, f"images/{name}", 320, 240))

dbm.save_annotation(image_ids[0], {
    "version": "5.4.1", "flags": {}, "imagePath": "../images/a.png",
    "imageData": None, "imageHeight": 240, "imageWidth": 320,
    "shapes": [
        {"label": "bucket", "points": [[10, 10], [100, 100]],
         "shape_type": "rectangle", "flags": {}, "group_id": None,
         "description": "", "mask": None},
        {"label": "arm", "points": [[120, 20], [200, 120]],
         "shape_type": "rectangle", "flags": {}, "group_id": None,
         "description": "", "mask": None},
        {"label": "arm", "points": [[210, 30], [260, 90]],
         "shape_type": "polygon", "flags": {}, "group_id": None,
         "description": "", "mask": None},
    ],
})
dbm.save_annotation(image_ids[1], {
    "version": "5.4.1", "flags": {}, "imagePath": "../images/b.png",
    "imageData": None, "imageHeight": 240, "imageWidth": 320,
    "shapes": [
        {"label": "bucket", "points": [[5, 5], [80, 80]],
         "shape_type": "rectangle", "flags": {}, "group_id": None,
         "description": "", "mask": None},
    ],
})

window = mw.MainWindow()
window.resize(1100, 800)
window.show()
app.processEvents()
window.current_project_id = project_id
window.loadImage(image_ids[0])
app.processEvents()

# Box helpers
check("_shapeBox on rectangle",
      window._shapeBox({"points": [[10, 20], [40, 60]]}) == [10.0, 20.0, 40.0, 60.0],
      window._shapeBox({"points": [[10, 20], [40, 60]]}))
check("_shapeBox on polygon uses bounds",
      window._shapeBox({"points": [[10, 50], [70, 20], [30, 90]]})
      == [10.0, 20.0, 70.0, 90.0],
      window._shapeBox({"points": [[10, 50], [70, 20], [30, 90]]}))
check("_shapeBox on empty", window._shapeBox({"points": []}) is None)
check("label filter matches", window._boxMatchesLabel({"label": "arm"}, "arm"))
check("label filter rejects", not window._boxMatchesLabel({"label": "bucket"}, "arm"))
check("all-labels filter accepts",
      window._boxMatchesLabel({"label": "bucket"}, ALL_LABELS))


class FakeService:
    """Stand-in for MobileSAMService that records the prompts it receives."""

    device_preference = "auto"
    device_description = "Fake GPU"

    def __init__(self):
        self.calls = []
        self.unloaded = False

    def unload(self):
        self.unloaded = True

    def segment_labeled(self, image_path, boxes, labels, progress_callback=None,
                        min_score=0.0):
        self.calls.append({"path": str(image_path), "boxes": boxes,
                           "labels": labels, "min_score": min_score})
        return [
            (index, label,
             [[float(b[0]), float(b[1])], [float(b[2]), float(b[1])],
              [float(b[2]), float(b[3])]])
            for index, (b, label) in enumerate(zip(boxes, labels))
        ]


fake = FakeService()
window._mobile_sam = fake

# Run on the current image only, filtered to the "arm" label, keeping boxes.
window.runMobileSam({
    "source": BOX_SOURCE_EXISTING, "label": "arm",
    "iou_threshold": 0.5, "remove_boxes": False, "image_ids": image_ids,
})
wait(600)
app.processEvents()

check("one image segmented", len(fake.calls) == 1, fake.calls)
if fake.calls:
    boxes = fake.calls[0]["boxes"]
    check("only arm boxes used as prompts", len(boxes) == 2, boxes)
    check("polygon shape contributes its bounds",
          [120.0, 20.0, 200.0, 120.0] in boxes, boxes)
    check("threshold forwarded", fake.calls[0]["min_score"] == 0.5,
          fake.calls[0]["min_score"])
    check("current image path used",
          fake.calls[0]["path"].endswith("a.png"), fake.calls[0]["path"])

canvas_shapes = window.canvas.getShapesData()
check("masks appended to canvas", len(canvas_shapes) == 5, len(canvas_shapes))
check("appended shapes are polygons",
      all(s["shape_type"] == "polygon" for s in canvas_shapes[-2:]),
      [s["shape_type"] for s in canvas_shapes])
check("appended shapes inherit the label",
      all(s["label"] == "arm" for s in canvas_shapes[-2:]),
      [s["label"] for s in canvas_shapes])
check("kept source boxes when unchecked",
      len([s for s in canvas_shapes if s["shape_type"] == "rectangle"]) == 2,
      [s["shape_type"] for s in canvas_shapes])
check("result is undoable", window.canvas.canUndo())

window._flushAutosave()
app.processEvents()
check("autosave persisted the masks",
      len(dbm.get_annotation(image_ids[0])["data"]["shapes"]) == 5,
      len(dbm.get_annotation(image_ids[0])["data"]["shapes"]))

# ------------------------------------------------- removing source boxes
# Start from a known state: two rectangles plus one hand-drawn polygon.
dbm.save_annotation(image_ids[0], {
    "version": "5.4.1", "flags": {}, "imagePath": "../images/a.png",
    "imageData": None, "imageHeight": 240, "imageWidth": 320,
    "shapes": [
        {"label": "bucket", "points": [[10, 10], [100, 100]],
         "shape_type": "rectangle", "flags": {}, "group_id": None,
         "description": "", "mask": None},
        {"label": "arm", "points": [[120, 20], [200, 120]],
         "shape_type": "rectangle", "flags": {}, "group_id": None,
         "description": "", "mask": None},
        {"label": "arm", "points": [[210, 30], [260, 90]],
         "shape_type": "polygon", "flags": {}, "group_id": None,
         "description": "", "mask": None},
    ],
})
window.canvas.loadShapes(dbm.get_annotation(image_ids[0])["data"]["shapes"])
window.canvas._resetHistory()
window.annotations_dirty = False

fake.calls.clear()
window.runMobileSam({
    "source": BOX_SOURCE_EXISTING, "label": ALL_LABELS,
    "iou_threshold": 0.0, "remove_boxes": True, "image_ids": image_ids,
})
wait(600)
app.processEvents()

after = window.canvas.getShapesData()
after_types = [s["shape_type"] for s in after]
check("removal dropped the rectangles",
      "rectangle" not in after_types, after_types)
check("removal kept the hand-drawn polygon",
      [210.0, 30.0] in [list(map(float, p)) for p in after[0]["points"]]
      if after and after[0]["shape_type"] == "polygon" else False,
      after_types)
check("removal added one polygon per box plus the kept hand-drawn one",
      len([s for s in after if s["shape_type"] == "polygon"]) == 4,
      after_types)
check("removal is undoable", window.canvas.canUndo())
window.canvas.undo()
app.processEvents()
check("undo restores the removed boxes",
      "rectangle" in [s["shape_type"] for s in window.canvas.getShapesData()],
      [s["shape_type"] for s in window.canvas.getShapesData()])
window.canvas.redo()
app.processEvents()

window._flushAutosave()
app.processEvents()

# ------------------------------------- all-images scope ignores selection
fake.calls.clear()
window.annotations_dirty = False
# The bug: the dialog passes whatever the user clicked, which is never empty.
window.runMobileSam({
    "source": BOX_SOURCE_ALL, "label": ALL_LABELS,
    "iou_threshold": 0.0, "remove_boxes": False,
    "image_ids": [image_ids[0]],
})
wait(600)
app.processEvents()

check("all-images scope segments every annotated image",
      len(fake.calls) == 2,
      [Path(c["path"]).name for c in fake.calls])
check("all-images scope ignores the grid selection",
      {Path(c["path"]).name for c in fake.calls} == {"a.png", "b.png"},
      [Path(c["path"]).name for c in fake.calls])
check("each box carries its own label",
      all(len(c["labels"]) == len(c["boxes"]) for c in fake.calls)
      and set(l for c in fake.calls for l in c["labels"]) == {"arm", "bucket"},
      [c["labels"] for c in fake.calls])

other = dbm.get_annotation(image_ids[1])["data"]["shapes"]
check("other image persisted new shapes", len(other) == 2, len(other))
check("other image shapes are polygons",
      all(s["shape_type"] == "polygon" for s in other[-1:]),
      [s["shape_type"] for s in other])
check("other image keeps its own label",
      other[-1]["label"] == "bucket", other[-1]["label"])
check("other image label file written",
      (base / "labels" / "b.json").exists())

# The grid must show the other image's new shapes, not its old ones.
grid_model = window.sidebar.image_grid.model
check("grid overlay refreshed for other images",
      len(grid_model.annotations.get(image_ids[1]) or []) == len(other),
      (len(grid_model.annotations.get(image_ids[1]) or []), len(other)))

# No matching boxes is reported, not crashed.
fake.calls.clear()
_message_boxes.clear()
window.runMobileSam({
    "source": BOX_SOURCE_EXISTING, "label": "nonexistent",
    "iou_threshold": 0.5, "remove_boxes": False,
    "image_ids": [image_ids[0]],
})
wait(400)
check("no matching boxes runs nothing", not fake.calls, fake.calls)
check("no matching boxes explains why",
      any("No boxes matched" in (t or "") for _, _, t in _message_boxes),
      _message_boxes)

# ------------------------------------------------------ device plumbing
check("dialog device choice reaches the service", fake.device_preference == "auto",
      fake.device_preference)
window._mobile_sam = fake
window.mobileSamService(device="cpu")
check("a new device preference replaces the service",
      not window._mobile_sam is fake, window._mobile_sam)
check("old service was unloaded", fake.unloaded)

window.annotations_dirty = False
window.close()

print()
if failures:
    print(f"FINAL_MOBILE_SAM_FAILED: {failures}")
    sys.exit(1)
print("FINAL_MOBILE_SAM_OK")
