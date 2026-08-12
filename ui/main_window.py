"""
ui/main_window.py - Main Application Window for FinAnalyzer Enterprise v2.2.0
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QStackedWidget, QLabel, QLineEdit, QStatusBar, QFrame, QListWidget, QListWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt, QSize
from pathlib import Path

from PySide6.QtGui import QIcon, QKeySequence, QShortcut

from ui.pages.dashboard import DashboardPage
from ui.pages.transactions import TransactionsPage
from ui.pages.accounts import AccountsPage
from ui.pages.banking import BankingPage
from ui.pages.reports import ReportsPage
from ui.pages.forecasting import ForecastingPage
from ui.pages.period_close import PeriodClosePage
from ui.pages.settings import SettingsPage
from ui.theme import ThemeManager
from core.database import DatabaseManager
from core.identity import IdentityConfigurationError, IdentityProvisioningDenied, IdentityService, IdentityValidationError

class MainWindow(QMainWindow):
    def __init__(self, app_instance=None):
        super().__init__()
        self.app_instance = app_instance
        self.identity_service = None
        self.principal = None
        self.setWindowTitle("FinAnalyzer Enterprise v2.5.0")
        self.resize(1400, 900)

        self.init_ui()
        self.setup_shortcuts()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet("""
            QFrame#Sidebar {
                background-color: palette(alternate-base);
                border-right: 1px solid palette(mid);
            }
        """)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(10)

        # App Logo / Title
        logo_label = QLabel("📊 FinAnalyzer")
        logo_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; color: palette(highlight);")
        sidebar_layout.addWidget(logo_label)

        # Navigation List
        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 12px 15px;
                border-radius: 6px;
                margin-bottom: 4px;
                font-weight: bold;
            }
            QListWidget::item:selected {
                background-color: palette(highlight);
                color: white;
            }
        """)

        nav_items = [
            "📈 Executive Dashboard",
            "💳 Transactions",
            "📚 Chart of Accounts",
            "🏦 Bank Connections",
            "📑 Financial Reports",
            "🤖 AI Forecasting",
            "🔒 Period Close Controls",
            "⚙️ Settings"
        ]
        for item_text in nav_items:
            item = QListWidgetItem(item_text)
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self.switch_page)
        sidebar_layout.addWidget(self.nav_list)

        sidebar_layout.addStretch()

        # User Info Footer in Sidebar
        user_label = QLabel("Enterprise security controls active\nSign-in required for protected operations")
        user_label.setStyleSheet("font-size: 9pt; color: palette(text); opacity: 0.7; padding: 10px;")
        sidebar_layout.addWidget(user_label)

        main_layout.addWidget(self.sidebar)

        # Right Content Area (Toolbar + Stacked Pages)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Top Toolbar / Command Bar
        toolbar = QFrame()
        toolbar.setStyleSheet("background-color: palette(alternate-base); border-bottom: 1px solid palette(mid);")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 10, 20, 10)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Command Palette (Ctrl+K) - Search accounts, transactions, reports...")
        self.search_bar.setFixedWidth(500)
        toolbar_layout.addWidget(self.search_bar)

        toolbar_layout.addStretch()

        self.identity_label = QLabel("Enterprise session: not signed in")
        self.identity_label.setStyleSheet("color: palette(mid); padding: 0 10px;")
        toolbar_layout.addWidget(self.identity_label)

        self.sign_in_button = QPushButton("Sign in with SSO")
        self.sign_in_button.clicked.connect(self.sign_in_enterprise)
        toolbar_layout.addWidget(self.sign_in_button)

        self.sign_out_button = QPushButton("Sign out")
        self.sign_out_button.setObjectName("secondaryButton")
        self.sign_out_button.setEnabled(False)
        self.sign_out_button.clicked.connect(self.sign_out_enterprise)
        toolbar_layout.addWidget(self.sign_out_button)

        right_layout.addWidget(toolbar)

        # Central Stacked Widget
        self.stack = QStackedWidget()
        self.dashboard_page = DashboardPage()
        self.transactions_page = TransactionsPage()
        self.accounts_page = AccountsPage()
        self.banking_page = BankingPage(principal=self.principal)
        self.reports_page = ReportsPage(principal=self.principal)
        self.forecasting_page = ForecastingPage()
        self.period_close_page = PeriodClosePage(principal=self.principal)
        self.settings_page = SettingsPage(theme_toggle_callback=self.change_theme)

        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.transactions_page)
        self.stack.addWidget(self.accounts_page)
        self.stack.addWidget(self.banking_page)
        self.stack.addWidget(self.reports_page)
        self.stack.addWidget(self.forecasting_page)
        self.stack.addWidget(self.period_close_page)
        self.stack.addWidget(self.settings_page)

        right_layout.addWidget(self.stack)
        main_layout.addWidget(right_container)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready | Connected to SQLite Enterprise Database | Encrypted Storage Active")

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)

    def setup_shortcuts(self):
        self.shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut.activated.connect(self.focus_search)

    def focus_search(self):
        self.search_bar.setFocus()
        self.search_bar.selectAll()

    def sign_in_enterprise(self):
        """Run the configured MSAL public-client flow and update protected pages."""
        try:
            root = Path(__file__).resolve().parents[2]
            database = DatabaseManager(str(root / "finanalyzer.db"))
            database.init_database()
            self.identity_service = IdentityService(database)
            self.principal = self.identity_service.sign_in_interactive()
            self.banking_page.set_principal(self.principal)
            self.reports_page.set_principal(self.principal)
            self.period_close_page.set_principal(self.principal)
            self.identity_label.setText(f"Enterprise session: user #{self.principal.user_id} | {self.principal.provider_code}")
            self.sign_in_button.setEnabled(False)
            self.sign_out_button.setEnabled(True)
            self.status_bar.showMessage("Enterprise SSO sign-in completed. Sensitive actions require current MFA evidence.")
        except IdentityProvisioningDenied as exc:
            QMessageBox.warning(self, "Enterprise account not provisioned", str(exc))
        except (IdentityConfigurationError, IdentityValidationError) as exc:
            QMessageBox.warning(self, "Enterprise SSO unavailable", str(exc))
        except Exception:
            QMessageBox.critical(self, "Sign-in failed", "Enterprise sign-in could not be completed safely. Review the local configuration and audit log.")

    def sign_out_enterprise(self):
        if self.identity_service and self.principal:
            try:
                self.identity_service.sign_out(self.principal)
            except Exception:
                QMessageBox.warning(self, "Sign-out incomplete", "The local session could not be fully revoked. Close the application and review the audit log.")
                return
        self.principal = None
        self.banking_page.set_principal(None)
        self.reports_page.set_principal(None)
        self.period_close_page.set_principal(None)
        self.identity_label.setText("Enterprise session: not signed in")
        self.sign_in_button.setEnabled(True)
        self.sign_out_button.setEnabled(False)
        self.status_bar.showMessage("Enterprise session ended.")

    def change_theme(self, theme_name):
        if self.app_instance:
            qss = ThemeManager.get_qss(theme_name)
            self.app_instance.setStyleSheet(qss)
            QMessageBox.information(self, "Theme Updated", f"Switched to {theme_name} theme successfully.")
