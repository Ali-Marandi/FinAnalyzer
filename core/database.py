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
from sqlalchemy import create_engine, event
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
        """Create all tables defined in models."""
        Base.metadata.create_all(bind=self.engine)

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
