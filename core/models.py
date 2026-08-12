"""
SQLAlchemy ORM models for FinAnalyzer Enterprise v2.0.0.
Supports multi-entity companies, hierarchical chart of accounts, double-entry transactions,
journal entries, budgeting, user management with RBAC, audit logging, multi-currency,
fiscal years, invoicing, and asset depreciation tracking.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    String, Numeric, DateTime, Date, ForeignKey, Text, Boolean, Integer, Enum as SQLEnum,
    UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"

class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class AccountType(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"

class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    POSTED = "posted"
    VOIDED = "voided"

class Company(Base):
    """Multi-entity support for corporate groups."""
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    legal_name: Mapped[Optional[str]] = mapped_column(String(255))
    tax_id: Mapped[Optional[str]] = mapped_column(String(100))
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    fiscal_year_end_month: Mapped[int] = mapped_column(Integer, default=12)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    accounts: Mapped[List["Account"]] = relationship("Account", back_populates="company", cascade="all, delete-orphan")
    journal_entries: Mapped[List["JournalEntry"]] = relationship("JournalEntry", back_populates="company", cascade="all, delete-orphan")
    budgets: Mapped[List["Budget"]] = relationship("Budget", back_populates="company", cascade="all, delete-orphan")
    assets: Mapped[List["Asset"]] = relationship("Asset", back_populates="company", cascade="all, delete-orphan")
    invoices: Mapped[List["Invoice"]] = relationship("Invoice", back_populates="company", cascade="all, delete-orphan")
    plaid_items: Mapped[List["PlaidItem"]] = relationship("PlaidItem", back_populates="company", cascade="all, delete-orphan")
    memberships: Mapped[List["CompanyMembership"]] = relationship("CompanyMembership", back_populates="company", cascade="all, delete-orphan")


class User(Base):
    """User accounts with RBAC support."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user")
    memberships: Mapped[List["CompanyMembership"]] = relationship("CompanyMembership", back_populates="user", cascade="all, delete-orphan")
    external_identities: Mapped[List["ExternalIdentity"]] = relationship("ExternalIdentity", back_populates="user", cascade="all, delete-orphan")
    auth_sessions: Mapped[List["AuthSession"]] = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    """Chart of Accounts with hierarchical parent-child relationships."""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"))
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(SQLEnum(AccountType), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped["Company"] = relationship("Company", back_populates="accounts")
    parent: Mapped[Optional["Account"]] = relationship("Account", remote_side=[id], back_populates="children")
    children: Mapped[List["Account"]] = relationship("Account", back_populates="parent", cascade="all, delete-orphan")
    transaction_lines: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="account")


class JournalEntry(Base):
    """Journal entry header containing multiple debit/credit transaction lines."""
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    entry_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(SQLEnum(TransactionStatus), default=TransactionStatus.POSTED)
    created_by: Mapped[Optional[str]] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="journal_entries")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="journal_entry", cascade="all, delete-orphan")


class Transaction(Base):
    """Double-entry transaction line supporting debit and credit amounts."""
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0.0000)
    credit: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0.0000)
    description: Mapped[Optional[str]] = mapped_column(Text)

    journal_entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="transactions")
    account: Mapped["Account"] = relationship("Account", back_populates="transaction_lines")


class Category(Base):
    """Transaction categorization for budgeting and analytics."""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category_type: Mapped[str] = mapped_column(String(50), nullable=False) # income, expense


class Budget(Base):
    """Budgeting model for variance analysis."""
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False) # 1-12
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="budgets")
    account: Mapped["Account"] = relationship("Account")


class Currency(Base):
    """Multi-currency support and exchange rates."""
    __tablename__ = "currencies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False) # e.g. USD, EUR
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(15, 6), default=1.000000) # relative to base currency
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FiscalYear(Base):
    """Fiscal year period locking and management."""
    __tablename__ = "fiscal_years"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)


class Invoice(Base):
    """Enterprise accounts receivable/payable invoice management."""
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="unpaid") # unpaid, paid, overdue

    company: Mapped["Company"] = relationship("Company", back_populates="invoices")


class Asset(Base):
    """Fixed assets tracking for depreciation calculation."""
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    salvage_value: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0.0000)
    useful_life_years: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_method: Mapped[str] = mapped_column(String(50), default="straight_line")

    company: Mapped["Company"] = relationship("Company", back_populates="assets")


class PlaidItem(Base):
    """A consented Plaid connection; its API access token is encrypted at rest."""
    __tablename__ = "plaid_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    cursor: Mapped[Optional[str]] = mapped_column(String(256))
    institution_id: Mapped[Optional[str]] = mapped_column(String(128))
    institution_name: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="linked")
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="plaid_items")
    accounts: Mapped[List["PlaidAccount"]] = relationship("PlaidAccount", back_populates="item", cascade="all, delete-orphan")
    transaction_mappings: Mapped[List["PlaidTransactionMapping"]] = relationship("PlaidTransactionMapping", back_populates="item", cascade="all, delete-orphan")


class PlaidAccount(Base):
    """A financial account returned for a linked Plaid Item."""
    __tablename__ = "plaid_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plaid_item_id: Mapped[int] = mapped_column(ForeignKey("plaid_items.id"), nullable=False, index=True)
    provider_account_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    local_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(255), default="")
    account_type: Mapped[Optional[str]] = mapped_column(String(50))
    account_subtype: Mapped[Optional[str]] = mapped_column(String(80))
    mask: Mapped[Optional[str]] = mapped_column(String(16))
    current_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    available_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    currency_code: Mapped[Optional[str]] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    item: Mapped["PlaidItem"] = relationship("PlaidItem", back_populates="accounts")
    local_account: Mapped[Optional["Account"]] = relationship("Account")


class PlaidTransactionMapping(Base):
    """Idempotency and provenance record for an imported bank transaction."""
    __tablename__ = "plaid_transaction_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plaid_item_id: Mapped[int] = mapped_column(ForeignKey("plaid_items.id"), nullable=False, index=True)
    provider_transaction_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    provider_account_id: Mapped[Optional[str]] = mapped_column(String(128))
    journal_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), unique=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    item: Mapped["PlaidItem"] = relationship("PlaidItem", back_populates="transaction_mappings")
    journal_entry: Mapped[Optional["JournalEntry"]] = relationship("JournalEntry")


class Role(Base):
    """Named, reusable enterprise role assigned within a company membership."""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    memberships: Mapped[List["MembershipRole"]] = relationship("MembershipRole", back_populates="role", cascade="all, delete-orphan")
    permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    """A stable resource.action permission, independent of user-interface labels."""
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    roles: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class CompanyMembership(Base):
    """A user's active or revoked membership boundary for one company tenant."""
    __tablename__ = "company_memberships"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_company_membership_user_company"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    status: Mapped[MembershipStatus] = mapped_column(SQLEnum(MembershipStatus), default=MembershipStatus.ACTIVE, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship("User", back_populates="memberships")
    company: Mapped["Company"] = relationship("Company", back_populates="memberships")
    roles: Mapped[List["MembershipRole"]] = relationship("MembershipRole", back_populates="membership", cascade="all, delete-orphan")


class MembershipRole(Base):
    """Many-to-many membership-to-role mapping scoped to a single company."""
    __tablename__ = "membership_roles"
    __table_args__ = (UniqueConstraint("membership_id", "role_id", name="uq_membership_role"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("company_memberships.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)

    membership: Mapped["CompanyMembership"] = relationship("CompanyMembership", back_populates="roles")
    role: Mapped["Role"] = relationship("Role", back_populates="memberships")


class RolePermission(Base):
    """Many-to-many role-to-permission mapping used by the central policy service."""
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), nullable=False, index=True)

    role: Mapped["Role"] = relationship("Role", back_populates="permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="roles")


class IdentityProvider(Base):
    """Approved OIDC identity provider configuration; client secrets are never stored here."""
    __tablename__ = "identity_providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    external_identities: Mapped[List["ExternalIdentity"]] = relationship("ExternalIdentity", back_populates="provider", cascade="all, delete-orphan")
    auth_sessions: Mapped[List["AuthSession"]] = relationship("AuthSession", back_populates="provider", cascade="all, delete-orphan")


class ExternalIdentity(Base):
    """Immutable provider subject-to-local-user mapping for federated sign-in."""
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("provider_id", "subject", name="uq_external_identity_provider_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("identity_providers.id"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    object_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    preferred_username: Mapped[Optional[str]] = mapped_column(String(255))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="external_identities")
    provider: Mapped["IdentityProvider"] = relationship("IdentityProvider", back_populates="external_identities")


class AuthSession(Base):
    """Server-validated local session created only after successful federated authentication."""
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("identity_providers.id"), nullable=False, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    auth_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    mfa_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    assurance_level: Mapped[Optional[str]] = mapped_column(String(64))
    device_id: Mapped[Optional[str]] = mapped_column(String(128))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="auth_sessions")
    provider: Mapped["IdentityProvider"] = relationship("IdentityProvider", back_populates="auth_sessions")


class AuditLog(Base):
    """Structured, append-only audit event with a signed integrity-chain link."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(36), unique=True, index=True)
    sequence: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    severity: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    source: Mapped[Optional[str]] = mapped_column(String(128))
    target_type: Mapped[Optional[str]] = mapped_column(String(64))
    target_id: Mapped[Optional[str]] = mapped_column(String(128))
    details: Mapped[Optional[str]] = mapped_column(Text)
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64))
    event_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    key_id: Mapped[Optional[str]] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")


class AuditChainState(Base):
    """Single-writer chain checkpoint used to verify all v2.4+ audit events."""
    __tablename__ = "audit_chain_state"

    scope: Mapped[str] = mapped_column(String(64), primary_key=True, default="global")
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="0" * 64)
    key_id: Mapped[Optional[str]] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
