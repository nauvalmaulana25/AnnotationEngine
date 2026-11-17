"""
AnnotationEngine Desktop - Main Entry Point
"""
import sys
import os
import logging
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import compiled resources
import annotation_engine.resources.icons_rc

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QIcon

from annotation_engine.config import APP_NAME, APP_VERSION, LOGS_DIR
from annotation_engine.ui.styles import get_application_stylesheet
from annotation_engine.ui.main_window import MainWindow
from annotation_engine.ui.welcome_window import WelcomeWindow
from annotation_engine.core.database import get_database
from annotation_engine.utils.encryption import EncryptionManager


def setup_logging():
    """Configure application logging."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"{APP_NAME.lower()}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('transformers').setLevel(logging.WARNING)
    logging.getLogger('onnxruntime').setLevel(logging.WARNING)
    logging.getLogger('torch').setLevel(logging.WARNING)


def setup_application() -> QApplication:
    """Create and configure QApplication."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    app.setOrganizationDomain("annotationengine.local")
    
    # Apply stylesheet
    settings = QSettings()
    dark_mode = settings.value("theme", "light") == "dark"
    app.setStyleSheet(get_application_stylesheet(dark_mode))
    
    # Set application icon
    icon_path = PROJECT_ROOT / "annotation_engine" / "resources" / "icons" / "app.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    return app


def main() -> int:
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    
    try:
        app = setup_application()
        
        # Initialize database
        db = get_database()
        logger.info("Database initialized")
        
        # Initialize encryption
        encryption = EncryptionManager()
        logger.info("Encryption manager initialized")
        
        # Create and show main window (handles welcome dialog internally)
        window = MainWindow()
        if not window.current_project_id:
            logger.info("No project selected on startup, exiting cleanly")
            return 0
        window.show()
        
        logger.info("Application started successfully")
        
        # Run event loop
        return app.exec()
        
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())