"""Tests for SqliteStore CRUD operations.

All tests use an in-memory SQLite database with the init schema applied.
"""

from pathlib import Path

import pytest

from server.services.sqlite_store import SqliteStore

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
INIT_SQL_PATH = MIGRATIONS_DIR / "0001_init.sql"


@pytest.fixture
async def store():
    s = SqliteStore(db_path=":memory:")
    await s.connect()
    # Apply schema directly on the aiosqlite connection
    init_sql = INIT_SQL_PATH.read_text(encoding="utf-8")
    await s.conn.executescript(init_sql)
    # Apply migration 0002 if it exists
    migration_0002_path = MIGRATIONS_DIR / "0002_provider_settings.sql"
    if migration_0002_path.exists():
        migration_sql = migration_0002_path.read_text(encoding="utf-8")
        await s.conn.executescript(migration_sql)
    await s.conn.commit()
    yield s
    await s.close()


class TestUsers:
    async def test_create_user(self, store):
        user = await store.create_user("alice@example.com", "hash123")
        assert user["email"] == "alice@example.com"
        assert user["password_hash"] == "hash123"
        assert "id" in user

    async def test_create_duplicate_email(self, store):
        await store.create_user("alice@example.com", "hash1")
        from core.errors import DuplicateError
        with pytest.raises(DuplicateError, match="already exists"):
            await store.create_user("alice@example.com", "hash2")

    async def test_get_user_by_email_found(self, store):
        created = await store.create_user("bob@example.com", "hash456")
        found = await store.get_user_by_email("bob@example.com")
        assert found is not None
        assert found["id"] == created["id"]

    async def test_get_user_by_email_not_found(self, store):
        found = await store.get_user_by_email("nobody@example.com")
        assert found is None

    async def test_get_user_by_id_found(self, store):
        created = await store.create_user("carol@example.com", "hash789")
        found = await store.get_user_by_id(created["id"])
        assert found is not None
        assert found["email"] == "carol@example.com"

    async def test_get_user_by_id_not_found(self, store):
        assert await store.get_user_by_id(999) is None


class TestAuthSessions:
    async def test_create_session(self, store):
        user = await store.create_user("alice@example.com", "hash")
        session = await store.create_auth_session(user["id"], "token_hash_abc")
        assert session["user_id"] == user["id"]
        assert session["token_hash"] == "token_hash_abc"
        assert "expires_at" in session

    async def test_lookup_by_token_hash_valid(self, store):
        user = await store.create_user("alice@example.com", "hash")
        created = await store.create_auth_session(user["id"], "th_valid")
        found = await store.get_auth_session_by_token_hash("th_valid")
        assert found is not None
        assert found["id"] == created["id"]

    async def test_lookup_by_token_hash_not_found(self, store):
        assert await store.get_auth_session_by_token_hash("nonexistent") is None

    async def test_delete_session(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_del")
        await store.delete_auth_session("th_del")
        assert await store.get_auth_session_by_token_hash("th_del") is None

    async def test_sweep_expired(self, store):
        """Create a session with a negative TTL so it is already expired,
        then sweep and verify it is gone."""
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_expired", ttl_seconds=-1)
        count = await store.sweep_expired_sessions()
        assert count >= 1
        assert await store.get_auth_session_by_token_hash("th_expired") is None


class TestChatSessions:
    async def test_create_and_list(self, store):
        user = await store.create_user("alice@example.com", "hash")
        created = await store.create_chat_session("ses_001", user["id"], "My chat")
        assert created["id"] == "ses_001"
        assert created["title"] == "My chat"

        sessions = await store.list_chat_sessions(user["id"])
        assert len(sessions) == 1
        assert sessions[0]["id"] == "ses_001"

    async def test_get_chat_session_owned(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_chat_session("ses_002", user["id"])
        found = await store.get_chat_session("ses_002", user["id"])
        assert found is not None

    async def test_get_chat_session_not_owned(self, store):
        user_a = await store.create_user("a@example.com", "hash1")
        user_b = await store.create_user("b@example.com", "hash2")
        await store.create_chat_session("ses_003", user_a["id"])
        # User B should not see user A's session
        found = await store.get_chat_session("ses_003", user_b["id"])
        assert found is None

    async def test_list_sessions_only_owned(self, store):
        user_a = await store.create_user("a@example.com", "hash1")
        user_b = await store.create_user("b@example.com", "hash2")
        await store.create_chat_session("ses_a1", user_a["id"])
        await store.create_chat_session("ses_a2", user_a["id"])
        await store.create_chat_session("ses_b1", user_b["id"])

        a_sessions = await store.list_chat_sessions(user_a["id"])
        assert len(a_sessions) == 2

        b_sessions = await store.list_chat_sessions(user_b["id"])
        assert len(b_sessions) == 1

    async def test_delete_chat_session_owned(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_chat_session("ses_del", user["id"])
        await store.delete_chat_session("ses_del", user["id"])
        found = await store.get_chat_session("ses_del", user["id"])
        assert found is None

    async def test_delete_chat_session_not_owned_noop(self, store):
        user_a = await store.create_user("a@example.com", "hash1")
        user_b = await store.create_user("b@example.com", "hash2")
        await store.create_chat_session("ses_nod", user_a["id"])
        # Delete by user_b — should not delete (no error raised, but no deletion)
        await store.delete_chat_session("ses_nod", user_b["id"])
        found = await store.get_chat_session("ses_nod", user_a["id"])
        assert found is not None


class TestWALMode:
    """Task 5.4: Verify WAL journal mode is active.

    WAL mode requires a file-based database; :memory: databases always
    return 'memory' for PRAGMA journal_mode. This test uses a temp file.
    """

    async def test_wal_mode(self):
        """PRAGMA journal_mode should return 'wal' for a file-based store."""
        import tempfile
        import os

        # Use a temp file so WAL mode can be activated
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            s = SqliteStore(db_path=db_path)
            await s.connect()
            cursor = await s.conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            journal_mode = row[0] if row else ""
            await s.close()
            assert "wal" in journal_mode.lower(), (
                f"Expected WAL mode, got {journal_mode}"
            )
        finally:
            # Clean up the temp file and any WAL/SHM files
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(db_path + suffix)
                except FileNotFoundError:
                    pass


class TestUserSettings:
    async def test_get_empty(self, store):
        user = await store.create_user("alice@example.com", "hash")
        assert await store.get_user_settings(user["id"]) is None

    async def test_upsert_create(self, store):
        user = await store.create_user("alice@example.com", "hash")
        result = await store.upsert_user_settings(
            user["id"],
            api_key_enc="enc_key_123",
            default_model="gpt-4o",
        )
        assert result["user_id"] == user["id"]
        assert result["api_key_enc"] == "enc_key_123"
        assert result["default_model"] == "gpt-4o"
        # New fields should be None by default
        assert result["provider_type"] is None
        assert result["base_url"] is None

    async def test_upsert_update_partial(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.upsert_user_settings(
            user["id"],
            api_key_enc="enc_orig",
            default_model="gpt-4o",
        )
        # Partial update — only change default_model
        result = await store.upsert_user_settings(
            user["id"],
            default_model="gpt-4o-mini",
        )
        assert result["default_model"] == "gpt-4o-mini"
        # api_key_enc should be unchanged from original
        assert result["api_key_enc"] == "enc_orig"
        # provider fields should be None
        assert result["provider_type"] is None
        assert result["base_url"] is None

    async def test_upsert_multiple_users(self, store):
        user_a = await store.create_user("a@example.com", "hash1")
        user_b = await store.create_user("b@example.com", "hash2")
        await store.upsert_user_settings(user_a["id"], default_model="model_a")
        await store.upsert_user_settings(user_b["id"], default_model="model_b")
        a_settings = await store.get_user_settings(user_a["id"])
        b_settings = await store.get_user_settings(user_b["id"])
        assert a_settings["default_model"] == "model_a"
        assert b_settings["default_model"] == "model_b"
        # provider fields should be None
        assert a_settings["provider_type"] is None
        assert a_settings["base_url"] is None

    async def test_upsert_with_provider_fields(self, store):
        """Test upsert with provider_type and base_url."""
        user = await store.create_user("alice@example.com", "hash")
        result = await store.upsert_user_settings(
            user["id"],
            provider_type="openrouter",
            base_url="https://openrouter.ai/api/v1",
            provider_type_provided=True,
            base_url_provided=True,
        )
        assert result["provider_type"] == "openrouter"
        assert result["base_url"] == "https://openrouter.ai/api/v1"

    async def test_provider_fields_partial_update_keep(self, store):
        """Test that provider_type/base_url are kept when not provided."""
        user = await store.create_user("alice@example.com", "hash")
        # Set initial values
        await store.upsert_user_settings(
            user["id"],
            provider_type="ollama",
            base_url="http://localhost:11434/v1",
            provider_type_provided=True,
            base_url_provided=True,
        )
        # Update only api_key_enc, provider fields should stay unchanged
        result = await store.upsert_user_settings(
            user["id"],
            api_key_enc="new_key",
        )
        assert result["api_key_enc"] == "new_key"
        assert result["provider_type"] == "ollama"
        assert result["base_url"] == "http://localhost:11434/v1"

    async def test_provider_fields_clear_when_provided_null(self, store):
        """Test that provider_type/base_url can be cleared when provided as null."""
        user = await store.create_user("alice@example.com", "hash")
        # Set initial values
        await store.upsert_user_settings(
            user["id"],
            provider_type="custom",
            base_url="https://api.example.com/v1",
            provider_type_provided=True,
            base_url_provided=True,
        )
        # Clear base_url by providing None with base_url_provided=True
        result = await store.upsert_user_settings(
            user["id"],
            base_url=None,
            base_url_provided=True,
        )
        assert result["base_url"] is None
        assert result["provider_type"] == "custom"  # unchanged

    async def test_concurrent_style_partial_updates(self, store):
        """Test that two overlapping PUTs (one api_key only, one default_model only)
        produce a merged row (spec: Concurrent settings updates)."""
        user = await store.create_user("alice@example.com", "hash")
        # Simulate concurrent updates
        result1 = await store.upsert_user_settings(
            user["id"],
            api_key_enc="key_123",
        )
        result2 = await store.upsert_user_settings(
            user["id"],
            default_model="gpt-4o",
        )
        # Get final state
        final = await store.get_user_settings(user["id"])
        assert final["api_key_enc"] == "key_123"
        assert final["default_model"] == "gpt-4o"