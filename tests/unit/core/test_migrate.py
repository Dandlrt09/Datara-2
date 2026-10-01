"""Tests for the migration system."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from server.migrate import apply_migrations, get_applied_versions, run_pending_migrations


class TestGetAppliedVersions:
    def test_no_migrations_table(self):
        conn = sqlite3.connect(":memory:")
        result = get_applied_versions(conn)
        assert result == set()

    def test_empty_migrations(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT)")
        result = get_applied_versions(conn)
        assert result == set()

    def test_with_migrations(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT)")
        conn.execute("INSERT INTO migrations (version, name) VALUES (1, '0001_init.sql')")
        result = get_applied_versions(conn)
        assert result == {1}


class TestRunPendingMigrations:
    @pytest.fixture
    def conn(self):
        return sqlite3.connect(":memory:")

    def test_applies_pending(self, conn, tmp_path):
        migration_file = tmp_path / "0001_test.sql"
        migration_file.write_text("CREATE TABLE test_table (id INTEGER PRIMARY KEY);")
        import server.migrate as m
        original_dir = m.MIGRATIONS_DIR
        m.MIGRATIONS_DIR = tmp_path
        try:
            run_pending_migrations(conn)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
            assert cursor.fetchone() is not None
            applied = get_applied_versions(conn)
            assert 1 in applied
        finally:
            m.MIGRATIONS_DIR = original_dir

    def test_skips_applied(self, conn, tmp_path):
        conn.execute("CREATE TABLE migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT)")
        conn.execute("INSERT INTO migrations (version, name) VALUES (1, '0001_test.sql')")
        migration_file = tmp_path / "0001_test.sql"
        migration_file.write_text("CREATE TABLE test_table (id INTEGER PRIMARY KEY);")
        import server.migrate as m
        original_dir = m.MIGRATIONS_DIR
        m.MIGRATIONS_DIR = tmp_path
        try:
            run_pending_migrations(conn)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            names = [row[0] for row in cursor.fetchall()]
            assert "test_table" not in names
        finally:
            m.MIGRATIONS_DIR = original_dir

    def test_applies_multiple_in_order(self, conn, tmp_path):
        (tmp_path / "0001_a.sql").write_text("CREATE TABLE tbl_a (id INTEGER PRIMARY KEY);")
        (tmp_path / "0002_b.sql").write_text("CREATE TABLE tbl_b (id INTEGER PRIMARY KEY);")
        import server.migrate as m
        original_dir = m.MIGRATIONS_DIR
        m.MIGRATIONS_DIR = tmp_path
        try:
            run_pending_migrations(conn)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tbl_%'")
            names = [row[0] for row in cursor.fetchall()]
            assert "tbl_a" in names
            assert "tbl_b" in names
            applied = get_applied_versions(conn)
            assert applied == {1, 2}
        finally:
            m.MIGRATIONS_DIR = original_dir


class TestApplyMigrations:
    def test_applies_init_sql(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            apply_migrations(db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {row[0] for row in cursor.fetchall()}
            assert "migrations" in tables
            assert "users" in tables
            assert "auth_sessions" in tables
            assert "chat_sessions" in tables
            assert "files" in tables
            assert "profiles" in tables
            assert "messages" in tables
            assert "archives" in tables
            assert "user_settings" in tables
            conn.close()
        finally:
            import os
            os.unlink(db_path)

    def test_migration_0002_preserves_existing_rows(self):
        """Test that 0002_provider_settings.sql migration preserves existing rows/keys
        and adds NULL columns (spec: Provider settings persistence)."""
        import tempfile
        import sqlite3
        
        # Create a temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # First apply initial schema (0001) ONLY
            # We need to apply 0001 but not 0002 yet
            from server.migrate import MIGRATIONS_DIR
            migration_0001_path = MIGRATIONS_DIR / "0001_init.sql"
            conn = sqlite3.connect(db_path)
            conn.executescript(migration_0001_path.read_text(encoding="utf-8"))
            # Create migrations table and record 0001 as applied
            conn.execute(
                "CREATE TABLE IF NOT EXISTS migrations ("
                "  version INTEGER PRIMARY KEY,"
                "  name TEXT NOT NULL,"
                "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
                ")"
            )
            conn.execute(
                "INSERT INTO migrations (version, name) VALUES (?, ?)",
                (1, "0001_init.sql")
            )
            conn.commit()
            
            # Insert a user
            conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("test@example.com", "hash123")
            )
            user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Insert settings with the OLD schema (before 0002)
            conn.execute(
                "INSERT INTO user_settings (user_id, api_key_enc, default_model) VALUES (?, ?, ?)",
                (user_id, "encrypted_key_abc", "gpt-4o")
            )
            conn.commit()
            
            # Now apply 0002 migration via the migration runner
            from server.migrate import run_pending_migrations
            run_pending_migrations(conn)
            conn.commit()
            
            # Verify the row still exists with all original values
            cursor = conn.execute(
                "SELECT user_id, api_key_enc, default_model, provider_type, base_url FROM user_settings WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == user_id
            assert row[1] == "encrypted_key_abc"
            assert row[2] == "gpt-4o"
            # New columns should be NULL
            assert row[3] is None  # provider_type
            assert row[4] is None  # base_url
            
            # Also verify the migration was recorded
            cursor = conn.execute("SELECT version FROM migrations ORDER BY version")
            versions = [row[0] for row in cursor.fetchall()]
            assert 1 in versions
            assert 2 in versions
            
            conn.close()
        finally:
            import os
            os.unlink(db_path)

    def test_migration_0005_preserves_archives_and_survives_session_delete(self):
        """0005 makes archives outlive their chat session.

        Apply 0001 only, seed a user/session/archive under the OLD schema, then
        run the pending migrations and assert: (a) the archive row survived
        unchanged, (b) deleting the session sets ``chat_session`` to NULL and
        the archive still exists, (c) the lookup index exists, and (d) the
        ``chat_session`` column is nullable.
        """
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            from server.migrate import MIGRATIONS_DIR, run_pending_migrations

            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(
                (MIGRATIONS_DIR / "0001_init.sql").read_text(encoding="utf-8")
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS migrations ("
                "  version INTEGER PRIMARY KEY,"
                "  name TEXT NOT NULL,"
                "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
                ")"
            )
            conn.execute(
                "INSERT INTO migrations (version, name) VALUES (?, ?)",
                (1, "0001_init.sql"),
            )

            # Seed with the OLD schema (chat_session NOT NULL, ON DELETE CASCADE).
            conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("archives@example.com", "hash123"),
            )
            user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
                ("s1", user_id, "Session"),
            )
            conn.execute(
                "INSERT INTO archives (user_id, name, chat_session, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, "My archive", "s1", '{"v": 1}', "2026-01-01 00:00:00"),
            )
            archive_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()

            run_pending_migrations(conn)

            # (a) The row survived byte-for-byte, ids included.
            row = conn.execute(
                "SELECT id, user_id, name, chat_session, payload_json, created_at "
                "FROM archives WHERE id = ?",
                (archive_id,),
            ).fetchone()
            assert row == (
                archive_id, user_id, "My archive", "s1",
                '{"v": 1}', "2026-01-01 00:00:00",
            )

            # (c) The new lookup index exists.
            index = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='idx_archives_user_created'"
            ).fetchone()
            assert index is not None

            # (d) chat_session is nullable (PRAGMA notnull == 0).
            columns = {
                c[1]: c for c in conn.execute("PRAGMA table_info(archives)").fetchall()
            }
            assert columns["chat_session"][3] == 0

            # (b) Deleting the session nulls chat_session and keeps the archive.
            conn.execute("DELETE FROM chat_sessions WHERE id = 's1'")
            conn.commit()
            row = conn.execute(
                "SELECT chat_session FROM archives WHERE id = ?", (archive_id,)
            ).fetchone()
            assert row is not None
            assert row[0] is None

            assert 5 in get_applied_versions(conn)
            conn.close()
        finally:
            import os
            os.unlink(db_path)


class TestMigration0004CaseInsensitiveFiles:
    """F12.1: 0004 recreates ``idx_files_unique_name`` with COLLATE NOCASE.

    Three properties: the index folds case; a pre-existing case-variant pair
    survives the guard (both rows kept, the non-lowest id renamed, none
    deleted); and the recreated index rejects a new case-variant insert.
    """

    @pytest.fixture
    def conn(self):
        return sqlite3.connect(":memory:")

    def _apply_through_0003(self, conn):
        """Apply migrations 1-3 and record them, leaving a version-3 DB."""
        from server.migrate import MIGRATIONS_DIR

        for version, name in (
            (1, "0001_init.sql"),
            (2, "0002_provider_settings.sql"),
            (3, "0003_files_unique_name.sql"),
        ):
            conn.executescript(
                (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS migrations ("
                "  version INTEGER PRIMARY KEY,"
                "  name TEXT NOT NULL,"
                "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
                ")"
            )
            conn.execute(
                "INSERT INTO migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
        conn.commit()

    def _seed_case_variant_pair(self, conn):
        """Insert CASE.csv (lowest id) + case.csv in one session; return ids."""
        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES ('case@example.com', 'h')"
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO chat_sessions (id, user_id) VALUES ('s1', ?)", (user_id,)
        )
        conn.execute(
            "INSERT INTO files (user_id, chat_session, filename, storage_path, "
            "size_bytes, format) VALUES (?, 's1', 'CASE.csv', '/tmp/1.csv', 1, 'csv')",
            (user_id,),
        )
        first_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO files (user_id, chat_session, filename, storage_path, "
            "size_bytes, format) VALUES (?, 's1', 'case.csv', '/tmp/2.csv', 1, 'csv')",
            (user_id,),
        )
        second_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        return user_id, first_id, second_id

    def test_index_sql_contains_collate_nocase(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            apply_migrations(db_path)
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='index' AND name='idx_files_unique_name'"
            ).fetchone()
            assert row is not None
            assert "COLLATE NOCASE" in row[0]
            conn.close()
        finally:
            import os
            os.unlink(db_path)

    def test_guard_renames_case_variant_pair_and_deletes_nothing(self, conn):
        self._apply_through_0003(conn)
        _, first_id, second_id = self._seed_case_variant_pair(conn)

        run_pending_migrations(conn)

        rows = dict(conn.execute("SELECT id, filename FROM files").fetchall())
        # BOTH rows survive — the guard renames, it never deletes.
        assert len(rows) == 2
        assert rows[first_id] == "CASE.csv"
        assert rows[second_id] == f"case.csv (dup-{second_id})"
        assert 4 in get_applied_versions(conn)

    def test_new_case_variant_insert_is_rejected_after_0004(self, conn):
        self._apply_through_0003(conn)
        user_id, _, _ = self._seed_case_variant_pair(conn)

        run_pending_migrations(conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO files (user_id, chat_session, filename, "
                "storage_path, size_bytes, format) "
                "VALUES (?, 's1', 'Case.CSV', '/tmp/3.csv', 1, 'csv')",
                (user_id,),
            )