"""
AnnotationEngine Desktop - Main Window (Simplified Working Version)
"""
import os
import logging
from pathlib import Path
from typing import Optional, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QDockWidget, QToolBar,
    QStatusBar, QMenuBar, QMenu, QFileDialog, QMessageBox,
    QVBoxLayout, QLabel, QProgressBar, QDialog, QScrollArea, QFrame,
    QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox,
    QAbstractItemView
)
from PySide6.QtCore import (
    Qt, QSettings, QSize, Signal, Slot, QThread, QTimer, QObject, QEvent
)
from PySide6.QtGui import QAction, QIcon, QKeySequence

from annotation_engine.config import (
    APP_NAME, APP_VERSION, PROJECTS_DIR, TOOL_NAMES, SHORTCUTS,
    SUPPORTED_IMAGE_FORMATS, DEFAULT_SETTINGS
)
from annotation_engine.core.database import (
    get_database, create_project, get_project, get_all_projects,
    update_project, delete_project, get_project_images, add_image, get_image,
    update_image, save_annotation, get_annotation, get_setting, set_setting,
    add_recent_project, get_recent_projects, clean_database,
    get_project_labels, save_project_labels, rename_label_in_project,
    label_in_use, get_project_annotations, get_last_image_id, set_last_image_id
)
from annotation_engine.ui.styles import get_application_stylesheet
from annotation_engine.ui.widgets.image_grid import ImageGridWidget
from annotation_engine.ui.widgets.sidebar import SidebarWidget
from annotation_engine.ui.widgets.toolbar import AnnotationToolbar
from annotation_engine.ui.widgets.status_bar import AnnotationStatusBar
from annotation_engine.ui.widgets.zoom_widget import ZoomWidget
from annotation_engine.ui.widgets.label_list import LabelListWidget
from annotation_engine.ui.dialogs.project_dialog import ProjectDialog
from annotation_engine.ui.dialogs.import_images import ImportImagesDialog
from annotation_engine.ui.dialogs.import_labels import ImportLabelsDialog
from annotation_engine.ui.dialogs.export_dialog import ExportDialog
from annotation_engine.ui.dialogs.settings_dialog import SettingsDialog
from annotation_engine.ui.dialogs.auto_annotate import AutoAnnotateDialog
from annotation_engine.ui.dialogs.progress_dialog import ProgressDialog
from annotation_engine.ui.dialogs.rename_label import RenameLabelDialog
from annotation_engine.ui.canvas import AnnotationCanvas
from annotation_engine.ui.welcome_window import WelcomeWindow
from annotation_engine.utils.encryption import EncryptionManager
from annotation_engine.utils.file_ops import build_labelme_payload, write_labelme_json
from annotation_engine.services.job_queue import JobQueue
from annotation_engine.services.mobile_sam import MobileSAMService
from annotation_engine.services.yolo_service import YOLOService
from annotation_engine.services.grounding_dino import (
    GroundingDINOSync,
    LocalGroundingDINOService,
    grounding_dino_mode,
)
from annotation_engine.services.model_manager import (
    ModelDownloadError,
    download_mobile_sam,
    mobile_sam_path,
)

# Project root for resources
PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""
    
    # Signals
    projectLoaded = Signal(int)  # project_id
    imageSelected = Signal(int)  # image_id
    toolChanged = Signal(str)    # tool_name
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1400, 900)
        
        # State
        self.current_project_id: Optional[int] = None
        self.current_image_id: Optional[int] = None
        self.current_tool: str = "select"
        self.annotations_dirty: bool = False
        self._suspend_label_persistence: bool = False
        self._label_counts: dict = {}
        self._project_images: List[dict] = []
        self._suspend_autosave: bool = False
        self._mobile_sam: Optional[MobileSAMService] = None
        self._mobile_sam_job: Optional[str] = None
        self._yolo_services: dict = {}
        self._yolo_job: Optional[str] = None
        self._local_grounding_dino: dict = {}
        self._grounding_dino_job: Optional[str] = None
        self._grounding_dino_mode: Optional[str] = None
        self._auto_annotate_dialog: Optional[AutoAnnotateDialog] = None
        self._managed_jobs: dict = {}
        self._auto_annotate_warmed: bool = False
        self._prewarm_thread: Optional[QThread] = None
        self._prewarm_worker = None
        
        # Autosave: every edit (including undo/redo) persists shortly after it
        # settles. A single-shot timer coalesces bursts, e.g. a delete that
        # rebuilds the label list, into one write.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(400)
        self._autosave_timer.timeout.connect(self._flushAutosave)
        
        # Services
        self.encryption = EncryptionManager()
        self.job_queue = JobQueue(self)
        
        # UI Components
        self.canvas: Optional[AnnotationCanvas] = None
        self.image_grid: Optional[ImageGridWidget] = None
        self.sidebar: Optional[SidebarWidget] = None
        self.toolbar: Optional[AnnotationToolbar] = None
        self.status_bar: Optional[AnnotationStatusBar] = None
        self.zoom_widget: Optional[ZoomWidget] = None
        self.label_list: Optional[LabelListWidget] = None
        
        # Progress dialog
        self.progress_dialog: Optional[ProgressDialog] = None
        
        self.setupUI()
        self.setupConnections()
        self.restoreSettings()
        self.loadRecentProjectsMenu()
        
        # Show welcome dialog first
        self.showWelcomeDialog()
    
    def setupUI(self):
        """Setup the main UI layout."""
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = AnnotationToolbar(self)
        self.toolbar.setObjectName("main_toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        
        # Main splitter (sidebar | canvas)
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # Left sidebar
        self.sidebar = SidebarWidget(self)
        sidebar_dock = QDockWidget("Images", self)
        sidebar_dock.setObjectName("images_dock")
        sidebar_dock.setWidget(self.sidebar)
        sidebar_dock.setFeatures(
            QDockWidget.DockWidgetClosable | 
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable
        )
        sidebar_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, sidebar_dock)
        
        # Right sidebar - Label list
        self.label_list = LabelListWidget(self)
        label_dock = QDockWidget("Labels", self)
        label_dock.setObjectName("labels_dock")
        label_dock.setWidget(self.label_list)
        label_dock.setFeatures(
            QDockWidget.DockWidgetClosable | 
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable
        )
        label_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, label_dock)
        
        # Canvas area. LabelMe 7.x requires a QScrollArea for panning,
        # scrolling and zooming to work.
        self.canvas = AnnotationCanvas()
        self.canvas_scroll_area = QScrollArea()
        self.canvas_scroll_area.setObjectName("canvas_scroll_area")
        self.canvas_scroll_area.setFrameShape(QFrame.NoFrame)
        self.canvas_scroll_area.setWidgetResizable(True)
        self.canvas_scroll_area.setWidget(self.canvas)
        self.main_splitter.addWidget(self.canvas_scroll_area)
        
        # Zoom widget (floating over the canvas viewport)
        self.zoom_widget = ZoomWidget(self.canvas, parent=self.canvas_scroll_area.viewport())
        self.zoom_widget.move(20, 20)
        self.zoom_widget.raise_()
        
        # Status bar
        self.status_bar = AnnotationStatusBar(self)
        self.setStatusBar(self.status_bar)
        
        # Menu bar
        self.setupMenuBar()
        
        # Apply stylesheet
        settings = QSettings()
        dark_mode = settings.value("theme", "light") == "dark"
        self.setStyleSheet(get_application_stylesheet(dark_mode))
        
        # Set window icon
        icon_path = PROJECT_ROOT / "annotation_engine" / "resources" / "icons" / "app.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
    
    def setupConnections(self):
        """Setup signal-slot connections."""
        # Toolbar signals
        self.toolbar.toolChanged.connect(self.setTool)
        self.toolbar.importImagesRequested.connect(self.importImages)
        self.toolbar.importLabelsRequested.connect(self.importLabels)
        self.toolbar.exportRequested.connect(self.exportDataset)
        self.toolbar.autoAnnotateRequested.connect(self.showAutoAnnotate)
        self.toolbar.undoRequested.connect(self.undo)
        self.toolbar.redoRequested.connect(self.redo)
        self.toolbar.deleteRequested.connect(self.deleteSelected)
        self.toolbar.welcomeRequested.connect(self.returnToWelcome)
        
        # Sidebar signals
        self.sidebar.imageSelected.connect(self.onImageSelected)
        self.sidebar.imageDoubleClicked.connect(self.onImageDoubleClicked)
        self.sidebar.selectionChanged.connect(self.onSelectionChanged)
        
        # Canvas signals
        self.canvas.shapeCreated.connect(self.onShapeCreated)
        self.canvas.shapeModified.connect(self.onShapeModified)
        self.canvas.shapeDeleted.connect(self.onShapeDeleted)
        self.canvas.selectionChanged.connect(self.onCanvasSelectionChanged)
        self.canvas.zoomChanged.connect(self.onZoomChanged)
        self.canvas.historyChanged.connect(self.toolbar.setUndoRedoEnabled)
        self.canvas.setLabelProvider(lambda: list(self.label_list.labels.keys()))
        self.canvas.shapesChanged.connect(self.onCanvasShapesChanged)
        # Arrow keys switch images unless a widget needs them or the canvas has
        # a selection to nudge. Application level, because Qt only delivers
        # keys to the focused widget and the canvas starts unfocused.
        QApplication.instance().installEventFilter(self)
        if hasattr(self.canvas, "mouse_moved"):
            self.canvas.mouse_moved.connect(self.onCanvasMouseMoved)
        if hasattr(self.canvas, "status_updated"):
            self.canvas.status_updated.connect(
                lambda text: self.status_bar.showMessage(text, 3000)
            )
        
        # Label list signals
        self.label_list.labelSelected.connect(self.onLabelSelected)
        self.label_list.labelVisibilityChanged.connect(self.onLabelVisibilityChanged)
        self.label_list.labelColorChanged.connect(self.onLabelColorChanged)
        self.label_list.selectShapesRequested.connect(self.onLabelSelectShapes)
        self.label_list.deleteShapesRequested.connect(self.onLabelDeleteShapes)
        self.label_list.removeLabelRequested.connect(self.onLabelRemove)
        self.label_list.renameLabelRequested.connect(self.onLabelRename)
        self.label_list.labelsChanged.connect(self._saveProjectLabels)
        self.label_list.instanceClicked.connect(self.onInstanceClicked)
        self.label_list.instanceDeleteRequested.connect(self.onInstanceDelete)
        self.canvas.setLabelColors(self.label_list.getLabelColors())
        
        # Job queue signals
        self.job_queue.jobStarted.connect(self.onJobStarted)
        self.job_queue.jobProgress.connect(self.onJobProgress)
        self.job_queue.jobFinished.connect(self.onJobFinished)
        self.job_queue.jobFailed.connect(self.onJobFailed)
    
    def setupMenuBar(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.newProject)
        file_menu.addAction(new_action)
        
        open_action = QAction("&Open Project", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.openProject)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        import_images_action = QAction("Import &Images...", self)
        import_images_action.setShortcut(QKeySequence("Ctrl+I"))
        import_images_action.triggered.connect(self.importImages)
        file_menu.addAction(import_images_action)
        
        import_labels_action = QAction("Import &Labels...", self)
        import_labels_action.triggered.connect(self.importLabels)
        file_menu.addAction(import_labels_action)
        
        file_menu.addSeparator()
        
        export_action = QAction("&Export Dataset...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.exportDataset)
        file_menu.addAction(export_action)
        
        # Manual save. Edits autosave, so this is a safety net rather than the
        # normal way to persist work.
        save_action = QAction("&Save Annotation", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.setStatusTip("Save the current annotation now (Ctrl+S)")
        save_action.triggered.connect(lambda: self.saveAnnotation(silent=False))
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        # Recent projects submenu
        self.recent_menu = file_menu.addMenu("Recent Projects")
        
        file_menu.addSeparator()
        
        welcome_action = QAction("&Welcome Screen...", self)
        welcome_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
        welcome_action.setStatusTip("Return to Welcome Screen to switch or create projects")
        welcome_action.triggered.connect(self.returnToWelcome)
        file_menu.addAction(welcome_action)
        
        close_project_action = QAction("&Close Project", self)
        close_project_action.setShortcut(QKeySequence("Ctrl+W"))
        close_project_action.setStatusTip("Close current project and return to Welcome Screen")
        close_project_action.triggered.connect(self.closeProject)
        file_menu.addAction(close_project_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.undo)
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("&Redo", self)
        redo_action.setShortcuts(
            [QKeySequence.Redo, QKeySequence("Ctrl+Shift+Z")]
        )
        redo_action.triggered.connect(self.redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        delete_action = QAction("&Delete", self)
        delete_action.setShortcuts(
            [QKeySequence(Qt.Key.Key_Delete), QKeySequence(Qt.Key.Key_Backspace)]
        )
        delete_action.triggered.connect(self.deleteSelected)
        edit_menu.addAction(delete_action)
        
        select_all_action = QAction("Select &All", self)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(self.selectAll)
        edit_menu.addAction(select_all_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        for tool_name, label, shortcut in [
            ("select", "Select", "V"),
            ("bbox", "Bounding Box", "B"),
            ("polygon", "Polygon", "P"),
            ("keypoint", "Keypoint", "K"),
            ("obb", "Oriented Box", "O"),
        ]:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(shortcut))
            action.setCheckable(True)
            action.setData(tool_name)
            action.triggered.connect(lambda checked, t=tool_name: self.setTool(t))
            tools_menu.addAction(action)
            setattr(self, f"tool_{tool_name}_action", action)
        
        tools_menu.addSeparator()
        
        auto_annotate_action = QAction("&Auto Annotate...", self)
        auto_annotate_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        auto_annotate_action.triggered.connect(self.showAutoAnnotate)
        tools_menu.addAction(auto_annotate_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        toggle_sidebar = QAction("Toggle Sidebar", self)
        toggle_sidebar.setShortcut(QKeySequence("Ctrl+Shift+S"))
        toggle_sidebar.setCheckable(True)
        toggle_sidebar.setChecked(True)
        toggle_sidebar.toggled.connect(self.toggleSidebar)
        view_menu.addAction(toggle_sidebar)
        
        toggle_labels = QAction("Toggle Labels Panel", self)
        toggle_labels.setShortcut(QKeySequence("Ctrl+Shift+L"))
        toggle_labels.setCheckable(True)
        toggle_labels.setChecked(True)
        toggle_labels.toggled.connect(self.toggleLabelsPanel)
        view_menu.addAction(toggle_labels)
        
        view_menu.addSeparator()
        
        # Explicit navigation shortcuts: these work even with a shape selected,
        # where the plain arrow keys nudge instead.
        prev_image = QAction("&Previous Image", self)
        prev_image.setShortcut(QKeySequence("Alt+Left"))
        prev_image.setStatusTip("Open the previous image")
        prev_image.triggered.connect(lambda: self.navigateImage(-1))
        view_menu.addAction(prev_image)
        
        next_image = QAction("&Next Image", self)
        next_image.setShortcut(QKeySequence("Alt+Right"))
        next_image.setStatusTip("Open the next image")
        next_image.triggered.connect(lambda: self.navigateImage(1))
        view_menu.addAction(next_image)
        
        view_menu.addSeparator()
        
        zoom_in = QAction("Zoom &In", self)
        zoom_in.setShortcut(QKeySequence.ZoomIn)
        zoom_in.triggered.connect(lambda: self.canvas.zoomIn())
        view_menu.addAction(zoom_in)
        
        zoom_out = QAction("Zoom &Out", self)
        zoom_out.setShortcut(QKeySequence.ZoomOut)
        zoom_out.triggered.connect(lambda: self.canvas.zoomOut())
        view_menu.addAction(zoom_out)
        
        zoom_fit = QAction("Zoom to &Fit", self)
        zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        zoom_fit.triggered.connect(lambda: self.canvas.zoomFit())
        view_menu.addAction(zoom_fit)
        
        # Settings menu
        settings_menu = menubar.addMenu("&Settings")
        
        prefs_action = QAction("&Preferences...", self)
        prefs_action.setShortcut(QKeySequence("Ctrl+,"))
        prefs_action.triggered.connect(self.showSettings)
        settings_menu.addAction(prefs_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.showAbout)
        help_menu.addAction(about_action)
    
    def returnToWelcome(self):
        """Prompt to save if dirty, then show welcome dialog."""
        self._flushAutosave()
        if self.annotations_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "There are unsaved annotations. Save before returning to the welcome screen?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if reply == QMessageBox.Save:
                self.saveAnnotation()
            elif reply == QMessageBox.Cancel:
                return
        
        self.showWelcomeDialog()

    def showWelcomeDialog(self):
        """Show welcome dialog to create/open project."""
        welcome = WelcomeWindow(self)
        if welcome.exec() != QDialog.Accepted:
            # If user explicitly requested quit or if no project is loaded on startup, exit
            if getattr(welcome, 'quit_requested', False) or not self.current_project_id:
                app = QApplication.instance()
                if app:
                    app.quit()
                self.close()
            return
        
        project_id = welcome.getSelectedProjectId()
        if project_id:
            self.loadProject(project_id)
        else:
            if not self.current_project_id:
                app = QApplication.instance()
                if app:
                    app.quit()
                self.close()
    
    # Project management
    def newProject(self):
        """Create a new project."""
        dialog = ProjectDialog(self, mode="create")
        if dialog.exec():
            name = dialog.projectName()
            base_path = dialog.basePath()
            description = dialog.description()
            
            project_id = create_project(name, base_path, description)
            self.loadProject(project_id)
    
    def openProject(self):
        """Open existing project."""
        path = QFileDialog.getExistingDirectory(
            self, "Open Project", str(PROJECTS_DIR)
        )
        if path:
            projects = get_all_projects()
            for p in projects:
                if p['base_path'] == path:
                    self.loadProject(p['id'])
                    return
            
            QMessageBox.warning(self, "Not a Project", 
                              "The selected folder is not an AnnotationEngine project.")
    
    def loadProject(self, project_id: int):
        """Load a project."""
        project = get_project(project_id)
        if not project:
            QMessageBox.critical(self, "Error", "Project not found.")
            return
        
        self.current_project_id = project_id
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - {project['name']}")
        
        # Add to recent
        add_recent_project(project_id)
        self.loadRecentProjectsMenu()
        
        # Load images
        images = get_project_images(project_id)
        self._project_images = images
        self.sidebar.setImages(images)
        
        # Load persisted label metadata for this project.
        self._suspend_label_persistence = True
        try:
            self.label_list.setLabels(get_project_labels(project_id))
        finally:
            self._suspend_label_persistence = False
        self.canvas.setLabelColors(self.label_list.getLabelColors())
        self._label_counts = {}
        self._syncGridAnnotations()
        
        # Clear canvas
        self.canvas.clear()
        self.canvas.setTool(TOOL_NAMES[self.current_tool])
        self.current_image_id = None
        self.status_bar.setShapeCount(0)
        
        # Update UI
        self.toolbar.setProjectLoaded(True)
        self.status_bar.setProject(project)
        
        self.projectLoaded.emit(project_id)
        
        # Reopen the image this project was last left on.
        self._restoreLastImage(images)
        
        # Warm the auto-annotate device list off the UI thread: enumerating
        # devices imports torch (~1.2s), and the dialog should open instantly.
        self._prewarmAutoAnnotate()
    
    def _restoreLastImage(self, images: List[dict]):
        """Reopen the project's last viewed image, if it still exists."""
        if not images or not self.current_project_id:
            return
        last_id = get_last_image_id(self.current_project_id)
        known = {image['id'] for image in images}
        if last_id is not None and last_id in known:
            self.sidebar.setLastSeen(last_id)
            self.loadImage(last_id)
        else:
            # A stale id (deleted image) is ignored; the next load overwrites it.
            self.sidebar.setLastSeen(None)
    
    def _prewarmAutoAnnotate(self):
        """Prepare auto-annotate dependencies in the background.

        Runs once per session, with no dialogs or progress UI: the only cost
        paid is a background thread that finishes before the user opens the
        Auto Annotate menu.
        """
        if self._auto_annotate_warmed or self._prewarm_thread is not None:
            return
        self._auto_annotate_warmed = True
        
        from annotation_engine.services.device import prewarm_devices
        
        class _WarmWorker(QObject):
            finished = Signal()
            
            @Slot()
            def run(self):
                try:
                    prewarm_devices()
                except Exception as exc:  # never let warm-up break the app
                    logger.warning("Auto-annotate warm-up failed: %s", exc)
                finally:
                    self.finished.emit()
        
        thread = QThread(self)
        worker = _WarmWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._onPrewarmFinished)
        self._prewarm_thread = thread
        self._prewarm_worker = worker
        thread.start()
    
    def _onPrewarmFinished(self):
        self._prewarm_thread = None
        self._prewarm_worker = None
    
    def closeProject(self):
        """Close current project."""
        self._flushAutosave()
        if self.annotations_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "There are unsaved annotations. Save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if reply == QMessageBox.Save:
                self.saveAnnotation()
            elif reply == QMessageBox.Cancel:
                return
        
        self.current_project_id = None
        self.current_image_id = None
        self._project_images = []
        self.sidebar.clear()
        self.canvas.clear()
        self._suspend_label_persistence = True
        try:
            self.label_list.clear()
        finally:
            self._suspend_label_persistence = False
        self.canvas.setLabelColors({})
        self.toolbar.setProjectLoaded(False)
        self.status_bar.clearProject()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.showWelcomeDialog()
    
    # Image management
    def importImages(self):
        """Open import images dialog."""
        if not self.current_project_id:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        
        dialog = ImportImagesDialog(self, self.current_project_id)
        if dialog.exec():
            self.refreshImageGrid()
    
    def importLabels(self):
        """Open import labels dialog."""
        if not self.current_project_id:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        
        dialog = ImportLabelsDialog(self, self.current_project_id)
        if dialog.exec():
            self.refreshImageGrid()
            # Reflect imported annotations for the open image without
            # clobbering unsaved edits.
            if self.current_image_id and not self.annotations_dirty:
                annotation = get_annotation(self.current_image_id)
                shapes = annotation['data'].get('shapes', []) if annotation else []
                self.canvas.loadShapes(shapes)
                self._label_counts = {}
                self.syncLabelsFromShapes()
                self.annotations_dirty = False
    
    def refreshImageGrid(self):
        """Refresh the image grid."""
        if self.current_project_id:
            images = get_project_images(self.current_project_id)
            self._project_images = images
            self.sidebar.setImages(images)
            self._syncGridAnnotations()

    def _gridLabelMeta(self):
        """Return (colors, visibility) maps for the current label list."""
        colors = self.label_list.getLabelColors()
        visibility = {
            label: bool(data.get('visible', True))
            for label, data in self.label_list.labels.items()
        }
        return colors, visibility

    def _pushGridLabelMeta(self):
        """Push label colors/visibility into the grid (no annotation refetch)."""
        if not self.current_project_id:
            return
        colors, visibility = self._gridLabelMeta()
        self.sidebar.setAnnotationData(
            annotations=None,
            label_colors=colors,
            label_visibility=visibility,
        )

    def _syncGridAnnotations(self):
        """Reload saved annotations and label metadata into the grid overlays."""
        if not self.current_project_id:
            return
        annotations = get_project_annotations(self.current_project_id)
        colors, visibility = self._gridLabelMeta()
        self.sidebar.setAnnotationData(
            annotations=annotations,
            label_colors=colors,
            label_visibility=visibility,
        )
    
    # Image management
    def onImageSelected(self, image_id: int):
        """Handle image selection from sidebar."""
        self.loadImage(image_id)
    
    def onImageDoubleClicked(self, image_id: int):
        """Handle image double-click."""
        self.loadImage(image_id)
    
    def onSelectionChanged(self, image_ids: List[int]):
        """Handle multi-selection change."""
        self.toolbar.setSelectionCount(len(image_ids))
    
    def loadImage(self, image_id: int):
        """Load image into canvas."""
        if self.current_image_id == image_id:
            return
        
        # Persist pending edits before the canvas switches images; otherwise a
        # queued autosave would write the old shapes into the new image.
        if self.annotations_dirty and self.current_image_id:
            self._autosave_timer.stop()
            self.saveAnnotation(silent=True)
        
        image = get_image(image_id)
        if not image:
            return
        
        image_path = os.path.join(
            get_project(self.current_project_id)['base_path'],
            image['relative_path']
        )
        
        if self.canvas.loadImage(image_path):
            self.current_image_id = image_id
            
            # Load existing annotation
            annotation = get_annotation(image_id)
            shapes = annotation['data'].get('shapes', []) if annotation else []
            self.canvas.loadShapes(shapes)
            # Switching images is not a label edit: start the count baseline
            # fresh so the new image never prunes labels from the old one.
            self._label_counts = {}
            self.syncLabelsFromShapes()
            self.status_bar.setShapeCount(len(self.canvas.shapes))
            
            self.annotations_dirty = False
            self.imageSelected.emit(image_id)
            self.status_bar.setImage(image)
            self._updateWindowTitle(image_id)
            # Remember where the user left off so reopening the project lands
            # on the same image.
            set_last_image_id(self.current_project_id, image_id)
            self.sidebar.setLastSeen(image_id)
            self.sidebar.revealImage(image_id)
            # Focus the canvas so drawing and arrow-key nudging work straight
            # away, without needing a click on the image first.
            self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            QMessageBox.warning(self, "Error", "Failed to load image.")

    def _imageIndex(self, image_id: int) -> Optional[tuple]:
        """Return (index, total) for an image, or None when not found."""
        for i, image in enumerate(self._project_images, start=1):
            if image['id'] == image_id:
                return (i, len(self._project_images))
        return None

    def _updateWindowTitle(self, image_id: Optional[int] = None):
        """Refresh the title bar with the current image index, e.g. '2/98'."""
        if not self.current_project_id:
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
            return
        project = get_project(self.current_project_id)
        name = project['name'] if project else ""
        position = self._imageIndex(image_id) if image_id is not None else None
        if position:
            index, total = position
            self.setWindowTitle(
                f"{APP_NAME} v{APP_VERSION} - {name} - {index}/{total}"
            )
        else:
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - {name}")
    
    # Annotation handling
    def syncLabelsFromShapes(self):
        """Add any shape labels to the label list and refresh their counts."""
        shapes = self.canvas.getShapesData() if self.canvas else []
        previous_counts = dict(self._label_counts)
        self.label_list.syncFromShapes(shapes)

        counts: dict = {}
        for shape in shapes:
            label = shape.get('label') or ''
            if label:
                counts[label] = counts.get(label, 0) + 1
        self._label_counts = counts

        # A label whose last shape just disappeared is clutter: drop it, but
        # only when no other image still uses it.
        vacated = [
            label
            for label, before in previous_counts.items()
            if before > 0 and counts.get(label, 0) == 0
        ]
        if vacated:
            self._pruneVacatedLabels(vacated)

        self.canvas.setLabelColors(self.label_list.getLabelColors())
        self.canvas.applyLabelVisibilities(
            {
                label: bool(data.get('visible', True))
                for label, data in self.label_list.labels.items()
            }
        )
        self.status_bar.setShapeCount(len(shapes))
        self._pushGridLabelMeta()

    def _pruneVacatedLabels(self, labels: List[str]):
        """Remove label categories that no shape in any image uses anymore."""
        if not self.current_project_id:
            return
        for label in labels:
            if label not in self.label_list.labels:
                continue
            if self.label_list.labelCount(label) > 0:
                continue
            if label_in_use(
                self.current_project_id,
                label,
                exclude_image_id=self.current_image_id,
            ):
                continue
            self.label_list.removeLabel(label)
    
    def onShapeCreated(self, shape_data: dict):
        self._markDirty()
        self.syncLabelsFromShapes()
    
    def onShapeModified(self, shape_data: dict):
        self._markDirty()
        self.syncLabelsFromShapes()
    
    def onShapeDeleted(self, shape_index: int):
        self._markDirty()
        self.syncLabelsFromShapes()
    
    def onCanvasSelectionChanged(self, selected_indices: List[int]):
        shapes = self.canvas.getShapesData() if self.canvas else []
        selected_labels = [
            shapes[i].get('label')
            for i in selected_indices
            if 0 <= i < len(shapes) and shapes[i].get('label')
        ]
        self.label_list.setSelectedLabels(selected_labels)
        self.status_bar.setShapeCount(len(shapes))
        self.toolbar.setDeleteEnabled(bool(selected_indices))
    
    def onLabelSelected(self, label: str):
        self.canvas.setSelectedLabel(label)
    
    def onLabelVisibilityChanged(self, label: str, visible: bool):
        self.canvas.setLabelVisibility(label, visible)
        self._pushGridLabelMeta()

    def onLabelColorChanged(self, label: str, color: str):
        self.canvas.setLabelColors(self.label_list.getLabelColors())
        self._pushGridLabelMeta()

    def onCanvasMouseMoved(self, pos):
        self.status_bar.setCoordinates(pos.x(), pos.y())

    # ------------------------------------------------------------------
    # Image navigation
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        """Let Left/Right switch images when nothing is selected.

        Installed on the QApplication rather than the canvas: Qt only delivers
        key events to the focused widget, and the canvas is not focused until
        the user clicks it. Filtering at application level keeps navigation
        working wherever focus happens to be, while the guards below leave the
        keys alone in widgets that need them.
        """
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                if event.modifiers() not in (
                    Qt.KeyboardModifier.NoModifier,
                    Qt.KeyboardModifier.KeypadModifier,
                ):
                    return super().eventFilter(obj, event)
                # Check the focused widget, not `obj`: an unhandled key
                # propagates up the parent chain, so `obj` can be an ancestor
                # even though the key was pressed in a combo or text field.
                target = QApplication.focusWidget() or obj
                if self._widgetNeedsArrowKeys(target):
                    return super().eventFilter(obj, event)
                if QApplication.activeModalWidget() is not None:
                    return super().eventFilter(obj, event)
                if self._canvasAllowsArrowNavigation():
                    step = -1 if event.key() == Qt.Key.Key_Left else 1
                    self.navigateImage(step)
                    return True
        return super().eventFilter(obj, event)

    def _widgetNeedsArrowKeys(self, widget) -> bool:
        """Whether a focused widget uses the arrow keys itself.

        Text entry needs them for the caret, spin boxes and combos to change
        value, and item views to move their selection. The image grid is the
        deliberate exception: arrowing through it should open the image.
        """
        if isinstance(
            widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)
        ):
            return True
        if isinstance(widget, QAbstractItemView):
            grid_view = getattr(getattr(self, "sidebar", None), "image_grid", None)
            return widget is not getattr(grid_view, "list_view", None)
        return False

    def _canvasAllowsArrowNavigation(self) -> bool:
        """Whether arrow keys should switch images instead of nudging."""
        if not self.current_project_id:
            return False
        if getattr(self.canvas, "is_drawing", False):
            return False
        selected = getattr(self.canvas, "selected_shapes", None) or []
        return not selected

    def navigateImage(self, step: int):
        """Open the previous/next image in the grid's visible order."""
        if not self.current_project_id or not step:
            return
        ids = self.sidebar.visibleImageIds()
        if not ids:
            return

        if self.current_image_id in ids:
            index = ids.index(self.current_image_id) + step
        else:
            # Nothing open yet: step opens the first (or last) image.
            index = 0 if step > 0 else len(ids) - 1

        if not 0 <= index < len(ids):
            return
        self.loadImage(ids[index])

    def onCanvasShapesChanged(self):
        """Refresh the UI after a canvas-initiated shape edit."""
        if self.current_image_id:
            self._afterShapeHistoryChange()
        else:
            self.syncLabelsFromShapes()

    def _saveProjectLabels(self):
        """Persist the current label metadata for the active project."""
        if self._suspend_label_persistence or not self.current_project_id:
            return
        save_project_labels(
            self.current_project_id, self.label_list.getLabelState()
        )

    def onLabelRename(self, old_label: str):
        """Rename a label category, optionally across the whole project."""
        dialog = RenameLabelDialog(
            self,
            old_label=old_label,
            existing_labels=self.label_list.getLabels(),
            allow_scope=True,
            has_current_image=bool(self.current_image_id),
        )
        if not dialog.exec():
            return

        new_label = dialog.newLabel()
        if not new_label or new_label == old_label:
            return

        scope = dialog.scope()
        target_exists = new_label in self.label_list.getLabels()
        old_color = self.label_list.labelColor(old_label)

        # Does another image still need the old category? Renaming only this
        # image must not take the category (and its color) away from them.
        old_used_elsewhere = bool(
            self.current_project_id
            and label_in_use(
                self.current_project_id,
                old_label,
                exclude_image_id=self.current_image_id,
            )
        )

        # Register the new label first so the shape refresh that follows reuses
        # the intended color instead of a palette fallback.
        if not target_exists:
            self.label_list.addLabel(new_label, color=old_color)

        if scope == "project" and self.current_project_id:
            rename_label_in_project(
                self.current_project_id, old_label, new_label
            )
            self.canvas.renameLabelCategory(old_label, new_label)
            self.label_list.renameLabel(old_label, new_label)
        else:
            if self.current_image_id:
                self.canvas.renameLabelCategory(old_label, new_label)
            if not old_used_elsewhere:
                self.label_list.renameLabel(old_label, new_label)

        self._saveProjectLabels()
        self.syncLabelsFromShapes()

    def onLabelSelectShapes(self, label: str):
        self.canvas.selectShapesByLabel(label)

    def onInstanceClicked(self, index: int):
        """Select a single shape instance (a layer of a label) on the canvas."""
        if not self.canvas or not (0 <= index < len(self.canvas.shapes)):
            return
        try:
            self.canvas.select_shapes(shapes=[self.canvas.shapes[index]])
        except (AttributeError, TypeError):
            self.canvas.selected_shapes = [self.canvas.shapes[index]]
        self.canvas.update()

    def onInstanceDelete(self, index: int):
        """Delete a single shape instance (a layer of a label)."""
        if not self.canvas or not (0 <= index < len(self.canvas.shapes)):
            return
        try:
            self.canvas.select_shapes(shapes=[self.canvas.shapes[index]])
        except (AttributeError, TypeError):
            self.canvas.selected_shapes = [self.canvas.shapes[index]]
        self.canvas.deleteSelected()

    def onLabelDeleteShapes(self, label: str):
        if self.canvas.deleteShapesByLabel(label):
            self.label_list.removeLabel(label)
            self._afterShapeHistoryChange()

    def onLabelRemove(self, label: str):
        count = self.label_list.labelCount(label)
        if count > 0:
            reply = QMessageBox.question(
                self, "Remove Label",
                f"'{label}' is used by {count} shape(s).\n"
                "Delete those shapes and remove the label?",
                QMessageBox.Yes | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return
            if not self.canvas.deleteShapesByLabel(label):
                return
        self.label_list.removeLabel(label)
        self._afterShapeHistoryChange()
    
    def onZoomChanged(self, zoom: float):
        self.zoom_widget.setZoom(zoom)
        self.status_bar.setZoom(zoom)
    
    def saveAnnotation(self, silent: bool = True):
        """Persist the current image's shapes to the database and label file.

        Autosave calls this with ``silent`` so routine edits do not flash a
        status message on every change.
        """
        if not self.current_image_id or not self.current_project_id:
            return
        
        shapes = self.canvas.getShapesData()
        image = get_image(self.current_image_id)
        if not image:
            return
        
        annotation_data = build_labelme_payload(
            shapes=shapes,
            image_path=self._labelImagePath(image),
            image_width=image['width'] or 0,
            image_height=image['height'] or 0,
        )
        
        save_annotation(self.current_image_id, annotation_data)
        update_image(self.current_image_id, has_annotation=1)
        self._writeLabelFile(image, annotation_data)
        self.annotations_dirty = False
        self.syncLabelsFromShapes()
        self._syncGridAnnotations()
        if not silent:
            self.status_bar.showMessage("Annotation saved", 2000)
    
    def _labelImagePath(self, image: dict) -> str:
        """Return the image path LabelMe should store in the label file.

        LabelMe resolves ``imagePath`` relative to the label file, and label
        files live in ``<project>/labels``, so the sibling images directory is
        reached with ``../images/<name>``.
        """
        relative = (image.get('relative_path') or image.get('filename') or '').replace('\\', '/')
        return f"../{relative}" if relative else (image.get('filename') or '')
    
    def _labelFilePath(self, image: dict) -> Optional[Path]:
        """Return ``<project>/labels/<image stem>.json`` for an image."""
        project = get_project(self.current_project_id)
        if not project:
            return None
        filename = image.get('filename') or ''
        if not filename:
            return None
        return Path(project['base_path']) / 'labels' / f"{Path(filename).stem}.json"
    
    def _writeLabelFile(self, image: dict, payload: dict):
        """Mirror the annotation to a standard LabelMe JSON file."""
        label_path = self._labelFilePath(image)
        if label_path is not None:
            write_labelme_json(payload, label_path)
    
    def _markDirty(self):
        """Flag the annotation as changed and schedule an autosave."""
        if not self.current_image_id:
            return
        self.annotations_dirty = True
        if not self._suspend_autosave:
            self._autosave_timer.start()
    
    def _flushAutosave(self):
        """Persist pending edits now, if any."""
        self._autosave_timer.stop()
        if self.annotations_dirty:
            self.saveAnnotation(silent=True)
    
    def _afterShapeHistoryChange(self):
        """Refresh UI state after an undo/redo or bulk label deletion."""
        if not self.current_image_id:
            return
        self._markDirty()
        self.syncLabelsFromShapes()
        self.status_bar.setShapeCount(len(self.canvas.shapes))

    def undo(self):
        if self.canvas and self.canvas.undo():
            self._afterShapeHistoryChange()
    
    def redo(self):
        if self.canvas and self.canvas.redo():
            self._afterShapeHistoryChange()
    
    def deleteSelected(self):
        if self.canvas:
            self.canvas.deleteSelected()
    
    def selectAll(self):
        if self.canvas:
            self.canvas.selectAll()
    
    def setTool(self, tool_name: str):
        if tool_name not in TOOL_NAMES:
            return
        
        self.current_tool = tool_name
        self.canvas.setTool(TOOL_NAMES[tool_name])
        
        # Update toolbar button states
        for t in TOOL_NAMES:
            action = getattr(self, f"tool_{t}_action", None)
            if action:
                action.setChecked(t == tool_name)
        
        self.toolbar.setTool(tool_name)
        self.toolChanged.emit(tool_name)
    
    # Auto-annotate
    def showAutoAnnotate(self):
        if not self.current_project_id:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        
        selected_images = self.sidebar.getSelectedImageIds()
        if not selected_images:
            images = get_project_images(self.current_project_id)
            selected_images = [img['id'] for img in images]
        
        dialog = AutoAnnotateDialog(
            self,
            self.current_project_id,
            selected_images,
            labels=self._autoAnnotateLabels(),
            annotated_count=len(
                get_project_annotations(self.current_project_id)
            ),
        )
        dialog.runMobileSAM.connect(self.runMobileSam)
        dialog.downloadMobileSAM.connect(self.downloadMobileSamModel)
        dialog.runYolo.connect(self.runYolo)
        dialog.loadYoloModel.connect(self.loadYoloModel)
        dialog.runGroundingDINO.connect(self.runGroundingDINO)
        self._auto_annotate_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._auto_annotate_dialog = None

    def _autoAnnotateLabels(self) -> List[str]:
        """Labels offered to the auto-annotate dialogs, in sidebar order."""
        labels = list(self.label_list.getLabels()) if self.label_list else []
        if labels or not self.current_project_id:
            return labels
        return [row['name'] for row in get_project_labels(self.current_project_id)]

    # ------------------------------------------------------------------
    # MobileSAM
    # ------------------------------------------------------------------
    def mobileSamService(self, device: str = None) -> MobileSAMService:
        """Return the shared MobileSAM service, creating it on first use.

        A changed device preference replaces the service, since the device is
        resolved once at construction.
        """
        from annotation_engine.services.device import DEVICE_AUTO

        wanted = device or DEVICE_AUTO
        if (
            self._mobile_sam is None
            or getattr(self._mobile_sam, "device_preference", None) != wanted
        ):
            if self._mobile_sam is not None:
                self._mobile_sam.unload()
            self._mobile_sam = MobileSAMService(device=wanted)
        return self._mobile_sam

    def downloadMobileSamModel(self):
        """Download the MobileSAM checkpoint into the models directory."""
        dialog = self._auto_annotate_dialog

        def worker(progress_callback=None):
            return str(download_mobile_sam(progress_callback=progress_callback))

        def on_done(path: str):
            if dialog is not None:
                dialog.refreshModelStatus()
                dialog.setProgress(100, "MobileSAM model ready")
            self.status_bar.showMessage(f"MobileSAM model saved to {path}", 5000)

        def on_error(message: str):
            if dialog is not None:
                dialog.setProgress(0, "Download failed")
            QMessageBox.critical(
                self, "Download Failed",
                f"Could not download the MobileSAM model:\n{message}"
            )

        self._runBackgroundJob(
            'mobile_sam_download', worker, on_done, on_error,
            title="Downloading MobileSAM",
        )

    def runMobileSam(self, options: dict):
        """Segment boxes with MobileSAM, in the background."""
        if not self.current_project_id:
            return

        label = options.get('label')
        labels = options.get('labels')
        if labels is None:
            # Older callers passed a single label (or the all-labels sentinel).
            labels = [] if label in (None, '', '__all__') else [label]
        labels = [name for name in labels if name]
        source = options.get('source') or 'existing'
        device = options.get('device') or 'auto'
        remove_boxes = bool(options.get('remove_boxes'))

        if source == 'existing':
            if not self.current_image_id:
                QMessageBox.warning(
                    self, "No Image", "Open an image before running MobileSAM."
                )
                return
            image_ids = [self.current_image_id]
        else:
            # "All annotated images" means exactly that. The dialog's selection
            # holds whatever the user clicked to open an image, so it cannot be
            # used to decide the scope.
            image_ids = list(
                get_project_annotations(self.current_project_id).keys()
            )

        # Persist in-flight edits first: the boxes are read from saved data.
        self._flushAutosave()

        tasks = []
        skipped = 0
        for image_id in image_ids:
            image = get_image(image_id)
            if not image:
                continue
            project = get_project(self.current_project_id)
            if not project:
                return
            image_path = os.path.join(project['base_path'], image['relative_path'])

            annotation = get_annotation(image_id)
            shapes = annotation['data'].get('shapes', []) if annotation else []
            matched = [
                (index, shape) for index, shape in enumerate(shapes)
                if self._boxMatchesLabels(shape, labels)
            ]
            prompts = []
            for _, shape in matched:
                box = self._shapeBox(shape)
                if box is not None:
                    prompts.append({
                        'box': box,
                        'label': shape.get('label') or 'object',
                        'removable': (shape.get('shape_type') or '') == 'rectangle',
                        'shape': shape,
                    })
            if not prompts:
                skipped += 1
                continue
            tasks.append({
                'image_id': image_id,
                'image_path': image_path,
                'prompts': prompts,
                'shapes': shapes,
            })

        if not tasks:
            QMessageBox.information(
                self, "MobileSAM",
                "No rectangles matched. Draw bounding boxes first, or tick "
                "the labels you want to segment."
            )
            return

        min_score = float(options.get('iou_threshold') or 0.0)
        # A single ticked label names the output; otherwise each mask keeps the
        # label of the box that prompted it.
        fallback_label = labels[0] if len(labels) == 1 else None

        def worker(progress_callback=None):
            service = self.mobileSamService(device)
            results = {}
            skipped_boxes = []
            total = len(tasks)
            for index, task in enumerate(tasks):
                def report(percent, message, _i=index):
                    overall = int(((_i + percent / 100) / total) * 100)
                    progress_callback(overall, message)

                # Each mask keeps the label of the box that prompted it, so an
                # all-labels run still produces per-class shapes.
                entries = service.segment_labeled(
                    task['image_path'],
                    [prompt['box'] for prompt in task['prompts']],
                    [prompt['label'] for prompt in task['prompts']],
                    report,
                    min_score=min_score,
                )
                results[task['image_id']] = entries
                for missing in getattr(service, 'last_skipped_labels', []):
                    skipped_boxes.append((task['image_id'], missing))
            return {
                'results': results,
                'label': fallback_label,
                'tasks': tasks,
                'device': service.device_description,
                'skipped_boxes': skipped_boxes,
            }

        def on_done(result: dict):
            self._applyMobileSamResult(result, remove_boxes=remove_boxes)
            for image_id, missing in result.get('skipped_boxes') or []:
                logger.info(
                    "MobileSAM skipped a box on image %s (label %r): "
                    "no mask above the confidence floor",
                    image_id, missing,
                )
            if skipped:
                self.status_bar.showMessage(
                    f"MobileSAM finished; {skipped} image(s) had no matching boxes",
                    4000,
                )

        def on_error(message: str):
            QMessageBox.critical(
                self, "MobileSAM Failed", f"Segmentation failed:\n{message}"
            )

        self._mobile_sam_job = self._runBackgroundJob(
            'mobile_sam', worker, on_done, on_error,
            title="Running MobileSAM",
        )

    @staticmethod
    def _shapeBox(shape: dict) -> Optional[List[float]]:
        """Return a shape's bounding box as ``[x1, y1, x2, y2]``."""
        points = shape.get('points') or []
        if not points:
            return None
        xs = [p[0] for p in points if len(p) >= 2]
        ys = [p[1] for p in points if len(p) >= 2]
        if not xs or not ys:
            return None
        return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]

    @staticmethod
    def _boxMatchesLabels(shape: dict, labels: Optional[List[str]]) -> bool:
        """Whether a shape should prompt MobileSAM for the chosen labels.

        Only rectangles qualify. MobileSAM is box-prompted, and a generated
        polygon must never feed back in as a prompt: doing so re-segments it
        on every run and multiplies the shape count.
        """
        if (shape.get('shape_type') or '') != 'rectangle':
            return False
        if not labels:
            return True
        return (shape.get('label') or '') in set(labels)

    def _applyMobileSamResult(self, result: dict, *, remove_boxes: bool = False):
        """Add the generated polygons to each image, dropping their prompts."""
        results = result.get('results') or {}
        tasks = {task['image_id']: task for task in (result.get('tasks') or [])}
        fallback_label = result.get('label')
        added = 0
        removed = 0
        duplicates = 0
        others_changed = False

        for image_id, entries in results.items():
            if not entries:
                continue
            image = get_image(image_id)
            if not image:
                continue

            task = tasks.get(image_id) or {}
            source_shapes = list(task.get('shapes') or [])
            prompts = task.get('prompts') or []

            # Which prompts actually produced a mask, identified by identity of
            # the box rather than list position, so a concurrent edit cannot
            # make us delete the wrong shape.
            used = set()
            for prompt_index, _label, _polygon in entries:
                if 0 <= prompt_index < len(prompts):
                    used.add(prompt_index)

            if remove_boxes:
                # Only rectangles: a hand-drawn polygon may carry detail the
                # mask does not reproduce.
                doomed = [
                    id(prompts[i]['shape'])
                    for i in used
                    if prompts[i].get('removable')
                ]
                kept = [s for s in source_shapes if id(s) not in doomed]
                removed += len(source_shapes) - len(kept)
                source_shapes = kept

            new_shapes = list(source_shapes)
            skipped_duplicates = 0
            for _index, label, polygon in entries:
                final_label = label or fallback_label or 'object'
                if self._hasEquivalentPolygon(new_shapes, final_label, polygon):
                    # Already segmented: re-adding it would duplicate the shape
                    # every time the user re-runs with boxes kept.
                    skipped_duplicates += 1
                    continue
                new_shapes.append({
                    'label': final_label,
                    'points': polygon,
                    'group_id': None,
                    'description': '',
                    'shape_type': 'polygon',
                    'flags': {},
                    'mask': None,
                })
                added += 1

            duplicates += skipped_duplicates

            if image_id == self.current_image_id:
                # applyShapes keeps the undo history, so both the new masks and
                # the removed prompts can be undone with Ctrl+Z.
                self.canvas.applyShapes(new_shapes)
            else:
                self._saveShapesForImage(image, new_shapes)
                others_changed = True

        if others_changed:
            # Other images were written straight to the database; refresh the
            # grid so their thumbnails stop showing stale annotations.
            self._syncGridAnnotations()

        device = result.get('device')
        suffix = f" on {device}" if device else ""
        skipped_boxes = len(result.get('skipped_boxes') or [])
        if added:
            detail = f"MobileSAM added {added} shape(s){suffix}"
            if removed:
                detail += f", removed {removed} box(es)"
            if duplicates:
                detail += f", skipped {duplicates} already-segmented box(es)"
            if skipped_boxes:
                detail += f"; {skipped_boxes} box(es) had no usable mask"
            self.status_bar.showMessage(detail, 6000)
        elif duplicates:
            self.status_bar.showMessage(
                f"MobileSAM skipped {duplicates} already-segmented box(es)",
                5000,
            )
        else:
            message = "MobileSAM produced no usable masks"
            if skipped_boxes:
                message += f" ({skipped_boxes} box(es) below the confidence floor)"
            self.status_bar.showMessage(message, 5000)

    # Tolerance in pixels when deciding two masks are the same shape.
    POLYGON_MATCH_TOLERANCE = 2.0

    @classmethod
    def _hasEquivalentPolygon(cls, shapes: List[dict], label: str,
                              polygon: List[List[float]]) -> bool:
        """Whether ``shapes`` already holds this polygon under this label.

        MobileSAM is deterministic, so a re-run over the same box reproduces
        the same outline; comparing bounds is enough to spot it. The small
        tolerance absorbs float noise without merging genuinely distinct masks.
        """
        new_bounds = cls._polygonBounds(polygon)
        if new_bounds is None:
            return False
        for shape in shapes:
            if (shape.get('shape_type') or '') != 'polygon':
                continue
            if (shape.get('label') or '') != label:
                continue
            bounds = cls._polygonBounds(shape.get('points') or [])
            if bounds is None:
                continue
            if all(
                abs(a - b) <= cls.POLYGON_MATCH_TOLERANCE
                for a, b in zip(bounds, new_bounds)
            ):
                return True
        return False

    @staticmethod
    def _polygonBounds(points: List) -> Optional[List[float]]:
        """Return ``[min_x, min_y, max_x, max_y]`` for a point list."""
        coords = [
            (float(p[0]), float(p[1]))
            for p in (points or [])
            if len(p) >= 2
        ]
        if not coords:
            return None
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return [min(xs), min(ys), max(xs), max(ys)]

    def _saveShapesForImage(self, image: dict, shapes: List[dict]):
        """Persist shapes for an image that is not currently open."""
        payload = build_labelme_payload(
            shapes=shapes,
            image_path=self._labelImagePath(image),
            image_width=image['width'] or 0,
            image_height=image['height'] or 0,
        )
        save_annotation(image['id'], payload)
        update_image(image['id'], has_annotation=1)
        self._writeLabelFile(image, payload)

    # ------------------------------------------------------------------
    # YOLO
    # ------------------------------------------------------------------
    def yoloService(self, model_path: str, device: str = None) -> YOLOService:
        """Return the YOLO service for a model path + device, cached."""
        from annotation_engine.services.device import DEVICE_AUTO

        wanted = device or DEVICE_AUTO
        key = (str(model_path), wanted)
        service = self._yolo_services.get(key)
        if service is None:
            service = YOLOService(model_path, device=wanted)
            self._yolo_services[key] = service
        return service

    def loadYoloModel(self, options: dict):
        """Load a YOLO model in the background and report its task + classes."""
        model_path = options.get('model_path')
        if not model_path:
            return
        device = options.get('device') or 'auto'
        dialog = self._auto_annotate_dialog

        def worker(progress_callback=None):
            service = self.yoloService(model_path, device)
            return service.load(progress_callback)

        def on_done(info: dict):
            if dialog is not None:
                dialog.setYoloModelInfo(info.get('task'), info.get('names') or {})
                dialog.setYoloRunning(False)
            self.status_bar.showMessage(
                f"YOLO model loaded ({info.get('task')})", 3000
            )

        def on_error(message: str):
            if dialog is not None:
                dialog.setYoloRunning(False)
                dialog.yolo_task_label.setText("Failed to load model")
            QMessageBox.critical(
                self, "YOLO Load Failed", f"Could not load the model:\n{message}"
            )

        if dialog is not None:
            dialog.setYoloRunning(True)
        self._runBackgroundJob(
            'yolo_load', worker, on_done, on_error, title="Loading YOLO model",
        )

    def runYolo(self, options: dict):
        """Run YOLO inference over the chosen images in the background."""
        if not self.current_project_id:
            return

        model_path = options.get('model_path')
        if not model_path:
            QMessageBox.warning(self, "YOLO", "Pick a model file first.")
            return
        labels = [name for name in (options.get('labels') or []) if name]
        if not labels:
            QMessageBox.warning(self, "YOLO", "Tick at least one label.")
            return

        conf = float(options.get('conf') or 0.25)
        iou = float(options.get('iou') or 0.45)
        device = options.get('device') or 'auto'
        scope = options.get('scope') or 'current'

        if scope == 'all':
            image_ids = [img['id'] for img in get_project_images(self.current_project_id)]
        else:
            if not self.current_image_id:
                QMessageBox.warning(self, "No Image", "Open an image before running YOLO.")
                return
            image_ids = [self.current_image_id]

        # Persist in-flight edits first: shapes are appended to saved data.
        self._flushAutosave()

        tasks = []
        for image_id in image_ids:
            image = get_image(image_id)
            if not image:
                continue
            project = get_project(self.current_project_id)
            if not project:
                return
            tasks.append({
                'image_id': image_id,
                'image_path': os.path.join(project['base_path'], image['relative_path']),
            })

        if not tasks:
            return

        def worker(progress_callback=None):
            service = self.yoloService(model_path, device)
            results = {}
            total = len(tasks)
            for index, task in enumerate(tasks):
                def report(percent, message, _i=index):
                    overall = int(((_i + percent / 100) / total) * 100)
                    progress_callback(overall, message)
                results[task['image_id']] = service.predict(
                    task['image_path'], labels, conf, iou, report
                )
            return {'results': results, 'device': service.device_description}

        def on_done(result: dict):
            self._applyYoloResult(result)

        def on_error(message: str):
            QMessageBox.critical(
                self, "YOLO Failed", f"Inference failed:\n{message}"
            )

        self._yolo_job = self._runBackgroundJob(
            'yolo', worker, on_done, on_error, title="Running YOLO",
        )

    def _applyYoloResult(self, result: dict):
        """Add generated shapes; undoable on the current image, else a write."""
        results = result.get('results') or {}
        added = 0
        others_changed = False

        for image_id, shapes in results.items():
            if not shapes:
                continue
            image = get_image(image_id)
            if not image:
                continue

            if image_id == self.current_image_id:
                self.canvas.appendShapes(shapes)
            else:
                annotation = get_annotation(image_id)
                existing = annotation['data'].get('shapes', []) if annotation else []
                self._saveShapesForImage(image, list(existing) + list(shapes))
                others_changed = True
            added += len(shapes)

        if others_changed:
            self._syncGridAnnotations()

        device = result.get('device')
        suffix = f" on {device}" if device else ""
        if added:
            self.status_bar.showMessage(f"YOLO added {added} shape(s){suffix}", 6000)
        else:
            self.status_bar.showMessage("YOLO produced no detections", 5000)

    # ------------------------------------------------------------------
    # Grounding DINO
    # ------------------------------------------------------------------
    def _hfApiKey(self) -> str:
        encrypted = get_setting('hf_api_key_encrypted', '') or ''
        return self.encryption.decrypt(encrypted) if encrypted else ''

    def groundingDinoMode(self) -> str:
        if self._grounding_dino_mode is None:
            self._grounding_dino_mode = grounding_dino_mode()
        return self._grounding_dino_mode

    def localGroundingDinoService(self, device: str = None):
        from annotation_engine.services.device import DEVICE_AUTO

        key = device or DEVICE_AUTO
        service = self._local_grounding_dino.get(key)
        if service is None:
            service = LocalGroundingDINOService(device=key)
            self._local_grounding_dino[key] = service
        return service

    def runGroundingDINO(self, options: dict):
        """Run Grounding DINO (local GPU or HF cloud) in the background."""
        if not self.current_project_id:
            return
        prompts = [p for p in (options.get('prompts') or []) if p]
        if not prompts:
            return
        threshold = float(options.get('threshold') or 0.3)
        device = options.get('device') or 'auto'
        scope = options.get('scope') or 'current'
        mode = options.get('mode') or self.groundingDinoMode()

        api_key = ''
        if mode == 'cloud':
            api_key = self._hfApiKey()
            if not api_key:
                QMessageBox.warning(
                    self, "Grounding DINO",
                    "Cloud mode requires a Hugging Face API key.\n"
                    "Set it in Settings → API Keys.",
                )
                return
            scope = 'current'  # cloud processes one image at a time

        if scope == 'all':
            image_ids = [img['id'] for img in get_project_images(self.current_project_id)]
        else:
            if not self.current_image_id:
                QMessageBox.warning(self, "No Image", "Open an image before running Grounding DINO.")
                return
            image_ids = [self.current_image_id]

        self._flushAutosave()

        tasks = []
        for image_id in image_ids:
            image = get_image(image_id)
            if not image:
                continue
            project = get_project(self.current_project_id)
            if not project:
                return
            tasks.append({
                'image_id': image_id,
                'image_path': os.path.join(project['base_path'], image['relative_path']),
            })
        if not tasks:
            return

        text_prompt = ', '.join(prompts)

        def worker(progress_callback=None):
            if mode == 'local':
                service = self.localGroundingDinoService(device)
                device_label = service.device_description
            else:
                service = GroundingDINOSync(api_key)
                device_label = 'cloud'
            results = {}
            total = len(tasks)
            for i, task in enumerate(tasks):
                def report(percent, message, _i=i):
                    overall = int(((_i + percent / 100) / total) * 100)
                    progress_callback(overall, message)
                try:
                    if mode == 'local':
                        dets = service.detect(task['image_path'], prompts, threshold, report)
                    else:
                        dets = service.detect(task['image_path'], text_prompt, threshold, report)
                    results[task['image_id']] = dets
                except Exception as exc:
                    logger.warning(
                        "Grounding DINO failed on image %s: %s", task['image_id'], exc
                    )
                    results[task['image_id']] = []
            return {'results': results, 'mode': mode, 'device': device_label}

        def on_done(result: dict):
            self._applyGroundingDinoResult(result)

        def on_error(message: str):
            QMessageBox.critical(
                self, "Grounding DINO Failed", f"Inference failed:\n{message}"
            )

        self._grounding_dino_job = self._runBackgroundJob(
            'grounding_dino', worker, on_done, on_error,
            title="Running Grounding DINO",
        )

    def _applyGroundingDinoResult(self, result: dict):
        """Add detected rectangles; undoable current, direct write for others."""
        results = result.get('results') or {}
        added = 0
        others_changed = False
        for image_id, detections in results.items():
            if not detections:
                continue
            image = get_image(image_id)
            if not image:
                continue

            shapes = []
            for det in detections:
                box = det.get('box') or []
                if len(box) < 4:
                    continue
                x1, y1, x2, y2 = box[:4]
                shapes.append({
                    'label': det.get('label') or 'object',
                    'points': [[x1, y1], [x2, y2]],
                    'group_id': None,
                    'description': '',
                    'shape_type': 'rectangle',
                    'flags': {},
                    'mask': None,
                })
            if not shapes:
                continue

            if image_id == self.current_image_id:
                self.canvas.appendShapes(shapes)
            else:
                annotation = get_annotation(image_id)
                existing = annotation['data'].get('shapes', []) if annotation else []
                self._saveShapesForImage(image, list(existing) + shapes)
                others_changed = True
            added += len(shapes)

        if others_changed:
            self._syncGridAnnotations()

        mode = result.get('mode')
        if added:
            self.status_bar.showMessage(
                f"Grounding DINO added {added} shape(s) ({mode})", 6000
            )
        else:
            self.status_bar.showMessage("Grounding DINO found no objects", 5000)

    def _runBackgroundJob(self, job_type: str, worker, on_done, on_error,
                          *, title: str) -> str:
        """Run ``worker`` off the UI thread and report its outcome.

        The job queue injects a ``progress_callback`` keyword argument, so
        workers must accept one. Signals are queued to the main thread, so
        connecting after ``enqueue`` cannot miss the result.
        """
        holder: dict = {}

        def run(progress_callback=None):
            try:
                holder['result'] = worker(progress_callback=progress_callback)
                return {'ok': True}
            except Exception as exc:  # reported through the job's error signal
                holder['error'] = str(exc)
                raise

        if job_type == 'mobile_sam' and self._auto_annotate_dialog is not None:
            self._auto_annotate_dialog.setMobileSamRunning(True)
        if job_type == 'yolo' and self._auto_annotate_dialog is not None:
            self._auto_annotate_dialog.setYoloRunning(True)
        if job_type == 'grounding_dino' and self._auto_annotate_dialog is not None:
            self._auto_annotate_dialog.setGroundingDinoRunning(True)

        job_id = self.job_queue.enqueue(job_type, run)
        holder['job_id'] = job_id

        def finished(finished_id: str, _result: dict):
            if finished_id != job_id:
                return
            self._detachJobHandlers(finished, failed)
            on_done(holder.get('result'))
            # Drop the entry only after the callback ran: the holder is what
            # keeps these closures alive for the signal connection.
            self._managed_jobs.pop(job_id, None)
            self._finishManagedJob(job_type)

        def failed(failed_id: str, message: str):
            if failed_id != job_id:
                return
            self._detachJobHandlers(finished, failed)
            on_error(holder.get('error') or message)
            self._managed_jobs.pop(job_id, None)
            self._finishManagedJob(job_type)

        holder['handlers'] = (finished, failed)
        self._managed_jobs[job_id] = holder
        self.job_queue.jobFinished.connect(finished)
        self.job_queue.jobFailed.connect(failed)
        return job_id

    def _detachJobHandlers(self, finished, failed):
        """Disconnect a job's one-shot result handlers."""
        try:
            self.job_queue.jobFinished.disconnect(finished)
        except (RuntimeError, TypeError):
            pass
        try:
            self.job_queue.jobFailed.disconnect(failed)
        except (RuntimeError, TypeError):
            pass

    def _finishManagedJob(self, job_type: str):
        """Clear per-job UI state once a self-managed job settles."""
        if job_type == 'mobile_sam':
            self._mobile_sam_job = None
            if self._auto_annotate_dialog is not None:
                self._auto_annotate_dialog.setMobileSamRunning(False)
        elif job_type == 'yolo':
            self._yolo_job = None
            if self._auto_annotate_dialog is not None:
                self._auto_annotate_dialog.setYoloRunning(False)
        elif job_type == 'grounding_dino':
            self._grounding_dino_job = None
            if self._auto_annotate_dialog is not None:
                self._auto_annotate_dialog.setGroundingDinoRunning(False)
    
    def onJobStarted(self, job_id: str):
        if job_id in self._managed_jobs:
            # Managed jobs drive their own dialog instead of the modal
            # progress window.
            if self._auto_annotate_dialog is not None:
                self._auto_annotate_dialog.setProgress(0, "Starting...")
            return
        self.showProgressDialog(f"Job {job_id}", "Starting...")
    
    def onJobProgress(self, job_id: str, progress: int, message: str):
        if job_id in self._managed_jobs:
            if self._auto_annotate_dialog is not None:
                self._auto_annotate_dialog.setProgress(progress, message)
            return
        if self.progress_dialog:
            self.progress_dialog.setProgress(progress, message)
    
    def onJobFinished(self, job_id: str, result: dict):
        if job_id in self._managed_jobs:
            # Self-managed jobs report through their own callbacks, which also
            # own the cleanup of this entry.
            return
        self.hideProgressDialog()
        self.handleAutoAnnotateResult(job_id, result)
        QMessageBox.information(self, "Complete", f"Job {job_id} completed.")
    
    def onJobFailed(self, job_id: str, error: str):
        if job_id in self._managed_jobs:
            return
        self.hideProgressDialog()
        QMessageBox.critical(self, "Job Failed", f"Job {job_id} failed:\n{error}")
    
    def showProgressDialog(self, title: str, message: str):
        self.progress_dialog = ProgressDialog(title, message, self)
        self.progress_dialog.show()
    
    def hideProgressDialog(self):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def handleAutoAnnotateResult(self, job_id: str, result: dict):
        if 'annotations' in result and self.current_image_id:
            self.canvas.loadShapes(result['annotations'])
            self.syncLabelsFromShapes()
            self._markDirty()
    
    # Export
    def exportDataset(self):
        if not self.current_project_id:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        
        dialog = ExportDialog(self, self.current_project_id)
        dialog.exec()
    
    # Settings
    def showSettings(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            self.applySettings()
    
    def applySettings(self):
        settings = QSettings()
        dark_mode = settings.value("theme", "light") == "dark"
        self.setStyleSheet(get_application_stylesheet(dark_mode))
    
    # View toggles
    def toggleSidebar(self, visible: bool):
        for dock in self.findChildren(QDockWidget):
            if dock.widget() == self.sidebar:
                dock.setVisible(visible)
                break
    
    def toggleLabelsPanel(self, visible: bool):
        for dock in self.findChildren(QDockWidget):
            if dock.widget() == self.label_list:
                dock.setVisible(visible)
                break
    
    # About
    def showAbout(self):
        QMessageBox.about(self, f"About {APP_NAME}",
            f"<h3>{APP_NAME} v{APP_VERSION}</h3>"
            "<p>Hybrid Image Annotation Application</p>"
            "<p>Powered by LabelMe, Grounding DINO, MobileSAM, and DINOv2</p>"
            "<p>Licensed under GPL-3.0</p>"
        )
    
    # Settings persistence
    def loadRecentProjectsMenu(self):
        """Populate recent projects menu."""
        self.recent_menu.clear()
        recent = get_recent_projects()
        for pid in recent[:10]:
            project = get_project(pid)
            if project:
                action = QAction(f"{project['name']} ({project['base_path']})", self)
                action.setData(pid)
                action.triggered.connect(lambda checked, p=pid: self.loadProject(p))
                self.recent_menu.addAction(action)
        
        if not recent:
            action = QAction("No recent projects", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
    
    # Settings persistence
    def restoreSettings(self):
        settings = QSettings()
        
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        state = settings.value("windowState")
        if state:
            self.restoreState(state)
        
        dark_mode = settings.value("theme", "light") == "dark"
        self.setStyleSheet(get_application_stylesheet(dark_mode))
    
    def saveSettings(self):
        settings = QSettings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        
        if self.main_splitter:
            settings.setValue("sidebar_width", self.main_splitter.sizes()[0])
    
    def closeEvent(self, event):
        self._flushAutosave()
        if self.current_project_id and self.annotations_dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "There are unsaved annotations. Save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if reply == QMessageBox.Save:
                self.saveAnnotation()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        
        self._stopPrewarm()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.saveSettings()
        super().closeEvent(event)
    
    def _stopPrewarm(self):
        """Wait for the warm-up thread so it is never destroyed mid-run."""
        thread = self._prewarm_thread
        if thread is None:
            return
        thread.quit()
        thread.wait(5000)
        self._prewarm_thread = None
        self._prewarm_worker = None