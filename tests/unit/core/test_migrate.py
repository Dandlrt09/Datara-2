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