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