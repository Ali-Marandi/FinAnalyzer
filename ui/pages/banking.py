"""Bank connection page for FinAnalyzer Enterprise.

This UI invokes Plaid only after user action. It reports operational status without
revealing credentials, access tokens, account numbers, or raw bank records.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from sqlalchemy import select

from core.authorization import AuthorizationDenied, AuthorizationService
from core.identity import AuthenticatedPrincipal
from core.database import DatabaseManager
from core.models import Company, PlaidItem
from core.plaid_connector import PlaidConfigurationError, PlaidConnector, PlaidSyncError
from core.plaid_link_desktop import PlaidDesktopLinkBridge


class BankingPage(QWidget):
    def __init__(self, parent=None, *, principal: AuthenticatedPrincipal | None = None):
        super().__init__(parent)
        self.principal = principal
        self.authorization = AuthorizationService()
        root = Path(__file__).resolve().parents[2]
        self.database = DatabaseManager(str(root / "finanalyzer.db"))
        self.database.init_database()
        self.company_id = self._ensure_company()
        self.connector = None
        self.bridge = None
        self._init_ui()
        self.set_principal(self.principal)

    def _ensure_company(self) -> int:
        with self.database.get_session() as session:
            company = session.scalar(select(Company).order_by(Company.id))
            if company is None:
                company = Company(name="Default Company", legal_name="Default Company", currency_code="USD")
                session.add(company)
                session.flush()
            return company.id

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QHBoxLayout()
        title = QLabel("Bank Connections")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.clicked.connect(self.refresh_connections)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        note = QLabel(
            "Link a financial institution through Plaid. Access tokens are encrypted locally; generated reports exclude banking credentials. "
            "Start with the Plaid Sandbox environment before production deployment."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); padding: 8px 0;")
        layout.addWidget(note)

        actions = QHBoxLayout()
        self.connect_button = QPushButton("Connect bank with Plaid")
        self.connect_button.clicked.connect(self.connect_bank)
        actions.addWidget(self.connect_button)
        self.sync_button = QPushButton("Synchronize transactions")
        self.sync_button.setObjectName("secondaryButton")
        self.sync_button.clicked.connect(self.synchronize)
        actions.addWidget(self.sync_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.connection_summary = QLabel()
        self.connection_summary.setWordWrap(True)
        self.connection_summary.setStyleSheet("font-family: 'Courier New'; padding: 14px; border: 1px solid palette(mid);")
        layout.addWidget(self.connection_summary)
        layout.addStretch()

    def _connector(self) -> PlaidConnector:
        if self.connector is None:
            self.connector = PlaidConnector(self.database)
        return self.connector

    def connect_bank(self) -> None:
        try:
            principal = self._require_principal()
            self.bridge = PlaidDesktopLinkBridge(self._connector(), self.company_id, principal)
            self.bridge.open()
            self.connection_summary.setText(
                "Plaid Link opened in the default browser. Complete the institution consent flow, then click Refresh or Synchronize."
            )
        except PlaidConfigurationError as exc:
            QMessageBox.warning(self, "Plaid configuration required", str(exc))
        except Exception:
            QMessageBox.critical(self, "Unable to open Plaid Link", "The banking consent window could not be opened. Check the local configuration and retry.")

    def synchronize(self) -> None:
        try:
            outcomes = self._connector().sync_company(self.company_id, self._require_principal())
            if not outcomes:
                QMessageBox.information(self, "No connections", "No bank connection is currently linked for this company.")
                return
            added = sum(int(item["added"]) for item in outcomes)
            modified = sum(int(item["modified"]) for item in outcomes)
            removed = sum(int(item["removed"]) for item in outcomes)
            self.connection_summary.setText(f"Synchronization completed. Added: {added} | Updated: {modified} | Removed: {removed}")
            self.refresh_connections()
        except (PlaidConfigurationError, PlaidSyncError) as exc:
            QMessageBox.warning(self, "Sync not completed", str(exc))
        except Exception:
            QMessageBox.critical(self, "Sync not completed", "The transaction sync failed safely. No partial cursor was saved; retry after reviewing the connection.")

    def refresh_connections(self) -> None:
        try:
            principal = self._require_principal()
            with self.database.get_session() as session:
                self.authorization.require(
                    session,
                    principal.authorization_context(
                        self.company_id,
                        "bank_connections_view",
                        mfa_max_age=self._connector().mfa_max_age,
                    ),
                    "company.read",
                )
                records = list(
                session.scalars(
                    select(PlaidItem).where(PlaidItem.company_id == self.company_id).order_by(PlaidItem.institution_name)
                    )
                )
        except AuthorizationDenied:
            self.connection_summary.setText("You do not have permission to view bank connections for this company.")
            return
        if not records:
            self.connection_summary.setText("No linked institutions. Select ‘Connect bank with Plaid’ to begin a consented connection.")
            return
        lines = ["Linked institutions:"]
        for item in records:
            label = item.institution_name or "Institution name unavailable"
            synced = item.last_synced_at.isoformat(sep=" ", timespec="minutes") if item.last_synced_at else "Not yet synchronized"
            lines.append(f"• {label} — status: {item.status}; last sync: {synced}")
        self.connection_summary.setText("\n".join(lines))

    def set_principal(self, principal: AuthenticatedPrincipal | None) -> None:
        """Called by the desktop shell after Enterprise sign-in or sign-out."""
        self.principal = principal
        enabled = principal is not None
        self.connect_button.setEnabled(enabled)
        self.sync_button.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        if enabled:
            self.refresh_connections()
        else:
            self.connection_summary.setText("A signed-in, authorized user is required to view or manage bank connections.")

    def _require_principal(self) -> AuthenticatedPrincipal:
        if self.principal is None:
            raise AuthorizationDenied("A validated Enterprise session is required for this operation.")
        return self.principal
