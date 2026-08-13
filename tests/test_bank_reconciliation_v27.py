"""Regression coverage for controlled Plaid bank-feed reconciliation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from core.audit import AuditLogger, AuditSigningKeyStore
from core.authorization import AuthorizationService
from core.bank_reconciliation import BankReconciliationError, BankReconciliationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal
from core.models import (
    Account,
    AccountType,
    AuditLog,
    BankReconciliationStatus,
    Company,
    FiscalYear,
    JournalEntry,
    PlaidItem,
    PlaidTransactionMapping,
    User,
    UserRole,
)
from core.plaid_connector import PLAID_SDK_AVAILABLE, PlaidConnector, PlaidSettings
from core.security import LocalSecretStore


class FakePlaidClient:
    def item_public_token_exchange(self, _request):
        return {"access_token": "access-sandbox-test", "item_id": "reconciliation-item-001"}

    def transactions_sync(self, _request):
        return {
            "added": [{
                "transaction_id": "reconciliation-tx-001",
                "account_id": "reconciliation-account-001",
                "date": "2026-08-01",
                "name": "Office supplier",
                "merchant_name": "Office Supplier",
                "amount": 125.50,
                "iso_currency_code": "USD",
                "pending": False,
            }],
            "modified": [],
            "removed": [],
            "accounts": [{
                "account_id": "reconciliation-account-001",
                "name": "Operating Account",
                "type": "depository",
                "subtype": "checking",
                "mask": "0000",
                "balances": {"current": 9999.50, "available": 9750.00, "iso_currency_code": "USD"},
            }],
            "next_cursor": "reconciliation-cursor-001",
            "has_more": False,
        }


@unittest.skipUnless(PLAID_SDK_AVAILABLE, "plaid-python must be installed")
class BankReconciliationV27Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database = DatabaseManager(str(root / "reconciliation.db"))
        self.database.init_database()
        self.audit_logger = AuditLogger(AuditSigningKeyStore(str(root / "reconciliation.hmac"), operating_system="Linux"))
        self.authorization = AuthorizationService(audit_logger=self.audit_logger)
        with self.database.get_session() as session:
            company = Company(name="Reconciliation Co", legal_name="Reconciliation Co", currency_code="USD")
            manager = User(username="recon-manager", email="manager@example.test", password_hash="x", role=UserRole.ADMIN)
            controller = User(username="recon-controller", email="controller@example.test", password_hash="x", role=UserRole.ADMIN)
            session.add_all([company, manager, controller])
            session.flush()
            self.company_id = company.id
            self.manager_id = manager.id
            self.controller_id = controller.id
            self.authorization.grant_role(session, self.manager_id, self.company_id, "finance_manager")
            self.authorization.grant_role(session, self.controller_id, self.company_id, "financial_controller")
            expense = Account(
                company_id=self.company_id,
                code="6100",
                name="Office supplies",
                account_type=AccountType.EXPENSE,
            )
            session.add(expense)
            session.flush()
            self.expense_account_id = expense.id
        self.manager = self._principal(self.manager_id, "manager")
        self.controller = self._principal(self.controller_id, "controller")
        self.connector = PlaidConnector(
            self.database,
            settings=PlaidSettings(client_id="test-client", secret="test-secret", environment="sandbox"),
            secret_store=LocalSecretStore(str(root / ".key")),
            authorization=self.authorization,
            audit_logger=self.audit_logger,
        )
        self.connector.client = FakePlaidClient()
        self.service = BankReconciliationService(
            self.database, authorization=self.authorization, audit_logger=self.audit_logger
        )
        self.connector.exchange_public_token(self.company_id, self.manager, "public-test", {"name": "Test Bank"})
        self.connector.sync_item("reconciliation-item-001", self.manager)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _principal(user_id: int, suffix: str) -> AuthenticatedPrincipal:
        now = datetime.now(timezone.utc)
        return AuthenticatedPrincipal(
            user_id=user_id,
            session_id=f"reconciliation-{suffix}",
            provider_code="test",
            issuer="https://issuer.example.test",
            subject=f"subject-{suffix}",
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
            mfa_at=now,
        )

    def _mapping(self, session) -> PlaidTransactionMapping:
        return session.scalar(select(PlaidTransactionMapping).where(
            PlaidTransactionMapping.provider_transaction_id == "reconciliation-tx-001"
        ))

    def test_imported_feed_item_appears_as_needs_review_without_raw_payload(self) -> None:
        items = self.service.list_work_items(self.company_id, self.manager)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, BankReconciliationStatus.NEEDS_REVIEW.value)
        self.assertNotIn("raw_payload", items[0].__dict__)
        summary = self.service.summary(self.company_id, self.manager)
        self.assertEqual(summary.needs_review, 1)
        self.assertEqual(summary.matched, 0)

    def test_match_changes_only_contra_account_and_preserves_balanced_entry(self) -> None:
        self.service.match_transaction(
            self.company_id, "reconciliation-tx-001", self.expense_account_id,
            self.manager, "Classified after invoice review",
        )
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            entry = session.get(JournalEntry, mapping.journal_entry_id)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.MATCHED)
            self.assertEqual(mapping.reconciled_by_user_id, self.manager_id)
            self.assertIn(self.expense_account_id, {line.account_id for line in entry.transactions})
            self.assertEqual(sum(line.debit for line in entry.transactions), sum(line.credit for line in entry.transactions))
            event = session.scalar(select(AuditLog).where(AuditLog.action == "bank.reconciliation.matched"))
            self.assertEqual(event.outcome, "success")
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_exception_requires_independent_resolver(self) -> None:
        self.service.mark_exception(
            self.company_id, "reconciliation-tx-001", "Supplier invoice needs review", self.manager
        )
        with self.assertRaises(BankReconciliationError):
            self.service.resolve_exception(
                self.company_id, "reconciliation-tx-001", self.expense_account_id,
                self.manager, "Attempted self-resolution",
            )
        self.service.resolve_exception(
            self.company_id, "reconciliation-tx-001", self.expense_account_id,
            self.controller, "Controller verified supplier invoice",
        )
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.MATCHED)
            self.assertEqual(mapping.reconciled_by_user_id, self.controller_id)
            denied = session.scalar(select(AuditLog).where(AuditLog.action == "bank.reconciliation.sod_denied"))
            self.assertEqual(denied.outcome, "denied")
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_locked_period_cannot_be_reclassified(self) -> None:
        with self.database.get_session() as session:
            session.add(FiscalYear(
                company_id=self.company_id,
                year=2026,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                is_closed=True,
            ))
        with self.assertRaises(BankReconciliationError):
            self.service.match_transaction(
                self.company_id, "reconciliation-tx-001", self.expense_account_id,
                self.manager, "Attempt while locked",
            )
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.NEEDS_REVIEW)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_close_readiness_can_distinguish_unreconciled_feed_work(self) -> None:
        from core.period_close import PeriodCloseService
        with self.database.get_session() as session:
            retained = Account(
                company_id=self.company_id,
                code="3000",
                name="Retained earnings",
                account_type=AccountType.EQUITY,
            )
            session.add_all([retained, FiscalYear(
                company_id=self.company_id,
                year=2026,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
            )])
            session.flush()
            retained_id = retained.id
        report = PeriodCloseService(
            self.database, authorization=self.authorization, audit_logger=self.audit_logger
        ).assess_readiness(self.company_id, 2026, retained_id, self.manager)
        self.assertIn("unreconciled_bank_transactions", report.blocker_codes)


if __name__ == "__main__":
    unittest.main()
