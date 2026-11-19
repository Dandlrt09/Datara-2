"""Schema-upgrade probe for migration 0014 (F1 / T2a, D1; risk item 1).

0014 rebuilds ``users`` so a local profile can exist without an email or a
password. SQLite cannot drop a NOT NULL, so the table is recreated -- and every
child table points at it with ON DELETE CASCADE. Dropping ``users`` with foreign
keys enforced would silently delete every chat, file and setting. These tests
pin the whole point of the migration: a populated install comes out the other
side with every row of every table intact.
"""

import sqlite3
from pathlib import Path

import pytest

from server.migrate import apply_migrations, run_pending_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
LAST_BEFORE_KIND = 13
CHILD_TABLES = [
    "auth_sessions",
    "chat_sessions",
    "files",
    "profiles",
    "messages",
    "archives",
    "user_settings",
    "auth_tokens",
    "auth_attempts",
]


def _apply_through(conn: sqlite3.Connection, last: int) -> None:
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version > last:
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO migrations (version, name) VALUES (?, ?)",
            (version, sql_file.name),
        )


def _populated_legacy_db(tmp_path) -> str:
    """An install at 0013 with data in users and in every child table."""
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    _apply_through(conn, LAST_BEFORE_KIND)
    conn.execute("PRAGMA foreign_keys=ON")
    # A deleted highest id: AUTOINCREMENT must never hand it out again.
    conn.execute("INSERT INTO users (email, password_hash) VALUES ('gone@x.com', 'h0')")
    conn.execute(
        "INSERT INTO users (email, password_hash, name, terms_version, "
        "terms_accepted_at, email_verified_at, pending_deletion_at) "
        "VALUES ('ana@example.com', 'h1', 'Ana', 'v1', '2026-01-01', '2026-01-02', NULL)"
    )
    conn.execute("INSERT INTO users (email, password_hash) VALUES ('bob@example.com', 'h2')")
    conn.execute("DELETE FROM users WHERE email = 'gone@x.com'")
    for uid in (2, 3):
        conn.execute(
            "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
            "VALUES (?, ?, '2099-01-01')",
            (uid, f"tok{uid}"),
        )
        conn.execute("INSERT INTO chat_sessions (id, user_id) VALUES (?, ?)", (f"c{uid}", uid))
        conn.execute(
            "INSERT INTO files (user_id, chat_session, filename, storage_path, "
            "size_bytes, format) VALUES (?, ?, 'a.csv', '/p', 10, 'csv')",
            (uid, f"c{uid}"),
        )
        conn.execute(
            "INSERT INTO messages (user_id, chat_session, role, content_text) "
            "VALUES (?, ?, 'user', 'hola')",
            (uid, f"c{uid}"),
        )
        conn.execute(
            "INSERT INTO archives (user_id, name, payload_json) VALUES (?, 'n', '{}')",
            (uid,),
        )
        conn.execute("INSERT INTO user_settings (user_id) VALUES (?)", (uid,))
        conn.execute(
            "INSERT INTO auth_tokens (user_id, token_hash, purpose, expires_at) "
            "VALUES (?, ?, 'verify_email', '2099-01-01')",
            (uid, f"at{uid}"),
        )
    conn.execute(
        "INSERT INTO profiles (file_id, schema_json, stats_json, sample_json) "
        "SELECT id, '{}', '{}', '{}' FROM files"
    )
    conn.commit()
    conn.close()
    return db_path


def _dump(db_path: str, table: str, columns: str = "*") -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT {columns} FROM {table} ORDER BY 1, 2").fetchall()
    finally:
        conn.close()


_USER_COLS = (
    "id, email, password_hash, created_at, pending_deletion_at, "
    "sessions_notice_seen_session_id, name, terms_version, terms_accepted_at, "
    "email_verified_at"
)


def test_upgrade_keeps_every_row_of_every_table(tmp_path):
    db = _populated_legacy_db(tmp_path)
    before = {t: _dump(db, t) for t in CHILD_TABLES}
    before_users = _dump(db, "users", _USER_COLS)
    assert len(before_users) == 2
    assert all(len(before[t]) >= 0 for t in CHILD_TABLES)
    assert len(before["messages"]) == 2 and len(before["files"]) == 2

    apply_migrations(db)

    assert _dump(db, "users", _USER_COLS) == before_users
    for table in CHILD_TABLES:
        assert _dump(db, table) == before[table], f"{table} changed in the upgrade"


def test_upgrade_leaves_no_orphans_and_keeps_the_foreign_keys(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)

    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    for table in (
        "auth_sessions", "chat_sessions", "files", "messages",
        "archives", "user_settings", "auth_tokens",
    ):
        targets = {r[2] for r in conn.execute(f"PRAGMA foreign_key_list({table})")}
        assert "users" in targets, f"{table} no longer references users"
    conn.close()


def test_cascade_delete_still_works_after_the_upgrade(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)

    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("DELETE FROM users WHERE id = 2")
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE user_id = 2").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE user_id = 3").fetchone()[0] == 1
    conn.close()


def test_existing_accounts_become_hosted_and_email_and_password_become_optional(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)

    conn = sqlite3.connect(db)
    assert {r[0] for r in conn.execute("SELECT kind FROM users")} == {"hosted"}
    info = {r[1]: r for r in conn.execute("PRAGMA table_info(users)")}
    assert info["email"][3] == 0, "email must be nullable"
    assert info["password_hash"][3] == 0, "password_hash must be nullable"
    assert info["kind"][3] == 1 and info["kind"][4] == "'hosted'"
    conn.close()


def test_local_profiles_need_no_email_and_hosted_ones_still_do(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO users (kind, name) VALUES ('local', 'Ana local')")
    conn.execute("INSERT INTO users (kind, name) VALUES ('local', 'Otra')")  # many NULLs ok
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO users (email, password_hash) VALUES (NULL, 'h')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO users (kind, email) VALUES ('hosted', 'x@y.com')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO users (kind) VALUES ('robot')")
    conn.close()


def test_email_uniqueness_survives_case_insensitively(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)

    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES ('ANA@example.com', 'h')"
        )
    conn.close()


def test_the_other_users_indexes_are_recreated(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)

    conn = sqlite3.connect(db)
    names = {r[1] for r in conn.execute("PRAGMA index_list(users)")}
    assert {"idx_users_email_nocase", "idx_users_pending_deletion"} <= names
    conn.close()


def test_a_deleted_id_is_never_reused(tmp_path):
    db = _populated_legacy_db(tmp_path)  # id 1 was created and deleted
    apply_migrations(db)

    conn = sqlite3.connect(db)
    new_id = conn.execute(
        "INSERT INTO users (email, password_hash) VALUES ('new@x.com', 'h')"
    ).lastrowid
    assert new_id == 4
    conn.close()


def test_a_backup_of_the_old_database_is_written_before_the_rebuild(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)

    backup = Path(db + ".pre-0014.bak")
    assert backup.exists()
    old = sqlite3.connect(str(backup))
    assert "kind" not in {r[1] for r in old.execute("PRAGMA table_info(users)")}
    assert old.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
    assert old.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
    old.close()


def test_a_brand_new_database_needs_no_backup(tmp_path):
    db = str(tmp_path / "fresh.db")
    apply_migrations(db)

    assert not Path(db + ".pre-0014.bak").exists()


def test_foreign_keys_are_enforced_again_after_the_migration(tmp_path):
    db = _populated_legacy_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys=ON")
    run_pending_migrations(conn)

    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_second_startup_is_a_no_op(tmp_path):
    db = _populated_legacy_db(tmp_path)
    apply_migrations(db)
    snapshot = {t: _dump(db, t) for t in CHILD_TABLES}

    apply_migrations(db)

    assert {t: _dump(db, t) for t in CHILD_TABLES} == snapshot
    versions = [r[0] for r in sqlite3.connect(db).execute("SELECT version FROM migrations")]
    assert versions.count(14) == 1


def test_an_orphan_aborts_the_migration_and_leaves_the_old_schema_untouched(tmp_path):
    """The guard turns a bad rebuild into a loud, fully rolled-back failure."""
    db = _populated_legacy_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys=OFF")  # how an orphan gets in at all
    conn.execute("INSERT INTO user_settings (user_id) VALUES (999)")
    conn.commit()
    before_users = _dump(db, "users", _USER_COLS)
    before_messages = _dump(db, "messages")
    conn.close()

    with pytest.raises(sqlite3.Error):
        apply_migrations(db)

    check = sqlite3.connect(db)
    columns = {r[1] for r in check.execute("PRAGMA table_info(users)")}
    assert "kind" not in columns, "the failed migration must roll back completely"
    assert 14 not in {r[0] for r in check.execute("SELECT version FROM migrations")}
    assert check.execute("SELECT name FROM sqlite_master WHERE name = 'users_new'").fetchone() is None
    check.close()
    assert _dump(db, "users", _USER_COLS) == before_users
    assert _dump(db, "messages") == before_messages


def test_foreign_keys_come_back_on_even_when_the_migration_fails(tmp_path):
    db = _populated_legacy_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO user_settings (user_id) VALUES (999)")
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")

    with pytest.raises(sqlite3.Error):
        run_pending_migrations(conn)

    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()
