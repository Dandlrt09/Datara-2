"""Shared test utilities for database bootstrap and migrations.

This module provides helpers to apply the full migration set in test fixtures.
"""

from pathlib import Path
import asyncio

from server.services.sqlite_store import SqliteStore

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "server" / "migrations"


async def apply_all_migrations(store: SqliteStore) -> None:
    """Apply all SQL migration files in sorted order to the given store.
    
    Args:
        store: An already-connected SqliteStore instance.
    """
    # Find all .sql files in migrations directory
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        raise RuntimeError(f"No migration files found in {MIGRATIONS_DIR}")
    
    # Apply each migration file in order
    for sql_file in sql_files:
        sql = sql_file.read_text(encoding="utf-8")
        await store.conn.executescript(sql)
    
    # Commit the changes
    await store.conn.commit()


async def create_test_store() -> SqliteStore:
    """Create and initialize a test store with all migrations applied.
    
    Returns:
        SqliteStore: A connected store ready for testing.
    """
    s = SqliteStore(db_path=":memory:")
    await s.connect()
    await apply_all_migrations(s)
    return s