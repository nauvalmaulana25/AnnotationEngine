"""
AnnotationEngine Desktop - Custom Annotation Canvas (extends LabelMe Canvas)
"""
import os
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Slot, Qt, QPoint, QRect, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont

# Import LabelMe components
try:
    from labelme._widgets._canvas import Canvas as LabelMeCanvas
    from labelme._shape._model import Shape as LabelMeShape
    from labelme._widgets._zoom_widget import ZoomWidget as LabelMeZoomWidget
except ImportError:
    # Fallback if labelme not installed as package
    import sys
    labelme_path = os.path.join(os.path.dirname(__file__), '..', 'labelme')
    if os.path.exists(labelme_path):
        sys.path.insert(0, labelme_path)
        from labelme.canvas import Canvas as LabelMeCanvas
        from labelme.shape import Shape as LabelMeShape
        from labelme.zoom_widget import ZoomWidget as LabelMeZoomWidget
    else:
        LabelMeCanvas = QWidget
        LabelMeShape = object
        LabelMeZoomWidget = QWidget


class AnnotationCanvas(LabelMeCanvas):
    """
    Extended LabelMe Canvas with custom signals and AnnotationEngine integration.
    """
    
    # Custom signals
    shapeCreated = Signal(dict)           # shape data
    shapeModified = Signal(dict)          # shape data
    shapeDeleted = Signal(int)            # shape index
    selectionChanged = Signal(list)       # list of selected indices
    zoomChanged = Signal(float)           # zoom level
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State
        self.current_tool = "rect"  # rect, polygon, point, line, circle
        self.selected_label = ""
        self.label_colors = {}
        
        # Connect LabelMe signals
        self.connectLabelMeSignals()
        
        # Custom cursor for tools
        self.setMouseTracking(True)
    
    def connectLabelMeSignals(self):
        """Connect LabelMe internal signals to our custom signals."""
        try:
            # LabelMe canvas emits these signals
            self.newShape.connect(self._onNewShape)
            self.shapeMoved.connect(self._onShapeMoved)
            self.shapeChanged.connect(self._onShapeChanged)
            self.selectionChanged.connect(self._onSelectionChanged)
        except (AttributeError, TypeError):
            # Signals might have different names or not exist
            pass
    
    def _onNewShape(self, shape):
        """Handle new shape created."""
        if hasattr(shape, 'to_dict'):
            shape_data = shape.to_dict()
        else:
            shape_data = self._shapeToDict(shape)
        self.shapeCreated.emit(shape_data)
    
    def _onShapeMoved(self, shape):
        """Handle shape moved."""
        if hasattr(shape, 'to_dict'):
            shape_data = shape.to_dict()
        else:
            shape_data = self._shapeToDict(shape)
        self.shapeModified.emit(shape_data)
    
    def _onShapeChanged(self, shape):
        """Handle shape changed (vertex edit, etc)."""
        if hasattr(shape, 'to_dict'):
            shape_data = shape.to_dict()
        else:
            shape_data = self._shapeToDict(shape)
        self.shapeModified.emit(shape_data)
    
    def _onSelectionChanged(self, selected_shapes):
        """Handle selection changed."""
        indices = []
        for i, shape in enumerate(self.shapes):
            if shape in selected_shapes:
                indices.append(i)
        self.selectionChanged.emit(indices)
    
    def _shapeToDict(self, shape) -> dict:
        """Convert LabelMe Shape to dictionary."""
        if hasattr(shape, 'to_dict'):
            return shape.to_dict()
        
        # Manual conversion
        points = []
        if hasattr(shape, 'points'):
            for p in shape.points:
                points.append([p.x(), p.y()])
        
        return {
            'label': getattr(shape, 'label', ''),
            'points': points,
            'shape_type': getattr(shape, 'shape_type', 'polygon'),
            'group_id': getattr(shape, 'group_id', None),
            'description': getattr(shape, 'description', ''),
            'flags': getattr(shape, 'flags', {}),
            'mask': None
        }
    
    def setTool(self, tool_name: str):
        """Set current annotation tool."""
        # Map our tool names to LabelMe tool names
        tool_map = {
            'select': 'select',
            'rect': 'rect',
            'polygon': 'polygon',
            'point': 'point',
            'line': 'line',
            'circle': 'circle',
            'pan': 'pan',
        }
        
        labelme_tool = tool_map.get(tool_name, 'select')
        
        # Call LabelMe's setTool method
        try:
            self.setTool(labelme_tool)
        except (AttributeError, TypeError):
            # Fallback: try different method names
            try:
                self.setToolAction(labelme_tool)
            except (AttributeError, TypeError):
                pass
        
        self.current_tool = tool_name
    
    def setSelectedLabel(self, label: str):
        """Set the label for new shapes."""
        self.selected_label = label
        try:
            self.setLabel(label)
        except (AttributeError, TypeError):
            pass
    
    def setLabelVisibility(self, label: str, visible: bool):
        """Show/hide shapes with specific label."""
        for shape in self.shapes:
            if getattr(shape, 'label', '') == label:
                shape.visible = visible
        self.update()
    
    def loadImage(self, image_path: str) -> bool:
        """Load image from file path."""
        try:
            # Use LabelMe's loadImage
            result = super().loadImage(image_path)
            if result:
                self.zoomFit()
            return result
        except (AttributeError, TypeError):
            # Fallback manual loading
            return self._loadImageFallback(image_path)
    
    def _loadImageFallback(self, image_path: str) -> bool:
        """Fallback image loading."""
        if not os.path.exists(image_path):
            return False
        
        image = QImage(image_path)
        if image.isNull():
            return False
        
        self.setPixmap(QPixmap.fromImage(image))
        self.zoomFit()
        return True
    
    def zoomFit(self):
        """Fit image to view."""
        try:
            self.fitWindow()
        except (AttributeError, TypeError):
            try:
                self.fitToWindow()
            except (AttributeError, TypeError):
                pass
    
    def zoomIn(self):
        """Zoom in."""
        try:
            self.zoomIn()
        except (AttributeError, TypeError):
            pass
    
    def zoomOut(self):
        """Zoom out."""
        try:
            self.zoomOut()
        except (AttributeError, TypeError):
            pass
    
    def loadShapes(self, shapes_data: List[dict]):
        """Load shapes from LabelMe JSON data."""
        try:
            self.shapes = []
            for shape_data in shapes_data:
                shape = LabelMeShape()
                shape.load(shape_data)
                self.shapes.append(shape)
            self.update()
        except Exception:
            pass
    
    def getShapesData(self) -> List[dict]:
        """Get all shapes as LabelMe JSON format."""
        shapes_data = []
        for shape in self.shapes:
            if hasattr(shape, 'to_dict'):
                shapes_data.append(shape.to_dict())
            else:
                shapes_data.append(self._shapeToDict(shape))
        return shapes_data
    
    def clear(self):
        """Clear all shapes and image."""
        try:
            self.shapes = []
            self.setPixmap(QPixmap())
            self.update()
        except Exception:
            pass
    
    def undo(self):
        """Undo last action."""
        try:
            self.undo()
        except (AttributeError, TypeError):
            pass
    
    def redo(self):
        """Redo last action."""
        try:
            self.redo()
        except (AttributeError, TypeError):
            pass
    
    def selectAll(self):
        """Select all shapes."""
        try:
            self.selectAll()
        except (AttributeError, TypeError):
            pass
    
    def deleteSelected(self):
        """Delete selected shapes."""
        try:
            self.deleteSelected()
        except (AttributeError, TypeError):
            pass
    
    def getSelectedIndices(self) -> List[int]:
        """Get indices of selected shapes."""
        indices = []
        try:
            selected = self.selectedShapes
            for i, shape in enumerate(self.shapes):
                if shape in selected:
                    indices.append(i)
        except (AttributeError, TypeError):
            pass
        return indices
    
    def setSelectedIndices(self, indices: List[int]):
        """Set selected shapes by indices."""
        try:
            selected = [self.shapes[i] for i in indices if i < len(self.shapes)]
            self.selectedShapes = selected
        except (AttributeError, TypeError):
            pass