# AnnotationEngine Desktop - LabelMe-based Python Desktop Application

## Project Overview

Native Python desktop application for image annotation with integrated zero-shot AI capabilities:
- **Grounding DINO** via Hugging Face Inference API (cloud) for object detection
- **MobileSAM** via PyTorch/Ultralytics (local CPU/GPU) for instance segmentation
- **DINOv2** via PyTorch (local CPU/GPU) for zero-shot keypoint estimation

**Tech Stack:**
- **UI Framework**: PySide6 (Qt 6) with QSS styling (Tailwind-inspired)
- **Annotation Canvas**: LabelMe (vendored, GPL-3.0) - `Canvas`, `Shape`, `ZoomWidget`
- **AI Services**: Python modules adapted from web backend
- **Database**: SQLite (projects, images, annotations, jobs) + LabelMe JSON per image
- **Packaging**: PyInstaller (single executable per platform)
- **License**: GPL-3.0 (copyleft - full source distribution required)

---

## Architecture Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| UI Framework | PySide6 (Qt 6) | LabelMe dependency, mature, cross-platform |
| Styling | QSS (Qt Style Sheets) | CSS-like, supports Tailwind-inspired design system |
| Canvas | LabelMe `Canvas` + `Shape` classes | Proven, GPL-3.0, LabelMe JSON native |
| Project Structure | Single package `annotation_engine/` | Monolithic desktop app |
| AI Inference | Local modules (no HTTP server) | Direct calls, no serialization overhead |
| Model Storage | App data directory (`~/AnnotationEngine/models/`) | Portable, no system dependencies |
| Settings | `QSettings` + encrypted JSON | Native persistence, cross-platform |
| Packaging | PyInstaller | Single-file executables, native installers |
| MobileSAM Runtime | PyTorch/Ultralytics (CPU/GPU) | No ONNX export needed, direct PyTorch inference |

---

## Repository Structure

```
AnnotationEngine/
├── annotation_engine/              # Main Python package
│   ├── __init__.py
│   ├── main.py                     # Application entry point
│   ├── config.py                   # Settings, paths, constants
│   │
│   ├── core/                       # Core application logic
│   │   ├── __init__.py
│   │   ├── database.py             # SQLite connection, migrations
│   │
│   ├── ui/                         # Qt UI components
│   │   ├── __init__.py
│   │   ├── styles.py               # QSS design system (Tailwind-inspired)
│   │   ├── main_window.py          # MainWindow (uses WelcomeWidget)
│   │   ├── canvas.py               # Custom Canvas (extends LabelMe Canvas)
│   │   ├── welcome_widget.py       # Welcome screen widget
│   │   ├── welcome_window.py       # Welcome dialog (deprecated)
│   │   ├── colors.py               # Color constants
│   │   ├── widgets/                # Custom Qt widgets
│   │   │   ├── __init__.py
│   │   │   ├── image_grid.py       # ImageListView (grid/list modes)
│   │   │   ├── sidebar.py          # Collapsible sidebar
│   │   │   ├── toolbar.py          # Top toolbar
│   │   │   ├── status_bar.py       # Bottom status bar
│   │   │   ├── zoom_widget.py      # Zoom control (extends LabelMe)
│   │   │   └── label_list.py       # Label management panel
│   │   ├── dialogs/
│   │   │   ├── __init__.py
│   │   │   ├── project_dialog.py   # Create/open project
│   │   │   ├── import_images.py    # Multi-file/folder import
│   │   │   ├── import_labels.py    # LabelMe JSON import
│   │   │   ├── export_dialog.py    # YOLO/COCO export
│   │   │   ├── settings_dialog.py  # HF API key, preferences
│   │   │   ├── auto_annotate.py    # 3-tab auto-annotate panel
│   │   │   ├── progress_dialog.py  # Job progress with cancel
│   │   │   └── rename_label.py     # Label rename dialog
│   │   └── resources/              # Icons, fonts, images
│   │
│   ├── services/                   # AI inference services
│   │   ├── __init__.py
│   │   ├── device.py               # Device detection (CPU/GPU)
│   │   ├── grounding_dino.py       # HF Inference API client
│   │   ├── mobile_sam.py           # PyTorch/Ultralytics inference
│   │   ├── dinov2.py               # PyTorch keypoint transfer
│   │   ├── export_service.py       # YOLO/COCO conversion
│   │   ├── job_queue.py            # QThread-based job processor
│   │   └── model_manager.py        # Model download/cache management
│   │
│   ├── labelme/                    # VENDORED LabelMe source (GPL-3.0)
│   │   ├── __init__.py
│   │   ├── widgets/                # LabelMe widgets (minimal)
│   │   └── utils/                  # LabelMe utilities (minimal)
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── encryption.py           # HF API key encryption
│   │   ├── file_ops.py             # File operations, import/export
│   │   └── image_utils.py          # Thumbnails, image info
│   │
│   └── scripts/
│       └── export_mobile_sam.py    # MobileSAM → ONNX export (optional, not used)
│
├── resources/                       # Application resources
│   ├── icons/                      # SVG icons (Lucide-style)
│   ├── fonts/                      # Inter, JetBrains Mono
│   └── styles/                     # Base QSS files
│
├── scripts/
│   └── export_mobile_sam.py    # MobileSAM → ONNX export (optional, not used)
│
├── tests/
│   ├── __init__.py
│   ├── test_services.py
│   ├── test_export.py
│   └── test_ui.py
│
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── README.md
├── LICENSE (GPL-3.0)
└── .gitignore
```

---

## UI Design System (QSS - Tailwind-Inspired)

### Color Palette
```python
# styles.py
COLORS = {
    # Primary (Blue)
    'primary_50': '#eff6ff', 'primary_100': '#dbeafe', 'primary_200': '#bfdbfe',
    'primary_300': '#93c5fd', 'primary_400': '#60a5fa', 'primary_500': '#3b82f6',
    'primary_600': '#2563eb', 'primary_700': '#1d4ed8', 'primary_800': '#1e40af',
    'primary_900': '#1e3a8a', 'primary_950': '#172554',
    
    # Gray (Neutral)
    'gray_50': '#f9fafb', 'gray_100': '#f3f4f6', 'gray_200': '#e5e7eb',
    'gray_300': '#d1d5db', 'gray_400': '#9ca3af', 'gray_500': '#6b7280',
    'gray_600': '#4b5563', 'gray_700': '#374151', 'gray_800': '#1f2937',
    'gray_900': '#111827', 'gray_950': '#030712',
    
    # Semantic
    'success': '#22c55e', 'warning': '#f59e0b', 'error': '#ef4444',
    'info': '#06b6d4',
    
    # Canvas
    'canvas_bg': '#1a1a2e', 'canvas_grid': '#2d2d44',
}
```

### QSS Design Tokens
```python
# styles.py - Generated QSS variables
QSS_TEMPLATE = """
/* Design Tokens */
* {
    /* Colors */
    --color-primary: #3b82f6;
    --color-primary-hover: #2563eb;
    --color-primary-pressed: #1d4ed8;
    --color-bg-primary: #ffffff;
    --color-bg-secondary: #f9fafb;
    --color-bg-tertiary: #f3f4f6;
    --color-bg-canvas: #1a1a2e;
    --color-border: #e5e7eb;
    --color-border-focus: #3b82f6;
    --color-text-primary: #111827;
    --color-text-secondary: #6b7280;
    --color-text-muted: #9ca3af;
    --color-text-inverse: #ffffff;
    
    /* Spacing (4px base) */
    --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
    --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px;
    
    /* Typography */
    --font-family: "Inter", "Segoe UI", sans-serif;
    --font-mono: "JetBrains Mono", "Consolas", monospace;
    --text-xs: 11px; --text-sm: 13px; --text-base: 14px;
    --text-lg: 16px; --text-xl: 18px; --text-2xl: 22px;
    
    /* Border Radius */
    --radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px; --radius-xl: 12px;
    
    /* Shadows */
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
    --shadow-md: 0 4px 6px rgba(0,0,0,0.07);
    --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
}

/* Base Widget Styles */
QWidget {
    font-family: var(--font-family);
    font-size: var(--text-base);
    color: var(--color-text-primary);
    background-color: var(--color-bg-primary);
}

QMainWindow, QDialog {
    background-color: var(--color-bg-primary);
}

/* Buttons */
QPushButton {
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background-color: var(--color-bg-primary);
    color: var(--color-text-primary);
    font-weight: 500;
}
QPushButton:hover { background-color: var(--color-bg-tertiary); }
QPushButton:pressed { background-color: var(--color-bg-secondary); }
QPushButton:disabled { color: var(--color-text-muted); border-color: var(--color-border); }

QPushButton[primary="true"] {
    background-color: var(--color-primary);
    color: var(--color-text-inverse);
    border-color: var(--color-primary);
}
QPushButton[primary="true"]:hover { background-color: var(--color-primary-hover); }
QPushButton[primary="true"]:pressed { background-color: var(--color-primary-pressed); }

/* Toolbar */
ToolBar {
    background-color: var(--color-bg-secondary);
    border-bottom: 1px solid var(--color-border);
    padding: var(--space-2);
    spacing: var(--space-2);
}

/* Sidebar */
QDockWidget {
    titlebar-close-icon: url(icons/close.svg);
    titlebar-normal-icon: url(icons/maximize.svg);
}
QDockWidget::title {
    background-color: var(--color-bg-secondary);
    padding: var(--space-3);
    border-bottom: 1px solid var(--color-border);
}

/* List/Grid View */
QListView, QTreeView {
    background-color: var(--color-bg-primary);
    border: none;
    outline: none;
    show-decoration-selected: 1;
}
QListView::item, QTreeView::item {
    padding: var(--space-2);
    border-radius: var(--radius-sm);
    margin: var(--space-1);
}
QListView::item:selected, QTreeView::item:selected {
    background-color: var(--color-primary-100);
    color: var(--color-primary-700);
}
QListView::item:hover, QTreeView::item:hover {
    background-color: var(--color-bg-tertiary);
}

/* Thumbnail Delegate */
ThumbnailDelegate {
    background-color: var(--color-bg-tertiary);
    border-radius: var(--radius-md);
}

/* Input Fields */
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background-color: var(--color-bg-primary);
    selection-background-color: var(--color-primary-200);
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border-color: var(--color-border-focus);
    outline: none;
}

/* Progress Bar */
QProgressBar {
    border: none;
    border-radius: var(--radius-sm);
    background-color: var(--color-bg-tertiary);
    text-align: center;
    height: 6px;
}
QProgressBar::chunk {
    background-color: var(--color-primary);
    border-radius: var(--radius-sm);
}

/* Scrollbars */
QScrollBar:vertical {
    width: 8px;
    background: transparent;
}
QScrollBar::handle:vertical {
    background: var(--color-gray-400);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: var(--color-gray-500);
}

/* Dialogs */
QDialog {
    border-radius: var(--radius-lg);
}
QDialog QDialogButtonBox {
    padding: var(--space-4);
}

/* Tooltips */
QToolTip {
    background-color: var(--color-gray-900);
    color: var(--color-gray-100);
    border: none;
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
}

/* Menu */
QMenu {
    background-color: var(--color-bg-primary);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-2);
}
QMenu::item {
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-sm);
}
QMenu::item:selected {
    background-color: var(--color-bg-tertiary);
}
QMenu::separator {
    height: 1px;
    background: var(--color-border);
    margin: var(--space-2) var(--space-4);
}

/* Splitter */
QSplitter::handle {
    background: var(--color-border);
    width: 1px;
    height: 1px;
}
QSplitter::handle:hover {
    background: var(--color-primary);
}
"""
```

---

## Database Schema (SQLite)

```python
# core/database.py
SCHEMA = """
-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    base_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Images
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    file_size INTEGER,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    split TEXT DEFAULT 'train',
    has_annotation BOOLEAN DEFAULT 0,
    UNIQUE(project_id, relative_path)
);

-- Annotations (LabelMe JSON)
CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    data TEXT NOT NULL,  -- LabelMe JSON as text
    version INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(image_id)
);

-- Jobs (Background processing)
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,  -- 'grounding_dino', 'mobile_sam', 'dinov2_keypoint', 'export'
    status TEXT DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'
    progress INTEGER DEFAULT 0,
    payload TEXT,  -- JSON
    result TEXT,   -- JSON
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_images_project ON images(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""
```

---

## Core Models

```python
# core/database.py (dataclasses)
@dataclass
class Project:
    id: Optional[int]
    name: str
    description: Optional[str]
    base_path: str
    created_at: datetime
    updated_at: datetime
    image_count: int = 0

@dataclass
class Image:
    id: Optional[int]
    project_id: int
    filename: str
    relative_path: str
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]
    imported_at: datetime
    split: str  # 'train', 'val', 'test'
    has_annotation: bool

@dataclass
class Annotation:
    id: Optional[int]
    image_id: int
    data: dict  # LabelMe format
    version: int
    updated_at: datetime

@dataclass
class Job:
    id: Optional[int]
    project_id: int
    job_type: str
    status: str
    progress: int
    payload: dict
    result: Optional[dict]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

---

## LabelMe Integration (Vendored)

### Canvas Extension
```python
# ui/canvas.py
from labelme._widgets._canvas import Canvas as LabelMeCanvas
from labelme._shape._model import Shape as LabelMeShape

class AnnotationCanvas(LabelMeCanvas):
    """Extended LabelMe canvas with custom tools and signals."""
    
    # Custom signals
    shapeCreated = Signal(object)      # LabelMeShape
    shapeModified = Signal(object)     # LabelMeShape
    shapeDeleted = Signal(int)         # shape index
    selectionChanged = Signal(list)    # list of shape indices
    zoomChanged = Signal(float)        # zoom level
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Setup custom tools mapping
        
    def loadImage(self, image_path: str) -> bool:
        """Load image using LabelMe's load_pixmap."""
        pixmap = QPixmap(image_path)
        self.load_pixmap(pixmap=pixmap)
        self.zoomFit()
        return True
    
    def setTool(self, tool_name: str):
        """Map our tools to LabelMe create modes."""
        tool_map = {
            'select': None,  # Disables create mode
            'rect': 'rectangle',
            'polygon': 'polygon',
            'point': 'point',
            'line': 'line',
            'circle': 'circle',
            'pan': None,
        }
        
        if tool_name in ('select', 'pan'):
            self._create_mode = None  # Disable create mode
        else:
            self._set_create_mode(value=labelme_tool)
    
    def loadShapes(self, shapes_data: List[dict]):
        """Load LabelMe shapes from JSON."""
        self.shapes = []
        for shape_data in shapes_data:
            shape = LabelMeShape()
            shape.load(shape_data)
            self.shapes.append(shape)
        self.update()
    
    def getShapesData(self) -> List[dict]:
        """Export shapes to LabelMe JSON format."""
        return [shape.to_dict() for shape in self.shapes]
    
    def clear(self):
        """Clear all shapes and image."""
        self.shapes = []
        self.load_pixmap(QPixmap())
        self.update()
```

### MainWindow (Simplified)
```python
# ui/main_window.py
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setupUI()
        self.setupConnections()
        self.restoreSettings()
        self.loadRecentProjectsMenu()
        self.showWelcomeDialog()
    
    def setupUI(self):
        # Central widget with splitter
        # Toolbar, sidebar, canvas, label list
        # Status bar, menu bar
        
    def showWelcomeDialog(self):
        """Show modal welcome dialog on startup."""
        welcome = WelcomeWindow(self)
        if welcome.exec() == QDialog.Accepted:
            self.loadProject(welcome.getSelectedProjectId())
        else:
            QApplication.quit()
    
    def closeProject(self):
        """Close project and return to welcome dialog."""
        # Save if dirty
        # Clear UI
        self.showWelcomeDialog()
```

---

## AI Services (Current Implementation Status)

### Grounding DINO Service (Implemented)
```python
# services/grounding_dino.py
class GroundingDINOService:
    def __init__(self, api_key: str = ""):
        self.api_url = "https://api-inference.huggingface.co/models/IDEA-Research/grounding-dino-tiny"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def detect(self, image_path: str, text_prompt: str, threshold: float = 0.3) -> List[Dict]:
        # Returns: [{label, score, box: [x1,y1,x2,y2]}, ...]
```

### MobileSAM Service (Implemented - PyTorch/Ultralytics)
```python
# services/mobile_sam.py
class MobileSAMService:
    def __init__(self, model_path: str = "", auto_download: bool = True, device: str = DEVICE_AUTO):
        self.model_path = str(model_path or mobile_sam_path())
        self.auto_download = auto_download
        self.device_preference = device
        self.device = resolve_device(device)
        self._model = None

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
        """Load the Ultralytics SAM wrapper, reusing it across calls."""
        if self._model is not None:
            return self._model

        path = self.ensure_model(progress_callback)
        _report(
            progress_callback, 100,
            f"Loading MobileSAM on {self.device_description}"
        )
        from ultralytics import SAM

        self._model = SAM(str(Path(path).resolve()))
        self._move_to_device(self._model)
        return self._model

    def segment_from_boxes(
        self,
        image: np.ndarray,
        boxes: List[List[float]],
        progress_callback: ProgressCallback = None,
        min_score: float = 0.0,
    ) -> List[np.ndarray]:
        """Segment an image from [x1, y1, x2, y2] box prompts."""
        if not boxes:
            return []

        model = self.load(progress_callback)

        results = self._predict(model, image, boxes)
        if not results:
            return [np.zeros(image.shape[:2], dtype=bool) for _ in boxes]

        height, width = image.shape[:2]
        masks = results[0].masks
        if masks is None or len(masks) == 0:
            return [np.zeros((height, width), dtype=bool) for _ in boxes]

        arrays = masks.data.cpu().numpy()
        keep = self._scoreMask(results[0], len(arrays), min_score)

        output: List[np.ndarray] = []
        for array, wanted in zip(arrays, keep):
            if array.shape[:2] != (height, width):
                array = cv2.resize(
                    array.astype(np.float32),
                    (width, height),
                    interpolation=cv2.INTER_LINEAR,
                )
            output.append((array > 0.5) if wanted else np.zeros((height, width), dtype=bool))
        return output
```

### DINOv2 Service (Partial)
```python
# services/dinov2.py
class DINOv2KeypointService:
    def __init__(self, model_name: str = "facebook/dinov2-small"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoImageProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
    
    def transfer_keypoints(self, target_image: Image.Image, reference_data: List[Dict], ...) -> List[Dict]:
        # Feature extraction + cosine similarity matching + consensus filtering
        ...
```

### Model Manager (Implemented)
```python
# services/model_manager.py
class ModelManager:
    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
    
    def ensure_mobile_sam(self) -> Path:
        # Download/verify MobileSAM PyTorch checkpoint
        ...
    
    def ensure_dinov2(self, model_name: str = "facebook/dinov2-small") -> Path:
        # Download/verify DINOv2 from HF
        ...
```

### Job Queue (QThread-based)
```python
# services/job_queue.py
class JobQueue(QObject):
    jobStarted = Signal(str)
    jobProgress = Signal(str, int, str)
    jobFinished = Signal(str, dict)
    jobFailed = Signal(str, str)
    
    def enqueue(self, job_type: str, func: Callable, *args, **kwargs) -> str:
        ...
    
    def start_job(self, job_id: str, func: Callable, *args, **kwargs):
        # Creates QThread + JobWorker, connects signals
        ...
```

---

## Auto-Annotate Dialog (3 Tabs - Implemented)

```python
# ui/dialogs/auto_annotate.py
class AutoAnnotateDialog(QDialog):
    # 3 tabs: Grounding DINO, MobileSAM, DINOv2 Keypoint
    # Each tab has parameters and "Run" button
    # Uses JobQueue for background processing
    # Progress bar + cancel button
```

---

## Export Dialog (Implemented)

```python
# ui/dialogs/export_dialog.py
class ExportDialog(QDialog):
    # YOLO (.txt + data.yaml) + COCO (.json)
    # Split ratios (train/val/test)
    # Include: bboxes, polygons, keypoints
    # Output to project folder or custom location
```

---

## Settings Dialog (Implemented)

```python
# ui/dialogs/settings_dialog.py
class SettingsDialog(QDialog):
    # General: theme (Light/Dark/System), auto-save interval
    # API Keys: Hugging Face API key (encrypted)
    # Advanced: models directory, Clean Database button (triple confirmation)
```

---

## Welcome Dialog (Current)

```python
# ui/welcome_window.py
class WelcomeWindow(QDialog):
    # Modal dialog on startup
    # Logo, app name, version
    # "Create New Project" / "Open Existing Project"
    # Recent projects list with delete buttons
    # Settings / Quit buttons
```

---

## Current Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Database (SQLite) | ✅ Complete | Projects, images, annotations, jobs, settings |
| Welcome Dialog | ✅ Complete | Modal dialog with create/open recent projects |
| Main Window | ✅ Complete | Toolbar, sidebar, canvas, label list, status bar |
| Canvas (LabelMe) | ✅ Complete | load_pixmap, setTool, shapes, signals |
| Image Grid | ✅ Complete | Grid/list view, thumbnails, selection |
| Sidebar | ✅ Complete | Image list, import, selection |
| Label List | ✅ Complete | Visibility, color, counts |
| Toolbar | ✅ Complete | Tools, import, export, auto-annotate, save |
| Status Bar | ✅ Complete | Zoom, coords, shape count |
| Welcome Dialog | ✅ Complete | Create/open project, recent projects with delete |
| Settings Dialog | ✅ Complete | Theme, HF API key (encrypted), Clean DB |
| Clean Database | ✅ Complete | Triple confirmation, resets AUTOINCREMENT |
| Image Import | ✅ Complete | Multi-file + folder, split assignment |
| Label Import | ✅ Complete | Match by filename |
| Export Dialog | ✅ Complete | YOLO/COCO, splits, includes |
| Auto-Annotate Dialog | ✅ UI Complete | 3 tabs, job queue integration |
| Job Queue | ✅ Complete | QThread-based, progress signals |
| Grounding DINO Service | ✅ Complete | HF API client, async detection |
| MobileSAM Service | ✅ Implemented | PyTorch/Ultralytics, CPU/GPU |
| DINOv2 Service | ⚠️ Partial | Feature extraction works, matching needs work |
| Model Manager | ✅ Complete | Download/cache models |
| Export Service | ✅ Complete | YOLO + COCO formats |
| Job Queue | ✅ Complete | QThread-based, progress signals |
| Device Detection | ✅ Complete | CPU/GPU selection |
| Model Manager | ✅ Complete | Download/cache MobileSAM, DINOv2 |

---

## Development Phases - Updated Status

### Phase 1: Foundation ✅ COMPLETE
- [x] Setup PySide6 project structure
- [x] Vendor LabelMe source code (minimal)
- [x] Create QSS design system
- [x] Implement MainWindow with welcome dialog flow
- [x] SQLite database with migrations

### Phase 2: Image Management ✅ COMPLETE
- [x] ImageGrid widget (grid/list view, thumbnails)
- [x] Sidebar with collapsible panels
- [x] Import images dialog (multi-file + folder)
- [x] Directory watcher for auto-import
- [x] Recent projects menu

### Phase 3: Annotation Canvas ✅ COMPLETE
- [x] Integrate LabelMe Canvas fully
- [x] Custom tool mapping (bbox/polygon/keypoint)
- [x] Keyboard shortcuts (V/B/P/K/H, Del, Esc, Space)
- [x] Zoom widget integration
- [x] Label list panel
- [x] Undo/Redo (LabelMe built-in)

### Phase 4: Auto-Annotation 🔄 IN PROGRESS
- [x] Grounding DINO service + dialog tab
- [x] Job queue with QThread workers
- [x] Progress dialogs with cancel
- [x] Auto-annotate dialog with 3 tabs
- [x] MobileSAM PyTorch/Ultralytics service + service
- [ ] MobileSAM segmentation from boxes
- [ ] DINOv2 keypoint service + dialog tab
- [ ] Results overlay on canvas

### Phase 5: Export & Settings ✅ COMPLETE
- [x] YOLO export service
- [x] COCO export service
- [x] Export dialog with options
- [x] Settings dialog (HF API key, preferences)
- [x] Encrypted API key storage
- [x] Clean Database (triple confirmation)

### Phase 6: Polish & Packaging 🔄 PLANNED
- [ ] Application icon, splash screen
- [ ] PyInstaller build scripts
- [ ] Installer creation (NSIS/Inno Setup for Windows, DMG for macOS)
- [ ] Cross-platform testing
- [ ] Performance optimization
- [ ] Documentation

---

## Validation Checklist - Updated

### Functional
- [x] Create project, choose directory
- [x] Import images (files + folders)
- [x] View images in grid/list with thumbnails
- [x] Select image → loads in canvas
- [x] Draw bbox, polygon, keypoint
- [x] Select, move, delete, edit shapes
- [x] Save/load LabelMe JSON
- [x] Run Grounding DINO on selected images
- [ ] Run MobileSAM on GDINO boxes
- [ ] Run DINOv2 keypoint transfer
- [x] Export YOLO format
- [x] Export COCO format
- [x] Settings persist (API key encrypted)
- [x] Clean database resets AUTOINCREMENT

### UI/UX
- [x] Tailwind-inspired QSS styling applied
- [x] Responsive layout (splitter, collapsible sidebar)
- [x] Dark canvas background
- [x] Toolbar with tool buttons + shortcuts
- [x] Status bar with zoom, coordinates, shape count
- [x] Progress dialogs during AI jobs
- [x] Keyboard shortcuts work globally

### Technical
- [ ] Single executable builds on Windows/macOS/Linux
- [ ] Models download/cache to app data directory
- [ ] No external server required
- [ ] GPL-3.0 license compliance (source included)
- [ ] Memory usage < 2GB for 1000 images
- [ ] Startup time < 3 seconds

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| GPL-3.0 license | High | Legal review, full source distribution |
| LabelMe customization limits | Medium | Vendor source, extend via inheritance |
| MobileSAM PyTorch integration complexity | Medium | Test early, Ultralytics handles complexity |
| PyInstaller binary size | Medium | Exclude unused modules, UPX compression |
| Cross-platform Qt issues | Medium | Test on all 3 platforms early |
| Large image handling | High | Downsample for display, tile for processing |
| HF API rate limits | High | Cache results, retry logic, local fallback |

---

## Open Questions

1. **LabelMe vendoring approach**: Current minimal vendoring works; consider full vendoring if customization needed
2. **Keypoint vs Point**: Use `point` tool with label prefix `kp_` for keypoints
3. **Auto-annotate UX**: Separate dialog works well; consider side panel for results preview
4. **Model storage**: Download on first use with caching; models dir in app data
5. **Project format**: Folder with JSON files (current); consider single `.aeproj` for portability
6. **Undo/Redo**: Use LabelMe's built-in (works well)

---

## Next Implementation Priority

1. **MobileSAM PyTorch/Ultralytics Integration** - Complete segmentation from boxes, integrate with auto-annotate
2. **DINOv2 Keypoint Matching** - Complete matching + consensus filtering
3. **Auto-annotate Results Overlay** - Load results into canvas, accept/reject per image
4. **PyInstaller Build** - Test cross-platform builds