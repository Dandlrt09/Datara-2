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

    async def test_upsert_multiple_users(self, store):
        user_a = await store.create_user("a@example.com", "hash1")
        user_b = await store.create_user("b@example.com", "hash2")
        await store.upsert_user_settings(user_a["id"], default_model="model_a")
        await store.upsert_user_settings(user_b["id"], default_model="model_b")
        a_settings = await store.get_user_settings(user_a["id"])
        b_settings = await store.get_user_settings(user_b["id"])
        assert a_settings["default_model"] == "model_a"
        assert b_settings["default_model"] == "model_b"