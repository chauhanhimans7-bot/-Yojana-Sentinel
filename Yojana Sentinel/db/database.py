"""
db/database.py — Unified Database Abstraction Layer for Yojana Sentinel

Supports both Supabase PostgreSQL (via DATABASE_URL or SUPABASE_DB_URL)
and local SQLite (data/yojana_sentinel.db) fallback.

Features:
  - Automatic driver selection (psycopg2 for PostgreSQL, sqlite3 for local fallback)
  - Parameter placeholder translation ('?' -> '%s' for PostgreSQL)
  - Dictionary row factory for uniform dict key access across all modules
  - Context manager and helper functions for execute / fetch / commit
"""

import os
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

log = logging.getLogger(__name__)

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"

# Check for PostgreSQL connection string in environment variables
DATABASE_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")

# Attempt to import psycopg2 if PostgreSQL URL is present
has_psycopg2 = False
if DATABASE_URL:
    try:
        import psycopg2
        import psycopg2.extras
        has_psycopg2 = True
        log.info("Database Adapter: PostgreSQL (Supabase) detected.")
    except ImportError:
        log.warning("DATABASE_URL present but psycopg2 is not installed. Falling back to SQLite.")

if not (DATABASE_URL and has_psycopg2):
    log.info("Database Adapter: SQLite local mode (%s)", DB_PATH)


class DictRow(dict):
    """Dictionary subclass supporting column attribute/key access."""
    def __getitem__(self, item: Any) -> Any:
        return super().__getitem__(item)


class DBConnection:
    """Unified Database Connection wrapper supporting PostgreSQL and SQLite."""

    def __init__(self):
        self.is_postgres = bool(DATABASE_URL and has_psycopg2)
        self.conn = None

    def connect(self):
        if self.is_postgres:
            import psycopg2
            import psycopg2.extras
            # Handle postgres:// vs postgresql:// prefix
            url = DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            self.conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
        else:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(DB_PATH))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys=ON")
        return self

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None:
                try:
                    self.conn.commit()
                except Exception:
                    pass
            else:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
            self.conn.close()

    def _prepare_sql(self, sql: str) -> str:
        """Translate SQLite '?' placeholders to PostgreSQL '%s' if using PostgreSQL."""
        if self.is_postgres:
            # Simple placeholder conversion for positional '?' parameters
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        formatted_sql = self._prepare_sql(sql)
        cursor = self.conn.cursor()
        cursor.execute(formatted_sql, params)
        return cursor

    def fetchone(self, sql: str, params: tuple | list = ()) -> Optional[dict]:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        if self.is_postgres:
            return DictRow(dict(row))
        return DictRow(dict(row))

    def fetchall(self, sql: str, params: tuple | list = ()) -> list[dict]:
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        if self.is_postgres:
            return [DictRow(dict(r)) for r in rows]
        return [DictRow(dict(r)) for r in rows]

    def commit(self):
        if self.conn:
            self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()


def get_db() -> DBConnection:
    """Return a new DBConnection instance."""
    return DBConnection()
