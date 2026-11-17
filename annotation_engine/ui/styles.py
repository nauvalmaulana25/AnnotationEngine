"""
AnnotationEngine Desktop - QSS Design System (Tailwind-Inspired)
"""
from annotation_engine.config import COLORS

def get_application_stylesheet(dark_mode: bool = False) -> str:
    """Generate complete QSS stylesheet for the application."""
    
    if dark_mode:
        bg_primary = "#111827"
        bg_secondary = "#1f2937"
        bg_tertiary = "#374151"
        bg_canvas = "#030712"
        text_primary = "#f9fafb"
        text_secondary = "#d1d5db"
        text_muted = "#9ca3af"
        border_color = "#374151"
        border_focus = "#60a5fa"
    else:
        bg_primary = "#ffffff"
        bg_secondary = "#f9fafb"
        bg_tertiary = "#f3f4f6"
        bg_canvas = "#1a1a2e"
        text_primary = "#111827"
        text_secondary = "#6b7280"
        text_muted = "#9ca3af"
        border_color = "#e5e7eb"
        border_focus = "#3b82f6"
    
    primary = "#3b82f6"
    primary_hover = "#2563eb"
    primary_pressed = "#1d4ed8"
    success = "#22c55e"
    warning = "#f59e0b"
    error = "#ef4444"
    
    return f"""
/* ========================================
   AnnotationEngine - Design System QSS
   ======================================== */

* {{
    font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 14px;
    color: {text_primary};
    background-color: {bg_primary};
}}

QMainWindow, QDialog {{
    background-color: {bg_primary};
}}

QPushButton {{
    padding: 8px 16px;
    border-radius: 6px;
    border: 1px solid {border_color};
    background-color: {bg_primary};
    color: {text_primary};
    font-weight: 500;
    min-height: 28px;
}}
QPushButton:hover {{ background-color: {bg_tertiary}; }}
QPushButton:pressed {{ background-color: {bg_secondary}; }}
QPushButton:disabled {{ color: {text_muted}; border-color: {border_color}; background-color: {bg_secondary}; }}
QPushButton:focus {{ border-color: {border_focus}; outline: none; }}

QPushButton[primary="true"] {{
    background-color: {primary};
    color: white;
    border-color: {primary};
}}
QPushButton[primary="true"]:hover {{ background-color: {primary_hover}; border-color: {primary_hover}; }}
QPushButton[primary="true"]:pressed {{ background-color: {primary_pressed}; }}

QPushButton[danger="true"] {{
    background-color: {error};
    color: white;
    border-color: {error};
}}
QPushButton[danger="true"]:hover {{ background-color: #dc2626; }}

QPushButton[flat="true"] {{
    border: none;
    background: transparent;
    padding: 8px;
}}
QPushButton[flat="true"]:hover {{ background-color: {bg_tertiary}; border-radius: 4px; }}

QToolBar {{
    background-color: {bg_secondary};
    border-bottom: 1px solid {border_color};
    padding: 8px;
    spacing: 8px;
}}
QToolBar::separator {{ background: {border_color}; width: 1px; margin: 4px 8px; }}

QMenuBar {{
    background-color: {bg_secondary};
    border-bottom: 1px solid {border_color};
    padding: 4px 12px;
}}
QMenuBar::item {{ padding: 8px 16px; border-radius: 4px; color: {text_primary}; }}
QMenuBar::item:selected {{ background-color: {bg_tertiary}; }}

QMenu {{
    background-color: {bg_primary};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 8px;
}}
QMenu::item {{ padding: 8px 16px; border-radius: 4px; color: {text_primary}; }}
QMenu::item:selected {{ background-color: {bg_tertiary}; }}
QMenu::separator {{ height: 1px; background: {border_color}; margin: 8px 16px; }}

QDockWidget {{
    titlebar-close-icon: url(:/icons/close.svg);
    titlebar-normal-icon: url(:/icons/maximize.svg);
    border: 1px solid {border_color};
    border-radius: 12px;
}}
QDockWidget::title {{
    background-color: {bg_secondary};
    padding: 12px 16px;
    border-bottom: 1px solid {border_color};
    font-weight: 600;
    color: {text_primary};
}}
QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent; border: none; padding: 4px; border-radius: 4px;
}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{ background-color: {bg_tertiary}; }}

QListView, QTreeView {{
    background-color: {bg_primary};
    border: none; outline: none;
    show-decoration-selected: 1;
    alternate-background-color: {bg_secondary};
}}
QListView::item, QTreeView::item {{
    padding: 8px; border-radius: 4px; margin: 4px; border: 2px solid transparent;
}}
QListView::item:selected, QTreeView::item:selected {{
    background-color: #dbeafe; border-color: {primary}; color: #1e40af;
}}
QListView::item:hover, QTreeView::item:hover {{ background-color: {bg_tertiary}; }}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    padding: 8px 12px; border: 1px solid {border_color}; border-radius: 6px;
    background-color: {bg_primary}; color: {text_primary};
    selection-background-color: #dbeafe; selection-color: {text_primary};
    min-height: 28px;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {border_focus}; outline: none;
}}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {bg_secondary}; color: {text_muted}; border-color: {border_color};
}}

QComboBox::drop-down {{ border: none; width: 24px; subcontrol-origin: padding; subcontrol-position: top right; }}
QComboBox::down-arrow {{ image: url(:/icons/chevron-down.svg); width: 16px; height: 16px; }}
QComboBox QAbstractItemView {{
    border: 1px solid {border_color}; border-radius: 6px;
    background-color: {bg_primary}; selection-background-color: {primary}; selection-color: white; padding: 4px;
}}

QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    border: none; background: {bg_tertiary}; width: 20px; border-radius: 0;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{ background-color: {bg_secondary}; }}
QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; border-radius: 0 6px 0 0; }}
QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; border-radius: 0 0 6px 0; }}

QProgressBar {{ border: none; border-radius: 3px; background-color: {bg_tertiary}; text-align: center; height: 6px; color: transparent; }}
QProgressBar::chunk {{ background-color: {primary}; border-radius: 3px; }}

QScrollBar:vertical {{ width: 8px; background: transparent; margin: 0; }}
QScrollBar::handle:vertical {{ background: {text_muted}; border-radius: 4px; min-height: 30px; margin: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {text_secondary}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{ height: 8px; background: transparent; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {text_muted}; border-radius: 4px; min-width: 30px; margin: 4px; }}
QScrollBar::handle:horizontal:hover {{ background: {text_secondary}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QDialog {{ border-radius: 12px; background-color: {bg_primary}; }}
QDialog QDialogButtonBox {{ padding: 16px; }}

QToolTip {{ background-color: #111827; color: #f9fafb; border: none; border-radius: 4px; padding: 8px 12px; font-size: 13px; font-family: "JetBrains Mono", "Consolas", monospace; }}

QMenu {{ background-color: {bg_primary}; border: 1px solid {border_color}; border-radius: 6px; padding: 8px; }}
QMenu::item {{ padding: 8px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {bg_tertiary}; }}
QMenu::separator {{ height: 1px; background: {border_color}; margin: 8px 16px; }}

QSplitter::handle {{ background: {border_color}; width: 1px; height: 1px; }}
QSplitter::handle:hover {{ background: {primary}; }}
QSplitter::handle:horizontal {{ width: 4px; }}
QSplitter::handle:vertical {{ height: 4px; }}

QStatusBar {{ background-color: {bg_secondary}; border-top: 1px solid {border_color}; padding: 4px 12px; color: {text_secondary}; font-size: 13px; }}
QStatusBar::item {{ border: none; padding: 4px 8px; }}

QTabWidget::pane {{ border: 1px solid {border_color}; border-radius: 6px; background-color: {bg_primary}; top: -1px; }}
QTabBar::tab {{ padding: 8px 16px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; background-color: {bg_secondary}; color: {text_secondary}; border: 1px solid transparent; border-bottom: none; min-width: 80px; }}
QTabBar::tab:selected {{ background-color: {bg_primary}; color: {text_primary}; border-color: {border_color}; border-bottom-color: {bg_primary}; }}
QTabBar::tab:hover:!selected {{ background-color: {bg_tertiary}; color: {text_primary}; }}

QGroupBox {{ font-weight: 600; border: 1px solid {border_color}; border-radius: 6px; margin-top: 16px; padding-top: 16px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 8px; color: {text_secondary}; font-size: 13px; }}

QCheckBox, QRadioButton {{ spacing: 8px; color: {text_primary}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; border-radius: 3px; border: 2px solid {border_color}; background-color: {bg_primary}; }}
QCheckBox::indicator:checked {{ background-color: {primary}; border-color: {primary}; image: url(:/icons/check.svg); }}
QRadioButton::indicator {{ border-radius: 9px; }}
QRadioButton::indicator:checked {{ background-color: {primary}; border-color: {primary}; }}

QSlider::groove:horizontal {{ border: none; height: 4px; background: {bg_tertiary}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {primary}; border: none; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: {primary_hover}; }}

AnnotationCanvas {{ background-color: {bg_canvas}; border: none; }}

LabelListWidget {{ background-color: {bg_primary}; border: 1px solid {border_color}; border-radius: 6px; }}
LabelListWidget::item {{ padding: 8px 12px; border-radius: 4px; }}
LabelListWidget::item:selected {{ background-color: {primary}; color: white; }}

ZoomWidget {{ background-color: {bg_secondary}; border: 1px solid {border_color}; border-radius: 6px; padding: 4px 8px; }}
ZoomWidget QComboBox {{ min-width: 80px; padding: 4px 8px; }}
"""

def get_dark_stylesheet() -> str:
    """Get dark mode stylesheet."""
    return get_application_stylesheet(dark_mode=True)

def get_light_stylesheet() -> str:
    """Get light mode stylesheet."""
    return get_application_stylesheet(dark_mode=False)