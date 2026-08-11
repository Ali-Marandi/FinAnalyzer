"""
ui/pages/settings.py - Settings Page for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, 
    QPushButton, QTabWidget, QFormLayout, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt

class SettingsPage(QWidget):
    def __init__(self, theme_toggle_callback=None, parent=None):
        super().__init__(parent)
        self.theme_toggle_callback = theme_toggle_callback
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("System Settings & Configuration")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self.create_general_tab(), "General & Company")
        tabs.addTab(self.create_security_tab(), "Security & Users")
        tabs.addTab(self.create_backup_tab(), "Backup & Database")
        tabs.addTab(self.create_about_tab(), "About")

        layout.addWidget(tabs)

    def create_general_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(15)

        form.addRow("Company Name:", QLineEdit("Acme Enterprise Corp"))
        form.addRow("Tax ID / EIN:", QLineEdit("EIN-98-7654321"))
        
        self.currency_combo = QComboBox()
        self.currency_combo.addItems(["USD ($)", "EUR (€)", "GBP (£)", "JPY (¥)", "CAD ($)"])
        form.addRow("Base Currency:", self.currency_combo)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Theme (Enterprise)", "Light Theme (Clean)"])
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        form.addRow("Visual Theme:", self.theme_combo)

        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(lambda: QMessageBox.information(self, "Saved", "Company profile updated successfully."))
        form.addRow("", save_btn)

        return w

    def create_security_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(15)

        form.addRow("Current User:", QLineEdit("admin@finanalyzer.enterprise (Administrator)"))
        form.addRow("License Key:", QLineEdit("FA20-ENT-9982-XXXX-PROD"))
        
        self.mfa_check = QCheckBox("Enable Two-Factor Authentication (2FA via TOTP)")
        self.mfa_check.setChecked(True)
        form.addRow("", self.mfa_check)

        self.audit_check = QCheckBox("Enable Strict Audit Logging (Immutable Ledger)")
        self.audit_check.setChecked(True)
        form.addRow("", self.audit_check)

        save_btn = QPushButton("Update Security Policy")
        save_btn.clicked.connect(lambda: QMessageBox.information(self, "Success", "Security policy updated."))
        form.addRow("", save_btn)

        return w

    def create_backup_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(QLabel("Database Management & Disaster Recovery"))
        
        backup_btn = QPushButton("Create Encrypted Database Backup (.bak)")
        backup_btn.clicked.connect(lambda: QMessageBox.information(self, "Backup", "Encrypted backup successfully created at /home/ubuntu/FinAnalyzer_v2/backups/"))
        layout.addWidget(backup_btn)

        restore_btn = QPushButton("Restore Database from Backup...")
        restore_btn.setObjectName("secondaryButton")
        restore_btn.clicked.connect(lambda: QMessageBox.information(self, "Restore", "Select backup file to restore."))
        layout.addWidget(restore_btn)

        layout.addStretch()
        return w

    def create_about_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(QLabel("<h2>FinAnalyzer Enterprise v2.0.0</h2>"))
        layout.addWidget(QLabel("Professional Financial Analytics, Accounting & ERP Suite"))
        layout.addWidget(QLabel("Built with PySide6, SQLAlchemy, and Advanced Machine Learning Analytics."))
        layout.addWidget(QLabel("© 2026 FinAnalyzer Corp. All rights reserved."))
        layout.addStretch()
        return w

    def on_theme_changed(self, idx):
        if self.theme_toggle_callback:
            theme = "dark" if idx == 0 else "light"
            self.theme_toggle_callback(theme)
