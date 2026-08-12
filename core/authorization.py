"""Central enterprise authorization service for FinAnalyzer.

Authorization is evaluated in the service layer, not inferred from UI visibility.
Every protected operation requires an authenticated, active user, an active company
membership, and an explicit permission granted through that membership's roles.
Unmatched requests are denied by default and recorded in the audit trail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import (
    AuditLog,
    CompanyMembership,
    MembershipRole,
    MembershipStatus,
    Permission,
    Role,
    RolePermission,
    User,
)


class AuthorizationDenied(PermissionError):
    """Raised when an actor lacks an explicit scoped permission."""


class AuthorizationConfigurationError(RuntimeError):
    """Raised when a requested permission has not been registered."""


@dataclass(frozen=True)
class AuthorizationContext:
    """Verified context supplied by the authentication/session layer."""

    actor_id: int
    company_id: int
    mfa_verified: bool = False
    reason: Optional[str] = None
    request_id: Optional[str] = None


PERMISSION_CATALOG: dict[str, dict[str, Any]] = {
    "company.read": {"description": "View company-scoped settings", "sensitive": False},
    "company.members.manage": {"description": "Manage company memberships", "sensitive": True},
    "identity.role.assign": {"description": "Assign company-scoped roles", "sensitive": True},
    "ledger.read": {"description": "Read ledger and financial statements", "sensitive": False},
    "ledger.draft.create": {"description": "Create accounting drafts", "sensitive": False},
    "ledger.entry.post": {"description": "Post accounting journal entries", "sensitive": True},
    "ledger.entry.void": {"description": "Void posted accounting journal entries", "sensitive": True},
    "account.manage": {"description": "Manage chart of accounts", "sensitive": True},
    "bank.link": {"description": "Initiate a bank connection", "sensitive": True},
    "bank.sync": {"description": "Synchronize a linked bank connection", "sensitive": False},
    "bank.unlink": {"description": "Revoke a linked bank connection", "sensitive": True},
    "report.generate": {"description": "Generate a company report", "sensitive": False},
    "report.schedule.manage": {"description": "Create or change report schedules", "sensitive": True},
    "report.deliver.external": {"description": "Send reports to external recipients", "sensitive": True},
    "audit.read": {"description": "Read audit events", "sensitive": True},
}

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "company_admin": set(PERMISSION_CATALOG),
    "finance_manager": {
        "company.read", "ledger.read", "ledger.draft.create", "ledger.entry.post",
        "ledger.entry.void", "account.manage", "bank.link", "bank.sync", "bank.unlink",
        "report.generate", "report.schedule.manage", "report.deliver.external", "audit.read",
    },
    "accountant": {"company.read", "ledger.read", "ledger.draft.create", "ledger.entry.post", "report.generate", "bank.sync"},
    "analyst": {"company.read", "ledger.read", "report.generate"},
    "auditor": {"company.read", "ledger.read", "audit.read"},
    "bank_operator": {"company.read", "ledger.read", "bank.link", "bank.sync"},
    "viewer": {"company.read", "ledger.read", "report.generate"},
}


class AuthorizationService:
    """Denies access unless a live company membership explicitly grants it."""

    def bootstrap_defaults(self, session: Session) -> None:
        """Create the canonical permission catalog and system roles idempotently."""
        permissions: dict[str, Permission] = {}
        for code, metadata in PERMISSION_CATALOG.items():
            permission = session.scalar(select(Permission).where(Permission.code == code))
            resource, action = code.split(".", 1)
            if permission is None:
                permission = Permission(
                    code=code,
                    resource=resource,
                    action=action,
                    description=metadata["description"],
                    is_sensitive=bool(metadata["sensitive"]),
                )
                session.add(permission)
                session.flush()
            permissions[code] = permission

        for role_code, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
            role = session.scalar(select(Role).where(Role.code == role_code))
            if role is None:
                role = Role(
                    code=role_code,
                    name=role_code.replace("_", " ").title(),
                    description=f"System role: {role_code}",
                    is_system=True,
                )
                session.add(role)
                session.flush()
            existing = set(session.scalars(
                select(Permission.code)
                .select_from(RolePermission)
                .join(Permission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            ))
            for permission_code in permission_codes - existing:
                session.add(RolePermission(role_id=role.id, permission_id=permissions[permission_code].id))

    def grant_role(self, session: Session, user_id: int, company_id: int, role_code: str) -> CompanyMembership:
        """Grant a role within exactly one company; caller authorization is external."""
        role = session.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            raise AuthorizationConfigurationError(f"Unknown role: {role_code}")
        membership = session.scalar(
            select(CompanyMembership).where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.company_id == company_id,
            )
        )
        if membership is None:
            membership = CompanyMembership(user_id=user_id, company_id=company_id, status=MembershipStatus.ACTIVE)
            session.add(membership)
            session.flush()
        elif membership.status != MembershipStatus.ACTIVE:
            membership.status = MembershipStatus.ACTIVE
            membership.revoked_at = None
        has_role = session.scalar(
            select(MembershipRole.id).where(
                MembershipRole.membership_id == membership.id,
                MembershipRole.role_id == role.id,
            )
        )
        if has_role is None:
            session.add(MembershipRole(membership_id=membership.id, role_id=role.id))
        return membership

    def revoke_membership(self, session: Session, user_id: int, company_id: int, actor_id: int) -> None:
        """Revoke access while retaining an auditable membership record."""
        membership = session.scalar(
            select(CompanyMembership).where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.company_id == company_id,
            )
        )
        if membership is None:
            return
        membership.status = MembershipStatus.REVOKED
        membership.revoked_at = datetime.now(timezone.utc)
        self._audit(session, actor_id, "authorization.membership_revoked", {
            "company_id": company_id,
            "subject_user_id": user_id,
        })

    def has_permission(self, session: Session, context: AuthorizationContext, permission_code: str) -> bool:
        """Return True only for an explicit permission in an active membership scope."""
        metadata = PERMISSION_CATALOG.get(permission_code)
        if metadata is None:
            return False
        user = session.get(User, context.actor_id)
        if user is None or not user.is_active:
            return False
        if metadata["sensitive"] and not context.mfa_verified:
            return False

        permission_id = session.scalar(select(Permission.id).where(Permission.code == permission_code))
        if permission_id is None:
            return False
        grant = session.scalar(
            select(RolePermission.id)
            .select_from(CompanyMembership)
            .join(MembershipRole, MembershipRole.membership_id == CompanyMembership.id)
            .join(Role, Role.id == MembershipRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .where(
                CompanyMembership.user_id == context.actor_id,
                CompanyMembership.company_id == context.company_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                RolePermission.permission_id == permission_id,
            )
        )
        return grant is not None

    def require(self, session: Session, context: AuthorizationContext, permission_code: str) -> None:
        """Enforce deny-by-default and record both sensitive grants and all denials."""
        allowed = self.has_permission(session, context, permission_code)
        metadata = PERMISSION_CATALOG.get(permission_code)
        details = {
            "company_id": context.company_id,
            "permission": permission_code,
            "request_id": context.request_id,
            "reason": context.reason,
        }
        if not allowed:
            self._audit(session, context.actor_id, "authorization.denied", details)
            raise AuthorizationDenied("Access denied: explicit scoped permission is required.")
        if metadata and metadata["sensitive"]:
            self._audit(session, context.actor_id, "authorization.granted_sensitive", details)

    def list_permissions(self, session: Session, user_id: int, company_id: int) -> set[str]:
        """Return effective permissions for UI rendering; service methods must still call require()."""
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            return set()
        result = session.scalars(
            select(Permission.code)
            .select_from(CompanyMembership)
            .join(MembershipRole, MembershipRole.membership_id == CompanyMembership.id)
            .join(Role, Role.id == MembershipRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.company_id == company_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
            )
        )
        return set(result)

    @staticmethod
    def _audit(session: Session, user_id: Optional[int], action: str, details: Mapping[str, Any]) -> None:
        session.add(AuditLog(
            user_id=user_id,
            action=action,
            details=json.dumps(details, sort_keys=True, default=str),
            timestamp=datetime.now(timezone.utc),
        ))
        session.flush()


__all__ = [
    "AuthorizationService", "AuthorizationContext", "AuthorizationDenied",
    "AuthorizationConfigurationError", "PERMISSION_CATALOG", "DEFAULT_ROLE_PERMISSIONS",
]
