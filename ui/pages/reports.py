"""Ledger-driven financial reports page for FinAnalyzer Enterprise."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from core.automated_reporting import AutomatedReportService, EnterpriseReportGenerator, ManagementReportBuilder, ReportingError
from core.authorization import AuthorizationContext, AuthorizationDenied, AuthorizationService
from core.database import DatabaseManager
from core.models import Company


class ReportsPage(QWidget):
    def __init__(self, parent=None, *, actor_id: int | None = None, mfa_verified: bool = False):
        super().__init__(parent)
        self.actor_id = actor_id
        self.mfa_verified = mfa_verified
        self.authorization = AuthorizationService()
        root = Path(__file__).resolve().parents[2]
        self.root = root
        self.database = DatabaseManager(str(root / "finanalyzer.db"))
        self.database.init_database()
        self.company_id = self._ensure_company()
        self.builder = ManagementReportBuilder(self.database)
        self.generator = EnterpriseReportGenerator(str(root / "reports"))
        self.schedules = AutomatedReportService(
            self.database,
            schedules_path=str(root / "data" / "report_schedules.json"),
            output_dir=str(root / "reports"),
        )
        self._init_ui()
        if self.actor_id is None:
            self.pdf_btn.setEnabled(False)
            self.excel_btn.setEnabled(False)
            self.schedule_btn.setEnabled(False)
            self.generate_btn.setEnabled(False)
            self.preview_pane.setPlainText("A signed-in, authorized user is required to view or export company reports.")
        else:
            self.generate_report()

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
        title = QLabel("Financial Reports & Statements")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.pdf_btn = QPushButton("Export PDF")
        self.pdf_btn.clicked.connect(lambda: self.export_report("pdf"))
        header.addWidget(self.pdf_btn)
        self.excel_btn = QPushButton("Export Excel")
        self.excel_btn.setObjectName("secondaryButton")
        self.excel_btn.clicked.connect(lambda: self.export_report("xlsx"))
        header.addWidget(self.excel_btn)
        self.schedule_btn = QPushButton("Schedule Monthly Pack")
        self.schedule_btn.setObjectName("secondaryButton")
        self.schedule_btn.clicked.connect(self.create_monthly_schedule)
        header.addWidget(self.schedule_btn)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Report View:"))
        self.report_type_combo = QComboBox()
        self.report_type_combo.addItems(["Balance Sheet", "Income Statement (P&L)", "Trial Balance", "Management Summary"])
        self.report_type_combo.currentIndexChanged.connect(self.generate_report)
        toolbar.addWidget(self.report_type_combo)
        toolbar.addWidget(QLabel("As of:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self.generate_report)
        toolbar.addWidget(self.date_edit)
        self.generate_btn = QPushButton("Refresh Preview")
        self.generate_btn.clicked.connect(self.generate_report)
        toolbar.addWidget(self.generate_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.preview_pane = QTextEdit()
        self.preview_pane.setReadOnly(True)
        self.preview_pane.setStyleSheet("font-family: 'Courier New', monospace; font-size: 10pt; padding: 15px;")
        layout.addWidget(self.preview_pane)

    def _build_report(self):
        actor_id = self._require_actor()
        with self.database.get_session() as session:
            self.authorization.require(
                session,
                AuthorizationContext(actor_id=actor_id, company_id=self.company_id, reason="report_preview"),
                "report.generate",
            )
        end = self.date_edit.date().toPython()
        start = end - timedelta(days=30)
        return self.builder.build(self.company_id, start, end)

    def generate_report(self, *_args) -> None:
        try:
            report = self._build_report()
            selected = self.report_type_combo.currentText()
            if selected == "Balance Sheet":
                content = self._format_balance_sheet(report["balance_sheet"], report["metadata"])
            elif selected == "Income Statement (P&L)":
                content = self._format_income_statement(report["income_statement"], report["metadata"])
            elif selected == "Trial Balance":
                content = self._format_trial_balance(report["trial_balance"], report["metadata"])
            else:
                content = self._format_management_summary(report)
            self.preview_pane.setPlainText(content)
        except Exception as exc:
            self.preview_pane.setPlainText(f"Report preview could not be generated.\n{exc}")

    def export_report(self, report_format: str) -> None:
        try:
            report = self._build_report()
            files = self.generator.generate_all(report, (report_format,), prefix="on_demand_management_pack")
            file_path = files[report_format]
            QMessageBox.information(self, "Report created", f"The {report_format.upper()} report was created locally:\n{file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"The report could not be created.\n{exc}")

    def create_monthly_schedule(self) -> None:
        try:
            schedule = self.schedules.create_schedule(
                company_id=self.company_id,
                actor_id=self._require_actor(),
                name="Monthly management pack",
                cadence="monthly",
                formats=("pdf", "xlsx"),
                hour_utc=8,
                mfa_verified=self.mfa_verified,
            )
            QMessageBox.information(
                self,
                "Schedule created",
                "A local monthly PDF/Excel schedule was created.\n\n"
                f"Next run: {schedule.next_run_at}\n\n"
                "To run it automatically, configure Windows Task Scheduler to execute scripts\\run_scheduled_reports.py under the intended Windows user.",
            )
        except (ReportingError, AuthorizationDenied) as exc:
            QMessageBox.warning(self, "Schedule not created", str(exc))

    def _require_actor(self) -> int:
        if self.actor_id is None:
            raise AuthorizationDenied("A signed-in user is required for this operation.")
        return self.actor_id

    @staticmethod
    def _money(value) -> str:
        return f"{float(value or 0):,.2f}"

    def _format_balance_sheet(self, statement, metadata) -> str:
        lines = [
            "=" * 72,
            "FINANALYZER ENTERPRISE | BALANCE SHEET",
            f"Company: {metadata['company']} | As of: {statement['as_of_date']}",
            "=" * 72,
            "ASSETS",
        ]
        lines.extend(f"  {item['code']:<12} {item['name']:<34} {self._money(item['net_balance']):>16}" for item in statement["assets"])
        lines.append(f"TOTAL ASSETS{'':<44}{self._money(statement['total_assets']):>16}")
        lines.append("\nLIABILITIES")
        lines.extend(f"  {item['code']:<12} {item['name']:<34} {self._money(item['net_balance']):>16}" for item in statement["liabilities"])
        lines.append(f"TOTAL LIABILITIES{'':<39}{self._money(statement['total_liabilities']):>16}")
        lines.append("\nEQUITY")
        lines.extend(f"  {item['code']:<12} {item['name']:<34} {self._money(item['net_balance']):>16}" for item in statement["equity"])
        lines.append(f"TOTAL EQUITY{'':<44}{self._money(statement['total_equity']):>16}")
        lines.append("=" * 72)
        lines.append(f"Balance check: {'BALANCED' if statement['is_balanced'] else 'REVIEW REQUIRED'}")
        return "\n".join(lines)

    def _format_income_statement(self, statement, metadata) -> str:
        lines = [
            "=" * 72,
            "FINANALYZER ENTERPRISE | INCOME STATEMENT",
            f"Company: {metadata['company']} | Period: {statement['start_date']} to {statement['end_date']}",
            "=" * 72,
            "REVENUE",
        ]
        lines.extend(f"  {item['code']:<12} {item['name']:<34} {self._money(item['amount']):>16}" for item in statement["revenues"])
        lines.append(f"TOTAL REVENUE{'':<43}{self._money(statement['total_revenue']):>16}")
        lines.append("\nEXPENSES")
        lines.extend(f"  {item['code']:<12} {item['name']:<34} {self._money(item['amount']):>16}" for item in statement["expenses"])
        lines.append(f"TOTAL EXPENSES{'':<42}{self._money(statement['total_expense']):>16}")
        lines.append("=" * 72)
        lines.append(f"NET INCOME{'':<46}{self._money(statement['net_income']):>16}")
        return "\n".join(lines)

    def _format_trial_balance(self, balances, metadata) -> str:
        lines = [
            "=" * 86,
            "FINANALYZER ENTERPRISE | TRIAL BALANCE",
            f"Company: {metadata['company']} | As of: {metadata['period_end']}",
            "=" * 86,
            f"{'Code':<12}{'Account':<34}{'Debit':>14}{'Credit':>14}{'Net':>14}",
            "-" * 86,
        ]
        for item in balances:
            lines.append(f"{item['code']:<12}{item['name'][:32]:<34}{self._money(item['debit']):>14}{self._money(item['credit']):>14}{self._money(item['net_balance']):>14}")
        return "\n".join(lines)

    def _format_management_summary(self, report) -> str:
        balance = report["balance_sheet"]
        income = report["income_statement"]
        metadata = report["metadata"]
        return "\n".join([
            "=" * 72,
            "FINANALYZER ENTERPRISE | MANAGEMENT SUMMARY",
            f"Company: {metadata['company']} | Currency: {metadata['currency_code']}",
            f"Period: {metadata['period_start']} to {metadata['period_end']}",
            "=" * 72,
            f"Ledger journal entries: {report['entry_count']}",
            f"Total assets:          {self._money(balance['total_assets'])}",
            f"Total liabilities:     {self._money(balance['total_liabilities'])}",
            f"Total equity:          {self._money(balance['total_equity'])}",
            f"Total revenue:         {self._money(income['total_revenue'])}",
            f"Total expenses:        {self._money(income['total_expense'])}",
            f"Net income:            {self._money(income['net_income'])}",
            f"Ledger balance check:  {'BALANCED' if balance['is_balanced'] else 'REVIEW REQUIRED'}",
            "=" * 72,
            "Exports exclude banking credentials and delivery secrets.",
        ])
