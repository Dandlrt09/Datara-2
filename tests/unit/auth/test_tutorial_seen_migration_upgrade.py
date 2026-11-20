"""Schema-upgrade probe for migration 0018 (first-boot-tutorial S3, D9).

Reconstructs an install that predates the tutorial flag: every migration through
0017 applied and recorded, plus one real user row. Then it runs the startup
migration runner and checks the upgrade is additive-only -- every pre-existing
column unchanged, the legacy row identical, the new column NOT NULL with the
documented default 0 -- and that the backfill marked the pre-existing profile as
"already seen" (D9), so only a profile created AFTER the migration starts at 0.
This is the risk-item-1 probe: the column lands on the table that login and /me
read.
"""

import sqlite3
from pathlib import Path

import pytest

from server.migrate import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
# Every migration on disk, in order. Derived so a later migration does not break
# this 0018 probe on an unrelated line.
ALL_VERSIONS = list(range(1, len(list(MIGRATIONS_DIR.glob("*.sql"))) + 1))
LAST_BEFORE_TUTORIAL = 17


@pytest.fixture
def legacy_db(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version > LAST_BEFORE_TUTORIAL:
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


def test_0018_backfills_existing_profiles_and_starts_new_ones_unseen(legacy_db):
    before = legacy_db["columns"]
    assert not any(column[0] == "tutorial_seen" for column in before)

    apply_migrations(legacy_db["path"])

    conn = sqlite3.connect(legacy_db["path"])
    after = [
        (r[1], r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(users)")
    ]
    # Every column that existed before is still there, unchanged, in order.
    # Filtered by the pre-upgrade set (not by this migration's own columns), so a
    # later migration does not fail this probe on an unrelated line.
    #
    # 0014 (F1 / T2a) is the one intended exception: it relaxes users.email and
    # users.password_hash to nullable so a local profile can exist without them,
    # while the row-level CHECK still demands both from a 'hosted' account. That
    # intent is recorded here instead of loosening the guard, which keeps pinning
    # the type, the default and the column order.
    intended_changes = {
        "email": ("email", "TEXT", 0, None),
        "password_hash": ("password_hash", "TEXT", 0, None),
    }
    expected = [intended_changes.get(column[0], column) for column in before]
    pre_existing = {column[0] for column in before}
    assert [column for column in after if column[0] in pre_existing] == expected
    # ("tutorial_seen", "INTEGER", notnull=1, default="0"): additive ALTER, so
    # a fresh profile -- created after this migration -- starts at "unseen" by
    # the column default (D9).
    assert [column for column in after if column[0] == "tutorial_seen"] == [
        ("tutorial_seen", "INTEGER", 1, "0")
    ]
    row_after = conn.execute(
        "SELECT id, email, password_hash, created_at, pending_deletion_at, "
        "sessions_notice_seen_session_id FROM users WHERE id = 1"
    ).fetchone()
    assert row_after == legacy_db["row"]
    # D9: the guided tour is for a NEW account, so a profile that already existed
    # is marked as already seen instead of being shown the tour on upgrade.
    assert conn.execute(
        "SELECT tutorial_seen FROM users WHERE id = 1"
    ).fetchone()[0] == 1
    # A profile created after the migration reads the documented default.
    conn.execute(
        "INSERT INTO users (email, password_hash) "
        "VALUES ('new@example.com', 'h2')"
    )
    new_row = conn.execute(
        "SELECT tutorial_seen FROM users WHERE email = 'new@example.com'"
    ).fetchone()[0]
    assert new_row == 0
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    conn.close()

    # A second startup applies nothing and does not resurrect the tour (S3).
    apply_migrations(legacy_db["path"])
    conn = sqlite3.connect(legacy_db["path"])
    versions = [
        r[0] for r in conn.execute("SELECT version FROM migrations ORDER BY version")
    ]
    assert versions == ALL_VERSIONS
    assert conn.execute(
        "SELECT tutorial_seen FROM users WHERE id = 1"
    ).fetchone()[0] == 1
    conn.close()
