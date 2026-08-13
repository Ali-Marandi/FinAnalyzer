"""Controlled fiscal-period close workflow with MFA, RBAC, and segregation of duties."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select

from core.accounting_engine import AccountingEngine
from core.audit import AuditLogger
from core.authorization import AuthorizationDenied, AuthorizationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal, IdentityValidationError
from core.models import (
    Account,
    AccountType,
    BankReconciliationStatus,
    FiscalYear,
    JournalEntry,
    PeriodCloseRequest,
    PeriodCloseRequestStatus,
    PlaidItem,
    PlaidTransactionMapping,
    Transaction,
)


class PeriodCloseError(RuntimeError):
    """Raised when a fiscal-period close cannot be completed safely."""


class SegregationOfDutiesViolation(PermissionError):
    """Raised when a requester attempts to approve their own close request."""


@dataclass(frozen=True)
class CloseReadinessFinding:
    """One explainable blocker or warning discovered before a fiscal-period close."""

    code: str
    severity: str
    message: str
    reference: Optional[str] = None

    @property
    def is_blocker(self) -> bool:
        return self.severity == "blocker"


@dataclass(frozen=True)
class CloseReadinessReport:
    """Deterministic readiness result used before requesting or executing a close."""

    company_id: int
    fiscal_year: int
    ready: bool
    findings: tuple[CloseReadinessFinding, ...]

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings if finding.is_blocker)

    @property
    def warning_codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings if not finding.is_blocker)


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

    def assess_readiness(
        self,
        company_id: int,
        fiscal_year: int,
        closing_account_id: int,
        principal: AuthenticatedPrincipal,
    ) -> CloseReadinessReport:
        """Return auditable, explainable blockers before a user requests a close."""
        with self.database.get_session() as session:
            context = self._context(principal, company_id, "period_close_readiness")
            self._require(session, context, "ledger.period.close.request")
            report = self._evaluate_readiness(session, company_id, fiscal_year, closing_account_id)
            self._record_readiness(session, principal, report, phase="assessment")
            return report

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
            report = self._evaluate_readiness(session, company_id, fiscal_year, closing_account_id)
            self._record_readiness(session, principal, report, phase="request")
            if not report.ready:
                session.commit()
                raise PeriodCloseError(self._readiness_error(report))
            year = self._fiscal_year(session, company_id, fiscal_year)
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
            report = self._evaluate_readiness(
                session, request.company_id, year.year, request.closing_account_id, exclude_request_id=request.id
            )
            self._record_readiness(session, principal, report, phase="approval", request_id=request.id)
            if not report.ready:
                session.commit()
                raise PeriodCloseError(self._readiness_error(report))
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

    def _evaluate_readiness(
        self,
        session,
        company_id: int,
        fiscal_year: int,
        closing_account_id: int,
        *,
        exclude_request_id: Optional[str] = None,
    ) -> CloseReadinessReport:
        """Evaluate close blockers without mutating accounting or bank records."""
        findings: list[CloseReadinessFinding] = []
        year = session.scalar(
            select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.year == fiscal_year)
        )
        if year is None:
            findings.append(CloseReadinessFinding(
                "fiscal_year_missing", "blocker", "The selected fiscal year does not exist in this company scope."
            ))
            return CloseReadinessReport(company_id, fiscal_year, False, tuple(findings))
        if year.is_closed:
            findings.append(CloseReadinessFinding(
                "fiscal_year_already_closed", "blocker", "The selected fiscal year is already locked.", str(year.id)
            ))

        account = session.get(Account, closing_account_id)
        if account is None or account.company_id != company_id:
            findings.append(CloseReadinessFinding(
                "closing_account_out_of_scope", "blocker", "The retained-earnings account is outside the selected company scope."
            ))
        elif not account.is_active or account.account_type != AccountType.EQUITY:
            findings.append(CloseReadinessFinding(
                "closing_account_ineligible", "blocker", "The close account must be an active equity account.", str(account.id)
            ))

        active_requests = list(session.scalars(
            select(PeriodCloseRequest).where(
                PeriodCloseRequest.company_id == company_id,
                PeriodCloseRequest.fiscal_year_id == year.id,
                PeriodCloseRequest.status.in_((PeriodCloseRequestStatus.PENDING, PeriodCloseRequestStatus.APPROVED)),
            )
        ))
        if any(record.id != exclude_request_id for record in active_requests):
            findings.append(CloseReadinessFinding(
                "active_close_request", "blocker", "An active fiscal-period close request already exists.", str(year.id)
            ))

        totals = list(session.execute(
            select(
                JournalEntry.id,
                func.coalesce(func.sum(Transaction.debit), 0).label("debit_total"),
                func.coalesce(func.sum(Transaction.credit), 0).label("credit_total"),
            )
            .outerjoin(Transaction, Transaction.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.date >= year.start_date,
                JournalEntry.date <= year.end_date,
            )
            .group_by(JournalEntry.id)
            .order_by(JournalEntry.id)
        ))
        for entry_id, debit_total, credit_total in totals:
            if abs(Decimal(str(debit_total)) - Decimal(str(credit_total))) > Decimal("0.0001"):
                findings.append(CloseReadinessFinding(
                    "unbalanced_journal_entry", "blocker", "A journal entry in the close period is not balanced.", str(entry_id)
                ))

        pending_bank_ids = list(session.scalars(
            select(PlaidTransactionMapping.provider_transaction_id)
            .join(PlaidItem, PlaidTransactionMapping.plaid_item_id == PlaidItem.id)
            .where(PlaidItem.company_id == company_id, PlaidTransactionMapping.pending.is_(True))
            .order_by(PlaidTransactionMapping.id)
            .limit(5)
        ))
        if pending_bank_ids:
            findings.append(CloseReadinessFinding(
                "pending_bank_transactions", "blocker",
                "Pending bank transactions must be resolved before closing the fiscal period.",
                ",".join(pending_bank_ids),
            ))

        unresolved_bank_ids = list(session.scalars(
            select(PlaidTransactionMapping.provider_transaction_id)
            .join(PlaidItem, PlaidTransactionMapping.plaid_item_id == PlaidItem.id)
            .where(
                PlaidItem.company_id == company_id,
                PlaidTransactionMapping.reconciliation_status.in_(
                    (BankReconciliationStatus.NEEDS_REVIEW, BankReconciliationStatus.EXCEPTION)
                ),
            )
            .order_by(PlaidTransactionMapping.id)
            .limit(5)
        ))
        if unresolved_bank_ids:
            findings.append(CloseReadinessFinding(
                "unreconciled_bank_transactions", "blocker",
                "Bank-feed transactions that need review or have an open exception must be reconciled before closing the fiscal period.",
                ",".join(unresolved_bank_ids),
            ))

        verification = self.audit_logger.verify_chain(session)
        if not verification.valid:
            findings.append(CloseReadinessFinding(
                "audit_chain_invalid", "blocker", "The security audit chain failed verification; close is blocked.",
                str(verification.first_invalid_sequence or "checkpoint"),
            ))

        return CloseReadinessReport(
            company_id=company_id,
            fiscal_year=fiscal_year,
            ready=not any(finding.is_blocker for finding in findings),
            findings=tuple(findings),
        )

    @staticmethod
    def _readiness_error(report: CloseReadinessReport) -> str:
        codes = ", ".join(report.blocker_codes) or "unknown_readiness_failure"
        return f"Fiscal-period close is not ready: {codes}. Resolve the readiness blockers and retry."

    def _record_readiness(
        self,
        session,
        principal: AuthenticatedPrincipal,
        report: CloseReadinessReport,
        *,
        phase: str,
        request_id: Optional[str] = None,
    ) -> None:
        reference = request_id or f"readiness:{report.company_id}:{report.fiscal_year}"
        self._audit(
            session,
            principal,
            "period_close.readiness_assessed",
            report.company_id,
            reference,
            outcome="success" if report.ready else "denied",
            severity="notice" if report.ready else "warning",
            details={
                "phase": phase,
                "fiscal_year": report.fiscal_year,
                "ready": report.ready,
                "blocker_codes": list(report.blocker_codes),
                "warning_codes": list(report.warning_codes),
            },
        )

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
    "CloseReadinessFinding", "CloseReadinessReport", "PeriodCloseService", "PeriodCloseError",
    "SegregationOfDutiesViolation", "PeriodCloseResult",
]
