from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from core.database import DatabaseManager
from core.models import Company, JournalEntry, PlaidItem, PlaidTransactionMapping
from core.plaid_connector import PLAID_SDK_AVAILABLE, PlaidConnector, PlaidSettings
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
        with self.database.get_session() as session:
            company = Company(name="Test Company", legal_name="Test Company", currency_code="USD")
            session.add(company)
            session.flush()
            self.company_id = company.id
        settings = PlaidSettings(client_id="test-client", secret="test-secret", environment="sandbox")
        self.connector = PlaidConnector(
            self.database,
            settings=settings,
            secret_store=LocalSecretStore(str(root / ".finanalyzer.key")),
        )
        self.connector.client = FakePlaidClient()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exchange_encrypts_token_and_sync_posts_balanced_entry(self):
        self.connector.exchange_public_token(self.company_id, "public-sandbox-test", {"name": "Test Bank"})
        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == "item-test-001"))
            self.assertIsNotNone(item)
            self.assertNotIn("access-sandbox-test", item.encrypted_access_token)

        result = self.connector.sync_item("item-test-001")
        self.assertEqual(result["added"], 1)
        with self.database.get_session() as session:
            mapping = session.scalar(select(PlaidTransactionMapping).where(PlaidTransactionMapping.provider_transaction_id == "tx-test-001"))
            entry = session.scalar(select(JournalEntry).where(JournalEntry.id == mapping.journal_entry_id))
            debits = sum(line.debit for line in entry.transactions)
            credits = sum(line.credit for line in entry.transactions)
            self.assertEqual(debits, credits)


if __name__ == "__main__":
    unittest.main()
