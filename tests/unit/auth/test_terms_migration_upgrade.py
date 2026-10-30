"""Schema-upgrade probes for migration 0011 (terms-of-use S6/D4).

Reconstructs an install that predates the terms: every migration through 0010
applied and recorded, plus one real user row. Then it runs the startup migration
runner and checks the upgrade is additive-only -- every pre-existing column
unchanged, the legacy row identical, both new columns nullable with no default
and NULL, and a second startup a no-op. This is the risk-item-1 probe: the
columns land on the table that login and /me read.
"""

import sqlite3
from pathlib import Path

import pytest

from server.migrate import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
# Every migration on disk, in order. Derived so a later migration does not break
# this 0011 probe on an unrelated line.
ALL_VERSIONS = list(range(1, len(list(MIGRATIONS_DIR.glob("*.sql"))) + 1))
LAST_BEFORE_TERMS = 10


@pytest.fixture
def legacy_db(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version > LAST_BEFORE_TERMS:
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
        "sessions_notice_seen_session_id FROM users WHERE id = 1"
    ).fetchone()
    columns = [
        (r[1], r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(users)")
    ]
    conn.close()
    return {"path": str(db_path), "row": row, "columns": columns}


def test_0011_upgrade_is_additive_and_legacy_rows_carry_no_acceptance(legacy_db):
    before = legacy_db["columns"]
    assert not any(column[0] == "terms_version" for column in before)

    apply_migrations(legacy_db["path"])

    conn = sqlite3.connect(legacy_db["path"])
    after = [
        (r[1], r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(users)")
    ]
    # Every column that existed before is still there, unchanged, in order.
    # Filtered by the pre-upgrade set (not by this migration's own columns),
    # so a later migration does not fail this probe on an unrelated line.
    new_names = {"terms_version", "terms_accepted_at"}
    pre_existing = {column[0] for column in before}
    assert [column for column in after if column[0] in pre_existing] == before
    # ("terms_version", "TEXT", notnull=0, default=None) and the same for the
    # date: nullable and with no default, so an old row reads as "never
    # accepted" instead of being assigned a version it never agreed to (D4).
    assert [column for column in after if column[0] in new_names] == [
        ("terms_version", "TEXT", 0, None),
        ("terms_accepted_at", "TEXT", 0, None),
    ]
    row_after = conn.execute(
        "SELECT id, email, password_hash, created_at, pending_deletion_at, "
        "sessions_notice_seen_session_id FROM users WHERE id = 1"
    ).fetchone()
    assert row_after == legacy_db["row"]
    acceptance = conn.execute(
        "SELECT terms_version, terms_accepted_at FROM users WHERE id = 1"
    ).fetchone()
    assert acceptance == (None, None)
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    conn.close()

    # A second startup applies nothing and does not disturb the legacy row (S6).
    apply_migrations(legacy_db["path"])
    conn = sqlite3.connect(legacy_db["path"])
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    assert conn.execute(
        "SELECT terms_version FROM users WHERE id = 1"
    ).fetchone()[0] is None
    conn.close()
