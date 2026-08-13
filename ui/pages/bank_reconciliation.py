"""Desktop workspace for controlled review of bank-feed accounting postings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from core.authorization import AuthorizationDenied
from core.bank_reconciliation import BankReconciliationError, BankReconciliationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal
from core.models import Account, Company


class BankReconciliationPage(QWidget):
    """Displays only review-safe fields and delegates every mutation to the service layer."""

    def __init__(self, principal: AuthenticatedPrincipal | None = None) -> None:
        super().__init__()
        root = Path(__file__).resolve().parents[2]
        self.database = DatabaseManager(str(root / "finanalyzer.db"))
        self.database.init_database()
        self.company_id = self._ensure_company()
        self.service = BankReconciliationService(self.database)
        self.principal = principal
        self._rows: list[object] = []
        self._build_ui()
        self.set_principal(principal)

    def _ensure_company(self) -> int:
        with self.database.get_session() as session:
            company = session.scalar(select(Company).order_by(Company.id))
            if company is None:
                company = Company(name="Default Company", legal_name="Default Company", currency_code="USD")
                session.add(company)
                session.flush()
            return company.id

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Bank Reconciliation Workspace")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.refresh_button = QPushButton("Refresh review queue")
        self.refresh_button.clicked.connect(self.refresh_workspace)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        self.summary_label = QLabel("Enterprise SSO is required to view reconciliation work.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("padding: 10px; background: palette(alternate-base); border-radius: 6px;")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Provider transaction", "Date", "Description", "Amount", "Status", "Note"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._sync_selected_item)
        self.table.setMinimumHeight(260)
        layout.addWidget(self.table)

        action_box = QWidget()
        action_form = QFormLayout(action_box)
        self.selection_label = QLabel("Select one open bank-feed item.")
        self.account_selector = QComboBox()
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Explanation for classification or exception; never enter credentials or bank secrets.")
        buttons = QHBoxLayout()
        self.match_button = QPushButton("Match to selected account")
        self.match_button.clicked.connect(self.match_selected)
        self.exception_button = QPushButton("Flag exception")
        self.exception_button.setObjectName("secondaryButton")
        self.exception_button.clicked.connect(self.flag_exception)
        self.resolve_button = QPushButton("Resolve exception")
        self.resolve_button.setObjectName("secondaryButton")
        self.resolve_button.clicked.connect(self.resolve_exception)
        buttons.addWidget(self.match_button)
        buttons.addWidget(self.exception_button)
        buttons.addWidget(self.resolve_button)
        buttons.addStretch()
        action_form.addRow("Selected item", self.selection_label)
        action_form.addRow("Contra account", self.account_selector)
        action_form.addRow("Review note", self.note_input)
        action_form.addRow("", buttons)
        layout.addWidget(action_box)

        self.status_label = QLabel(
            "New and provider-revised bank postings require review. A matched posting is retained as a balanced journal entry; raw provider payloads are never shown in this workspace."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: palette(mid); padding: 8px 0;")
        layout.addWidget(self.status_label)

    def set_principal(self, principal: AuthenticatedPrincipal | None) -> None:
        self.principal = principal
        enabled = principal is not None
        self.refresh_button.setEnabled(enabled)
        self.table.setEnabled(enabled)
        self.account_selector.setEnabled(enabled)
        self.note_input.setEnabled(enabled)
        self.match_button.setEnabled(enabled)
        self.exception_button.setEnabled(enabled)
        self.resolve_button.setEnabled(enabled)
        if enabled:
            self.refresh_workspace()
        else:
            self.table.setRowCount(0)
            self.summary_label.setText("Enterprise sign-in is required to view or resolve bank reconciliation work.")

    def refresh_workspace(self) -> None:
        try:
            principal = self._require_principal()
            self._load_accounts()
            self._rows = self.service.list_work_items(self.company_id, principal)
            summary = self.service.summary(self.company_id, principal)
            self.summary_label.setText(
                f"Open review queue: {summary.needs_review} | Exceptions: {summary.exceptions} | "
                f"Matched: {summary.matched} | Provider-pending: {summary.pending}"
            )
            self.table.setRowCount(len(self._rows))
            for row_index, item in enumerate(self._rows):
                values = [
                    item.provider_transaction_id,
                    item.entry_date or "—",
                    item.description,
                    item.amount,
                    item.status,
                    item.note or "—",
                ]
                for column, value in enumerate(values):
                    self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
            self.table.resizeColumnsToContents()
            self._sync_selected_item()
        except (AuthorizationDenied, BankReconciliationError) as exc:
            self.summary_label.setText(f"Workspace unavailable: {exc}")
        except Exception:
            self.summary_label.setText("Workspace could not be refreshed. No reconciliation change was made.")

    def _load_accounts(self) -> None:
        current_id = self.account_selector.currentData()
        self.account_selector.clear()
        with self.database.get_session() as session:
            accounts = list(session.scalars(
                select(Account).where(Account.company_id == self.company_id, Account.is_active.is_(True)).order_by(Account.code)
            ))
        for account in accounts:
            self.account_selector.addItem(f"{account.code} — {account.name}", account.id)
        if current_id is not None:
            index = self.account_selector.findData(current_id)
            if index >= 0:
                self.account_selector.setCurrentIndex(index)

    def _sync_selected_item(self) -> None:
        index = self.table.currentRow()
        if index < 0 or index >= len(self._rows):
            self.selection_label.setText("Select one open bank-feed item.")
            return
        item = self._rows[index]
        self.selection_label.setText(f"{item.provider_transaction_id} · {item.status} · journal entry #{item.journal_entry_id or '—'}")

    def _selected_provider_transaction_id(self) -> str:
        index = self.table.currentRow()
        if index < 0 or index >= len(self._rows):
            raise BankReconciliationError("Select one bank-feed work item first.")
        return self._rows[index].provider_transaction_id

    def match_selected(self) -> None:
        self._perform_action("match")

    def flag_exception(self) -> None:
        self._perform_action("exception")

    def resolve_exception(self) -> None:
        self._perform_action("resolve")

    def _perform_action(self, action: str) -> None:
        try:
            principal = self._require_principal()
            transaction_id = self._selected_provider_transaction_id()
            note = self.note_input.text().strip()
            if action == "match":
                self.service.match_transaction(self.company_id, transaction_id, int(self.account_selector.currentData()), principal, note)
                message = "The bank-feed item was matched and the balanced journal entry was retained."
            elif action == "exception":
                self.service.mark_exception(self.company_id, transaction_id, note, principal)
                message = "The item was flagged as an exception without changing the journal entry."
            else:
                self.service.resolve_exception(self.company_id, transaction_id, int(self.account_selector.currentData()), principal, note)
                message = "The exception was independently resolved and the entry was matched."
            self.note_input.clear()
            self.status_label.setText(message)
            self.refresh_workspace()
        except (AuthorizationDenied, BankReconciliationError, TypeError) as exc:
            QMessageBox.warning(self, "Reconciliation blocked", str(exc))
        except Exception:
            QMessageBox.critical(self, "Reconciliation not completed", "No partial reconciliation change was retained. Review the audit trail and retry.")

    def _require_principal(self) -> AuthenticatedPrincipal:
        if not isinstance(self.principal, AuthenticatedPrincipal):
            raise AuthorizationDenied("A validated Enterprise session is required for reconciliation.")
        return self.principal


__all__ = ["BankReconciliationPage"]
