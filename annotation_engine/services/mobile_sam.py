"""
AnnotationEngine Desktop - MobileSAM Service

Box-prompted segmentation backed by Ultralytics' MobileSAM build. Ultralytics
ships the ``mobile_sam.pt`` architecture and its downloader, so no additional
package beyond ``ultralytics`` (already a dependency) is required.
"""
import os
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from annotation_engine.services.device import (
    DEVICE_AUTO,
    DEVICE_CPU,
    describe_device,
    resolve_device,
    ultralytics_device,
)
from annotation_engine.services.model_manager import (
    ModelDownloadError,
    ensure_mobile_sam,
    mobile_sam_path,
    mobile_sam_status,
)

ProgressCallback = Optional[Callable[[int, str], None]]

logger = logging.getLogger(__name__)

# Minimum contour area in pixels; drops speckle the model sometimes emits.
MIN_MASK_AREA = 16.0
# Contour simplification, as a fraction of the contour perimeter.
CONTOUR_EPSILON_RATIO = 0.002


def _report(progress_callback: ProgressCallback, percent: int, message: str):
    if progress_callback is not None:
        progress_callback(percent, message)


def mask_to_polygon(mask: np.ndarray) -> List[List[float]]:
    """Convert a binary mask into a simplified polygon.

    The canvas renders polygons (it has no mask renderer), and LabelMe reads
    polygons natively, so this keeps generated shapes visible and editable.
    Returns an empty list when the mask has no usable contour.
    """
    binary = (np.asarray(mask) > 0.5).astype(np.uint8)
    contours, _ = cv2.findContours(
        binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return []

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < MIN_MASK_AREA:
        return []

    epsilon = CONTOUR_EPSILON_RATIO * cv2.arcLength(contour, True)
    simplified = cv2.approxPolyDP(contour, epsilon, True)

    points = [[float(pt[0][0]), float(pt[0][1])] for pt in simplified]
    # A polygon needs at least three points to be drawable.
    return points if len(points) >= 3 else []


class MobileSAMService:
    """MobileSAM instance segmentation driven by bounding-box prompts."""

    def __init__(self, model_path: Optional[str] = None, *, auto_download: bool = True,
                 device: str = DEVICE_AUTO):
        """
        Args:
            model_path: Path to the ``mobile_sam.pt`` checkpoint. Defaults to
                ``MODELS_DIR/mobile_sam.pt``.
            auto_download: Fetch the checkpoint when it is missing.
            device: Inference device preference (``auto``, ``cpu``, ``cuda:0``…).
                Resolved once here so a run cannot change device mid-flight.
        """
        self.model_path = str(model_path or mobile_sam_path())
        self.auto_download = auto_download
        self.device_preference = device
        self.device = resolve_device(device)
        self._model = None
        # Filled by the last segment_from_boxes / segment_labeled call.
        self.last_skipped: List[int] = []
        self.last_skipped_labels: List[str] = []

    @property
    def device_description(self) -> str:
        """Human-readable name of the device in use."""
        return describe_device(self.device)

    def _is_cuda(self) -> bool:
        return self.device.startswith("cuda")

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------
    @staticmethod
    def status() -> dict:
        """Report whether the checkpoint is present, without loading it."""
        return mobile_sam_status()

    def ensure_model(self, progress_callback: ProgressCallback = None):
        """Return the checkpoint path, downloading it when allowed."""
        if os.path.isfile(self.model_path):
            return self.model_path
        if not self.auto_download:
            raise FileNotFoundError(
                f"MobileSAM model not found at {self.model_path}. "
                "Enable automatic download or place the file there manually."
            )
        _report(progress_callback, 0, "Preparing MobileSAM model")
        try:
            path = ensure_mobile_sam(progress_callback)
        except ModelDownloadError as exc:
            raise FileNotFoundError(str(exc)) from exc
        self.model_path = str(path)
        return self.model_path

    def load(self, progress_callback: ProgressCallback = None):
        """Load the Ultralytics SAM wrapper, reusing it across calls.

        The import is deferred: ``ultralytics`` pulls in torch, which is far too
        slow to pay for at application startup.
        """
        if self._model is not None:
            return self._model

        path = self.ensure_model(progress_callback)
        _report(
            progress_callback, 100,
            f"Loading MobileSAM on {self.device_description}"
        )
        from ultralytics import SAM

        # An absolute path is required: Ultralytics otherwise resolves bare
        # filenames against its own global weights directory, which belongs to
        # whatever project first ran it.
        self._model = SAM(str(Path(path).resolve()))
        self._move_to_device(self._model)
        return self._model

    def _move_to_device(self, model):
        """Place the network on the resolved device before the first predict.

        Ultralytics loads on CPU and migrates lazily, which makes the first
        image pay the transfer on top of the encoder pass.
        """
        try:
            model.model.to(self.device)
        except Exception as exc:  # e.g. a device that vanished mid-run
            logger.warning(
                "Could not move MobileSAM to %s (%s); falling back to CPU",
                self.device, exc,
            )
            self.device = DEVICE_CPU
            try:
                model.model.to(DEVICE_CPU)
            except Exception:
                pass

    def unload(self):
        """Drop the loaded model so the next run reloads it."""
        self._model = None

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def segment_from_boxes(
        self,
        image: np.ndarray,
        boxes: List[List[float]],
        progress_callback: ProgressCallback = None,
        min_score: float = 0.0,
    ) -> List[np.ndarray]:
        """Segment an image from ``[x1, y1, x2, y2]`` box prompts.

        Args:
            image: BGR image as a numpy array.
            boxes: Boxes in original image pixel coordinates.
            progress_callback: Optional ``(percent, message)`` reporter.
            min_score: Masks whose confidence is below this value are skipped
                (returned as all-zero masks). The model does not always report
                scores, in which case every mask is kept.

        Returns:
            One boolean mask per input box, in the same order, so a mask can
            always be traced back to the box that prompted it.
        """
        self.last_skipped: List[int] = []
        if not boxes:
            return []

        model = self.load(progress_callback)
        _report(progress_callback, 0, f"Segmenting {len(boxes)} box(es)")

        results = self._predict(model, image, boxes)
        if not results:
            return [np.zeros(image.shape[:2], dtype=bool) for _ in boxes]

        height, width = image.shape[:2]
        masks = results[0].masks
        if masks is None or len(masks) == 0:
            _report(progress_callback, 100, "No masks produced")
            self.last_skipped = list(range(len(boxes)))
            return [np.zeros((height, width), dtype=bool) for _ in boxes]

        arrays = masks.data.cpu().numpy()
        if len(arrays) != len(boxes):
            # Should not happen now that predict runs with conf=0, but a
            # shortened list would silently misalign masks with prompts.
            logger.warning(
                "MobileSAM returned %d masks for %d boxes; treating as unusable",
                len(arrays), len(boxes),
            )
            self.last_skipped = list(range(len(boxes)))
            return [np.zeros((height, width), dtype=bool) for _ in boxes]

        keep = self._scoreMask(results[0], len(arrays), min_score)
        self.last_skipped = [i for i, wanted in enumerate(keep) if not wanted]
        _report(progress_callback, 100, f"Generated {len(arrays)} mask(s)")

        output: List[np.ndarray] = []
        for array, wanted in zip(arrays, keep):
            if array.shape[:2] != (height, width):
                array = cv2.resize(
                    array.astype(np.float32),
                    (width, height),
                    interpolation=cv2.INTER_LINEAR,
                )
            # A filtered mask still occupies its slot, so the result stays
            # aligned with the prompt boxes.
            output.append((array > 0.5) if wanted else np.zeros((height, width), dtype=bool))
        return output

    def _predict(self, model, image: np.ndarray, boxes: List[List[float]]):
        """Run ``predict`` on the resolved device, falling back on OOM.

        A GPU that runs out of memory mid-run would otherwise fail the whole
        batch; retrying the image on CPU keeps the run productive.
        """
        prompts = [list(map(float, box)) for box in boxes]
        # conf=0 keeps every mask Ultralytics produced. Its own 0.25 filter
        # shortens the mask list, which would misalign masks with prompts.
        options = dict(
            source=image, bboxes=prompts, conf=0.0, verbose=False
        )
        try:
            return model.predict(
                device=ultralytics_device(self.device), **options
            )
        except Exception as exc:
            if not self._is_cuda() or not self._is_out_of_memory(exc):
                raise
            logger.warning(
                "CUDA out of memory during MobileSAM; retrying on CPU: %s", exc
            )
            self._release_cuda(model)
            self.device = DEVICE_CPU
            return model.predict(device=DEVICE_CPU, **options)

    @staticmethod
    def _is_out_of_memory(exc: Exception) -> bool:
        """Whether an exception is a CUDA out-of-memory error."""
        if type(exc).__name__ in ("OutOfMemoryError", "CudaOutOfMemoryError"):
            return True
        return "out of memory" in str(exc).lower()

    def _release_cuda(self, model):
        """Move the model off the GPU and free its cached blocks."""
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

    @staticmethod
    def _scoreMask(result, count: int, min_score: float) -> List[bool]:
        """Return a keep-flag per mask, filtered by confidence when available."""
        if min_score <= 0 or count == 0:
            return [True] * count
        boxes = getattr(result, "boxes", None)
        if boxes is None or getattr(boxes, "conf", None) is None:
            return [True] * count
        try:
            scores = boxes.conf.cpu().numpy().tolist()
        except (AttributeError, RuntimeError):
            return [True] * count
        if len(scores) != count:
            return [True] * count
        return [float(score) >= min_score for score in scores]

    def segment(
        self,
        image_path: str,
        boxes: List[List[float]],
        progress_callback: ProgressCallback = None,
        min_score: float = 0.0,
    ) -> List[np.ndarray]:
        """Segment an image file from box prompts."""
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Failed to load image: {image_path}")
        return self.segment_from_boxes(
            image, boxes, progress_callback, min_score=min_score
        )

    def segment_polygons(
        self,
        image_path: str,
        boxes: List[List[float]],
        progress_callback: ProgressCallback = None,
        min_score: float = 0.0,
    ) -> List[List[List[float]]]:
        """Segment an image file and return one polygon per box.

        Boxes whose mask has no usable contour are skipped, so the result may
        be shorter than ``boxes``.
        """
        masks = self.segment(
            image_path, boxes, progress_callback, min_score=min_score
        )
        polygons = []
        for mask in masks:
            polygon = mask_to_polygon(mask)
            if polygon:
                polygons.append(polygon)
        return polygons

    def segment_labeled(
        self,
        image_path: str,
        boxes: List[List[float]],
        labels: List[str],
        progress_callback: ProgressCallback = None,
        min_score: float = 0.0,
    ) -> List[Tuple[int, str, List[List[float]]]]:
        """Segment boxes and pair each mask with its prompt.

        Unlike :meth:`segment_polygons` this keeps the prompt order, so a mask
        can be traced back to the box that produced it (the caller needs that
        to drop the source box afterwards).

        Returns:
            ``(prompt_index, label, polygon)`` per usable mask. Boxes whose mask
            has no drawable contour are omitted.

        ``self.last_skipped_labels`` records the labels of the omitted boxes so
        the caller can report them instead of losing them silently.
        """
        masks = self.segment(
            image_path, boxes, progress_callback, min_score=min_score
        )
        results: List[Tuple[int, str, List[List[float]]]] = []
        skipped: List[str] = []
        for index, mask in enumerate(masks):
            polygon = mask_to_polygon(mask)
            label = labels[index] if index < len(labels) else ''
            if not polygon:
                skipped.append(label or f"box {index}")
                continue
            results.append((index, label, polygon))
        self.last_skipped_labels = skipped
        return results

    def batch_segment(
        self,
        image_paths: List[str],
        boxes_list: List[List[List[float]]],
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, List[np.ndarray]]:
        """Segment several images, keyed by path."""
        results: Dict[str, List[np.ndarray]] = {}
        total = max(len(image_paths), 1)

        for i, (image_path, boxes) in enumerate(zip(image_paths, boxes_list)):
            _report(
                progress_callback,
                int((i / total) * 100),
                f"Processing {i + 1}/{total}: {os.path.basename(image_path)}",
            )
            try:
                results[image_path] = self.segment(image_path, boxes)
            except Exception as exc:
                print(f"Error segmenting {image_path}: {exc}")
                results[image_path] = []

        _report(progress_callback, 100, f"Completed {total} image(s)")
        return results
