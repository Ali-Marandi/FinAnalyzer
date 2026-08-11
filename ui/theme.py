"""
ui/theme.py - Theme engine for FinAnalyzer Enterprise v2.0.0
Supports Light and Dark professional financial themes with QSS stylesheets.
"""

from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt

class ThemeManager:
    DARK_PALETTE = {
        "bg_primary": "#1a1a2e",
        "bg_secondary": "#16213e",
        "bg_tertiary": "#0f3460",
        "accent": "#e94560",
        "accent_hover": "#ff6b81",
        "text_primary": "#ffffff",
        "text_secondary": "#a0aab2",
        "border": "#2a3a5e",
        "success": "#2ecc71",
        "warning": "#f39c12",
        "danger": "#e74c3c",
        "card_bg": "#16213e",
        "table_alt": "#1f2b48",
        "input_bg": "#0f3460"
    }

    LIGHT_PALETTE = {
        "bg_primary": "#f8f9fa",
        "bg_secondary": "#ffffff",
        "bg_tertiary": "#e9ecef",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "text_primary": "#1e293b",
        "text_secondary": "#64748b",
        "border": "#cbd5e1",
        "success": "#16a34a",
        "warning": "#d97706",
        "danger": "#dc2626",
        "card_bg": "#ffffff",
        "table_alt": "#f1f5f9",
        "input_bg": "#ffffff"
    }

    @staticmethod
    def get_system_font():
        return QFont("Segoe UI", 10)

    @classmethod
    def get_qss(cls, theme_name="dark"):
        p = cls.DARK_PALETTE if theme_name == "dark" else cls.LIGHT_PALETTE
        return f"""
        QMainWindow, QDialog {{
            background-color: {p["bg_primary"]};
            color: {p["text_primary"]};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10pt;
        }}
        QWidget {{
            background-color: transparent;
            color: {p["text_primary"]};
        }}
        QLabel {{
            color: {p["text_primary"]};
            background: transparent;
        }}
        QPushButton {{
            background-color: {p["accent"]};
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {p["accent_hover"]};
        }}
        QPushButton:pressed {{
            background-color: {p["accent"]};
        }}
        QPushButton#secondaryButton {{
            background-color: {p["bg_tertiary"]};
            color: {p["text_primary"]};
            border: 1px solid {p["border"]};
        }}
        QPushButton#secondaryButton:hover {{
            background-color: {p["border"]};
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
            background-color: {p["input_bg"]};
            color: {p["text_primary"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: {p["accent"]};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left-width: 0px;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }}
        QTableWidget, QTableView {{
            background-color: {p["card_bg"]};
            alternate-background-color: {p["table_alt"]};
            color: {p["text_primary"]};
            gridline-color: {p["border"]};
            border: 1px solid {p["border"]};
            border-radius: 8px;
            selection-background-color: {p["accent"]};
            selection-color: #ffffff;
        }}
        QHeaderView::section {{
            background-color: {p["bg_secondary"]};
            color: {p["text_primary"]};
            padding: 8px;
            border: none;
            border-bottom: 2px solid {p["accent"]};
            font-weight: bold;
        }}
        QTabWidget::pane {{
            border: 1px solid {p["border"]};
            background-color: {p["card_bg"]};
            border-radius: 8px;
        }}
        QTabBar::tab {{
            background-color: {p["bg_secondary"]};
            color: {p["text_secondary"]};
            padding: 10px 20px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {p["accent"]};
            color: #ffffff;
            font-weight: bold;
        }}
        QScrollBar:vertical {{
            border: none;
            background: {p["bg_primary"]};
            width: 10px;
            margin: 0px 0px 0px 0px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {p["border"]};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p["accent"]};
        }}
        QProgressBar {{
            border: 1px solid {p["border"]};
            border-radius: 5px;
            background: {p["input_bg"]};
            text-align: center;
            color: {p["text_primary"]};
        }}
        QProgressBar::chunk {{
            background-color: {p["accent"]};
            border-radius: 4px;
        }}
        QMenuBar {{
            background-color: {p["bg_secondary"]};
            color: {p["text_primary"]};
            border-bottom: 1px solid {p["border"]};
        }}
        QMenuBar::item:selected {{
            background-color: {p["accent"]};
            color: #ffffff;
        }}
        QMenu {{
            background-color: {p["bg_secondary"]};
            color: {p["text_primary"]};
            border: 1px solid {p["border"]};
        }}
        QMenu::item:selected {{
            background-color: {p["accent"]};
            color: #ffffff;
        }}
        QStatusBar {{
            background-color: {p["bg_secondary"]};
            color: {p["text_secondary"]};
            border-top: 1px solid {p["border"]};
        }}
        """
