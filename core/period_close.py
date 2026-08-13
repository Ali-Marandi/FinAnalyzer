"""Controlled fiscal-period close workflow with MFA, RBAC, and segregation of duties."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select

from core.accounting_engine import AccountingEngine
from core.audit import AuditLogger
from core.authorization import AuthorizationDenied, AuthorizationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal, IdentityValidationError
from core.models import Account, AccountType, FiscalYear, PeriodCloseRequest, PeriodCloseRequestStatus


class PeriodCloseError(RuntimeError):
    """Raised when a fiscal-period close cannot be completed safely."""


class SegregationOfDutiesViolation(PermissionError):
    """Raised when a requester attempts to approve their own close request."""


@dataclass(frozen=True)
class PeriodCloseResult:
    """Small immutable outcome returned after a close request is executed."""

    request_id: str
    fiscal_year_id: int
    fiscal_year: int
    status: str
    executed_at: datetime


class PeriodCloseService:
    """Enforces a two-person close of a company fiscal year.

    A preparer with ``ledger.period.close.request`` may create a request. A
    separate Financial Controller or Company Admin with
    ``ledger.period.close.approve`` and recent MFA must approve and execute it.
    The closing journal entry, fiscal lock, workflow update, and audit record
    are committed together by the database transaction.
    """

    MFA_MAX_AGE = timedelta(minutes=15)

    def __init__(
        self,
        database: DatabaseManager,
        authorization: Optional[AuthorizationService] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.database = database
        self.audit_logger = audit_logger or AuditLogger()
        self.authorization = authorization or AuthorizationService(audit_logger=self.audit_logger)

    def request_close(
        self,
        company_id: int,
        fiscal_year: int,
        closing_account_id: int,
        principal: AuthenticatedPrincipal,
    ) -> str:
        """Create a pending close request after scoped, recent-MFA authorization."""
        with self.database.get_session() as session:
            context = self._context(principal, company_id, "period_close_request")
            self._require(session, context, "ledger.period.close.request")
            year = self._fiscal_year(session, company_id, fiscal_year)
            if year.is_closed:
                raise PeriodCloseError(f"Fiscal year {fiscal_year} is already closed.")
            self._validate_closing_account(session, company_id, closing_account_id)
            existing = session.scalar(
                select(PeriodCloseRequest).where(
                    PeriodCloseRequest.company_id == company_id,
                    PeriodCloseRequest.fiscal_year_id == year.id,
                    PeriodCloseRequest.status.in_((PeriodCloseRequestStatus.PENDING, PeriodCloseRequestStatus.APPROVED)),
                )
            )
            if existing is not None:
                raise PeriodCloseError("An active close request already exists for this fiscal year.")
            request = PeriodCloseRequest(
                id=str(uuid4()),
                company_id=company_id,
                fiscal_year_id=year.id,
                closing_account_id=closing_account_id,
                requested_by_user_id=principal.user_id,
                status=PeriodCloseRequestStatus.PENDING,
            )
            session.add(request)
            self._audit(
                session, principal, "period_close.requested", company_id, request.id,
                outcome="success", severity="notice",
                details={"fiscal_year": fiscal_year, "closing_account_id": closing_account_id},
            )
            return request.id

    def approve_and_execute(self, request_id: str, principal: AuthenticatedPrincipal) -> PeriodCloseResult:
        """Approve and execute a pending request; the requester cannot self-approve."""
        with self.database.get_session() as session:
            request = self._request(session, request_id)
            context = self._context(principal, request.company_id, "period_close_approve")
            self._require(session, context, "ledger.period.close.approve")
            if request.status != PeriodCloseRequestStatus.PENDING:
                raise PeriodCloseError("Only a pending fiscal-period close request can be approved.")
            if request.requested_by_user_id == principal.user_id:
                self._audit(
                    session, principal, "period_close.sod_violation", request.company_id, request.id,
                    outcome="denied", severity="warning",
                    details={"fiscal_year_id": request.fiscal_year_id, "reason": "self_approval"},
                )
                session.commit()
                raise SegregationOfDutiesViolation("The requester cannot approve their own fiscal-period close.")
            year = session.get(FiscalYear, request.fiscal_year_id)
            if year is None or year.company_id != request.company_id:
                raise PeriodCloseError("The requested fiscal year no longer exists in this company scope.")
            if year.is_closed:
                raise PeriodCloseError("The fiscal year has already been closed.")
            self._validate_closing_account(session, request.company_id, request.closing_account_id)
            request.status = PeriodCloseRequestStatus.APPROVED
            request.approved_by_user_id = principal.user_id
            request.approved_at = datetime.now(timezone.utc)
            AccountingEngine(session, request.company_id).close_fiscal_year(
                year.year, request.closing_account_id, commit=False
            )
            executed_at = datetime.now(timezone.utc)
            request.status = PeriodCloseRequestStatus.EXECUTED
            request.executed_at = executed_at
            self._audit(
                session, principal, "period_close.executed", request.company_id, request.id,
                outcome="success", severity="notice",
                details={"fiscal_year": year.year, "closing_account_id": request.closing_account_id},
            )
            return PeriodCloseResult(
                request_id=request.id,
                fiscal_year_id=year.id,
                fiscal_year=year.year,
                status=request.status.value,
                executed_at=executed_at,
            )

    def reject(self, request_id: str, reason: str, principal: AuthenticatedPrincipal) -> None:
        """Reject a pending request with a bounded, auditable reason."""
        reason = (reason or "").strip()
        if not reason:
            raise PeriodCloseError("A rejection reason is required.")
        with self.database.get_session() as session:
            request = self._request(session, request_id)
            context = self._context(principal, request.company_id, "period_close_reject")
            self._require(session, context, "ledger.period.close.approve")
            if request.status != PeriodCloseRequestStatus.PENDING:
                raise PeriodCloseError("Only a pending fiscal-period close request can be rejected.")
            if request.requested_by_user_id == principal.user_id:
                self._audit(
                    session, principal, "period_close.sod_violation", request.company_id, request.id,
                    outcome="denied", severity="warning",
                    details={"fiscal_year_id": request.fiscal_year_id, "reason": "self_rejection"},
                )
                session.commit()
                raise SegregationOfDutiesViolation("The requester cannot reject their own fiscal-period close.")
            request.status = PeriodCloseRequestStatus.REJECTED
            request.approved_by_user_id = principal.user_id
            request.approved_at = datetime.now(timezone.utc)
            request.rejection_reason = reason[:500]
            self._audit(
                session, principal, "period_close.rejected", request.company_id, request.id,
                outcome="success", severity="notice",
                details={"fiscal_year_id": request.fiscal_year_id, "reason_present": True},
            )

    def _require(self, session, context, permission: str) -> None:
        """Persist an authorization-denial audit event before propagating the denial."""
        try:
            self.authorization.require(session, context, permission)
        except AuthorizationDenied:
            session.commit()
            raise

    @staticmethod
    def _fiscal_year(session, company_id: int, fiscal_year: int) -> FiscalYear:
        year = session.scalar(
            select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.year == fiscal_year)
        )
        if year is None:
            raise PeriodCloseError(f"Fiscal year {fiscal_year} does not exist for this company.")
        return year

    @staticmethod
    def _request(session, request_id: str) -> PeriodCloseRequest:
        request = session.get(PeriodCloseRequest, request_id)
        if request is None:
            raise PeriodCloseError("The fiscal-period close request does not exist.")
        return request

    @staticmethod
    def _validate_closing_account(session, company_id: int, closing_account_id: int) -> None:
        account = session.get(Account, closing_account_id)
        if account is None or account.company_id != company_id:
            raise PeriodCloseError("The retained-earnings account is outside the selected company scope.")
        if not account.is_active or account.account_type != AccountType.EQUITY:
            raise PeriodCloseError("The close account must be an active equity account.")

    @classmethod
    def _context(cls, principal: AuthenticatedPrincipal, company_id: int, reason: str):
        if not isinstance(principal, AuthenticatedPrincipal):
            raise IdentityValidationError("A validated Enterprise session principal is required for fiscal close operations.")
        return principal.authorization_context(company_id, reason, mfa_max_age=cls.MFA_MAX_AGE)

    def _audit(
        self,
        session,
        principal: AuthenticatedPrincipal,
        action: str,
        company_id: int,
        request_id: str,
        *,
        outcome: str,
        severity: str,
        details: dict,
    ) -> None:
        self.audit_logger.record(
            session,
            action=action,
            category="financial_close",
            outcome=outcome,
            severity=severity,
            actor_id=principal.user_id,
            company_id=company_id,
            session_id=principal.session_id,
            request_id=request_id,
            source="period_close_service",
            target_type="period_close_request",
            target_id=request_id,
            details=details,
        )


__all__ = [
    "PeriodCloseService", "PeriodCloseError", "SegregationOfDutiesViolation", "PeriodCloseResult",
]
