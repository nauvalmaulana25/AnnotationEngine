"""
AnnotationEngine Desktop - Main Window (Simplified Working Version)
"""
import os
from pathlib import Path
from typing import Optional, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QDockWidget, QToolBar,
    QStatusBar, QMenuBar, QMenu, QFileDialog, QMessageBox,
    QVBoxLayout, QLabel, QProgressBar, QDialog, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QSettings, QSize, Signal, Slot, QThread
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
    label_in_use
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
from annotation_engine.services.job_queue import JobQueue

# Project root for resources
PROJECT_ROOT = Path(__file__).parent.parent.parent


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
        self.toolbar.saveRequested.connect(self.saveAnnotation)
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
        
        for tool_name, shortcut in [
            ("select", "V"), ("bbox", "B"), ("polygon", "P"),
            ("keypoint", "K")
        ]:
            action = QAction(tool_name.capitalize(), self)
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
        
        # Clear canvas
        self.canvas.clear()
        self.canvas.setTool(TOOL_NAMES[self.current_tool])
        self.current_image_id = None
        self.status_bar.setShapeCount(0)
        
        # Update UI
        self.toolbar.setProjectLoaded(True)
        self.status_bar.setProject(project)
        
        self.projectLoaded.emit(project_id)
    
    def closeProject(self):
        """Close current project."""
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
        
        # Save current annotations if dirty
        if self.annotations_dirty and self.current_image_id:
            self.saveAnnotation()
        
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
        self.annotations_dirty = True
        self.toolbar.setSaveEnabled(True)
        self.syncLabelsFromShapes()
    
    def onShapeModified(self, shape_data: dict):
        self.annotations_dirty = True
        self.toolbar.setSaveEnabled(True)
        self.syncLabelsFromShapes()
    
    def onShapeDeleted(self, shape_index: int):
        self.annotations_dirty = True
        self.toolbar.setSaveEnabled(True)
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

    def onLabelColorChanged(self, label: str, color: str):
        self.canvas.setLabelColors(self.label_list.getLabelColors())

    def onCanvasMouseMoved(self, pos):
        self.status_bar.setCoordinates(pos.x(), pos.y())

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
    
    def saveAnnotation(self):
        if not self.current_image_id or not self.current_project_id:
            return
        
        shapes = self.canvas.getShapesData()
        image = get_image(self.current_image_id)
        
        annotation_data = {
            "version": "5.4.1",
            "flags": {},
            "shapes": shapes,
            "imagePath": image['filename'],
            "imageData": None,
            "imageHeight": image['height'] or 0,
            "imageWidth": image['width'] or 0
        }
        
        save_annotation(self.current_image_id, annotation_data)
        update_image(self.current_image_id, has_annotation=1)
        self.annotations_dirty = False
        self.toolbar.setSaveEnabled(False)
        self.syncLabelsFromShapes()
        self.status_bar.showMessage("Annotation saved", 2000)
    
    def _afterShapeHistoryChange(self):
        """Refresh UI state after an undo/redo or bulk label deletion."""
        if not self.current_image_id:
            return
        self.annotations_dirty = True
        self.toolbar.setSaveEnabled(True)
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
        
        dialog = AutoAnnotateDialog(self, self.current_project_id, selected_images)
        dialog.exec()
    
    def onJobStarted(self, job_id: str):
        self.showProgressDialog(f"Job {job_id}", "Starting...")
    
    def onJobProgress(self, job_id: str, progress: int, message: str):
        if self.progress_dialog:
            self.progress_dialog.setProgress(progress, message)
    
    def onJobFinished(self, job_id: str, result: dict):
        self.hideProgressDialog()
        self.handleAutoAnnotateResult(job_id, result)
        QMessageBox.information(self, "Complete", f"Job {job_id} completed.")
    
    def onJobFailed(self, job_id: str, error: str):
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
            self.annotations_dirty = True
            self.toolbar.setSaveEnabled(True)
    
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
        
        self.saveSettings()
        super().closeEvent(event)