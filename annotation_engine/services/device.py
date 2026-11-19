"""
AnnotationEngine Desktop - Device Selection

One place that decides where inference runs, shared by every auto-annotation
service. Torch is imported lazily so importing this module (and therefore the
services package) stays cheap at application startup.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

# Preference ids stored in settings and sent by the dialog.
DEVICE_AUTO = "auto"
DEVICE_CPU = "cpu"


@dataclass(frozen=True)
class DeviceOption:
    """A selectable inference device."""

    id: str
    label: str
    is_accelerator: bool


def _torch():
    """Import torch on demand; it costs seconds to load."""
    import torch

    return torch


def _cuda_available() -> bool:
    try:
        torch = _torch()
        return bool(torch.cuda.is_available() and torch.cuda.device_count() > 0)
    except Exception:  # torch missing or a broken CUDA install
        return False


def _mps_available() -> bool:
    try:
        torch = _torch()
        backend = getattr(torch.backends, "mps", None)
        return bool(backend is not None and backend.is_available())
    except Exception:
        return False


def _cuda_name(index: int) -> str:
    try:
        return _torch().cuda.get_device_name(index)
    except Exception:
        return f"CUDA device {index}"


def _cuda_memory_gb(index: int) -> Optional[float]:
    try:
        props = _torch().cuda.get_device_properties(index)
        return props.total_memory / (1024 ** 3)
    except Exception:
        return None


def auto_device_id() -> str:
    """Return the id ``auto`` resolves to on this machine."""
    if _cuda_available():
        return "cuda:0"
    if _mps_available():
        return "mps"
    return DEVICE_CPU


def list_devices() -> List[DeviceOption]:
    """List the devices a user can pick from, best first.

    ``auto`` is always first and reports what it would choose, so the default
    entry is informative rather than opaque.
    """
    options: List[DeviceOption] = []

    if _cuda_available():
        options.append(
            DeviceOption(
                id=DEVICE_AUTO,
                label=f"Auto ({_cuda_name(0)})",
                is_accelerator=True,
            )
        )
        for index in range(_torch().cuda.device_count()):
            options.append(
                DeviceOption(
                    id=f"cuda:{index}",
                    label=f"GPU {index}: {_cuda_name(index)}",
                    is_accelerator=True,
                )
            )
    elif _mps_available():
        options.append(
            DeviceOption(id=DEVICE_AUTO, label="Auto (Apple GPU)", is_accelerator=True)
        )
    else:
        options.append(
            DeviceOption(id=DEVICE_AUTO, label="Auto (CPU only)", is_accelerator=False)
        )

    if _mps_available() and not _cuda_available():
        options.append(
            DeviceOption(id="mps", label="Apple GPU (MPS)", is_accelerator=True)
        )

    options.append(DeviceOption(id=DEVICE_CPU, label="CPU", is_accelerator=False))
    return options


def resolve_device(preference: str = DEVICE_AUTO) -> str:
    """Resolve a preference id to a concrete device string.

    Unknown or unavailable choices fall back to CPU with a warning instead of
    raising, so a stale saved setting or a broken driver cannot stop a run.
    """
    preference = (preference or DEVICE_AUTO).strip().lower()

    if preference == DEVICE_CPU:
        return DEVICE_CPU

    if preference == DEVICE_AUTO:
        return auto_device_id()

    if preference.startswith("cuda"):
        if not _cuda_available():
            logger.warning(
                "CUDA device %r requested but CUDA is unavailable; using CPU",
                preference,
            )
            return DEVICE_CPU
        try:
            index = int(preference.split(":", 1)[1])
        except (IndexError, ValueError):
            index = 0
        if index >= _torch().cuda.device_count():
            logger.warning(
                "CUDA device %r requested but only %d present; using CPU",
                preference,
                _torch().cuda.device_count(),
            )
            return DEVICE_CPU
        return f"cuda:{index}"

    if preference == "mps":
        if _mps_available():
            return "mps"
        logger.warning("MPS requested but unavailable; using CPU")
        return DEVICE_CPU

    logger.warning("Unknown device preference %r; using auto", preference)
    return auto_device_id()


def torch_device(preference: str = DEVICE_AUTO):
    """Resolve a preference to a ``torch.device``."""
    return _torch().device(resolve_device(preference))


def ultralytics_device(preference: str = DEVICE_AUTO):
    """Convert a preference into what Ultralytics expects.

    Ultralytics wants a bare index for CUDA (``0``) and a name otherwise
    (``"cpu"``, ``"mps"``).
    """
    resolved = resolve_device(preference)
    if resolved.startswith("cuda:"):
        try:
            return int(resolved.split(":", 1)[1])
        except ValueError:
            return 0
    return resolved


def describe_device(preference: str = DEVICE_AUTO) -> str:
    """Human-readable summary for status messages and tooltips."""
    resolved = resolve_device(preference)
    if resolved.startswith("cuda:"):
        try:
            index = int(resolved.split(":", 1)[1])
            name = _cuda_name(index)
            memory = _cuda_memory_gb(index)
            if memory:
                return f"{name} ({memory:.1f} GB, CUDA)"
            return f"{name} (CUDA)"
        except Exception:
            return "CUDA GPU"
    if resolved == "mps":
        return "Apple GPU (MPS)"
    return "CPU"


def is_accelerator(preference: str = DEVICE_AUTO) -> bool:
    """Whether the resolved device is a GPU."""
    return resolve_device(preference) != DEVICE_CPU
