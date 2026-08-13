"""Plaid bank-connection service for FinAnalyzer Enterprise v2.

The implementation follows Plaid's Link → public-token exchange → encrypted access
-token → cursor-based Transactions Sync pattern. It maps imported bank records into
balanced journal entries using a clearly labelled uncategorized account, preserving
an auditable path for accountant review instead of silently asserting tax treatment.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
import time
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from sqlalchemy import select

from core.accounting_engine import AccountingEngine
from core.audit import AuditLogger
from core.authorization import AuthorizationService
from core.identity import AuthenticatedPrincipal, IdentityValidationError
from core.database import DatabaseManager
from core.models import (
    Account,
    AccountType,
    AuditLog,
    Company,
    JournalEntry,
    PlaidAccount,
    PlaidItem,
    PlaidTransactionMapping,
    TransactionStatus,
)
from core.security import LocalSecretStore

try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.country_code import CountryCode
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.link_token_transactions import LinkTokenTransactions
    from plaid.model.products import Products
    from plaid.model.transactions_sync_request import TransactionsSyncRequest

    PLAID_SDK_AVAILABLE = True
except ImportError:
    PLAID_SDK_AVAILABLE = False


class PlaidConfigurationError(RuntimeError):
    """Plaid was not installed or configured correctly on this desktop."""


class PlaidSyncError(RuntimeError):
    """The application could not complete a safe synchronization."""


@dataclass(frozen=True)
class PlaidSettings:
    client_id: str
    secret: str
    environment: str = "sandbox"
    client_name: str = "FinAnalyzer Enterprise"
    country_codes: tuple[str, ...] = ("US",)
    webhook_url: Optional[str] = None
    redirect_uri: Optional[str] = None
    days_requested: int = 90

    @classmethod
    def from_environment(cls) -> "PlaidSettings":
        client_id = os.getenv("PLAID_CLIENT_ID", "").strip()
        secret = os.getenv("PLAID_SECRET", "").strip()
        if not client_id or not secret:
            raise PlaidConfigurationError(
                "Set PLAID_CLIENT_ID and PLAID_SECRET in the local environment before connecting a bank."
            )
        days_requested = int(os.getenv("PLAID_DAYS_REQUESTED", "90"))
        if not 1 <= days_requested <= 730:
            raise PlaidConfigurationError("PLAID_DAYS_REQUESTED must be between 1 and 730.")
        countries = tuple(
            value.strip().upper()
            for value in os.getenv("PLAID_COUNTRY_CODES", "US").split(",")
            if value.strip()
        )
        return cls(
            client_id=client_id,
            secret=secret,
            environment=os.getenv("PLAID_ENV", "sandbox").strip().lower(),
            client_name=os.getenv("PLAID_CLIENT_NAME", "FinAnalyzer Enterprise").strip(),
            country_codes=countries or ("US",),
            webhook_url=os.getenv("PLAID_WEBHOOK_URL") or None,
            redirect_uri=os.getenv("PLAID_REDIRECT_URI") or None,
            days_requested=days_requested,
        )


class PlaidConnector:
    """Connect consented banks to a company without persisting plaintext access tokens."""

    def __init__(
        self,
        database: DatabaseManager,
        settings: Optional[PlaidSettings] = None,
        secret_store: Optional[LocalSecretStore] = None,
        authorization: Optional[AuthorizationService] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        if not PLAID_SDK_AVAILABLE:
            raise PlaidConfigurationError("The Plaid SDK is missing. Install plaid-python first.")
        self.database = database
        self.settings = settings or PlaidSettings.from_environment()
        self.secret_store = secret_store or LocalSecretStore()
        self.authorization = authorization or AuthorizationService()
        self.audit_logger = audit_logger or AuditLogger()
        self.client = self._build_client()

    def _build_client(self):
        environment_map = {
            "sandbox": getattr(plaid.Environment, "Sandbox", "https://sandbox.plaid.com"),
            "development": getattr(plaid.Environment, "Development", "https://development.plaid.com"),
            "production": getattr(plaid.Environment, "Production", "https://production.plaid.com"),
        }
        if self.settings.environment not in environment_map:
            raise PlaidConfigurationError("PLAID_ENV must be sandbox, development, or production.")
        configuration = plaid.Configuration(
            host=environment_map[self.settings.environment],
            api_key={"clientId": self.settings.client_id, "secret": self.settings.secret},
        )
        return plaid_api.PlaidApi(plaid.ApiClient(configuration))

    @staticmethod
    def _dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        return value.to_dict() if hasattr(value, "to_dict") else dict(value)

    def create_link_token(self, company_id: int, principal: AuthenticatedPrincipal) -> Dict[str, Any]:
        """Create a Link token only for an authorized, MFA-backed Enterprise session."""
        with self.database.get_session() as session:
            company = session.get(Company, company_id)
            if company is None:
                raise PlaidSyncError("The selected company does not exist.")
            self.authorization.require(
                session,
                self._context(principal, company_id, "plaid_link"),
                "bank.link",
            )
        payload: Dict[str, Any] = {
            "products": [Products("transactions")],
            "client_name": self.settings.client_name[:30],
            "country_codes": [CountryCode(code) for code in self.settings.country_codes],
            "language": "en",
            "user": LinkTokenCreateRequestUser(client_user_id=f"company-{company_id}"),
            "transactions": LinkTokenTransactions(days_requested=self.settings.days_requested),
        }
        if self.settings.webhook_url:
            payload["webhook"] = self.settings.webhook_url
        if self.settings.redirect_uri:
            payload["redirect_uri"] = self.settings.redirect_uri
        result = self._dict(self.client.link_token_create(LinkTokenCreateRequest(**payload)))
        with self.database.get_session() as session:
            self._audit(
                session, principal, "bank.link_token_created", company_id, "link_token",
                outcome="success", severity="notice", details={"environment": self.settings.environment},
            )
        return result

    def exchange_public_token(
        self,
        company_id: int,
        principal: AuthenticatedPrincipal,
        public_token: str,
        institution: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Exchange and locally encrypt the returned persistent Plaid access token."""
        if not public_token:
            raise PlaidSyncError("A Plaid public token is required to complete bank linking.")
        with self.database.get_session() as session:
            self.authorization.require(
                session,
                self._context(principal, company_id, "plaid_exchange"),
                "bank.link",
            )
        response = self.client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
        result = self._dict(response)
        item_id = result["item_id"]
        access_token = result["access_token"]
        institution = institution or {}
        with self.database.get_session() as session:
            if session.get(Company, company_id) is None:
                raise PlaidSyncError("The selected company does not exist.")
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == item_id))
            if item is None:
                item = PlaidItem(
                    company_id=company_id,
                    item_id=item_id,
                    encrypted_access_token=self.secret_store.encrypt(access_token),
                    institution_id=institution.get("institution_id"),
                    institution_name=institution.get("name"),
                    status="linked",
                )
                session.add(item)
            else:
                item.company_id = company_id
                item.encrypted_access_token = self.secret_store.encrypt(access_token)
                item.institution_id = institution.get("institution_id") or item.institution_id
                item.institution_name = institution.get("name") or item.institution_name
                item.status = "linked"
            self._audit(
                session, principal, "bank.item_linked", company_id, item_id,
                outcome="success", severity="notice",
                details={"institution_id": item.institution_id, "environment": self.settings.environment},
            )
        return {"item_id": item_id, "status": "linked"}

    def sync_company(self, company_id: int, principal: AuthenticatedPrincipal) -> list[Dict[str, Any]]:
        with self.database.get_session() as session:
            self.authorization.require(
                session,
                self._context(principal, company_id, "plaid_sync_company"),
                "bank.sync",
            )
            item_ids = list(session.scalars(select(PlaidItem.item_id).where(PlaidItem.company_id == company_id)))
        return [self.sync_item(item_id, principal) for item_id in item_ids]

    def sync_item(self, item_id: str, principal: AuthenticatedPrincipal) -> Dict[str, Any]:
        """Fetch and apply changes only after the actor is authorized in the Item company scope."""
        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == item_id))
            if item is None:
                raise PlaidSyncError("The requested bank connection does not exist locally.")
            self.authorization.require(
                session,
                self._context(principal, item.company_id, "plaid_sync_item"),
                "bank.sync",
            )
            item_company_id = item.company_id
            access_token = self.secret_store.decrypt(item.encrypted_access_token)
            original_cursor = item.cursor

        cursor = original_cursor
        added: list[Dict[str, Any]] = []
        modified: list[Dict[str, Any]] = []
        removed: list[Dict[str, Any]] = []
        accounts: Dict[str, Dict[str, Any]] = {}
        has_more = True
        try:
            while has_more:
                request_args = {"access_token": access_token, "count": 500}
                if cursor:
                    request_args["cursor"] = cursor
                response = self.client.transactions_sync(TransactionsSyncRequest(**request_args))
                page = self._dict(response)
                added.extend(page.get("added", []))
                modified.extend(page.get("modified", []))
                removed.extend(page.get("removed", []))
                accounts.update({entry["account_id"]: entry for entry in page.get("accounts", [])})
                cursor = page.get("next_cursor")
                has_more = bool(page.get("has_more"))
        except Exception as exc:
            # Do not persist a partially advanced cursor; the next sync retries safely.
            with self.database.get_session() as session:
                self._audit(
                    session, principal, "bank.sync_failed", item_company_id, item_id,
                    outcome="failure", severity="warning", details={"error_type": type(exc).__name__},
                )
            raise PlaidSyncError("Transaction sync failed before completion. No partial cursor was saved; retry the sync.") from exc

        try:
            with self.database.get_session() as session:
                item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == item_id))
                if item is None:
                    raise PlaidSyncError("The bank connection was removed during synchronization.")
                local_accounts = self._upsert_accounts(session, item, accounts.values())
                counts = self._apply_changes(session, item, added, modified, removed, local_accounts)
                item.cursor = cursor
                item.last_synced_at = datetime.now(timezone.utc)
                item.status = "synced"
                self._audit(
                    session, principal, "bank.item_synced", item.company_id, item_id,
                    outcome="success", severity="info", details=counts,
                )
        except PlaidSyncError:
            raise
        except Exception as exc:
            # The apply transaction has rolled back. Record only safe error metadata in a new transaction.
            with self.database.get_session() as session:
                failed_item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == item_id))
                if failed_item is not None:
                    self._audit(
                        session, principal, "bank.sync_apply_failed", failed_item.company_id, item_id,
                        outcome="failure", severity="warning",
                        details={"error_type": type(exc).__name__, "phase": "ledger_apply", "cursor_preserved": True},
                    )
            raise PlaidSyncError(
                "Transaction changes could not be applied safely. No transaction, mapping, or cursor change was saved; review the audit log."
            ) from exc
        return {"item_id": item_id, **counts, "cursor_advanced": bool(cursor and cursor != original_cursor)}

    def remove_item(self, item_id: str, principal: AuthenticatedPrincipal) -> bool:
        """Revoke remote access only for an MFA-backed, authorized Enterprise session."""
        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == item_id))
            if item is None:
                return False
            self.authorization.require(
                session,
                self._context(principal, item.company_id, "plaid_unlink"),
                "bank.unlink",
            )
            access_token = self.secret_store.decrypt(item.encrypted_access_token)
        try:
            from plaid.model.item_remove_request import ItemRemoveRequest
            self.client.item_remove(ItemRemoveRequest(access_token=access_token))
        except Exception as exc:
            raise PlaidSyncError("Remote access revocation failed; local banking data remains unchanged.") from exc
        with self.database.get_session() as session:
            item = session.scalar(select(PlaidItem).where(PlaidItem.item_id == item_id))
            if item:
                self._audit(
                    session, principal, "bank.item_removed", item.company_id, item_id,
                    outcome="success", severity="notice", details={"environment": self.settings.environment},
                )
                session.delete(item)
        return True

    @staticmethod
    def _context(principal: AuthenticatedPrincipal, company_id: int, reason: str):
        if not isinstance(principal, AuthenticatedPrincipal):
            raise IdentityValidationError("A validated Enterprise session principal is required for banking operations.")
        return principal.authorization_context(company_id, reason, mfa_max_age=timedelta(minutes=15))

    def _upsert_accounts(self, session, item: PlaidItem, records: Iterable[Dict[str, Any]]) -> Dict[str, PlaidAccount]:
        local_accounts: Dict[str, PlaidAccount] = {}
        for record in records:
            provider_id = record.get("account_id")
            if not provider_id:
                continue
            account = session.scalar(select(PlaidAccount).where(PlaidAccount.provider_account_id == provider_id))
            if account is None:
                account = PlaidAccount(plaid_item_id=item.id, provider_account_id=provider_id)
                session.add(account)
                session.flush()
            account.name = record.get("name") or "Bank account"
            account.account_type = record.get("type")
            account.account_subtype = record.get("subtype")
            account.mask = record.get("mask")
            balances = record.get("balances") or {}
            account.current_balance = self._decimal_or_none(balances.get("current"))
            account.available_balance = self._decimal_or_none(balances.get("available"))
            account.currency_code = balances.get("iso_currency_code") or balances.get("unofficial_currency_code")
            if account.local_account_id is None:
                account.local_account_id = self._create_gl_bank_account(session, item.company_id, account)
            local_accounts[provider_id] = account
        return local_accounts

    def _create_gl_bank_account(self, session, company_id: int, plaid_account: PlaidAccount) -> int:
        source_type = (plaid_account.account_type or "").lower()
        account_type = AccountType.LIABILITY if source_type in {"credit", "loan"} else AccountType.ASSET
        prefix = "2100" if account_type == AccountType.LIABILITY else "1010"
        code = f"{prefix}-{plaid_account.provider_account_id[-8:]}"
        account = Account(
            company_id=company_id,
            code=code,
            name=f"Bank feed | {plaid_account.name}",
            account_type=account_type,
            description="Automatically created from Plaid. Review in Chart of Accounts.",
        )
        session.add(account)
        session.flush()
        return account.id

    def _apply_changes(
        self,
        session,
        item: PlaidItem,
        added: Iterable[Dict[str, Any]],
        modified: Iterable[Dict[str, Any]],
        removed: Iterable[Dict[str, Any]],
        local_accounts: Dict[str, PlaidAccount],
    ) -> Dict[str, int]:
        counts = {"added": 0, "modified": 0, "removed": 0}
        for record in added:
            if self._post_or_replace(session, item, record, local_accounts, is_revision=False):
                counts["added"] += 1
        for record in modified:
            if self._post_or_replace(session, item, record, local_accounts, is_revision=True):
                counts["modified"] += 1
        for record in removed:
            provider_id = record.get("transaction_id")
            mapping = session.scalar(select(PlaidTransactionMapping).where(PlaidTransactionMapping.provider_transaction_id == provider_id))
            if mapping:
                if mapping.journal_entry:
                    self._assert_entry_not_locked(session, item.company_id, mapping.journal_entry)
                    mapping.journal_entry.status = TransactionStatus.VOIDED
                mapping.pending = False
                mapping.raw_payload = json.dumps({"removed": True, "transaction_id": provider_id})
                counts["removed"] += 1
        return counts

    def _post_or_replace(
        self,
        session,
        item: PlaidItem,
        record: Dict[str, Any],
        local_accounts: Dict[str, PlaidAccount],
        is_revision: bool,
    ) -> bool:
        provider_id = record.get("transaction_id")
        provider_account_id = record.get("account_id")
        if not provider_id or provider_account_id not in local_accounts:
            return False
        mapping = session.scalar(select(PlaidTransactionMapping).where(PlaidTransactionMapping.provider_transaction_id == provider_id))
        if mapping and not is_revision:
            return False
        if mapping is None:
            mapping = PlaidTransactionMapping(
                plaid_item_id=item.id,
                provider_transaction_id=provider_id,
                provider_account_id=provider_account_id,
            )
            session.add(mapping)
            session.flush()
        elif mapping.journal_entry:
            # A bank correction must not void or replace an entry in a locked fiscal period.
            self._assert_entry_not_locked(session, item.company_id, mapping.journal_entry)
            mapping.journal_entry.status = TransactionStatus.VOIDED

        bank_account_id = local_accounts[provider_account_id].local_account_id
        amount = Decimal(str(record.get("amount") or 0)).copy_abs()
        if amount == 0:
            return False
        raw_amount = Decimal(str(record.get("amount") or 0))
        is_outflow = raw_amount >= 0  # Plaid positive values are user outflows.
        contra_account_id = self._ensure_uncategorized_account(
            session,
            item.company_id,
            AccountType.EXPENSE if is_outflow else AccountType.REVENUE,
        )
        record_date = self._record_date(record)
        entry_number = f"PLD-{provider_id[-8:]}-{uuid4().hex[:12]}"
        description = record.get("merchant_name") or record.get("name") or "Plaid bank transaction"
        lines = (
            [
                {"account_id": contra_account_id, "debit": amount, "credit": 0, "description": description},
                {"account_id": bank_account_id, "debit": 0, "credit": amount, "description": description},
            ]
            if is_outflow
            else [
                {"account_id": bank_account_id, "debit": amount, "credit": 0, "description": description},
                {"account_id": contra_account_id, "debit": 0, "credit": amount, "description": description},
            ]
        )
        engine = AccountingEngine(session, item.company_id)
        entry = engine.post_journal_entry(
            entry_number, record_date, description, lines, created_by="Plaid Sync", commit=False
        )
        mapping.journal_entry_id = entry.id
        mapping.provider_account_id = provider_account_id
        mapping.pending = bool(record.get("pending"))
        mapping.raw_payload = json.dumps(record, default=str, ensure_ascii=False)
        return True

    @staticmethod
    def _assert_entry_not_locked(session, company_id: int, entry: JournalEntry) -> None:
        """Reject bank-feed voids or revisions that would alter a locked fiscal period."""
        if AccountingEngine(session, company_id)._is_period_locked(entry.date):
            raise ValueError("A bank-feed transaction in a locked fiscal period cannot be voided or revised.")

    def _ensure_uncategorized_account(self, session, company_id: int, account_type: AccountType) -> int:
        code = "6999" if account_type == AccountType.EXPENSE else "4999"
        name = "Uncategorized bank feed expense" if account_type == AccountType.EXPENSE else "Uncategorized bank feed income"
        account = session.scalar(select(Account).where(Account.company_id == company_id, Account.code == code))
        if account is None:
            account = Account(company_id=company_id, code=code, name=name, account_type=account_type, description="Requires accountant categorization.")
            session.add(account)
            session.flush()
        return account.id

    @staticmethod
    def _record_date(record: Dict[str, Any]) -> date:
        value = record.get("authorized_date") or record.get("date")
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)) if value else date.today()

    @staticmethod
    def _decimal_or_none(value: Any) -> Optional[Decimal]:
        return Decimal(str(value)) if value is not None else None

    def _audit(
        self,
        session,
        principal: AuthenticatedPrincipal,
        action: str,
        company_id: int,
        target_id: str,
        *,
        outcome: str,
        severity: str,
        details: Dict[str, Any],
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
            source="plaid_connector",
            target_type="plaid_item",
            target_id=target_id,
            details=details,
        )


__all__ = ["PlaidConnector", "PlaidSettings", "PlaidConfigurationError", "PlaidSyncError", "PLAID_SDK_AVAILABLE"]
