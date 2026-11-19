"""
AnnotationEngine Desktop - Services Package

Exports are lazy: importing this package must not pull in torch,
transformers or ultralytics, which together cost several seconds at startup.
Each name is imported on first access instead.
"""
import importlib
from typing import Dict, Tuple

# name -> (module, attribute)
_EXPORTS: Dict[str, Tuple[str, str]] = {
    'GroundingDINOService': ('.grounding_dino', 'GroundingDINOService'),
    'GroundingDINOSync': ('.grounding_dino', 'GroundingDINOSync'),
    'MobileSAMService': ('.mobile_sam', 'MobileSAMService'),
    'ModelDownloadError': ('.model_manager', 'ModelDownloadError'),
    'download_mobile_sam': ('.model_manager', 'download_mobile_sam'),
    'ensure_mobile_sam': ('.model_manager', 'ensure_mobile_sam'),
    'mobile_sam_path': ('.model_manager', 'mobile_sam_path'),
    'mobile_sam_status': ('.model_manager', 'mobile_sam_status'),
    'DINOv2KeypointService': ('.dinov2', 'DINOv2KeypointService'),
    'ExportService': ('.export_service', 'ExportService'),
    'JobQueue': ('.job_queue', 'JobQueue'),
    'JobWorker': ('.job_queue', 'JobWorker'),
    'Job': ('.job_queue', 'Job'),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    """Import a service on first access (PEP 562)."""
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from None

    module = importlib.import_module(module_name, __name__)
    value = getattr(module, attribute)
    globals()[name] = value  # cache for subsequent lookups
    return value


def __dir__():
    return sorted(list(globals()) + __all__)
