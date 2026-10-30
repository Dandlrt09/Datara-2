"""Schema-upgrade probes for migration 0009 (T1/S3/S4/D1).

Reconstructs a pre-T1 install: migrations 1-8 applied and recorded plus one real
user row. Then it runs the startup migration runner and checks the upgrade is
additive-only -- every pre-existing column unchanged, the legacy row identical,
``name`` nullable with no default and NULL, and a second startup a no-op. This is
the risk-item-1 probe: the column lands on a table login and /me read.
"""

import sqlite3
from pathlib import Path

import pytest

from server.migrate import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
# Every migration on disk, in order. Derived so a later migration does not
# break this 0009 probe on an unrelated line.
ALL_VERSIONS = list(range(1, len(list(MIGRATIONS_DIR.glob("*.sql"))) + 1))


@pytest.fixture
def legacy_db(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version > 8:
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


def test_0009_upgrade_is_additive_and_legacy_rows_stay_null(legacy_db):
    before = legacy_db["columns"]
    assert not any(column[0] == "name" for column in before)

    apply_migrations(legacy_db["path"])

    conn = sqlite3.connect(legacy_db["path"])
    after = [
        (r[1], r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(users)")
    ]
    # Every column that existed before is still there, unchanged, in order.
    # The filter is the set seen *before* the upgrade, not the columns this
    # migration adds: a later migration introducing its own column (0011 did)
    # must not make this probe fail on an unrelated line.
    pre_existing = {column[0] for column in before}
    assert [column for column in after if column[0] in pre_existing] == before
    # ("name", "TEXT", notnull=0, default=None) -> nullable, no default (D1).
    assert [column for column in after if column[0] == "name"] == [
        ("name", "TEXT", 0, None)
    ]
    row_after = conn.execute(
        "SELECT id, email, password_hash, created_at, pending_deletion_at, "
        "sessions_notice_seen_session_id FROM users WHERE id = 1"
    ).fetchone()
    assert row_after == legacy_db["row"]
    assert conn.execute("SELECT name FROM users WHERE id = 1").fetchone()[0] is None
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    conn.close()

    # A second startup applies nothing and does not disturb the legacy row (S3).
    apply_migrations(legacy_db["path"])
    conn = sqlite3.connect(legacy_db["path"])
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    assert conn.execute("SELECT name FROM users WHERE id = 1").fetchone()[0] is None
    conn.close()
