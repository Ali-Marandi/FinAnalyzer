"""Offline tests for v2.4 tamper-evident audit logging and additive schema migration."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from core.audit import AuditLogger, AuditSigningKeyStore
from core.authorization import AuthorizationContext, AuthorizationDenied, AuthorizationService
from core.database import DatabaseManager
from core.models import AuditLog, Company, User, UserRole


class AuditV24Tests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.database = DatabaseManager(str(self.root / "audit.db"))
        self.database.init_database()
        self.logger = AuditLogger(AuditSigningKeyStore(str(self.root / "audit.key"), operating_system="Linux"))

    def tearDown(self):
        self.tempdir.cleanup()

    def test_event_details_are_redacted_and_chain_verifies(self):
        with self.database.get_session() as session:
            self.logger.record(
                session,
                action="bank.item_linked",
                category="banking",
                outcome="success",
                severity="notice",
                actor_id=None,
                details={"access_token": "never-store-me", "nested": {"refresh_token": "also-secret"}, "item_id": "safe-id"},
            )
            self.logger.record(
                session,
                action="authorization.denied",
                category="authorization",
                outcome="denied",
                severity="warning",
                details={"permission": "bank.unlink"},
            )
        with self.database.get_session() as session:
            event = session.scalar(select(AuditLog).where(AuditLog.sequence == 1))
            self.assertIn("[REDACTED]", event.details)
            self.assertNotIn("never-store-me", event.details)
            result = self.logger.verify_chain(session)
            self.assertTrue(result.valid)
            self.assertEqual(result.checked_events, 2)

    def test_tampering_is_detected_during_verification(self):
        with self.database.get_session() as session:
            self.logger.record(
                session, action="identity.sign_in_succeeded", category="identity", outcome="success", details={"provider": "test"}
            )
        with self.database.get_session() as session:
            event = session.scalar(select(AuditLog).where(AuditLog.sequence == 1))
            event.details = json.dumps({"provider": "tampered"})
        with self.database.get_session() as session:
            result = self.logger.verify_chain(session)
            self.assertFalse(result.valid)
            self.assertEqual(result.first_invalid_sequence, 1)

    def test_authorization_denial_writes_structured_chained_event(self):
        with self.database.get_session() as session:
            company = Company(name="Audit Company", legal_name="Audit Company", currency_code="USD")
            user = User(username="audit-viewer", email="audit@example.test", password_hash="x", role=UserRole.VIEWER)
            session.add_all([company, user])
            session.flush()
            company_id = company.id
            authorization = AuthorizationService(audit_logger=self.logger)
            with self.assertRaises(AuthorizationDenied):
                authorization.require(
                    session,
                    AuthorizationContext(actor_id=user.id, company_id=company.id, reason="audit_test"),
                    "bank.unlink",
                )
        with self.database.get_session() as session:
            event = session.scalar(select(AuditLog).where(AuditLog.action == "authorization.denied"))
            self.assertEqual(event.category, "authorization")
            self.assertEqual(event.outcome, "denied")
            self.assertEqual(event.company_id, company_id)
            self.assertTrue(event.event_hash)
            self.assertTrue(self.logger.verify_chain(session).valid)

    def test_legacy_audit_table_is_upgraded_additively(self):
        legacy_db = self.root / "legacy.db"
        connection = sqlite3.connect(legacy_db)
        connection.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, user_id INTEGER, action VARCHAR(255) NOT NULL, details TEXT, timestamp DATETIME)")
        connection.execute("INSERT INTO audit_logs (id, action, details) VALUES (1, 'legacy.event', '{}')")
        connection.commit()
        connection.close()
        manager = DatabaseManager(str(legacy_db))
        manager.init_database()
        with manager.get_session() as session:
            self.logger.record(
                session, action="audit.migration_checked", category="audit", outcome="success", details={"legacy": True}
            )
            result = self.logger.verify_chain(session)
            self.assertTrue(result.valid)
            self.assertEqual(result.legacy_events, 1)


if __name__ == "__main__":
    unittest.main()
