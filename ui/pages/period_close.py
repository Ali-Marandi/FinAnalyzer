"""Enterprise desktop page for controlled financial-period close workflows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from core.authorization import AuthorizationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal
from core.models import PeriodCloseRequest
from core.period_close import PeriodCloseError, PeriodCloseService, SegregationOfDutiesViolation


class PeriodClosePage(QWidget):
    """UI shell for the MFA-protected, two-person fiscal-close workflow."""

    def __init__(self, principal: AuthenticatedPrincipal | None = None) -> None:
        super().__init__()
        root = Path(__file__).resolve().parents[2]
        self.database = DatabaseManager(str(root / "finanalyzer.db"))
        self.database.init_database()
        self.authorization = AuthorizationService()
        self.service = PeriodCloseService(self.database, authorization=self.authorization)
        self.principal = principal
        self._build_ui()
        self._set_session_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Financial Period Close Controls")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel(
            "Dual-control close workflow. The requester and approver must be different authenticated users with recent MFA."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: palette(mid);")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.session_label = QLabel()
        self.session_label.setStyleSheet("padding: 10px; background: palette(alternate-base); border-radius: 6px;")
        layout.addWidget(self.session_label)

        readiness_box = QGroupBox("0. Validate close readiness before requesting approval")
        readiness_layout = QVBoxLayout(readiness_box)
        readiness_actions = QHBoxLayout()
        self.readiness_button = QPushButton("Run close readiness checks")
        self.readiness_button.clicked.connect(self.check_readiness)
        readiness_actions.addWidget(self.readiness_button)
        readiness_actions.addStretch()
        readiness_layout.addLayout(readiness_actions)
        self.readiness_label = QLabel(
            "Run the assessment to verify the fiscal period, close account, journal balance, pending bank work and audit-chain integrity."
        )
        self.readiness_label.setWordWrap(True)
        self.readiness_label.setStyleSheet("padding: 10px; background: palette(alternate-base); border-radius: 6px;")
        readiness_layout.addWidget(self.readiness_label)
        layout.addWidget(readiness_box)

        request_box = QGroupBox("1. Request a fiscal-period close")
        request_form = QFormLayout(request_box)
        self.company_input = QSpinBox()
        self.company_input.setRange(1, 2_147_483_647)
        self.year_input = QSpinBox()
        self.year_input.setRange(2000, 2200)
        self.year_input.setValue(2025)
        self.closing_account_input = QSpinBox()
        self.closing_account_input.setRange(1, 2_147_483_647)
        self.request_button = QPushButton("Create controlled close request")
        self.request_button.clicked.connect(self.create_request)
        request_form.addRow("Company ID", self.company_input)
        request_form.addRow("Fiscal year", self.year_input)
        request_form.addRow("Retained-earnings account ID", self.closing_account_input)
        request_form.addRow("", self.request_button)
        layout.addWidget(request_box)

        approval_box = QGroupBox("2. Review and execute as Financial Controller")
        approval_layout = QVBoxLayout(approval_box)
        selector = QHBoxLayout()
        self.request_id_input = QLineEdit()
        self.request_id_input.setPlaceholderText("Select a pending request below or paste its request UUID")
        self.approve_button = QPushButton("Approve and execute close")
        self.approve_button.clicked.connect(self.approve_request)
        self.reject_button = QPushButton("Reject selected request")
        self.reject_button.clicked.connect(self.reject_request)
        selector.addWidget(self.request_id_input, 1)
        selector.addWidget(self.approve_button)
        selector.addWidget(self.reject_button)
        approval_layout.addLayout(selector)
        layout.addWidget(approval_box)

        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("Close request history"))
        list_header.addStretch()
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_requests)
        list_header.addWidget(refresh_button)
        layout.addLayout(list_header)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Request", "Fiscal year", "Status", "Requester", "Approver", "Executed (UTC)"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._select_request)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

    def set_principal(self, principal: AuthenticatedPrincipal | None) -> None:
        self.principal = principal
        self._set_session_state()
        self.refresh_requests()

    def _set_session_state(self) -> None:
        active = isinstance(self.principal, AuthenticatedPrincipal)
        self.readiness_button.setEnabled(active)
        self.request_button.setEnabled(active)
        self.approve_button.setEnabled(active)
        self.reject_button.setEnabled(active)
        if active:
            self.session_label.setText(f"Enterprise session active for user #{self.principal.user_id}. Sensitive actions require MFA evidence from the last 15 minutes.")
        else:
            self.session_label.setText("Sign in with Enterprise SSO before requesting or approving a fiscal-period close.")

    def check_readiness(self) -> None:
        if not self._require_principal():
            return
        try:
            report = self.service.assess_readiness(
                self.company_input.value(), self.year_input.value(), self.closing_account_input.value(), self.principal
            )
            if report.ready:
                self.readiness_label.setText(
                    "READY: no close blockers were found. Request and approval will run the checks again before accounting is locked."
                )
                self.readiness_label.setStyleSheet("padding: 10px; color: #0b6e4f; background: #e8f5ee; border-radius: 6px;")
            else:
                details = "\n".join(
                    f"• {finding.code}: {finding.message}" for finding in report.findings if finding.is_blocker
                )
                self.readiness_label.setText(f"BLOCKED: resolve the following before close:\n{details}")
                self.readiness_label.setStyleSheet("padding: 10px; color: #a01818; background: #fff0f0; border-radius: 6px;")
        except (PermissionError, PeriodCloseError) as exc:
            self.readiness_label.setText(f"Readiness check denied: {exc}")
            self.readiness_label.setStyleSheet("padding: 10px; color: #a01818; background: #fff0f0; border-radius: 6px;")
        except Exception:
            self.readiness_label.setText("Readiness check could not be completed safely. Review the audit log.")
            self.readiness_label.setStyleSheet("padding: 10px; color: #a01818; background: #fff0f0; border-radius: 6px;")

    def create_request(self) -> None:
        if not self._require_principal():
            return
        try:
            request_id = self.service.request_close(
                self.company_input.value(), self.year_input.value(), self.closing_account_input.value(), self.principal
            )
            self.request_id_input.setText(request_id)
            QMessageBox.information(self, "Close request created", "The request is pending an independent Financial Controller approval.")
            self.refresh_requests()
        except (PermissionError, PeriodCloseError) as exc:
            QMessageBox.warning(self, "Close request not created", str(exc))
        except Exception:
            QMessageBox.critical(self, "Close request failed", "The request could not be created safely. Review the audit log.")

    def approve_request(self) -> None:
        if not self._require_principal():
            return
        request_id = self.request_id_input.text().strip()
        if not request_id:
            QMessageBox.warning(self, "Request required", "Select a pending close request before approval.")
            return
        try:
            result = self.service.approve_and_execute(request_id, self.principal)
            QMessageBox.information(self, "Fiscal year locked", f"Fiscal year {result.fiscal_year} is now closed and locked.")
            self.refresh_requests()
        except SegregationOfDutiesViolation as exc:
            QMessageBox.warning(self, "Segregation of duties", str(exc))
        except (PermissionError, PeriodCloseError) as exc:
            QMessageBox.warning(self, "Close not approved", str(exc))
        except Exception:
            QMessageBox.critical(self, "Close failed", "The fiscal-period close could not be executed safely. Review the audit log.")

    def reject_request(self) -> None:
        if not self._require_principal():
            return
        request_id = self.request_id_input.text().strip()
        if not request_id:
            QMessageBox.warning(self, "Request required", "Select a pending close request before rejection.")
            return
        try:
            self.service.reject(request_id, "Rejected by Financial Controller in desktop workflow", self.principal)
            QMessageBox.information(self, "Close request rejected", "The close request is retained in the audit trail with its rejection decision.")
            self.refresh_requests()
        except SegregationOfDutiesViolation as exc:
            QMessageBox.warning(self, "Segregation of duties", str(exc))
        except (PermissionError, PeriodCloseError) as exc:
            QMessageBox.warning(self, "Close not rejected", str(exc))
        except Exception:
            QMessageBox.critical(self, "Rejection failed", "The close request could not be rejected safely. Review the audit log.")

    def refresh_requests(self) -> None:
        self.table.setRowCount(0)
        if not isinstance(self.principal, AuthenticatedPrincipal):
            return
        company_id = self.company_input.value()
        try:
            with self.database.get_session() as session:
                context = self.principal.authorization_context(company_id, "period_close_history", mfa_max_age=self.service.MFA_MAX_AGE)
                self.authorization.require(session, context, "ledger.read")
                requests = list(session.scalars(
                    select(PeriodCloseRequest)
                    .where(PeriodCloseRequest.company_id == company_id)
                    .order_by(PeriodCloseRequest.requested_at.desc())
                ))
                for record in requests:
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    values = [
                        record.id,
                        str(record.fiscal_year.year),
                        record.status.value,
                        str(record.requested_by_user_id),
                        str(record.approved_by_user_id or "—"),
                        record.executed_at.isoformat() if record.executed_at else "—",
                    ]
                    for column, value in enumerate(values):
                        item = QTableWidgetItem(value)
                        item.setData(Qt.ItemDataRole.UserRole, record.id)
                        self.table.setItem(row, column, item)
        except PermissionError:
            self.table.setRowCount(0)
        except Exception:
            self.table.setRowCount(0)

    def _select_request(self) -> None:
        row = self.table.currentRow()
        if row >= 0 and self.table.item(row, 0):
            self.request_id_input.setText(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def _require_principal(self) -> bool:
        if isinstance(self.principal, AuthenticatedPrincipal):
            return True
        QMessageBox.warning(self, "Enterprise sign-in required", "Sign in with Enterprise SSO before performing protected close operations.")
        return False
