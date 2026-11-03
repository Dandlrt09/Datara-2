"""Schema-upgrade probe for migration 0012 (S4/D1, risk item 1).

Rebuilds an install that predates email verification: every migration through
0011 applied and recorded, plus one real user row. Then it runs the startup
migration runner and checks the upgrade is additive-only -- every pre-existing
column unchanged, the legacy row identical, the new column nullable with no
default and NULL for the old row, the new token table present with its
constraint, and a second startup a no-op.
"""

import sqlite3
from pathlib import Path

from server.migrate import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
ALL_VERSIONS = list(range(1, len(list(MIGRATIONS_DIR.glob("*.sql"))) + 1))
LAST_BEFORE_VERIFICATION = 11

_TOKEN_COLUMNS = [
    ("id", "INTEGER", 0, None),
    ("user_id", "INTEGER", 1, None),
    ("token_hash", "TEXT", 1, None),
    ("purpose", "TEXT", 1, None),
    ("email", "TEXT", 0, None),
    ("created_at", "TEXT", 1, "datetime('now')"),
    ("expires_at", "TEXT", 1, None),
    ("used_at", "TEXT", 0, None),
]


def _legacy_db(tmp_path) -> dict:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version > LAST_BEFORE_VERIFICATION:
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO migrations (version, name) VALUES (?, ?)",
            (version, sql_file.name),
        )
    conn.execute(
        "INSERT INTO users (email, password_hash) VALUES ('legacy@example.com', 'h1')"
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, email, password_hash, created_at, pending_deletion_at, "
        "sessions_notice_seen_session_id, terms_version, terms_accepted_at "
        "FROM users WHERE id = 1"
    ).fetchone()
    columns = [
        (r[1], r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(users)")
    ]
    conn.close()
    return {"path": str(db_path), "row": row, "columns": columns}


def test_0012_upgrade_is_additive_and_legacy_rows_read_as_unverified(tmp_path):
    legacy = _legacy_db(tmp_path)
    before = legacy["columns"]
    assert not any(column[0] == "email_verified_at" for column in before)

    apply_migrations(legacy["path"])

    conn = sqlite3.connect(legacy["path"])
    after = [
        (r[1], r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(users)")
    ]
    # Every pre-existing column is still there, unchanged and in order.
    pre_existing = {column[0] for column in before}
    assert [column for column in after if column[0] in pre_existing] == before
    # The new column is nullable with no default: an old account reads as
    # "never verified", which is exactly its history (D1).
    assert [column for column in after if column[0] == "email_verified_at"] == [
        ("email_verified_at", "TEXT", 0, None)
    ]
    row_after = conn.execute(
        "SELECT id, email, password_hash, created_at, pending_deletion_at, "
        "sessions_notice_seen_session_id, terms_version, terms_accepted_at "
        "FROM users WHERE id = 1"
    ).fetchone()
    assert row_after == legacy["row"]
    assert (
        conn.execute("SELECT email_verified_at FROM users WHERE id = 1").fetchone()[0]
        is None
    )
    # The token table and both indexes landed.
    token_columns = [
        (r[1], r[2], r[3], r[4])
        for r in conn.execute("PRAGMA table_info(auth_tokens)")
    ]
    assert token_columns == _TOKEN_COLUMNS
    indexes = {r[1] for r in conn.execute("PRAGMA index_list(auth_tokens)")}
    assert {"idx_auth_tokens_user_purpose", "idx_auth_tokens_expires"} <= indexes
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    conn.close()

    # A second startup applies nothing and does not disturb the legacy row.
    apply_migrations(legacy["path"])
    conn = sqlite3.connect(legacy["path"])
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    assert (
        conn.execute("SELECT email_verified_at FROM users WHERE id = 1").fetchone()[0]
        is None
    )
    conn.close()
