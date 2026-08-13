"""
Database manager for FinAnalyzer Enterprise v2.0.0.
Provides SQLite database engine setup with connection pooling, session management,
schema migration/initialization, and secure backup/restore functionality.
"""

import os
import shutil
import sqlite3
from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from core.models import Base

class DatabaseManager:
    """Manages database lifecycle, connection pooling, sessions, and backups."""

    def __init__(self, db_path: str = "finanalyzer.db", echo: bool = False):
        self.db_path = db_path
        self.db_url = f"sqlite:///{os.path.abspath(db_path)}"
        
        # SQLite connection pooling with QueuePool
        self.engine = create_engine(
            self.db_url,
            echo=echo,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            connect_args={"timeout": 30}
        )
        
        # Enable SQLite foreign key constraints
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if isinstance(dbapi_connection, sqlite3.Connection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL") # Write-Ahead Logging for ACID compliance & concurrency
                cursor.close()

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    def init_database(self) -> None:
        """Create schema objects, apply additive local migrations, and seed security defaults."""
        Base.metadata.create_all(bind=self.engine)
        self._migrate_v24_audit_schema()
        self._migrate_v25_period_close_schema()
        self._migrate_v27_bank_reconciliation_schema()
        self.bootstrap_enterprise_security()

    def _migrate_v24_audit_schema(self) -> None:
        """Apply additive SQLite-safe columns/indexes for v2.4 structured audit events."""
        inspector = inspect(self.engine)
        if "audit_logs" not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns("audit_logs")}
        additions = {
            "event_id": "VARCHAR(36)",
            "sequence": "INTEGER",
            "company_id": "INTEGER",
            "session_id": "VARCHAR(64)",
            "request_id": "VARCHAR(128)",
            "category": "VARCHAR(64)",
            "severity": "VARCHAR(16)",
            "outcome": "VARCHAR(32)",
            "source": "VARCHAR(128)",
            "target_type": "VARCHAR(64)",
            "target_id": "VARCHAR(128)",
            "previous_hash": "VARCHAR(64)",
            "event_hash": "VARCHAR(64)",
            "key_id": "VARCHAR(32)",
        }
        with self.engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE audit_logs ADD COLUMN {name} {sql_type}"))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_logs_event_id_v24 "
                "ON audit_logs(event_id) WHERE event_id IS NOT NULL"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_logs_sequence_v24 "
                "ON audit_logs(sequence) WHERE sequence IS NOT NULL"
            ))
            for name in ("company_id", "session_id", "request_id", "category", "severity", "outcome", "event_hash"):
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_audit_logs_{name}_v24 ON audit_logs({name})"))

    def _migrate_v25_period_close_schema(self) -> None:
        """Prevent more than one pending/approved close request for the same fiscal year."""
        inspector = inspect(self.engine)
        if "period_close_requests" not in inspector.get_table_names():
            return
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_period_close_requests_active_v25 "
                "ON period_close_requests(company_id, fiscal_year_id) "
                "WHERE status IN ('PENDING', 'APPROVED')"
            ))

    def _migrate_v27_bank_reconciliation_schema(self) -> None:
        """Add workflow state for bank-feed reconciliation without rewriting local history."""
        inspector = inspect(self.engine)
        if "plaid_transaction_mappings" not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns("plaid_transaction_mappings")}
        additions = {
            "reconciliation_status": "VARCHAR(32) NOT NULL DEFAULT 'NEEDS_REVIEW'",
            "reconciliation_note": "VARCHAR(500)",
            "reconciled_by_user_id": "INTEGER",
            "reconciled_at": "DATETIME",
        }
        with self.engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE plaid_transaction_mappings ADD COLUMN {name} {sql_type}"))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_plaid_mappings_reconciliation_v27 "
                "ON plaid_transaction_mappings(reconciliation_status)"
            ))

    def bootstrap_enterprise_security(self) -> None:
        """Ensure canonical roles and permissions exist without granting any user access."""
        from core.authorization import AuthorizationService
        with self.get_session() as session:
            AuthorizationService().bootstrap_defaults(session)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def backup_database(self, backup_path: str) -> bool:
        """Create a safe SQLite backup snapshot."""
        try:
            if not os.path.exists(self.db_path):
                raise FileNotFoundError(f"Database file not found at {self.db_path}")
            
            # Use SQLite backup API for hot backup
            src = sqlite3.connect(self.db_path)
            dst = sqlite3.connect(backup_path)
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            return True
        except Exception as e:
            print(f"Backup failed: {e}")
            return False

    def restore_database(self, backup_path: str) -> bool:
        """Restore database from a backup snapshot."""
        try:
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"Backup file not found at {backup_path}")
            
            shutil.copyfile(backup_path, self.db_path)
            return True
        except Exception as e:
            print(f"Restore failed: {e}")
            return False
