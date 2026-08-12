from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from core.authorization import AuthorizationContext, AuthorizationDenied, AuthorizationService
from core.database import DatabaseManager
from core.models import AuditLog, Company, User, UserRole
from core.security import LocalSecretStore, WindowsDpapiProtector


class EnterpriseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = DatabaseManager(str(self.root / "finanalyzer.db"))
        self.database.init_database()
        self.authorization = AuthorizationService()
        with self.database.get_session() as session:
            self.company_a = Company(name="Company A", legal_name="Company A", currency_code="USD")
            self.company_b = Company(name="Company B", legal_name="Company B", currency_code="USD")
            self.admin = User(username="admin", email="admin@example.test", password_hash="x", role=UserRole.ADMIN)
            self.viewer = User(username="viewer", email="viewer@example.test", password_hash="x", role=UserRole.VIEWER)
            session.add_all([self.company_a, self.company_b, self.admin, self.viewer])
            session.flush()
            self.company_a_id = self.company_a.id
            self.company_b_id = self.company_b.id
            self.admin_id = self.admin.id
            self.viewer_id = self.viewer.id
            self.authorization.grant_role(session, self.admin_id, self.company_a_id, "company_admin")
            self.authorization.grant_role(session, self.viewer_id, self.company_a_id, "viewer")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_denies_unspecified_permission_by_default_and_records_event(self):
        with self.database.get_session() as session:
            context = AuthorizationContext(actor_id=self.viewer_id, company_id=self.company_a_id)
            self.assertTrue(self.authorization.has_permission(session, context, "ledger.read"))
            self.assertFalse(self.authorization.has_permission(session, context, "bank.sync"))
            with self.assertRaises(AuthorizationDenied):
                self.authorization.require(session, context, "bank.sync")
            event = session.scalar(select(AuditLog).where(AuditLog.action == "authorization.denied"))
            self.assertIsNotNone(event)

    def test_company_scope_and_mfa_are_enforced(self):
        with self.database.get_session() as session:
            cross_company = AuthorizationContext(actor_id=self.admin_id, company_id=self.company_b_id, mfa_verified=True)
            with self.assertRaises(AuthorizationDenied):
                self.authorization.require(session, cross_company, "bank.link")

            no_mfa = AuthorizationContext(actor_id=self.admin_id, company_id=self.company_a_id, mfa_verified=False)
            with self.assertRaises(AuthorizationDenied):
                self.authorization.require(session, no_mfa, "bank.link")

            mfa = AuthorizationContext(actor_id=self.admin_id, company_id=self.company_a_id, mfa_verified=True)
            self.authorization.require(session, mfa, "bank.link")

    def test_windows_dpapi_store_migrates_legacy_raw_key(self):
        def protect(value: bytes) -> bytes:
            return b"DPAPI:" + value[::-1]

        def unprotect(value: bytes) -> bytes:
            return value[6:][::-1]

        key_path = self.root / "migration" / ".finanalyzer.key"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_key = b"pLTyi-fz4Y6J60VmrvG_G3Vxwl-XNLzgzsqjGpPZW64="
        key_path.write_bytes(legacy_key)
        store = LocalSecretStore(
            str(key_path),
            dpapi=WindowsDpapiProtector(protect, unprotect),
            operating_system="Windows",
        )
        self.assertEqual(store.protection_mode, "dpapi")
        self.assertFalse(key_path.exists())
        self.assertTrue(Path(str(key_path) + ".dpapi").exists())
        self.assertEqual(store.decrypt(store.encrypt("migration-check")), "migration-check")

    def test_windows_dpapi_store_never_persists_raw_key(self):
        def protect(value: bytes) -> bytes:
            return b"DPAPI:" + value[::-1]

        def unprotect(value: bytes) -> bytes:
            self.assertTrue(value.startswith(b"DPAPI:"))
            return value[6:][::-1]

        key_path = self.root / "data" / ".finanalyzer.key"
        store = LocalSecretStore(
            str(key_path),
            dpapi=WindowsDpapiProtector(protect, unprotect),
            operating_system="Windows",
        )
        encrypted = store.encrypt("plaid-access-token")
        self.assertEqual(store.decrypt(encrypted), "plaid-access-token")
        self.assertEqual(store.protection_mode, "dpapi")
        self.assertFalse(key_path.exists())
        protected_path = Path(str(key_path) + ".dpapi")
        self.assertTrue(protected_path.exists())
        self.assertNotIn(b"plaid-access-token", protected_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
