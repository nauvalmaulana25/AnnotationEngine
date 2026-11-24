"""
AnnotationEngine Desktop - Model Manager

Resolves and fetches the model weights the auto-annotation services need.

Weights live in ``MODELS_DIR`` (``config.py``), which is the platform's app data
directory, so they survive reinstalls and are shared by every project.
"""
import os
from pathlib import Path
from typing import Callable, List, Optional

import requests

from annotation_engine.config import MODELS_DIR

# MobileSAM checkpoint published as an Ultralytics asset. Ultralytics ships a
# ``mobile_sam.pt`` builder, so no extra package is needed to run it.
MOBILE_SAM_FILENAME = "mobile_sam.pt"
MOBILE_SAM_URL = (
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/"
    + MOBILE_SAM_FILENAME
)
# Size of the published asset, used to reject truncated downloads.
MOBILE_SAM_SIZE = 40_728_226

ProgressCallback = Optional[Callable[[int, str], None]]


class ModelDownloadError(RuntimeError):
    """Raised when a model file is missing and cannot be fetched."""


def mobile_sam_path() -> Path:
    """Return the on-disk location of the MobileSAM checkpoint."""
    return Path(MODELS_DIR) / MOBILE_SAM_FILENAME


def _is_complete(path: Path, expected_size: int) -> bool:
    """Whether ``path`` holds a complete download of the expected size."""
    try:
        return path.is_file() and path.stat().st_size == expected_size
    except OSError:
        return False


def _report(progress_callback: ProgressCallback, percent: int, message: str):
    if progress_callback is not None:
        progress_callback(percent, message)


def download_mobile_sam(
    *, force: bool = False, progress_callback: ProgressCallback = None
) -> Path:
    """Download the MobileSAM checkpoint into ``MODELS_DIR``.

    The bytes go to a ``.part`` sibling first and are moved into place only
    once the size checks out, so an interrupted download can never leave a
    half-written checkpoint that later fails deep inside the model loader.
    """
    target = mobile_sam_path()
    if not force and _is_complete(target, MOBILE_SAM_SIZE):
        _report(progress_callback, 100, f"MobileSAM already present: {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")

    _report(progress_callback, 0, f"Downloading MobileSAM to {target}")
    try:
        with requests.get(MOBILE_SAM_URL, stream=True, timeout=60) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or MOBILE_SAM_SIZE)
            written = 0
            with open(partial, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written += len(chunk)
                    percent = int((written / max(total, 1)) * 100)
                    _report(
                        progress_callback,
                        min(percent, 99),
                        f"Downloading MobileSAM {written // 1024} KB",
                    )
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"Could not download MobileSAM from {MOBILE_SAM_URL}: {exc}"
        ) from exc

    if partial.stat().st_size != MOBILE_SAM_SIZE:
        size = partial.stat().st_size
        partial.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"MobileSAM download was incomplete ({size} of {MOBILE_SAM_SIZE} bytes)."
        )

    os.replace(partial, target)
    _report(progress_callback, 100, f"MobileSAM ready: {target}")
    return target


def ensure_mobile_sam(progress_callback: ProgressCallback = None) -> Path:
    """Return the MobileSAM checkpoint, downloading it when absent."""
    target = mobile_sam_path()
    if _is_complete(target, MOBILE_SAM_SIZE):
        return target
    return download_mobile_sam(progress_callback=progress_callback)


def mobile_sam_status() -> dict:
    """Describe the local MobileSAM state without touching the network."""
    target = mobile_sam_path()
    present = _is_complete(target, MOBILE_SAM_SIZE)
    return {
        "path": target,
        "present": present,
        "size": target.stat().st_size if target.is_file() else 0,
        "expected_size": MOBILE_SAM_SIZE,
    }


# YOLO weight presets offered for download. The files themselves can also be
# placed into MODELS_DIR manually (``list_yolo_models`` scans the directory).
YOLO_PRESET_URLS = {
    "yolo11n.pt": (
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/"
        "yolo11n.pt"
    ),
    "yolo11n-seg.pt": (
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/"
        "yolo11n-seg.pt"
    ),
    "yolo11n-pose.pt": (
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/"
        "yolo11n-pose.pt"
    ),
    "yolo11n-obb.pt": (
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/"
        "yolo11n-obb.pt"
    ),
    "yolo11n-cls.pt": (
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/"
        "yolo11n-cls.pt"
    ),
    "yolo11s.pt": (
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/"
        "yolo11s.pt"
    ),
}


def list_yolo_models() -> List[str]:
    """Return the full paths of ``*.pt`` checkpoints present in MODELS_DIR."""
    models_dir = Path(MODELS_DIR)
    if not models_dir.is_dir():
        return []
    return sorted(str(p) for p in models_dir.glob("*.pt"))


def yolo_model_path(name: str) -> Path:
    """Return the on-disk location of a YOLO checkpoint by filename."""
    return Path(MODELS_DIR) / Path(name).name


def download_yolo_model(
    name: str, *, progress_callback: ProgressCallback = None
) -> Path:
    """Download a preset YOLO checkpoint into MODELS_DIR.

    The bytes go to a ``.part`` sibling first and are moved into place only once
    the transfer matches the server's ``content-length``, so an interrupted
    download can never leave a half-written checkpoint behind.
    """
    url = YOLO_PRESET_URLS.get(Path(name).name)
    if url is None:
        raise ModelDownloadError(
            f"No download URL for YOLO model {name!r}; place the .pt file in "
            f"{MODELS_DIR} manually."
        )

    target = yolo_model_path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")

    _report(progress_callback, 0, f"Downloading YOLO model to {target}")
    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            written = 0
            with open(partial, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written += len(chunk)
                    if total:
                        percent = int((written / total) * 100)
                        _report(
                            progress_callback,
                            min(percent, 99),
                            f"Downloading {name} {written // 1024} KB",
                        )
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"Could not download YOLO model from {url}: {exc}"
        ) from exc

    if total and written != total:
        partial.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"YOLO download was incomplete ({written} of {total} bytes)."
        )

    os.replace(partial, target)
    _report(progress_callback, 100, f"YOLO model ready: {target}")
    return target
