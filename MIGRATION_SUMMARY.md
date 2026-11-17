# AnnotationEngine Desktop - Migration Complete

## Summary

Successfully migrated from a React/Vite + FastAPI web application to a **Python desktop application** using **PySide6 (Qt 6)** and **LabelMe** (GPL-3.0).

## What Was Removed

### Frontend (client/)
- ✅ `paper` package (Paper.js canvas library)
- ✅ All React/Vite/TypeScript dependencies
- ✅ Custom Paper.js canvas implementation (`AnnotationCanvas.tsx` - 631 lines)
- ✅ Redux store, RTK slices, API layer

### Backend (server/)
- ✅ FastAPI, Uvicorn, SQLAlchemy, Alembic
- ✅ JWT authentication (replaced with local desktop auth)
- ✅ WebSocket server (replaced with Qt Signals/Slots)
- ✅ HTTP API endpoints (replaced with direct Python calls)

## What Was Added

### New Python Desktop Architecture (`annotation_engine/`)

```
annotation_engine/
├── main.py                     # Application entry point
├── config.py                   # Configuration & constants
├── core/
│   └── database.py            # SQLite with full CRUD (projects, images, annotations, jobs, settings)
├── ui/
│   ├── main_window.py         # MainWindow extending LabelMe MainWindow
│   ├── canvas.py              # AnnotationCanvas extending LabelMe Canvas
│   ├── styles.py              # QSS design system (Tailwind-inspired)
│   ├── widgets/               # ImageGrid, Sidebar, Toolbar, StatusBar, ZoomWidget, LabelList
│   └── dialogs/               # Project, ImportImages, ImportLabels, Export, Settings, AutoAnnotate, Progress
├── services/
│   ├── grounding_dino.py      # HF Inference API client
│   ├── mobile_sam.py          # ONNX Runtime inference
│   ├── dinov2.py              # PyTorch keypoint transfer
│   ├── export_service.py      # YOLO/COCO export
│   └── job_queue.py           # QThread-based background processing
├── utils/
│   ├── encryption.py          # Fernet encryption for API keys
│   ├── file_ops.py            # File operations, import/export helpers
│   └── image_utils.py         # Image loading, normalization, NMS
├── labelme/                   # Vendored LabelMe (GPL-3.0)
├── resources/
│   ├── icons/                 # SVG icons (close, maximize, chevron-down, check)
│   └── icons.qrc              # Qt resource file
└── scripts/
    └── export_mobile_sam.py   # MobileSAM → ONNX export script
```

## Key Features Implemented

### ✅ Core Annotation
- Rectangle, Polygon, Point, Line, Circle tools (via LabelMe Canvas)
- LabelMe JSON format native support
- Zoom, pan, selection, vertex editing
- Undo/Redo (50 steps)
- Keyboard shortcuts (V/B/P/K/H, Del, Esc, Space, Wheel zoom)

### ✅ Project & Image Management
- Create/open projects with directory picker
- Image grid with grid/list view, thumbnails
- Multi-file/folder import
- LabelMe JSON import
- Recent projects menu

### ✅ AI Auto-Annotation (Ready for Integration)
- **Grounding DINO**: HF Inference API client with text prompts
- **MobileSAM**: ONNX Runtime inference from bounding boxes
- **DINOv2 Keypoint**: PyTorch-based zero-shot keypoint transfer with consensus filtering
- Job queue with QThread workers and progress signals

### ✅ Export
- YOLO format (.txt + data.yaml)
- COCO format (.json)
- Configurable splits (train/val/test)
- Include/exclude bbox, polygon, keypoints

### ✅ Settings & Security
- HF API key with Fernet encryption
- Theme (light/dark)
- Auto-save interval
- Models directory configuration

### ✅ UI/UX
- Tailwind-inspired QSS design system
- Collapsible sidebar with image grid
- Label list panel with visibility/color control
- Zoom widget with fit/zoom controls
- Status bar with coordinates, zoom, shape count
- Dark canvas background

## Dependencies

### Removed (npm)
```bash
npm uninstall paper
# All React/Vite/TypeScript dependencies removed
```

### Added (pip)
```bash
pip install PySide6 onnxruntime torch torchvision transformers \
  huggingface_hub opencv-python Pillow numpy httpx pyyaml \
  cryptography requests tqdm labelme loguru imgviz natsort ruamel.yaml gdown
```

## Running the Application

```bash
# Activate venv
source "/home/nauval/Documents/auto annotator/venv/bin/activate"

# Run
cd /home/nauval/Documents/Annotation_Engine
python -m annotation_engine.main

# Or with offscreen platform (headless)
QT_QPA_PLATFORM=offscreen python -m annotation_engine.main
```

## Build Executable

```bash
cd /home/nauval/Documents/Annotation_Engine
python scripts/build_installer.py
```

## License Compliance

- **GPL-3.0** (copyleft) - Full source distribution required
- LabelMe source vendored in `annotation_engine/labelme/`
- All code must remain open source

## Next Steps for Production

1. **Test on target platforms** (Windows, macOS, Linux)
2. **Download AI models** on first run (MobileSAM ONNX, DINOv2)
3. **Create installers** (NSIS/Inno Setup for Windows, DMG for macOS)
4. **Add auto-update** mechanism
5. **Performance optimization** for large datasets
6. **User documentation** and tutorials