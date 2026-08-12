from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from core.accounting_engine import AccountingEngine
from core.automated_reporting import AutomatedReportService, EnterpriseReportGenerator, ManagementReportBuilder
from core.database import DatabaseManager
from core.models import Account, AccountType, Company


class ReportingV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = DatabaseManager(str(self.root / "finanalyzer.db"))
        self.database.init_database()
        with self.database.get_session() as session:
            company = Company(name="Reporting Test Co", legal_name="Reporting Test Co", currency_code="USD")
            session.add(company)
            session.flush()
            self.company_id = company.id
            cash = Account(company_id=company.id, code="1010", name="Cash", account_type=AccountType.ASSET)
            revenue = Account(company_id=company.id, code="4000", name="Service Revenue", account_type=AccountType.REVENUE)
            expense = Account(company_id=company.id, code="6000", name="Software Expense", account_type=AccountType.EXPENSE)
            session.add_all([cash, revenue, expense])
            session.flush()
            engine = AccountingEngine(session, company.id)
            engine.post_journal_entry(
                "TEST-REVENUE", date(2026, 8, 1), "Consulting revenue",
                [
                    {"account_id": cash.id, "debit": Decimal("1000.00"), "credit": 0},
                    {"account_id": revenue.id, "debit": 0, "credit": Decimal("1000.00")},
                ],
            )
            engine.post_journal_entry(
                "TEST-EXPENSE", date(2026, 8, 2), "Software subscription",
                [
                    {"account_id": expense.id, "debit": Decimal("125.00"), "credit": 0},
                    {"account_id": cash.id, "debit": 0, "credit": Decimal("125.00")},
                ],
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_and_export_management_pack(self):
        report = ManagementReportBuilder(self.database).build(self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report["income_statement"]["total_revenue"], Decimal("1000.0000"))
        self.assertEqual(report["income_statement"]["total_expense"], Decimal("125.0000"))
        files = EnterpriseReportGenerator(str(self.root / "reports")).generate_all(report, ("pdf", "xlsx"), "test_management_pack")
        self.assertTrue(Path(files["pdf"]).exists())
        self.assertTrue(Path(files["xlsx"]).exists())

    def test_due_schedule_creates_both_files(self):
        service = AutomatedReportService(
            self.database,
            schedules_path=str(self.root / "data" / "schedules.json"),
            output_dir=str(self.root / "reports"),
        )
        schedule = service.create_schedule(self.company_id, "Monthly management pack", "monthly", ("pdf", "xlsx"))
        schedule.next_run_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        service._write_schedules([schedule])
        outcomes = service.run_due()
        self.assertEqual(outcomes[0]["status"], "completed")
        self.assertTrue(Path(outcomes[0]["files"]["pdf"]).exists())
        self.assertTrue(Path(outcomes[0]["files"]["xlsx"]).exists())


if __name__ == "__main__":
    unittest.main()
