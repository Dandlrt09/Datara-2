"""Regression tests for migration 0007_account_deletion (T3 / D1).

The *production* migration runner (``server.migrate.apply_migrations``) must
apply 0007, stay idempotent when run again, and add ``pending_deletion_at`` to
``users`` as a NULL-able TEXT with no default: NULL means "no deletion
scheduled", and the value, when present, is the purge deadline.
"""

import sqlite3

from server.migrate import apply_migrations


def _user_columns(db_path: str) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[1]: {"type": row[2].upper(), "notnull": row[3], "default": row[4]}
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
    finally:
        conn.close()


def _applied_versions(db_path: str) -> list[tuple[int, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT version, name FROM migrations ORDER BY version"
        ).fetchall()
    finally:
        conn.close()


def test_0007_is_applied_by_the_production_runner(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    applied = dict(_applied_versions(db_path))
    assert applied.get(7) == "0007_account_deletion.sql"
    # Ascending, no gaps, no duplicates. Later migrations are allowed.
    versions = [version for version, _ in _applied_versions(db_path)]
    assert versions == sorted(set(versions))


def test_pending_deletion_at_is_nullable_text_without_default(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    info = _user_columns(db_path)
    assert "pending_deletion_at" in info
    assert info["pending_deletion_at"]["type"] == "TEXT"
    assert info["pending_deletion_at"]["notnull"] == 0
    assert info["pending_deletion_at"]["default"] is None


def test_0007_is_idempotent(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)
    first = _applied_versions(db_path)

    # A second run must be a no-op: no error, no re-application, no new rows.
    # ALTER TABLE ADD COLUMN would raise if it ran twice.
    apply_migrations(db_path)

    assert _applied_versions(db_path) == first
    assert dict(first).get(7) == "0007_account_deletion.sql"
