"""Headless smoke test for YOLO service, dialog tab and wiring (no downloads)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_yolo_"))

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


# ------------------------------------------------------- service conversion
from annotation_engine.services.yolo_service import (
    COCO_KEYPOINTS, YOLOService,
)

check("COCO-17 keypoint names hardcoded", len(COCO_KEYPOINTS) == 17,
      len(COCO_KEYPOINTS))

service = YOLOService("/nonexistent/yolo11n.pt", device="cpu")

NAMES = {0: "person", 1: "car"}


class _Boxes:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = np.asarray(xyxy, dtype=np.float32)
        self.conf = np.asarray(conf, dtype=np.float32)
        self.cls = np.asarray(cls, dtype=np.float32)


class _DetectResult:
    def __init__(self, boxes):
        self.boxes = boxes


det = service._detect_shapes(
    _DetectResult(_Boxes(
        [[10, 10, 50, 60], [100, 20, 200, 90]],
        [0.9, 0.8], [0, 1],
    )),
    NAMES, None,
)
check("detect emits a rectangle per box", len(det) == 2, det)
check("detect rectangle uses corners",
      det[0]["shape_type"] == "rectangle"
      and det[0]["points"] == [[10.0, 10.0], [50.0, 60.0]], det[0])
check("detect labels from names",
      [s["label"] for s in det] == ["person", "car"], [s["label"] for s in det])

det_person = service._detect_shapes(
    _DetectResult(_Boxes(
        [[10, 10, 50, 60], [100, 20, 200, 90]],
        [0.9, 0.8], [0, 1],
    )),
    NAMES, {"person"},
)
check("detect filters to ticked classes",
      [s["label"] for s in det_person] == ["person"],
      [s["label"] for s in det_person])


class _Masks:
    def __init__(self, xy):
        self.xy = xy


class _SegResult:
    def __init__(self, xy, cls):
        self.masks = _Masks(xy)
        self.boxes = _Boxes(None, None, cls)


seg = service._segment_shapes(
    _SegResult(
        [np.array([[0, 0], [10, 0], [10, 10], [0, 10]], np.float32),
         np.array([[50, 50], [60, 50]], np.float32)],  # < 3 points: dropped
        [0, 1],
    ),
    NAMES, None,
)
check("segment converts masks to polygons", len(seg) == 1, seg)
check("segment drops degenerate contours",
      seg[0]["shape_type"] == "polygon" and len(seg[0]["points"]) == 4, seg)


class _Keypoints:
    def __init__(self, xy, conf):
        self.xy = np.asarray(xy, dtype=np.float32)
        self.conf = np.asarray(conf, dtype=np.float32)


class _PoseResult:
    def __init__(self, xy, conf, cls):
        self.keypoints = _Keypoints(xy, conf)
        self.boxes = _Boxes(None, None, cls)


pose = service._pose_shapes(
    _PoseResult(
        [[[5, 5], [6, 6]] + [[0, 0]] * 15],  # person 0: nose + left_eye
        [[0.9, 0.8] + [0.0] * 15],
        [0],
    ),
    NAMES, None,
)
check("pose emits one point per valid keypoint", len(pose) == 2, pose)
check("pose labels keypoint + class",
      [s["label"] for s in pose] == ["person_nose", "person_left_eye"],
      [s["label"] for s in pose])
check("pose groups keypoints per person",
      all(s["group_id"] == 0 for s in pose), [s["group_id"] for s in pose])
check("pose points are single-point shapes",
      all(s["shape_type"] == "point" for s in pose),
      [s["shape_type"] for s in pose])


class _Obb:
    def __init__(self, corners, cls):
        self.xyxyxyxy = np.asarray(corners, dtype=np.float32)
        self.cls = np.asarray(cls, dtype=np.float32)


class _ObbResult:
    def __init__(self, corners, cls):
        self.obb = _Obb(corners, cls)


obb = service._obb_shapes(
    _ObbResult([[[16.0, 303.0], [31.1, 287.8], [4.7, 261.6], [-10.4, 276.9]]],
               [0]),
    NAMES, None,
)
check("obb maps to oriented_rectangle", len(obb) == 1, obb)
check("obb keeps 4 raw corners (no clamp)",
      obb[0]["shape_type"] == "oriented_rectangle"
      and len(obb[0]["points"]) == 4
      and abs(obb[0]["points"][3][0] - (-10.4)) < 1e-3, obb[0])


# ------------------------------------------------------- predict + fake model
class _FakeModel:
    task = "detect"
    names = {0: "person", 1: "car"}

    def __init__(self):
        self.calls = []

        class _Inner:
            def to(self, device):
                pass

        self.model = _Inner()

    def predict(self, source=None, conf=None, iou=None, device=None,
                verbose=False):
        self.calls.append({"conf": conf, "iou": iou, "device": device})
        if conf == 0.0:  # sentinel for "no detections"
            return []
        return [_DetectResult(_Boxes(
            [[1, 1, 9, 9], [20, 20, 30, 30]], [0.9, 0.8], [0, 1]
        ))]


fake = _FakeModel()
service._model = fake
shapes = service.predict("/tmp/img.png", ["person"], 0.5, 0.4)
check("predict filters and forwards conf/iou",
      fake.calls and fake.calls[0]["conf"] == 0.5
      and fake.calls[0]["iou"] == 0.4, fake.calls)
check("predict returns only ticked classes",
      [s["label"] for s in shapes] == ["person"], [s["label"] for s in shapes])

service._model = _FakeModel()
empty = service.predict("/tmp/img.png", ["person"], 0.0, 0.4)
check("empty results do not crash", empty == [], empty)


# ------------------------------------------------------- classify is rejected
class _ClassifyModel(_FakeModel):
    task = "classify"


service._model = _ClassifyModel()
cls_shapes = service.predict("/tmp/img.png", None, 0.25, 0.45)
check("classify model produces no shapes", cls_shapes == [], cls_shapes)


# ------------------------------------------------------- model manager
from annotation_engine.services import model_manager as mm

models_dir = TMP / "models"
models_dir.mkdir(parents=True, exist_ok=True)
(models_dir / "yolo11n.pt").write_bytes(b"x")
(models_dir / "yolo11n-seg.pt").write_bytes(b"x")
(models_dir / "notes.txt").write_bytes(b"x")
original_models_dir = mm.MODELS_DIR
mm.MODELS_DIR = models_dir
try:
    listed = mm.list_yolo_models()
    check("list_yolo_models scans MODELS_DIR for .pt",
          sorted(Path(p).name for p in listed)
          == ["yolo11n-seg.pt", "yolo11n.pt"], listed)
    check("list_yolo_models ignores non-pt files",
          all(p.endswith(".pt") for p in listed), listed)
finally:
    mm.MODELS_DIR = original_models_dir

try:
    mm.download_yolo_model("not-a-real-model.pt")
    check("unknown preset raises", False, "no exception raised")
except mm.ModelDownloadError:
    check("unknown preset raises", True)


# ------------------------------------------------------- dialog tab
from annotation_engine.ui.dialogs.auto_annotate import AutoAnnotateDialog

dialog = AutoAnnotateDialog()
check("YOLO run disabled before load", not dialog.yolo_btn.isEnabled())

dialog.setYoloModelInfo("detect", {0: "person", 1: "car"})
check("YOLO label checkboxes populate from model names",
      sorted(dialog.yolo_label_boxes) == ["car", "person"],
      list(dialog.yolo_label_boxes))
check("YOLO labels default to all checked",
      sorted(dialog.selectedYoloLabels()) == ["car", "person"],
      dialog.selectedYoloLabels())
check("YOLO task label shows the task",
      "detect" in dialog.yolo_task_label.text(), dialog.yolo_task_label.text())
check("YOLO run enabled after load", dialog.yolo_btn.isEnabled())

dialog.setYoloModelInfo("classify", {0: "a", 1: "b"})
check("classify model keeps run disabled", not dialog.yolo_btn.isEnabled())
check("classify model reports unsupported",
      "not supported" in dialog.yolo_task_label.text(),
      dialog.yolo_task_label.text())
dialog.close()


# ------------------------------------------------------- window integration
import annotation_engine.ui.main_window as mw

mw.MainWindow.showWelcomeDialog = lambda self: None

_messages = []


def _record(kind):
    def handler(parent, title, text, *a, **k):
        _messages.append((kind, text))
        return 0
    return handler


mw.QMessageBox.warning = staticmethod(_record("warning"))
mw.QMessageBox.critical = staticmethod(_record("critical"))
mw.QMessageBox.information = staticmethod(_record("info"))

project_id = dbm.create_project("YOLO", TMP / "projects")
base = Path(dbm.get_project(project_id)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)
image_ids = []
for name in ("a.png", "b.png"):
    path = base / "images" / name
    pixmap = QPixmap(320, 240)
    pixmap.fill(QColor("white"))
    pixmap.save(str(path))
    image_ids.append(dbm.add_image(project_id, name, f"images/{name}", 320, 240))

window = mw.MainWindow()
window.current_project_id = project_id
window.loadImage(image_ids[0])
app.processEvents()

# Direct-write helper writes through the DB.
new_rect = {"label": "person", "points": [[1, 1], [20, 20]],
            "shape_type": "rectangle", "flags": {}, "group_id": None,
            "description": "", "mask": None}
new_point = {"label": "person_nose", "points": [[5, 5]],
             "shape_type": "point", "flags": {}, "group_id": 0,
             "description": "", "mask": None}

grid_refreshes = []
window._syncGridAnnotations = lambda: grid_refreshes.append(1)

window._applyYoloResult({"results": {
    image_ids[0]: [new_rect, new_point],
    image_ids[1]: [new_rect],
}})

canvas_shapes = window.canvas.getShapesData()
check("current image appended undoably",
      len(canvas_shapes) == 2 and window.canvas.canUndo(),
      len(canvas_shapes))
check("current image keeps the generated labels",
      sorted(s["label"] for s in canvas_shapes) == ["person", "person_nose"],
      [s["label"] for s in canvas_shapes])
other_shapes = dbm.get_annotation(image_ids[1])["data"]["shapes"]
check("other image written directly", len(other_shapes) == 1
      and other_shapes[0]["label"] == "person", other_shapes)
check("grid refreshed for other images", len(grid_refreshes) == 1,
      grid_refreshes)

# Cache keyed by (model_path, device).
s1 = window.yoloService("/m/yolo11n.pt", "cpu")
s2 = window.yoloService("/m/yolo11n.pt", "cpu")
s3 = window.yoloService("/m/yolo11n.pt", "cuda:0")
check("yolo service cached by path+device", s1 is s2 and s1 is not s3)

window.annotations_dirty = False
window.close()

print()
if failures:
    print(f"FINAL_YOLO_FAILED: {failures}")
    sys.exit(1)
print("FINAL_YOLO_OK")
