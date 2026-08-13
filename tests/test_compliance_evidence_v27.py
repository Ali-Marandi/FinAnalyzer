"""Tests for verified company-scoped compliance evidence packs."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from core.audit import AuditLogger, AuditSigningKeyStore
from core.authorization import AuthorizationDenied, AuthorizationService
from core.compliance_evidence import ComplianceEvidenceService, EvidenceExportError
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal
from core.models import AuditLog, Company, FiscalYear, User, UserRole


class ComplianceEvidenceV27Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.output_dir = root / "evidence-output"
        self.database = DatabaseManager(str(root / "evidence.db"))
        self.database.init_database()
        self.logger = AuditLogger(AuditSigningKeyStore(str(root / "evidence.hmac"), operating_system="Linux"))
        self.authorization = AuthorizationService(audit_logger=self.logger)
        with self.database.get_session() as session:
            self.company = Company(name="Evidence Co", legal_name="Evidence Co", currency_code="USD")
            self.controller = User(
                username="evidence.controller",
                email="controller@example.test",
                password_hash="x",
                role=UserRole.ADMIN,
            )
            self.viewer = User(
                username="evidence.viewer",
                email="viewer@example.test",
                password_hash="x",
                role=UserRole.VIEWER,
            )
            session.add_all([self.company, self.controller, self.viewer])
            session.flush()
            self.company_id = self.company.id
            self.controller_id = self.controller.id
            self.viewer_id = self.viewer.id
            session.add(FiscalYear(
                company_id=self.company_id,
                year=2025,
                start_date=datetime(2025, 1, 1).date(),
                end_date=datetime(2025, 12, 31).date(),
            ))
            self.authorization.grant_role(session, self.controller_id, self.company_id, "financial_controller")
            self.authorization.grant_role(session, self.viewer_id, self.company_id, "viewer")
        self.service = ComplianceEvidenceService(
            self.database,
            authorization=self.authorization,
            audit_logger=self.logger,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @staticmethod
    def _principal(user_id: int, *, mfa_age_minutes: int = 0) -> AuthenticatedPrincipal:
        now = datetime.now(timezone.utc)
        return AuthenticatedPrincipal(
            user_id=user_id,
            session_id=f"evidence-session-{user_id}-{mfa_age_minutes}",
            provider_code="entra",
            issuer="https://issuer.example.test",
            subject=f"subject-{user_id}",
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
            mfa_at=now - timedelta(minutes=mfa_age_minutes),
            assurance_level="mfa",
        )

    def _record_company_event(self) -> None:
        with self.database.get_session() as session:
            self.logger.record(
                session,
                action="bank.sync.completed",
                category="banking",
                outcome="success",
                actor_id=self.controller_id,
                company_id=self.company_id,
                source="test",
                details={"access_token": "never-export-this", "transaction_count": 1},
            )

    def test_verified_pack_contains_hash_manifest_and_redacted_events(self) -> None:
        self._record_company_event()
        result = self.service.export_company_evidence(
            self.company_id, self.output_dir, self._principal(self.controller_id)
        )
        manifest_path = Path(result.manifest_path)
        self.assertTrue(manifest_path.exists())
        self.assertTrue((Path(result.pack_directory) / "audit-events.json").exists())
        self.assertTrue((Path(result.pack_directory) / "fiscal-years.json").exists())
        self.assertTrue((Path(result.pack_directory) / "period-close-requests.json").exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_sha256"], result.manifest_sha256)
        self.assertTrue(manifest["audit_chain"]["verified"])
        events = json.loads((Path(result.pack_directory) / "audit-events.json").read_text(encoding="utf-8"))
        bank_event = next(event for event in events if event["action"] == "bank.sync.completed")
        self.assertEqual(bank_event["details"]["access_token"], "[REDACTED]")
        with self.database.get_session() as session:
            exported = session.scalar(select(AuditLog).where(AuditLog.action == "compliance.evidence.exported"))
            self.assertEqual(exported.outcome, "success")
            self.assertTrue(self.logger.verify_chain(session).valid)

    def test_invalid_local_audit_chain_blocks_evidence_export_and_deletes_partial_output(self) -> None:
        self._record_company_event()
        with self.database.get_session() as session:
            event = session.scalar(select(AuditLog).where(AuditLog.action == "bank.sync.completed"))
            event.details = '{"transaction_count": 999}'
        with self.assertRaises(EvidenceExportError):
            self.service.export_company_evidence(
                self.company_id, self.output_dir, self._principal(self.controller_id)
            )
        self.assertFalse(self.output_dir.exists())
        with self.database.get_session() as session:
            denied = session.scalar(select(AuditLog).where(AuditLog.action == "compliance.evidence.exported"))
            self.assertEqual(denied.outcome, "denied")
            self.assertFalse(self.logger.verify_chain(session).valid)

    def test_export_requires_recent_mfa_and_explicit_company_permission(self) -> None:
        with self.assertRaises(AuthorizationDenied):
            self.service.export_company_evidence(
                self.company_id, self.output_dir, self._principal(self.viewer_id)
            )
        with self.assertRaises(AuthorizationDenied):
            self.service.export_company_evidence(
                self.company_id, self.output_dir, self._principal(self.controller_id, mfa_age_minutes=16)
            )
        self.assertFalse(self.output_dir.exists())
        with self.database.get_session() as session:
            denials = list(session.scalars(select(AuditLog).where(AuditLog.action == "authorization.denied")))
            self.assertEqual(len(denials), 2)
            self.assertTrue(self.logger.verify_chain(session).valid)


if __name__ == "__main__":
    unittest.main()
