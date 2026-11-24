"""
AnnotationEngine Desktop - YOLO Service

Detection / segmentation / pose / oriented-box inference backed by Ultralytics.
Mirrors ``MobileSAMService``'s shape: lazy import, cached model, device-aware,
with an out-of-memory fallback to CPU.
"""
import os
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from annotation_engine.services.device import (
    DEVICE_AUTO,
    DEVICE_CPU,
    describe_device,
    resolve_device,
    ultralytics_device,
)

ProgressCallback = Optional[Callable[[int, str], None]]

logger = logging.getLogger(__name__)

# Ultralytics does not expose keypoint names (``kpt_names`` is absent), so the
# COCO-17 names the pose models are trained on are hardcoded here.
COCO_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

# Keypoints scoring below this confidence are dropped (undetected keypoints
# report 0 confidence).
KEYPOINT_CONF_THRESHOLD = 0.0

# Segmentation masks with fewer than this many points are not drawable.
MIN_POLYGON_POINTS = 3


def _report(progress_callback: ProgressCallback, percent: int, message: str):
    if progress_callback is not None:
        progress_callback(percent, message)


def _numpy(tensor) -> np.ndarray:
    """Convert a torch tensor (or anything array-like) to a numpy array."""
    try:
        return tensor.cpu().numpy()
    except Exception:
        return np.asarray(tensor)


def _names_dict(names) -> Dict[int, str]:
    """Normalize Ultralytics ``names`` (dict or list) into ``{id: name}``."""
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    if isinstance(names, (list, tuple)):
        return {i: str(n) for i, n in enumerate(names)}
    return {}


class YOLOService:
    """Ultralytics YOLO inference for detection / segment / pose / OBB."""

    def __init__(self, model_path: str, *, device: str = DEVICE_AUTO):
        """
        Args:
            model_path: Path to a ``.pt`` checkpoint.
            device: Inference device preference (``auto``, ``cpu``, ``cuda:0``…).
                Resolved once here so a run cannot change device mid-flight.
        """
        self.model_path = str(model_path)
        self.device_preference = device
        self.device = resolve_device(device)
        self._model = None

    @property
    def device_description(self) -> str:
        """Human-readable name of the device in use."""
        return describe_device(self.device)

    def _is_cuda(self) -> bool:
        return self.device.startswith("cuda")

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------
    def load(self, progress_callback: ProgressCallback = None) -> dict:
        """Load the Ultralytics YOLO model, returning ``{"task", "names"}``.

        The import is deferred: ``ultralytics`` pulls in torch, which is far too
        slow to pay for at application startup.
        """
        if self._model is not None:
            return self._describe(self._model)

        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"YOLO model not found at {self.model_path}")

        _report(
            progress_callback, 100,
            f"Loading YOLO model on {self.device_description}",
        )
        from ultralytics import YOLO

        # An absolute path is required: Ultralytics otherwise resolves bare
        # filenames against its own global weights directory.
        self._model = YOLO(str(Path(self.model_path).resolve()))
        try:
            self._model.model.to(self.device)
        except Exception as exc:  # a device that vanished mid-run
            logger.warning(
                "Could not move YOLO model to %s (%s); falling back to CPU",
                self.device, exc,
            )
            self.device = DEVICE_CPU
        return self._describe(self._model)

    def _describe(self, model) -> dict:
        names = _names_dict(getattr(model, "names", None))
        task = getattr(model, "task", None)
        if task is None:
            task = getattr(model.model, "task", None) if hasattr(model, "model") else None
        return {"task": (task or "detect"), "names": names}

    def unload(self):
        """Drop the loaded model so the next run reloads it."""
        self._model = None

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def predict(
        self,
        image_path: str,
        labels: Optional[List[str]],
        conf: float,
        iou: float,
        progress_callback: ProgressCallback = None,
    ) -> List[dict]:
        """Run YOLO on one image and return LabelMe shape dicts.

        ``labels`` filters which class names are kept (``None`` keeps all).
        The task is read from the loaded model; a classify model produces no
        coordinates and is reported through :meth:`describe`.
        """
        info = self.load(progress_callback)
        model = self._model
        task = info.get("task") or "detect"
        names = info.get("names") or {}

        _report(progress_callback, 0, f"Running YOLO on {os.path.basename(image_path)}")

        results = self._predict(model, image_path, conf, iou)
        if not results:
            _report(progress_callback, 100, "No detections")
            return []

        wanted = set(labels) if labels is not None else None
        result = results[0]

        if task == "classify":
            # Image-level prediction has no coordinates to draw.
            _report(progress_callback, 100, "Classify models produce no shapes")
            return []
        if task == "segment":
            shapes = self._segment_shapes(result, names, wanted)
        elif task == "pose":
            shapes = self._pose_shapes(result, names, wanted)
        elif task == "obb":
            shapes = self._obb_shapes(result, names, wanted)
        else:
            shapes = self._detect_shapes(result, names, wanted)

        _report(progress_callback, 100, f"Found {len(shapes)} shape(s)")
        return shapes

    def _predict(self, model, image_path: str, conf: float, iou: float):
        """Run ``predict`` on the resolved device, falling back on OOM."""
        options = dict(
            source=str(image_path), conf=float(conf), iou=float(iou), verbose=False
        )
        try:
            return model.predict(device=ultralytics_device(self.device), **options)
        except Exception as exc:
            if not self._is_cuda() or not self._is_out_of_memory(exc):
                raise
            logger.warning("CUDA out of memory during YOLO; retrying on CPU: %s", exc)
            self._release_cuda(model)
            self.device = DEVICE_CPU
            return model.predict(device=DEVICE_CPU, **options)

    @staticmethod
    def _is_out_of_memory(exc: Exception) -> bool:
        if type(exc).__name__ in ("OutOfMemoryError", "CudaOutOfMemoryError"):
            return True
        return "out of memory" in str(exc).lower()

    def _release_cuda(self, model):
        try:
            model.model.to(DEVICE_CPU)
        except Exception:
            pass
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Result conversion
    # ------------------------------------------------------------------
    @staticmethod
    def _keep(cls_id: int, names: Dict[int, str], wanted: Optional[set]) -> bool:
        name = names.get(int(cls_id), "")
        return wanted is None or name in wanted

    def _detect_shapes(self, result, names, wanted) -> List[dict]:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        try:
            xyxy = _numpy(boxes.xyxy)
            confs = _numpy(boxes.conf)
            classes = _numpy(boxes.cls)
        except Exception:
            return []

        shapes: List[dict] = []
        for i in range(len(xyxy)):
            cls_id = int(classes[i])
            if not self._keep(cls_id, names, wanted):
                continue
            x1, y1, x2, y2 = (float(v) for v in xyxy[i][:4])
            shapes.append({
                "label": names.get(cls_id, str(cls_id)),
                "points": [[x1, y1], [x2, y2]],
                "group_id": None,
                "description": "",
                "shape_type": "rectangle",
                "flags": {},
                "mask": None,
            })
        return shapes

    def _segment_shapes(self, result, names, wanted) -> List[dict]:
        masks = getattr(result, "masks", None)
        boxes = getattr(result, "boxes", None)
        if masks is None or boxes is None:
            return []
        try:
            classes = _numpy(boxes.cls)
            polygons = masks.xy  # list of [M, 2] numpy arrays
        except Exception:
            return []

        shapes: List[dict] = []
        for i, polygon in enumerate(polygons or []):
            cls_id = int(classes[i]) if i < len(classes) else -1
            if not self._keep(cls_id, names, wanted):
                continue
            points = [[float(p[0]), float(p[1])] for p in polygon]
            if len(points) < MIN_POLYGON_POINTS:
                continue
            shapes.append({
                "label": names.get(cls_id, str(cls_id)),
                "points": points,
                "group_id": None,
                "description": "",
                "shape_type": "polygon",
                "flags": {},
                "mask": None,
            })
        return shapes

    def _pose_shapes(self, result, names, wanted) -> List[dict]:
        keypoints = getattr(result, "keypoints", None)
        boxes = getattr(result, "boxes", None)
        if keypoints is None or boxes is None:
            return []
        try:
            xy = _numpy(keypoints.xy)        # [N, 17, 2]
            conf = _numpy(keypoints.conf)    # [N, 17]
            classes = _numpy(boxes.cls)
        except Exception:
            return []

        shapes: List[dict] = []
        for person, (kpts, confs) in enumerate(zip(xy, conf)):
            cls_id = int(classes[person]) if person < len(classes) else -1
            if not self._keep(cls_id, names, wanted):
                continue
            base = names.get(cls_id, str(cls_id))
            for j, name in enumerate(COCO_KEYPOINTS):
                if j >= len(confs) or float(confs[j]) <= KEYPOINT_CONF_THRESHOLD:
                    continue
                x = float(kpts[j][0])
                y = float(kpts[j][1])
                if not np.isfinite(x) or not np.isfinite(y):
                    continue
                shapes.append({
                    "label": f"{base}_{name}",
                    "points": [[x, y]],
                    "group_id": person,
                    "description": "",
                    "shape_type": "point",
                    "flags": {},
                    "mask": None,
                })
        return shapes

    def _obb_shapes(self, result, names, wanted) -> List[dict]:
        obb = getattr(result, "obb", None)
        if obb is None:
            return []
        try:
            corners = _numpy(obb.xyxyxyxy)    # [N, 4, 2]
            classes = _numpy(obb.cls)
        except Exception:
            return []

        shapes: List[dict] = []
        for i in range(len(corners)):
            cls_id = int(classes[i]) if i < len(classes) else -1
            if not self._keep(cls_id, names, wanted):
                continue
            points = [[float(p[0]), float(p[1])] for p in corners[i][:4]]
            shapes.append({
                "label": names.get(cls_id, str(cls_id)),
                "points": points,
                "group_id": None,
                "description": "",
                "shape_type": "oriented_rectangle",
                "flags": {},
                "mask": None,
            })
        return shapes
