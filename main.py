"""
main.py - Entry Point for FinAnalyzer Enterprise v2.3.0
"""

import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QColor, QPainter, QFont

from core.database import DatabaseManager
from ui.theme import ThemeManager
from ui.main_window import MainWindow

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("finanalyzer.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("FinAnalyzerApp")

def main():
    logger.info("Initializing FinAnalyzer Enterprise v2.3.0...")

    # Initialize Database
    try:
        db_manager = DatabaseManager(db_path=os.path.join(os.path.dirname(__file__), "finanalyzer.db"))
        db_manager.init_database()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # Initialize QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("FinAnalyzer Enterprise")
    app.setOrganizationName("FinAnalyzer Corp")

    # Apply Default Dark Theme
    qss = ThemeManager.get_qss("dark")
    app.setStyleSheet(qss)

    # Create Splash Screen
    splash_pix = QPixmap(500, 300)
    splash_pix.fill(QColor("#16213e"))
    painter = QPainter(splash_pix)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
    painter.drawText(splash_pix.rect(), Qt.AlignCenter, "FinAnalyzer Enterprise v2.3.0\n\nLoading Enterprise Identity & Financial Engine...")
    painter.end()

    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    # Create Main Window
    main_window = MainWindow(app_instance=app)

    # Close splash and show main window after brief delay
    def show_main():
        splash.finish(main_window)
        main_window.show()
        logger.info("Main application window displayed successfully.")

    QTimer.singleShot(1500, show_main)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
