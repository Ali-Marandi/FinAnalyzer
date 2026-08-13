"""Controlled reconciliation of imported bank-feed journal entries.

This service deliberately changes only the contra line of a balanced entry. It never
creates a new entry, it refuses to mutate a locked fiscal period, and it records each
review decision in the structured HMAC audit chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from core.accounting_engine import AccountingEngine
from core.audit import AuditLogger
from core.authorization import AuthorizationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal, IdentityValidationError
from core.models import (
    Account,
    BankReconciliationStatus,
    JournalEntry,
    PlaidAccount,
    PlaidItem,
    PlaidTransactionMapping,
    Transaction,
    TransactionStatus,
)


class BankReconciliationError(RuntimeError):
    """Raised when a bank-feed item cannot safely enter the requested state."""


@dataclass(frozen=True)
class ReconciliationWorkItem:
    provider_transaction_id: str
    provider_account_id: Optional[str]
    journal_entry_id: Optional[int]
    entry_date: Optional[str]
    description: str
    amount: str
    pending: bool
    status: str
    note: Optional[str]
    reconciled_by_user_id: Optional[int]
    reconciled_at: Optional[str]


@dataclass(frozen=True)
class ReconciliationSummary:
    needs_review: int
    exceptions: int
    matched: int
    pending: int


class BankReconciliationService:
    """Company-scoped review workflow for Plaid-backed double-entry postings."""

    def __init__(
        self,
        database: DatabaseManager,
        authorization: Optional[AuthorizationService] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.database = database
        self.audit_logger = audit_logger or AuditLogger()
        self.authorization = authorization or AuthorizationService(audit_logger=self.audit_logger)

    def list_work_items(
        self,
        company_id: int,
        principal: AuthenticatedPrincipal,
        *,
        include_resolved: bool = False,
    ) -> list[ReconciliationWorkItem]:
        """Return a company-scoped queue without exposing raw provider payloads."""
        with self.database.get_session() as session:
            self.authorization.require(
                session, self._context(principal, company_id, "bank_reconciliation_list"), "ledger.read"
            )
            statuses = (
                tuple(BankReconciliationStatus)
                if include_resolved
                else (BankReconciliationStatus.NEEDS_REVIEW, BankReconciliationStatus.EXCEPTION)
            )
            mappings = list(session.scalars(
                select(PlaidTransactionMapping)
                .join(PlaidItem, PlaidTransactionMapping.plaid_item_id == PlaidItem.id)
                .where(
                    PlaidItem.company_id == company_id,
                    PlaidTransactionMapping.reconciliation_status.in_(statuses),
                )
                .order_by(PlaidTransactionMapping.imported_at, PlaidTransactionMapping.id)
            ))
            return [self._work_item(session, mapping) for mapping in mappings]

    def summary(self, company_id: int, principal: AuthenticatedPrincipal) -> ReconciliationSummary:
        """Report open workload counts for the current company scope."""
        items = self.list_work_items(company_id, principal, include_resolved=True)
        return ReconciliationSummary(
            needs_review=sum(item.status == BankReconciliationStatus.NEEDS_REVIEW.value for item in items),
            exceptions=sum(item.status == BankReconciliationStatus.EXCEPTION.value for item in items),
            matched=sum(item.status == BankReconciliationStatus.MATCHED.value for item in items),
            pending=sum(item.pending for item in items),
        )

    def mark_exception(
        self,
        company_id: int,
        provider_transaction_id: str,
        reason: str,
        principal: AuthenticatedPrincipal,
    ) -> None:
        """Flag a work item without modifying its accounting entry."""
        reason = self._validated_note(reason)
        with self.database.get_session() as session:
            self.authorization.require(
                session,
                self._context(principal, company_id, "bank_reconciliation_exception"),
                "bank.reconcile.match",
            )
            mapping = self._mapping_for_company(session, company_id, provider_transaction_id)
            self._assert_open_and_mutable(session, company_id, mapping)
            if mapping.reconciliation_status == BankReconciliationStatus.MATCHED:
                raise BankReconciliationError("A matched transaction cannot be re-opened as an exception without an approved adjustment workflow.")
            mapping.reconciliation_status = BankReconciliationStatus.EXCEPTION
            mapping.reconciliation_note = reason
            mapping.reconciled_by_user_id = principal.user_id
            mapping.reconciled_at = datetime.now(timezone.utc)
            self._audit(
                session, principal, "bank.reconciliation.exception_flagged", company_id, mapping,
                outcome="success", severity="notice", details={"reason_length": len(reason)},
            )

    def match_transaction(
        self,
        company_id: int,
        provider_transaction_id: str,
        contra_account_id: int,
        principal: AuthenticatedPrincipal,
        note: str = "",
    ) -> None:
        """Classify a reviewed feed item by replacing its uncategorized contra account."""
        self._reconcile(
            company_id, provider_transaction_id, contra_account_id, principal, note,
            permission="bank.reconcile.match", reason="bank_reconciliation_match",
            required_status=BankReconciliationStatus.NEEDS_REVIEW,
        )

    def resolve_exception(
        self,
        company_id: int,
        provider_transaction_id: str,
        contra_account_id: int,
        principal: AuthenticatedPrincipal,
        note: str,
    ) -> None:
        """Resolve an exception through a separately permissioned, reviewed classification."""
        self._reconcile(
            company_id, provider_transaction_id, contra_account_id, principal, note,
            permission="bank.reconcile.exception.resolve", reason="bank_reconciliation_exception_resolve",
            required_status=BankReconciliationStatus.EXCEPTION,
        )

    def _reconcile(
        self,
        company_id: int,
        provider_transaction_id: str,
        contra_account_id: int,
        principal: AuthenticatedPrincipal,
        note: str,
        *,
        permission: str,
        reason: str,
        required_status: Optional[BankReconciliationStatus],
    ) -> None:
        clean_note = self._validated_note(note, allow_empty=True)
        with self.database.get_session() as session:
            self.authorization.require(session, self._context(principal, company_id, reason), permission)
            mapping = self._mapping_for_company(session, company_id, provider_transaction_id)
            self._assert_open_and_mutable(session, company_id, mapping)
            if required_status is not None and mapping.reconciliation_status != required_status:
                raise BankReconciliationError("Only an open reconciliation exception can use the exception-resolution workflow.")
            if (
                required_status == BankReconciliationStatus.EXCEPTION
                and mapping.reconciled_by_user_id == principal.user_id
            ):
                self._audit(
                    session, principal, "bank.reconciliation.sod_denied", company_id, mapping,
                    outcome="denied", severity="warning", details={"reason": "exception_flagger_cannot_resolve"},
                )
                # Persist the denial before raising: the session context rolls back on exceptions.
                session.commit()
                raise BankReconciliationError("The user who flagged an exception cannot resolve it; an independent reviewer is required.")
            account = session.get(Account, contra_account_id)
            if account is None or account.company_id != company_id or not account.is_active:
                raise BankReconciliationError("The selected reconciliation account must be active and in the same company scope.")
            entry = mapping.journal_entry
            if entry is None:
                raise BankReconciliationError("The bank-feed work item has no journal entry to classify.")
            bank_account_id = self._bank_account_id(session, mapping)
            if account.id == bank_account_id:
                raise BankReconciliationError("The linked bank account cannot be selected as its own contra account.")
            contra_lines = [line for line in entry.transactions if line.account_id != bank_account_id]
            if len(contra_lines) != 1:
                raise BankReconciliationError("The bank-feed journal entry has an unexpected line structure and requires investigation.")
            contra_lines[0].account_id = account.id
            mapping.reconciliation_status = BankReconciliationStatus.MATCHED
            mapping.reconciliation_note = clean_note or None
            mapping.reconciled_by_user_id = principal.user_id
            mapping.reconciled_at = datetime.now(timezone.utc)
            self._audit(
                session, principal, "bank.reconciliation.matched", company_id, mapping,
                outcome="success", severity="notice",
                details={"contra_account_id": account.id, "resolution_path": permission},
            )

    def _mapping_for_company(self, session, company_id: int, provider_transaction_id: str) -> PlaidTransactionMapping:
        mapping = session.scalar(
            select(PlaidTransactionMapping)
            .join(PlaidItem, PlaidTransactionMapping.plaid_item_id == PlaidItem.id)
            .where(
                PlaidItem.company_id == company_id,
                PlaidTransactionMapping.provider_transaction_id == provider_transaction_id,
            )
        )
        if mapping is None:
            raise BankReconciliationError("The bank-feed transaction does not exist in the selected company scope.")
        return mapping

    @staticmethod
    def _bank_account_id(session, mapping: PlaidTransactionMapping) -> int:
        account = session.scalar(select(PlaidAccount).where(
            PlaidAccount.plaid_item_id == mapping.plaid_item_id,
            PlaidAccount.provider_account_id == mapping.provider_account_id,
        ))
        if account is None or account.local_account_id is None:
            raise BankReconciliationError("The linked local bank account is unavailable for this feed item.")
        return account.local_account_id

    @staticmethod
    def _assert_open_and_mutable(session, company_id: int, mapping: PlaidTransactionMapping) -> None:
        if mapping.pending:
            raise BankReconciliationError("A pending bank transaction cannot be reconciled until the provider posts it.")
        if mapping.reconciliation_status == BankReconciliationStatus.REMOVED:
            raise BankReconciliationError("A removed bank-feed transaction cannot be reconciled.")
        entry = mapping.journal_entry
        if entry is None or entry.status != TransactionStatus.POSTED:
            raise BankReconciliationError("Only posted bank-feed journal entries can be reconciled.")
        if AccountingEngine(session, company_id)._is_period_locked(entry.date):
            raise BankReconciliationError("A bank-feed transaction in a locked fiscal period cannot be reclassified.")

    @staticmethod
    def _work_item(session, mapping: PlaidTransactionMapping) -> ReconciliationWorkItem:
        entry = mapping.journal_entry
        amount = Decimal("0")
        description = ""
        if entry is not None:
            amount = sum((line.debit if line.debit else line.credit) for line in entry.transactions)
            description = entry.description
        status = mapping.reconciliation_status
        return ReconciliationWorkItem(
            provider_transaction_id=mapping.provider_transaction_id,
            provider_account_id=mapping.provider_account_id,
            journal_entry_id=mapping.journal_entry_id,
            entry_date=entry.date.isoformat() if entry is not None else None,
            description=description,
            amount=str(amount),
            pending=bool(mapping.pending),
            status=status.value if hasattr(status, "value") else str(status).lower(),
            note=mapping.reconciliation_note,
            reconciled_by_user_id=mapping.reconciled_by_user_id,
            reconciled_at=mapping.reconciled_at.isoformat() if mapping.reconciled_at else None,
        )

    @staticmethod
    def _validated_note(value: str, *, allow_empty: bool = False) -> str:
        value = (value or "").strip()
        if not value and allow_empty:
            return ""
        if len(value) < 3:
            raise BankReconciliationError("A reconciliation explanation must contain at least three characters.")
        if len(value) > 500:
            raise BankReconciliationError("A reconciliation explanation cannot exceed 500 characters.")
        return value

    @staticmethod
    def _context(principal: AuthenticatedPrincipal, company_id: int, reason: str):
        if not isinstance(principal, AuthenticatedPrincipal):
            raise IdentityValidationError("A validated Enterprise session principal is required for reconciliation.")
        return principal.authorization_context(company_id, reason, mfa_max_age=timedelta(minutes=15))

    def _audit(
        self,
        session,
        principal: AuthenticatedPrincipal,
        action: str,
        company_id: int,
        mapping: PlaidTransactionMapping,
        *,
        outcome: str,
        severity: str,
        details: dict[str, object],
    ) -> None:
        self.audit_logger.record(
            session,
            action=action,
            category="banking",
            outcome=outcome,
            severity=severity,
            actor_id=principal.user_id,
            company_id=company_id,
            session_id=principal.session_id,
            request_id=principal.session_id,
            source="bank_reconciliation",
            target_type="plaid_transaction_mapping",
            target_id=mapping.provider_transaction_id,
            details=details,
        )


__all__ = [
    "BankReconciliationError",
    "BankReconciliationService",
    "ReconciliationSummary",
    "ReconciliationWorkItem",
]
