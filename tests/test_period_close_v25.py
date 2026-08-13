"""Tests for the controlled financial-close workflow introduced after v2.4.0."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from core.audit import AuditLogger, AuditSigningKeyStore
from core.authorization import AuthorizationDenied, AuthorizationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal
from core.models import (
    Account,
    AccountType,
    AuditLog,
    Company,
    FiscalYear,
    PeriodCloseRequest,
    PeriodCloseRequestStatus,
    User,
    UserRole,
)
from core.period_close import PeriodCloseError, PeriodCloseService, SegregationOfDutiesViolation


class PeriodCloseV25Tests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.database = DatabaseManager(str(root / "period-close.db"))
        self.database.init_database()
        self.logger = AuditLogger(AuditSigningKeyStore(str(root / "period-close.hmac"), operating_system="Linux"))
        self.authorization = AuthorizationService(audit_logger=self.logger)
        with self.database.get_session() as session:
            company = Company(name="Close Control Co", legal_name="Close Control Co", currency_code="USD")
            requester = User(username="close.preparer", email="preparer@example.test", password_hash="x", role=UserRole.ACCOUNTANT)
            controller = User(username="close.controller", email="controller@example.test", password_hash="x", role=UserRole.ADMIN)
            admin = User(username="close.admin", email="admin@example.test", password_hash="x", role=UserRole.ADMIN)
            session.add_all([company, requester, controller, admin])
            session.flush()
            self.company_id = company.id
            self.requester_id = requester.id
            self.controller_id = controller.id
            self.admin_id = admin.id
            session.add(FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)))
            account = Account(company_id=company.id, code="3000", name="Retained earnings", account_type=AccountType.EQUITY)
            session.add(account)
            session.flush()
            self.closing_account_id = account.id
            self.authorization.grant_role(session, requester.id, company.id, "finance_manager")
            self.authorization.grant_role(session, controller.id, company.id, "financial_controller")
            self.authorization.grant_role(session, admin.id, company.id, "company_admin")
        self.service = PeriodCloseService(self.database, authorization=self.authorization, audit_logger=self.logger)

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def _principal(user_id: int, *, mfa_age_minutes: int = 0) -> AuthenticatedPrincipal:
        now = datetime.now(timezone.utc)
        return AuthenticatedPrincipal(
            user_id=user_id,
            session_id=f"session-{user_id}-{mfa_age_minutes}",
            provider_code="entra",
            issuer="https://issuer.example.test",
            subject=f"subject-{user_id}",
            authenticated_at=now,
            expires_at=now + timedelta(hours=1),
            mfa_at=now - timedelta(minutes=mfa_age_minutes),
            assurance_level="mfa",
        )

    def test_different_controller_approves_and_locks_fiscal_year(self):
        request_id = self.service.request_close(
            self.company_id, 2025, self.closing_account_id, self._principal(self.requester_id)
        )
        result = self.service.approve_and_execute(request_id, self._principal(self.controller_id))
        self.assertEqual(result.status, PeriodCloseRequestStatus.EXECUTED.value)
        with self.database.get_session() as session:
            fiscal_year = session.scalar(select(FiscalYear).where(FiscalYear.company_id == self.company_id, FiscalYear.year == 2025))
            request = session.get(PeriodCloseRequest, request_id)
            actions = set(session.scalars(select(AuditLog.action).where(AuditLog.category == "financial_close")))
            self.assertTrue(fiscal_year.is_closed)
            self.assertEqual(request.status, PeriodCloseRequestStatus.EXECUTED)
            self.assertEqual(request.approved_by_user_id, self.controller_id)
            self.assertEqual(actions, {"period_close.requested", "period_close.executed"})
            close_event = session.scalar(select(AuditLog).where(AuditLog.action == "period_close.executed"))
            self.assertEqual(close_event.request_id, request_id)
            self.assertEqual(close_event.target_id, request_id)
            self.assertTrue(self.logger.verify_chain(session).valid)

    def test_self_approval_is_blocked_and_audited(self):
        request_id = self.service.request_close(
            self.company_id, 2025, self.closing_account_id, self._principal(self.admin_id)
        )
        with self.assertRaises(SegregationOfDutiesViolation):
            self.service.approve_and_execute(request_id, self._principal(self.admin_id))
        with self.database.get_session() as session:
            request = session.get(PeriodCloseRequest, request_id)
            event = session.scalar(select(AuditLog).where(AuditLog.action == "period_close.sod_violation"))
            self.assertEqual(request.status, PeriodCloseRequestStatus.PENDING)
            self.assertEqual(event.outcome, "denied")
            self.assertTrue(self.logger.verify_chain(session).valid)

    def test_requester_cannot_reject_own_close_and_event_is_chained(self):
        request_id = self.service.request_close(
            self.company_id, 2025, self.closing_account_id, self._principal(self.admin_id)
        )
        with self.assertRaises(SegregationOfDutiesViolation):
            self.service.reject(request_id, "Requester cannot provide independent control.", self._principal(self.admin_id))
        with self.database.get_session() as session:
            request = session.get(PeriodCloseRequest, request_id)
            event = session.scalar(select(AuditLog).where(AuditLog.action == "period_close.sod_violation"))
            self.assertEqual(request.status, PeriodCloseRequestStatus.PENDING)
            self.assertEqual(event.outcome, "denied")
            self.assertEqual(event.target_id, request_id)
            self.assertTrue(self.logger.verify_chain(session).valid)

    def test_execution_failure_rolls_back_approval_close_and_success_audit(self):
        request_id = self.service.request_close(
            self.company_id, 2025, self.closing_account_id, self._principal(self.requester_id)
        )
        with patch("core.period_close.AccountingEngine.close_fiscal_year", side_effect=RuntimeError("simulated close failure")):
            with self.assertRaisesRegex(RuntimeError, "simulated close failure"):
                self.service.approve_and_execute(request_id, self._principal(self.controller_id))
        with self.database.get_session() as session:
            request = session.get(PeriodCloseRequest, request_id)
            fiscal_year = session.scalar(select(FiscalYear).where(FiscalYear.id == request.fiscal_year_id))
            executed_event = session.scalar(select(AuditLog).where(AuditLog.action == "period_close.executed"))
            self.assertEqual(request.status, PeriodCloseRequestStatus.PENDING)
            self.assertIsNone(request.approved_by_user_id)
            self.assertIsNone(request.executed_at)
            self.assertFalse(fiscal_year.is_closed)
            self.assertIsNone(executed_event)
            self.assertTrue(self.logger.verify_chain(session).valid)

    def test_duplicate_active_close_request_is_rejected(self):
        self.service.request_close(self.company_id, 2025, self.closing_account_id, self._principal(self.requester_id))
        with self.assertRaises(PeriodCloseError):
            self.service.request_close(self.company_id, 2025, self.closing_account_id, self._principal(self.requester_id))

    def test_stale_mfa_cannot_create_close_request(self):
        with self.assertRaises(AuthorizationDenied):
            self.service.request_close(
                self.company_id, 2025, self.closing_account_id, self._principal(self.requester_id, mfa_age_minutes=16)
            )
        with self.database.get_session() as session:
            event = session.scalar(select(AuditLog).where(AuditLog.action == "authorization.denied"))
            self.assertEqual(event.company_id, self.company_id)
            self.assertEqual(event.outcome, "denied")
            self.assertTrue(self.logger.verify_chain(session).valid)


if __name__ == "__main__":
    unittest.main()
