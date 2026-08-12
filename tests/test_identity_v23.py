"""Offline security tests for the v2.3 OIDC/MFA session boundary.

No Entra tenant, browser, Plaid API, or real token is contacted. The validator is
replaced with a deterministic test double so the tests verify local trust boundaries.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.authorization import AuthorizationService
from core.automated_reporting import AutomatedReportService
from core.database import DatabaseManager
from core.identity import (
    EntraOidcSettings,
    IdentityProvisioningDenied,
    IdentityService,
    IdentityValidationError,
)
from core.models import Company, User, UserRole
from core.plaid_connector import PlaidConnector


class FixedValidator:
    def __init__(self, claims):
        self.claims = claims

    def validate(self, _raw_token):
        return self.claims


class IdentityV23Tests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = DatabaseManager(str(Path(self.tempdir.name) / "identity.db"))
        self.database.init_database()
        self.now = datetime.now(timezone.utc)
        self.settings = EntraOidcSettings(
            tenant_id="tenant-test",
            client_id="client-test",
            session_minutes=60,
            mfa_max_age_minutes=15,
        )
        with self.database.get_session() as session:
            self.user = User(
                username="entra.finance.manager",
                email="finance.manager@example.test",
                password_hash="federated-no-local-password",
                role=UserRole.VIEWER,
                is_active=True,
            )
            self.company = Company(name="OIDC Test Company", legal_name="OIDC Test Company", currency_code="USD")
            session.add_all([self.user, self.company])
            session.flush()
            self.user_id, self.company_id = self.user.id, self.company.id
            AuthorizationService().grant_role(session, self.user_id, self.company_id, "finance_manager")

    def tearDown(self):
        self.tempdir.cleanup()

    def _claims(self, **overrides):
        claims = {
            "sub": "subject-finance-manager",
            "oid": "object-finance-manager",
            "tid": "tenant-test",
            "preferred_username": "finance.manager@example.test",
            "iat": int(self.now.timestamp()),
            "auth_time": int(self.now.timestamp()),
            "exp": int((self.now + timedelta(minutes=30)).timestamp()),
            "amr": ["pwd", "mfa"],
        }
        claims.update(overrides)
        return claims

    def _identity(self, claims):
        return IdentityService(self.database, self.settings, token_validator=FixedValidator(claims))

    def test_provisioned_mfa_principal_can_form_sensitive_context(self):
        identity = self._identity(self._claims())
        identity.bind_external_identity(user_id=self.user_id, subject="subject-finance-manager", object_id="object-finance-manager")
        principal = identity.sign_in_from_token_for_test("unused")
        self.assertTrue(principal.has_recent_mfa(timedelta(minutes=15)))
        context = principal.authorization_context(
            self.company_id,
            "test_sensitive_action",
            mfa_max_age=timedelta(minutes=15),
        )
        self.assertTrue(context.mfa_verified)
        self.assertEqual(context.actor_id, self.user_id)
        self.assertEqual(context.auth_source, "entra")
        with self.database.get_session() as session:
            AuthorizationService().require(session, context, "bank.link")

    def test_unprovisioned_identity_is_denied_without_role_fallback(self):
        identity = self._identity(self._claims(sub="unapproved-subject"))
        with self.assertRaises(IdentityProvisioningDenied):
            identity.sign_in_from_token_for_test("unused")

    def test_expired_identity_token_is_rejected_before_session_creation(self):
        identity = self._identity(self._claims(exp=int((self.now - timedelta(seconds=1)).timestamp())))
        identity.bind_external_identity(user_id=self.user_id, subject="subject-finance-manager")
        with self.assertRaises(IdentityValidationError):
            identity.sign_in_from_token_for_test("unused")

    def test_stale_mfa_cannot_authorize_a_sensitive_bank_operation(self):
        identity = self._identity(self._claims(auth_time=int((self.now - timedelta(hours=1)).timestamp())))
        identity.bind_external_identity(user_id=self.user_id, subject="subject-finance-manager")
        principal = identity.sign_in_from_token_for_test("unused")
        context = principal.authorization_context(
            self.company_id,
            "stale_mfa_attempt",
            mfa_max_age=timedelta(minutes=15),
        )
        self.assertFalse(context.mfa_verified)
        with self.database.get_session() as session:
            with self.assertRaises(PermissionError):
                AuthorizationService().require(session, context, "bank.link")

    def test_sign_out_revokes_the_local_enterprise_session(self):
        identity = self._identity(self._claims())
        identity.bind_external_identity(user_id=self.user_id, subject="subject-finance-manager")
        principal = identity.sign_in_from_token_for_test("unused")
        identity.sign_out(principal)
        with self.assertRaises(IdentityValidationError):
            identity.get_active_principal(principal.session_id)

    def test_sensitive_services_reject_raw_actor_or_mfa_flag(self):
        with self.assertRaises(IdentityValidationError):
            PlaidConnector._context(None, self.company_id, "raw_actor_attempt")
        with self.assertRaises(IdentityValidationError):
            AutomatedReportService._context(None, self.company_id, "raw_actor_attempt")


if __name__ == "__main__":
    unittest.main()
