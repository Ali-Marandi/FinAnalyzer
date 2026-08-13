from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from core.audit import AuditLogger, AuditSigningKeyStore
from core.authorization import AuthorizationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal
from core.models import AuditLog, Company, FiscalYear, JournalEntry, PlaidItem, PlaidTransactionMapping, User, UserRole
from core.plaid_connector import PLAID_SDK_AVAILABLE, PlaidConnector, PlaidSettings, PlaidSyncError
from core.security import LocalSecretStore


class FakePlaidClient:
    def item_public_token_exchange(self, _request):
        return {"access_token": "access-sandbox-test", "item_id": "item-test-001"}

    def transactions_sync(self, _request):
        return {
            "added": [
                {
                    "transaction_id": "tx-test-001",
                    "account_id": "acc-test-001",
                    "date": "2026-08-01",
                    "name": "Cloud subscription",
                    "merchant_name": "Cloud Provider",
                    "amount": 125.50,
                    "iso_currency_code": "USD",
                    "pending": False,
                    "personal_finance_category": {"primary": "GENERAL_SERVICES"},
                }
            ],
            "modified": [],
            "removed": [],
            "accounts": [
                {
                    "account_id": "acc-test-001",
                    "name": "Operating Account",
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "0000",
                    "balances": {"current": 9999.50, "available": 9750.00, "iso_currency_code": "USD"},
                }
            ],
            "next_cursor": "cursor-test-001",
            "has_more": False,
        }


@unittest.skipUnless(PLAID_SDK_AVAILABLE, "plaid-python must be installed")
class PlaidV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database = DatabaseManager(str(root / "finanalyzer.db"))
        self.database.init_database()
        self.audit_logger = AuditLogger(AuditSigningKeyStore(str(root / ".audit.hmac"), operating_system="Linux"))
        self.authorization = AuthorizationService(audit_logger=self.audit_logger)
        with self.database.get_session() as session:
            company = Company(name="Test Company", legal_name="Test Company", currency_code="USD")
            session.add(company)
            session.flush()
            user = User(username="bank-operator", email="bank-operator@example.test", password_hash="x", role=UserRole.ADMIN)
            session.add(user)
            session.flush()
            self.company_id = company.id
            self.actor_id = user.id
            self.authorization.grant_role(session, self.actor_id, self.company_id, "finance_manager")
        settings = PlaidSettings(client_id="test-client", secret="test-secret", environment="sandbox")
        self.connector = PlaidConnector(
            self.database,
            settings=settings,
            secret_store=LocalSecretStore(str(root / ".finanalyzer.key")),
            authorization=self.authorization,
            audit_logger=self.audit_logger,
        )
        self.connector.client = FakePlaidClient()
        now = datetime.now(timezone.utc)
        self.principal = AuthenticatedPrincipal(
            user_id=self.actor_id,
            session_id="test-plaid-session",
            provider_code="test",
            issuer="https://issuer.example.test",
            subject="test-bank-operator",
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
            mfa_at=now,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exchange_encrypts_token_and_sync_posts_balanced_entry(self):
        self.connector.exchange_public_token(
            self.company_id,
            self.principal,
            "public-sandbox-test",
            {"name": "Test Bank"},
        )
        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == "item-test-001"))
            self.assertIsNotNone(item)
            self.assertNotIn("access-sandbox-test", item.encrypted_access_token)

        result = self.connector.sync_item("item-test-001", self.principal)
        self.assertEqual(result["added"], 1)
        with self.database.get_session() as session:
            mapping = session.scalar(select(PlaidTransactionMapping).where(PlaidTransactionMapping.provider_transaction_id == "tx-test-001"))
            entry = session.scalar(select(JournalEntry).where(JournalEntry.id == mapping.journal_entry_id))
            debits = sum(line.debit for line in entry.transactions)
            credits = sum(line.credit for line in entry.transactions)
            self.assertEqual(debits, credits)

    def test_bank_revision_cannot_void_entry_in_closed_fiscal_period(self):
        self.connector.exchange_public_token(
            self.company_id,
            self.principal,
            "public-sandbox-test",
            {"name": "Test Bank"},
        )
        self.connector.sync_item("item-test-001", self.principal)

        class RevisionClient(FakePlaidClient):
            def transactions_sync(self, request):
                payload = super().transactions_sync(request)
                revised = payload["added"][0]
                revised["amount"] = 129.50
                payload["added"] = []
                payload["modified"] = [revised]
                payload["next_cursor"] = "cursor-revision-001"
                return payload

        self.connector.client = RevisionClient()
        with self.database.get_session() as session:
            session.add(FiscalYear(
                company_id=self.company_id,
                year=2026,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                is_closed=True,
            ))
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == "item-test-001"))
            original_cursor = item.cursor
            mapping = session.scalar(select(PlaidTransactionMapping).where(
                PlaidTransactionMapping.provider_transaction_id == "tx-test-001"
            ))
            original_entry_id = mapping.journal_entry_id

        with self.assertRaises(PlaidSyncError):
            self.connector.sync_item("item-test-001", self.principal)

        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == "item-test-001"))
            mapping = session.scalar(select(PlaidTransactionMapping).where(
                PlaidTransactionMapping.provider_transaction_id == "tx-test-001"
            ))
            entry = session.get(JournalEntry, original_entry_id)
            failure = session.scalar(select(AuditLog).where(AuditLog.action == "bank.sync_apply_failed"))
            self.assertEqual(item.cursor, original_cursor)
            self.assertEqual(mapping.journal_entry_id, original_entry_id)
            self.assertEqual(entry.status.value, "posted")
            self.assertEqual(failure.outcome, "failure")
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_bank_removal_cannot_void_entry_in_closed_fiscal_period(self):
        self.connector.exchange_public_token(
            self.company_id,
            self.principal,
            "public-sandbox-test",
            {"name": "Test Bank"},
        )
        self.connector.sync_item("item-test-001", self.principal)

        class RemovalClient(FakePlaidClient):
            def transactions_sync(self, request):
                payload = super().transactions_sync(request)
                payload["added"] = []
                payload["modified"] = []
                payload["removed"] = [{"transaction_id": "tx-test-001"}]
                payload["accounts"] = []
                payload["next_cursor"] = "cursor-removal-001"
                return payload

        self.connector.client = RemovalClient()
        with self.database.get_session() as session:
            session.add(FiscalYear(
                company_id=self.company_id,
                year=2026,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                is_closed=True,
            ))
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == "item-test-001"))
            original_cursor = item.cursor
            mapping = session.scalar(select(PlaidTransactionMapping).where(
                PlaidTransactionMapping.provider_transaction_id == "tx-test-001"
            ))
            original_entry_id = mapping.journal_entry_id

        with self.assertRaises(PlaidSyncError):
            self.connector.sync_item("item-test-001", self.principal)

        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == "item-test-001"))
            mapping = session.scalar(select(PlaidTransactionMapping).where(
                PlaidTransactionMapping.provider_transaction_id == "tx-test-001"
            ))
            entry = session.get(JournalEntry, original_entry_id)
            failure = session.scalar(select(AuditLog).where(AuditLog.action == "bank.sync_apply_failed"))
            self.assertEqual(item.cursor, original_cursor)
            self.assertFalse(mapping.pending)
            self.assertEqual(entry.status.value, "posted")
            self.assertEqual(failure.outcome, "failure")
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_sync_for_closed_fiscal_period_rolls_back_mapping_cursor_and_entry(self):
        self.connector.exchange_public_token(
            self.company_id,
            self.principal,
            "public-sandbox-test",
            {"name": "Test Bank"},
        )
        with self.database.get_session() as session:
            session.add(FiscalYear(
                company_id=self.company_id,
                year=2026,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                is_closed=True,
            ))

        with self.assertRaises(PlaidSyncError):
            self.connector.sync_item("item-test-001", self.principal)

        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == "item-test-001"))
            mapping = session.scalar(select(PlaidTransactionMapping).where(
                PlaidTransactionMapping.provider_transaction_id == "tx-test-001"
            ))
            entry = session.scalar(select(JournalEntry).where(JournalEntry.description == "Cloud Provider"))
            failure = session.scalar(select(AuditLog).where(AuditLog.action == "bank.sync_apply_failed"))
            self.assertIsNone(mapping)
            self.assertIsNone(entry)
            self.assertIsNone(item.cursor)
            self.assertEqual(item.status, "linked")
            self.assertEqual(failure.outcome, "failure")
            self.assertEqual(failure.company_id, self.company_id)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)


if __name__ == "__main__":
    unittest.main()
