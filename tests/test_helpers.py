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


def upload_csv(
    client,
    cookie: str,
    session_id: str,
    *,
    filename: str = "dataset.csv",
) -> None:
    """Attach a small CSV to a chat session via the files endpoint.

    The chat router refuses to run the sandbox when a session has no
    attached files (no-dataset guard), so integration tests that exercise
    the sandbox path must attach a dataset first. The CSV is fixed (3 rows)
    so profile-related assertions stay stable across callers.
    """
    content = b"name,age,score\nAlice,30,95.5\nBob,25,87.3\nCharlie,35,92.1\n"
    resp = client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (filename, content, "text/csv")},
        headers={"Cookie": cookie},
    )
    assert resp.status_code in (200, 201), resp.text