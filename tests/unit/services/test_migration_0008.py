"""Regression tests for migration 0008_active_sessions (T2 / D1, D2, D9).

The *production* migration runner (``server.migrate.apply_migrations``) must
apply 0008, stay idempotent, and add two NULL-able TEXT columns:

- ``auth_sessions.user_agent`` holds the truncated user-agent header of the
  session that was opened (D2: no IP is ever stored).
- ``users.sessions_notice_seen_session_id`` holds the newest *other* session id
  the user acknowledged, so the notice shows once per user and not once per
  browser (D9).
"""

import shutil
import sqlite3

from server import migrate
from server.migrate import apply_migrations


def _columns(db_path: str, table: str) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[1]: {"type": row[2].upper(), "notnull": row[3], "default": row[4]}
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
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


def test_0008_is_applied_by_the_production_runner(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    applied = dict(_applied_versions(db_path))
    assert applied.get(8) == "0008_active_sessions.sql"
    versions = [version for version, _ in _applied_versions(db_path)]
    assert versions == sorted(set(versions))


def test_auth_sessions_user_agent_is_nullable_text_without_default(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    info = _columns(db_path, "auth_sessions")
    assert info["user_agent"]["type"] == "TEXT"
    assert info["user_agent"]["notnull"] == 0
    assert info["user_agent"]["default"] is None


def test_sessions_notice_seen_session_id_is_nullable_integer(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    info = _columns(db_path, "users")
    assert info["sessions_notice_seen_session_id"]["type"] == "INTEGER"
    assert info["sessions_notice_seen_session_id"]["notnull"] == 0
    assert info["sessions_notice_seen_session_id"]["default"] is None


def test_0008_applies_to_a_database_that_already_holds_rows(tmp_path, monkeypatch):
    """Risk item 1: an ALTER that breaks on real data would break the upgrade.

    The pre-0008 schema is applied from a copy of the previous migrations, rows
    are inserted, and only then is 0008 applied.
    """
    previous_dir = tmp_path / "migrations-0001-0007"
    previous_dir.mkdir()
    for path in sorted(migrate.MIGRATIONS_DIR.glob("0*.sql")):
        if not path.name.startswith("0008"):
            shutil.copy(path, previous_dir / path.name)

    db_path = str(tmp_path / "datara.db")
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", previous_dir)
    apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'hash')"
    )
    user_id = conn.execute("SELECT id FROM users").fetchone()[0]
    conn.execute(
        "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
        "VALUES (?, 'th_existing', datetime('now', '+8 hours'))",
        (user_id,),
    )
    conn.commit()
    conn.close()

    monkeypatch.undo()
    apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT token_hash, user_agent FROM auth_sessions"
        ).fetchone()
        notice_mark = conn.execute(
            "SELECT sessions_notice_seen_session_id FROM users"
        ).fetchone()
    finally:
        conn.close()

    assert existing == ("th_existing", None)
    assert notice_mark == (None,)


def test_0008_is_idempotent(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)
    first = _applied_versions(db_path)

    # A second run must be a no-op: ALTER TABLE ADD COLUMN would raise if it ran
    # twice.
    apply_migrations(db_path)

    assert _applied_versions(db_path) == first
    assert dict(first).get(8) == "0008_active_sessions.sql"
