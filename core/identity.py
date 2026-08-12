"""Enterprise OIDC/PKCE identity services for FinAnalyzer v2.3.0.

This module deliberately keeps Microsoft Entra authentication separate from local
RBAC. Entra/OIDC establishes a verified person and MFA evidence; the existing
AuthorizationService remains the policy enforcement point for company-scoped
permissions.

Security properties:
* Desktop clients are public clients: no client secret is embedded or read.
* MSAL uses the authorization-code flow with PKCE for interactive desktop sign-in.
* ID tokens are verified against the provider JWKS and required issuer/audience.
* A user is identified by the immutable (issuer, subject) pair, never email alone.
* MFA is derived from verified claims and a short-lived local session, not from UI input.
* The optional persistent MSAL cache is DPAPI protected on Windows only.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.authorization import AuthorizationContext
from core.database import DatabaseManager
from core.models import AuditLog, AuthSession, ExternalIdentity, IdentityProvider, User
from core.security import KeyProtectionError, WindowsDpapiProtector


class IdentityConfigurationError(RuntimeError):
    """Raised when required Entra/OIDC desktop configuration is absent or unsafe."""


class IdentityValidationError(PermissionError):
    """Raised when an identity token or authentication result cannot be trusted."""


class IdentityProvisioningDenied(PermissionError):
    """Raised when a valid external identity has not been approved in FinAnalyzer."""


class StepUpRequired(PermissionError):
    """Raised when a sensitive action needs a newer or stronger MFA event."""


@dataclass(frozen=True)
class EntraOidcSettings:
    """Non-secret configuration for a Microsoft Entra public desktop client."""

    tenant_id: str
    client_id: str
    redirect_uri: str = "http://localhost"
    provider_code: str = "entra"
    required_acr: Optional[str] = None
    session_minutes: int = 60
    mfa_max_age_minutes: int = 15

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def jwks_uri(self) -> str:
        return f"{self.authority}/discovery/v2.0/keys"

    @classmethod
    def from_environment(cls) -> "EntraOidcSettings":
        tenant_id = os.getenv("FINANALYZER_ENTRA_TENANT_ID", "").strip()
        client_id = os.getenv("FINANALYZER_ENTRA_CLIENT_ID", "").strip()
        if not tenant_id or not client_id:
            raise IdentityConfigurationError(
                "Set FINANALYZER_ENTRA_TENANT_ID and FINANALYZER_ENTRA_CLIENT_ID before enabling Enterprise SSO."
            )
        redirect_uri = os.getenv("FINANALYZER_ENTRA_REDIRECT_URI", "http://localhost").strip()
        if redirect_uri != "http://localhost" and not redirect_uri.startswith("http://127.0.0.1"):
            raise IdentityConfigurationError(
                "Desktop SSO redirect URI must be the registered http://localhost or 127.0.0.1 loopback URI."
            )
        return cls(
            tenant_id=tenant_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            provider_code=os.getenv("FINANALYZER_ENTRA_PROVIDER_CODE", "entra").strip() or "entra",
            required_acr=os.getenv("FINANALYZER_ENTRA_REQUIRED_ACR", "").strip() or None,
            session_minutes=int(os.getenv("FINANALYZER_SESSION_MINUTES", "60")),
            mfa_max_age_minutes=int(os.getenv("FINANALYZER_MFA_MAX_AGE_MINUTES", "15")),
        )


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Read-only local representation of a validated federated session."""

    user_id: int
    session_id: str
    provider_code: str
    issuer: str
    subject: str
    authenticated_at: datetime
    expires_at: datetime
    mfa_at: Optional[datetime] = None
    assurance_level: Optional[str] = None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.expires_at <= now

    def has_recent_mfa(self, max_age: timedelta, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.mfa_at is not None and self.mfa_at <= now and (now - self.mfa_at) <= max_age

    def authorization_context(
        self,
        company_id: int,
        reason: str,
        *,
        mfa_max_age: timedelta,
        request_id: Optional[str] = None,
    ) -> AuthorizationContext:
        if self.is_expired():
            raise IdentityValidationError("The authenticated session has expired. Sign in again before continuing.")
        return AuthorizationContext(
            actor_id=self.user_id,
            company_id=company_id,
            mfa_verified=self.has_recent_mfa(mfa_max_age),
            reason=reason,
            request_id=request_id or self.session_id,
            session_id=self.session_id,
            mfa_at=self.mfa_at,
            auth_source=self.provider_code,
        )


class DpapiMsalCache:
    """DPAPI-protected persistence for MSAL cache on Windows; memory-only elsewhere."""

    def __init__(self, cache_path: str = "data/.finanalyzer.msalcache.dpapi", *, dpapi: Optional[WindowsDpapiProtector] = None):
        self.path = Path(cache_path)
        self.dpapi = dpapi or WindowsDpapiProtector()

    def create_cache(self):
        try:
            import msal
        except ImportError as exc:
            raise IdentityConfigurationError("Install the 'msal' package to enable Enterprise SSO.") from exc
        cache = msal.SerializableTokenCache()
        if platform.system() != "Windows":
            # Do not persist bearer/refresh tokens unprotected on non-Windows developer hosts.
            return cache
        if self.path.exists():
            try:
                cache.deserialize(self.dpapi.unprotect(self.path.read_bytes()).decode("utf-8"))
            except Exception as exc:
                raise KeyProtectionError("The protected MSAL cache could not be recovered for this Windows user.") from exc

        def persist(updated_cache):
            if not updated_cache.has_state_changed:
                return
            payload = updated_cache.serialize().encode("utf-8")
            protected = self.dpapi.protect(payload)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_bytes(protected)
            os.replace(temporary, self.path)

        cache.add_after_change = persist
        return cache

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class IdTokenValidator:
    """Verifies Microsoft Entra ID-token signature and critical OIDC claims."""

    def __init__(self, settings: EntraOidcSettings):
        self.settings = settings

    def validate(self, raw_id_token: str) -> Mapping[str, Any]:
        if not raw_id_token:
            raise IdentityValidationError("The identity provider did not return an ID token.")
        try:
            import jwt
            signing_key = jwt.PyJWKClient(self.settings.jwks_uri).get_signing_key_from_jwt(raw_id_token).key
            claims = jwt.decode(
                raw_id_token,
                signing_key,
                algorithms=["RS256"],
                audience=self.settings.client_id,
                issuer=self.settings.issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except Exception as exc:
            raise IdentityValidationError("The Entra ID token is invalid, expired, or issued for another application.") from exc
        if claims.get("tid") != self.settings.tenant_id:
            raise IdentityValidationError("The sign-in tenant does not match the configured Enterprise tenant.")
        return claims


class IdentityService:
    """Creates validated local sessions from Entra/OIDC authentication results."""

    MFA_AMR_VALUES = {"mfa", "fido", "whfb"}

    def __init__(
        self,
        database: DatabaseManager,
        settings: Optional[EntraOidcSettings] = None,
        *,
        cache_store: Optional[DpapiMsalCache] = None,
        token_validator: Optional[IdTokenValidator] = None,
    ) -> None:
        self.database = database
        self.settings = settings or EntraOidcSettings.from_environment()
        self.cache_store = cache_store or DpapiMsalCache()
        self.validator = token_validator or IdTokenValidator(self.settings)

    @property
    def mfa_max_age(self) -> timedelta:
        return timedelta(minutes=self.settings.mfa_max_age_minutes)

    def _msal_app(self):
        try:
            import msal
        except ImportError as exc:
            raise IdentityConfigurationError("Install the 'msal' package to enable Enterprise SSO.") from exc
        return msal.PublicClientApplication(
            client_id=self.settings.client_id,
            authority=self.settings.authority,
            token_cache=self.cache_store.create_cache(),
        )

    def sign_in_interactive(self, *, force_step_up: bool = False) -> AuthenticatedPrincipal:
        """Open the system-browser MSAL flow. PKCE is handled by MSAL for public clients."""
        scopes = ["openid", "profile", "email"]
        extra: dict[str, Any] = {"redirect_uri": self.settings.redirect_uri, "prompt": "select_account"}
        if force_step_up:
            extra["prompt"] = "login"
            if self.settings.required_acr:
                extra["claims_challenge"] = json.dumps({
                    "id_token": {"acrs": {"essential": True, "value": self.settings.required_acr}}
                })
        result = self._msal_app().acquire_token_interactive(scopes=scopes, **extra)
        if "error" in result:
            description = str(result.get("error_description", "Authentication was not completed."))
            raise IdentityValidationError(f"Enterprise sign-in was not completed: {description}")
        raw_id_token = result.get("id_token")
        claims = self.validator.validate(raw_id_token)
        return self._create_session_from_claims(claims)

    def sign_in_from_token_for_test(self, raw_id_token: str) -> AuthenticatedPrincipal:
        """Test seam: production callers must use sign_in_interactive(), never submit raw tokens from UI."""
        return self._create_session_from_claims(self.validator.validate(raw_id_token))

    def _create_session_from_claims(self, claims: Mapping[str, Any]) -> AuthenticatedPrincipal:
        subject = str(claims["sub"])
        now = datetime.now(timezone.utc)
        exp = self._as_utc_timestamp(claims.get("exp"))
        auth_time = self._as_utc_timestamp(claims.get("auth_time")) or now
        if exp is None or exp <= now:
            raise IdentityValidationError("The identity token has expired.")
        amr = {str(value).lower() for value in (claims.get("amr") or [])}
        acrs = {str(value) for value in (claims.get("acrs") or [])}
        verified_mfa = bool(amr & self.MFA_AMR_VALUES) or (
            self.settings.required_acr is not None and self.settings.required_acr in acrs
        )
        mfa_at = auth_time if verified_mfa else None
        preferred_username = str(claims.get("preferred_username") or claims.get("email") or "")
        object_id = str(claims.get("oid") or "") or None

        with self.database.get_session() as session:
            provider = self._ensure_provider(session)
            external = session.scalar(
                select(ExternalIdentity).where(
                    ExternalIdentity.provider_id == provider.id,
                    ExternalIdentity.subject == subject,
                )
            )
            if external is None:
                self._audit(session, None, "identity.provisioning_denied", {"provider": provider.code, "subject": subject})
                raise IdentityProvisioningDenied(
                    "This organization account is not provisioned in FinAnalyzer. An administrator must bind the external identity before sign-in."
                )
            user = session.get(User, external.user_id)
            if user is None or not user.is_active:
                self._audit(session, external.user_id, "identity.sign_in_denied", {"reason": "local_user_inactive"})
                raise IdentityValidationError("The corresponding FinAnalyzer user is not active.")
            external.object_id = object_id
            external.preferred_username = preferred_username or external.preferred_username
            external.last_seen_at = now
            session_id = uuid4().hex
            local_expiry = min(exp, now + timedelta(minutes=self.settings.session_minutes))
            auth_session = AuthSession(
                id=session_id,
                user_id=user.id,
                provider_id=provider.id,
                issued_at=now,
                expires_at=local_expiry,
                auth_time=auth_time,
                mfa_at=mfa_at,
                assurance_level=self.settings.required_acr if self.settings.required_acr in acrs else None,
            )
            session.add(auth_session)
            self._audit(session, user.id, "identity.sign_in_succeeded", {
                "provider": provider.code,
                "session_id": session_id,
                "mfa": verified_mfa,
                "subject": subject,
            })
            return AuthenticatedPrincipal(
                user_id=user.id,
                session_id=session_id,
                provider_code=provider.code,
                issuer=self.settings.issuer,
                subject=subject,
                authenticated_at=auth_time,
                expires_at=local_expiry,
                mfa_at=mfa_at,
                assurance_level=auth_session.assurance_level,
            )

    def get_active_principal(self, session_id: str) -> AuthenticatedPrincipal:
        now = datetime.now(timezone.utc)
        with self.database.get_session() as session:
            record = session.get(AuthSession, session_id)
            if record is None or record.revoked_at is not None or record.expires_at <= now or not record.user.is_active:
                raise IdentityValidationError("The local Enterprise session is no longer valid.")
            return AuthenticatedPrincipal(
                user_id=record.user_id,
                session_id=record.id,
                provider_code=record.provider.code,
                issuer=record.provider.issuer,
                subject=next((entry.subject for entry in record.user.external_identities if entry.provider_id == record.provider_id), ""),
                authenticated_at=record.auth_time,
                expires_at=record.expires_at,
                mfa_at=record.mfa_at,
                assurance_level=record.assurance_level,
            )

    def sign_out(self, principal: AuthenticatedPrincipal) -> None:
        with self.database.get_session() as session:
            record = session.get(AuthSession, principal.session_id)
            if record and record.revoked_at is None:
                record.revoked_at = datetime.now(timezone.utc)
                self._audit(session, principal.user_id, "identity.sign_out", {"session_id": principal.session_id})
        self.cache_store.clear()

    def bind_external_identity(
        self,
        *,
        user_id: int,
        subject: str,
        object_id: Optional[str] = None,
        preferred_username: Optional[str] = None,
    ) -> None:
        """Administrative provisioning helper; call only from an already-authorized admin workflow."""
        if not subject:
            raise ValueError("An immutable external subject is required.")
        with self.database.get_session() as session:
            provider = self._ensure_provider(session)
            user = session.get(User, user_id)
            if user is None:
                raise IdentityProvisioningDenied("Cannot provision an external identity for an unknown local user.")
            existing = session.scalar(select(ExternalIdentity).where(
                ExternalIdentity.provider_id == provider.id,
                ExternalIdentity.subject == subject,
            ))
            if existing and existing.user_id != user_id:
                raise IdentityProvisioningDenied("This external identity is already bound to a different local user.")
            if existing is None:
                session.add(ExternalIdentity(
                    user_id=user_id,
                    provider_id=provider.id,
                    subject=subject,
                    object_id=object_id,
                    preferred_username=preferred_username,
                ))
            self._audit(session, user_id, "identity.external_identity_bound", {"provider": provider.code, "subject": subject})

    def _ensure_provider(self, session: Session) -> IdentityProvider:
        provider = session.scalar(select(IdentityProvider).where(IdentityProvider.code == self.settings.provider_code))
        if provider is None:
            provider = IdentityProvider(
                code=self.settings.provider_code,
                issuer=self.settings.issuer,
                tenant_id=self.settings.tenant_id,
                client_id=self.settings.client_id,
                enabled=True,
            )
            session.add(provider)
            session.flush()
        if not provider.enabled or provider.issuer != self.settings.issuer or provider.client_id != self.settings.client_id:
            raise IdentityConfigurationError("The configured Entra provider does not match the approved local identity-provider record.")
        return provider

    @staticmethod
    def _as_utc_timestamp(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            raise IdentityValidationError("A required identity-token timestamp is invalid.")

    @staticmethod
    def _audit(session: Session, user_id: Optional[int], action: str, details: Mapping[str, Any]) -> None:
        session.add(AuditLog(
            user_id=user_id,
            action=action,
            details=json.dumps(dict(details), sort_keys=True),
            timestamp=datetime.now(timezone.utc),
        ))
        session.flush()


__all__ = [
    "AuthenticatedPrincipal", "DpapiMsalCache", "EntraOidcSettings", "IdentityConfigurationError",
    "IdentityProvisioningDenied", "IdentityService", "IdentityValidationError", "IdTokenValidator", "StepUpRequired",
]
