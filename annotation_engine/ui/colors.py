"""
AnnotationEngine Desktop - Shared label color resolution.
"""
from typing import Dict, Optional

from PySide6.QtGui import QColor

from annotation_engine.config import ANNOTATION_COLORS


def resolve_label_color(
    label: Optional[str], label_colors: Optional[Dict[str, str]] = None
) -> QColor:
    """Return the display color for a label.

    Prefers the project's configured label color; falls back to the cycling
    ANNOTATION_COLORS palette keyed by the label name, matching the canvas.
    """
    color = (label_colors or {}).get(label or "", "")
    qcolor = QColor(color) if color else QColor()
    if not qcolor.isValid():
        index = sum(ord(char) for char in (label or "shape"))
        qcolor = QColor(ANNOTATION_COLORS[index % len(ANNOTATION_COLORS)])
    return qcolor
