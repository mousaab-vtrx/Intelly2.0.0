"""
Database abstraction layer for PostgreSQL/pgvector runtime support.

SQLite support is retained here only for the one-time migration utility.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)
DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent / "ops_data.db"


class DatabaseConnection(ABC):
    """Abstract base class for database connections."""

    @abstractmethod
    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        """Execute a query and return the cursor/result."""
        pass

    @abstractmethod
    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        """Execute many queries with different parameters."""
        pass

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        pass


class SqliteConnection(DatabaseConnection):
    """SQLite database connection wrapper."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def _convert_query(self, query: str) -> str:
        """Convert %s parameter markers to ? for SQLite compatibility."""
        import re
        # Replace %s with ? but be careful with string literals
        return re.sub(r'%s', '?', query)

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        return self.conn.execute(self._convert_query(query), params)

    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        self.conn.executemany(self._convert_query(query), params)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def rollback(self) -> None:
        self.conn.rollback()

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        return self.conn.execute(self._convert_query(query), params).fetchone()

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
        return self.conn.execute(self._convert_query(query), params).fetchall()


class PostgresConnection(DatabaseConnection):
    """PostgreSQL database connection wrapper."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.cursor = conn.cursor()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        self.cursor.execute(query, params)
        return self.cursor

    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        self.cursor.executemany(query, params)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.cursor.close()
        self.conn.close()

    def rollback(self) -> None:
        self.conn.rollback()

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        self.cursor.execute(query, params)
        return self.cursor.fetchone()

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
        self.cursor.execute(query, params)
        return self.cursor.fetchall()


class Database(ABC):
    """Abstract database interface."""

    @abstractmethod
    def connect(self) -> DatabaseConnection:
        """Create and return a database connection."""
        pass

    @abstractmethod
    def init_tables(self) -> None:
        """Initialize database tables."""
        pass

    @staticmethod
    def factory(database_url: str | None = None) -> Database:
        """Factory method to create appropriate database instance."""
        if database_url is None:
            database_url = os.getenv(
                "DATABASE_URL",
                "postgresql://uvreactor:uvreactor@localhost:5432/uvreactor",
            )

        if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
            try:
                return PostgresDatabase(database_url)
            except ImportError as err:
                logger.warning(
                    "PostgreSQL driver unavailable, falling back to SQLite at %s: %s",
                    DEFAULT_SQLITE_PATH,
                    err,
                )
                return SqliteDatabase(DEFAULT_SQLITE_PATH)
        elif database_url.startswith("sqlite://"):
            db_path = database_url.replace("sqlite:///", "")
            return SqliteDatabase(db_path)
        else:
            raise ValueError(f"Unsupported database URL: {database_url}")


class SqliteDatabase(Database):
    """SQLite database implementation."""

    def __init__(self, db_path: str | Path = "ops_data.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[SqliteConnection]:
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield SqliteConnection(conn)
        finally:
            conn.close()

    def init_tables(self) -> None:
        """Initialize SQLite tables."""
        with self.connect() as conn:
            # Reports table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    report_date TEXT,
                    structured_content TEXT NOT NULL,
                    plain_text TEXT NOT NULL,
                    latex_content TEXT NOT NULL,
                    pdf_path TEXT,
                    tex_path TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_single_active_notification
                ON reports(report_type)
                WHERE report_type = 'notification_report' AND is_active = 1
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reports_type_created
                ON reports(report_type, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reports_type_date
                ON reports(report_type, report_date DESC)
                """
            )

            # Scheduled tasks table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    executed_at TEXT,
                    ai_evaluation TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_telemetry_history_recorded_at
                ON telemetry_history(recorded_at DESC)
                """
            )
            conn.commit()


class PostgresDatabase(Database):
    """PostgreSQL database implementation with pgvector support."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        # Parse connection details
        try:
            import psycopg2
            self.psycopg2 = psycopg2
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgreSQL support. "
                "Install it with: pip install psycopg2-binary"
            )

    @contextmanager
    def connect(self) -> Iterator[PostgresConnection]:
        """Context manager for PostgreSQL connections."""
        try:
            conn = self.psycopg2.connect(self.database_url)
            yield PostgresConnection(conn)
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def init_tables(self) -> None:
        """Initialize PostgreSQL tables with pgvector support."""
        with self.connect() as conn:
            # Enable pgvector extension
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()

            # Reports table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT false,
                    created_at TEXT NOT NULL,
                    report_date TEXT,
                    structured_content JSONB NOT NULL,
                    plain_text TEXT NOT NULL,
                    latex_content TEXT NOT NULL,
                    pdf_path TEXT,
                    tex_path TEXT,
                    metadata_json JSONB NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_single_active_notification
                ON reports(report_type)
                WHERE report_type = 'notification_report' AND is_active = true
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reports_type_created
                ON reports(report_type, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reports_type_date
                ON reports(report_type, report_date DESC)
                """
            )

            # Scheduled tasks table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completed BOOLEAN NOT NULL DEFAULT false,
                    created_at TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    executed_at TEXT,
                    ai_evaluation JSONB
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_for
                ON scheduled_tasks(scheduled_for ASC)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_history (
                    id BIGSERIAL PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    payload JSONB NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_telemetry_history_recorded_at
                ON telemetry_history(recorded_at DESC)
                """
            )

            conn.commit()


def get_database() -> Database:
    """Get database instance based on environment configuration."""
    database_url = os.getenv("DATABASE_URL")
    return Database.factory(database_url)
