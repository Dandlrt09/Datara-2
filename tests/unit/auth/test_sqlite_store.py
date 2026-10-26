"""Tests for SqliteStore CRUD operations.

All tests use an in-memory SQLite database with the init schema applied.
"""

import json

import pytest

from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
async def store():
    s = SqliteStore(db_path=":memory:")
    await s.connect()
    await apply_all_migrations(s)
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


class TestUpdateUserPassword:
    async def test_update_user_password_changes_hash(self, store):
        user = await store.create_user("alice@example.com", "old_hash")
        changed = await store.update_user_password(user["id"], "new_hash")
        assert changed is True
        refreshed = await store.get_user_by_id(user["id"])
        assert refreshed["password_hash"] == "new_hash"

    async def test_update_user_password_missing_user_returns_false(self, store):
        changed = await store.update_user_password(999, "new_hash")
        assert changed is False

    async def test_update_user_password_only_targets_one_user(self, store):
        alice = await store.create_user("alice@example.com", "a_hash")
        bob = await store.create_user("bob@example.com", "b_hash")
        await store.update_user_password(alice["id"], "a_new")
        assert (await store.get_user_by_id(alice["id"]))["password_hash"] == "a_new"
        assert (await store.get_user_by_id(bob["id"]))["password_hash"] == "b_hash"


class TestDeleteOtherAuthSessions:
    async def test_deletes_others_and_keeps_current(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "keep_hash")
        await store.create_auth_session(user["id"], "other_1")
        await store.create_auth_session(user["id"], "other_2")

        deleted = await store.delete_other_auth_sessions(user["id"], "keep_hash")

        assert deleted == 2
        assert await store.get_auth_session_by_token_hash("keep_hash") is not None
        assert await store.get_auth_session_by_token_hash("other_1") is None
        assert await store.get_auth_session_by_token_hash("other_2") is None

    async def test_only_deletes_sessions_of_that_user(self, store):
        alice = await store.create_user("alice@example.com", "hash")
        bob = await store.create_user("bob@example.com", "hash")
        await store.create_auth_session(alice["id"], "alice_keep")
        await store.create_auth_session(alice["id"], "alice_other")
        await store.create_auth_session(bob["id"], "bob_session")

        deleted = await store.delete_other_auth_sessions(alice["id"], "alice_keep")

        assert deleted == 1
        assert await store.get_auth_session_by_token_hash("alice_other") is None
        assert await store.get_auth_session_by_token_hash("bob_session") is not None

    async def test_no_others_returns_zero(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "only_hash")

        deleted = await store.delete_other_auth_sessions(user["id"], "only_hash")

        assert deleted == 0
        assert await store.get_auth_session_by_token_hash("only_hash") is not None


class TestActiveSessions:
    """Active sessions list, real activity and the new-session notice (T2).

    ``_age_activity`` backdates a row the way real history would: timestamps
    here have second granularity, so ordering and the activity threshold cannot
    be observed without it. The notice does not need it, because its mark is a
    session id.
    """

    async def _age_activity(self, store, token_hash: str, minutes: int) -> None:
        await store.conn.execute(
            "UPDATE auth_sessions SET last_seen_at = datetime('now', ?) "
            "WHERE token_hash = ?",
            (f"-{minutes} minutes", token_hash),
        )
        await store.conn.commit()

    async def test_create_session_stores_the_user_agent(self, store):
        user = await store.create_user("alice@example.com", "hash")
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0"

        session = await store.create_auth_session(user["id"], "th_ua", user_agent=ua)

        assert session["user_agent"] == ua

    async def test_create_session_without_user_agent_is_null(self, store):
        user = await store.create_user("alice@example.com", "hash")

        session = await store.create_auth_session(user["id"], "th_no_ua")

        assert session["user_agent"] is None

    async def test_create_session_with_an_empty_user_agent_is_null(self, store):
        """An empty header says no more than a missing one (D2)."""
        user = await store.create_user("alice@example.com", "hash")

        session = await store.create_auth_session(user["id"], "th_empty_ua", user_agent="")

        assert session["user_agent"] is None

    async def test_create_session_truncates_the_user_agent(self, store):
        """D2: the header is caller-controlled and unbounded; the column is not."""
        user = await store.create_user("alice@example.com", "hash")

        session = await store.create_auth_session(
            user["id"], "th_long_ua", user_agent="x" * 500
        )

        assert len(session["user_agent"]) == 120
        assert session["user_agent"] == "x" * 120

    async def test_list_sessions_is_owner_scoped_and_marks_the_current_one(self, store):
        alice = await store.create_user("alice@example.com", "hash")
        bob = await store.create_user("bob@example.com", "hash")
        alice_current = await store.create_auth_session(alice["id"], "th_a1")
        await store.create_auth_session(alice["id"], "th_a2")
        await store.create_auth_session(bob["id"], "th_b1")

        listed = await store.list_auth_sessions(alice["id"], "th_a1")

        assert len(listed) == 2
        current = [row for row in listed if row["is_current"]]
        assert [row["id"] for row in current] == [alice_current["id"]]

    async def test_list_sessions_excludes_expired_ones(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_live")
        await store.create_auth_session(user["id"], "th_dead", ttl_seconds=-1)

        listed = await store.list_auth_sessions(user["id"], "th_live")

        assert [row["is_current"] for row in listed] == [True]

    async def test_list_sessions_orders_by_last_activity(self, store):
        user = await store.create_user("alice@example.com", "hash")
        current = await store.create_auth_session(user["id"], "th_now")
        older = await store.create_auth_session(user["id"], "th_older")
        newest = await store.create_auth_session(user["id"], "th_newest")
        await self._age_activity(store, "th_older", 30)
        await self._age_activity(store, "th_now", 10)

        listed = await store.list_auth_sessions(user["id"], "th_now")

        assert [row["id"] for row in listed] == [
            newest["id"],
            current["id"],
            older["id"],
        ]

    async def test_touch_skips_a_recent_mark(self, store):
        """D8: inside the threshold the row is left alone (no write)."""
        user = await store.create_user("alice@example.com", "hash")
        created = await store.create_auth_session(user["id"], "th_recent")

        touched = await store.touch_auth_session("th_recent")

        assert touched is False
        listed = await store.list_auth_sessions(user["id"], "th_recent")
        assert listed[0]["last_seen_at"] == created["last_seen_at"]

    async def test_touch_rewrites_a_stale_mark(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_stale")
        await self._age_activity(store, "th_stale", 10)
        stale = await store.get_auth_session_by_token_hash("th_stale")

        touched = await store.touch_auth_session("th_stale")

        assert touched is True
        listed = await store.list_auth_sessions(user["id"], "th_stale")
        assert listed[0]["last_seen_at"] > stale["last_seen_at"]

    async def test_touch_ignores_an_unknown_token(self, store):
        assert await store.touch_auth_session("th_missing") is False

    async def test_get_session_by_id_is_owner_scoped(self, store):
        alice = await store.create_user("alice@example.com", "hash")
        bob = await store.create_user("bob@example.com", "hash")
        alice_session = await store.create_auth_session(alice["id"], "th_a")
        bob_session = await store.create_auth_session(bob["id"], "th_b")

        assert (
            await store.get_auth_session_by_id(alice["id"], alice_session["id"])
        ) is not None
        assert await store.get_auth_session_by_id(alice["id"], bob_session["id"]) is None
        assert await store.get_auth_session_by_id(alice["id"], 9999) is None

    async def test_delete_session_row_is_owner_scoped(self, store):
        """A foreign id must not close anything (D5)."""
        alice = await store.create_user("alice@example.com", "hash")
        bob = await store.create_user("bob@example.com", "hash")
        alice_session = await store.create_auth_session(alice["id"], "th_a")
        bob_session = await store.create_auth_session(bob["id"], "th_b")

        assert await store.delete_auth_session_row(alice["id"], bob_session["id"]) == 0
        assert await store.get_auth_session_by_token_hash("th_b") is not None

        assert await store.delete_auth_session_row(alice["id"], alice_session["id"]) == 1
        assert await store.get_auth_session_by_token_hash("th_a") is None

    async def test_delete_session_row_missing_returns_zero(self, store):
        alice = await store.create_user("alice@example.com", "hash")
        assert await store.delete_auth_session_row(alice["id"], 4242) == 0

    async def test_pending_notice_is_none_without_other_sessions(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_only")

        assert await store.pending_new_session_at(user["id"], "th_only") is None

    async def test_no_notice_on_the_newest_session(self, store):
        """S6: the notice means a session was created after *this* one.

        The mark is per user, so without the age check the newest session would
        announce an older, unacknowledged one as "a new session", with a date
        from before it existed.
        """
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_old")
        newest = await store.create_auth_session(user["id"], "th_new")

        assert (
            await store.pending_new_session_at(user["id"], "th_old")
            == newest["created_at"]
        )
        assert await store.pending_new_session_at(user["id"], "th_new") is None

    async def test_pending_notice_reports_the_newest_other_session(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_mine")
        other = await store.create_auth_session(user["id"], "th_other")

        pending = await store.pending_new_session_at(user["id"], "th_mine")

        assert pending == other["created_at"]

    async def test_acknowledging_the_notice_clears_it(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_mine")
        await store.create_auth_session(user["id"], "th_other")

        await store.mark_sessions_notice_seen(user["id"], "th_mine")

        assert await store.pending_new_session_at(user["id"], "th_mine") is None

    async def test_notice_reappears_for_a_session_created_after_the_mark(self, store):
        """A login in the same second as the acknowledgement still warns."""
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_mine")
        await store.create_auth_session(user["id"], "th_acked")
        await store.mark_sessions_notice_seen(user["id"], "th_mine")
        later = await store.create_auth_session(user["id"], "th_later")

        assert (
            await store.pending_new_session_at(user["id"], "th_mine")
            == later["created_at"]
        )

    async def test_acknowledging_alone_still_warns_on_a_later_session(self, store):
        """Acknowledging with no other session must not swallow the next one."""
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_only")
        await store.mark_sessions_notice_seen(user["id"], "th_only")
        later = await store.create_auth_session(user["id"], "th_phone")

        assert (
            await store.pending_new_session_at(user["id"], "th_only")
            == later["created_at"]
        )

    async def test_acknowledging_is_idempotent(self, store):
        user = await store.create_user("alice@example.com", "hash")
        await store.create_auth_session(user["id"], "th_mine")
        await store.create_auth_session(user["id"], "th_other")

        await store.mark_sessions_notice_seen(user["id"], "th_mine")
        await store.mark_sessions_notice_seen(user["id"], "th_mine")

        assert await store.pending_new_session_at(user["id"], "th_mine") is None

    async def test_pending_notice_is_owner_scoped(self, store):
        alice = await store.create_user("alice@example.com", "hash")
        bob = await store.create_user("bob@example.com", "hash")
        await store.create_auth_session(alice["id"], "th_alice")
        await store.create_auth_session(bob["id"], "th_bob")

        assert await store.pending_new_session_at(alice["id"], "th_alice") is None


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


class TestUserSettingsEncryption:
    """API keys must be ciphertext at rest while callers still see plaintext."""

    async def test_upsert_stores_ciphertext_and_get_round_trips(self, store):
        user = await store.create_user("enc@example.com", "hash")
        plaintext = "sk-super-secret-123"

        result = await store.upsert_user_settings(user["id"], api_key_enc=plaintext)
        # The store boundary still hands callers the plaintext key.
        assert result["api_key_enc"] == plaintext

        # Bypass get_user_settings and inspect the raw column directly.
        rows = await store.conn.execute_fetchall(
            "SELECT api_key_enc FROM user_settings WHERE user_id = ?",
            (user["id"],),
        )
        raw = rows[0]["api_key_enc"]
        assert raw != plaintext
        assert plaintext not in raw
        assert raw.startswith("gAAAAA")

        # Read path decrypts back to the original plaintext.
        settings = await store.get_user_settings(user["id"])
        assert settings["api_key_enc"] == plaintext

    async def test_partial_update_keeps_encrypted_key(self, store):
        user = await store.create_user("enc2@example.com", "hash")
        plaintext = "sk-keep-me-456"
        await store.upsert_user_settings(user["id"], api_key_enc=plaintext)

        # Omitted key (None) must not wipe or rewrite the stored ciphertext.
        result = await store.upsert_user_settings(
            user["id"], default_model="gpt-4o"
        )
        assert result["api_key_enc"] == plaintext
        rows = await store.conn.execute_fetchall(
            "SELECT api_key_enc FROM user_settings WHERE user_id = ?",
            (user["id"],),
        )
        assert plaintext not in rows[0]["api_key_enc"]

    async def test_encrypt_legacy_api_keys_is_idempotent(self, store):
        user = await store.create_user("legacy@example.com", "hash")
        plaintext = "sk-legacy-plain-789"
        # Simulate a row written before encryption existed.
        await store.conn.execute(
            "INSERT INTO user_settings (user_id, api_key_enc, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (user["id"], plaintext),
        )
        await store.conn.commit()

        first = await store.encrypt_legacy_api_keys()
        assert first == 1

        rows = await store.conn.execute_fetchall(
            "SELECT api_key_enc FROM user_settings WHERE user_id = ?",
            (user["id"],),
        )
        raw = rows[0]["api_key_enc"]
        assert raw != plaintext
        assert plaintext not in raw
        assert (await store.get_user_settings(user["id"]))["api_key_enc"] == plaintext

        # Running the sweep again must re-encrypt nothing.
        second = await store.encrypt_legacy_api_keys()
        assert second == 0
        rows_after = await store.conn.execute_fetchall(
            "SELECT api_key_enc FROM user_settings WHERE user_id = ?",
            (user["id"],),
        )
        assert rows_after[0]["api_key_enc"] == raw

    async def test_empty_string_api_key_keeps_existing_ciphertext(self, store):
        """An empty string at the store boundary must keep the stored key.

        ``""`` is not ``None``, so without normalization it would be encrypted
        and overwrite the real key. It must instead leave the ciphertext
        untouched while the read path still returns the original plaintext.
        """
        user = await store.create_user("enc-empty@example.com", "hash")
        plaintext = "sk-original-key-000"
        await store.upsert_user_settings(user["id"], api_key_enc=plaintext)

        rows = await store.conn.execute_fetchall(
            "SELECT api_key_enc FROM user_settings WHERE user_id = ?",
            (user["id"],),
        )
        before = rows[0]["api_key_enc"]

        result = await store.upsert_user_settings(user["id"], api_key_enc="")

        assert result["api_key_enc"] == plaintext
        rows_after = await store.conn.execute_fetchall(
            "SELECT api_key_enc FROM user_settings WHERE user_id = ?",
            (user["id"],),
        )
        assert rows_after[0]["api_key_enc"] == before


class TestFilesUniqueName:
    """The files table enforces UNIQUE(user_id, chat_session, filename).

    The second insert with a colliding key must raise ``DuplicateError`` and
    must not leave a second row behind, and the connection must stay usable
    afterwards (proving the failure rolled back cleanly).
    """

    async def test_create_file_duplicate_name_raises_and_keeps_one_row(self, store):
        from core.errors import DuplicateError

        user = await store.create_user("dedupe@example.com", "hash")
        await store.create_chat_session("ses_dedupe", user["id"], "Dedupe")

        first = await store.create_file(
            user_id=user["id"],
            chat_session="ses_dedupe",
            filename="same.csv",
            storage_path="/tmp/same.csv",
            size_bytes=10,
            format_val="csv",
            row_count=1,
        )
        with pytest.raises(DuplicateError, match="already exists"):
            await store.create_file(
                user_id=user["id"],
                chat_session="ses_dedupe",
                filename="same.csv",
                storage_path="/tmp/same.csv",
                size_bytes=20,
                format_val="csv",
                row_count=2,
            )

        rows = await store.conn.execute_fetchall(
            "SELECT id FROM files WHERE user_id = ? AND chat_session = ? AND filename = ?",
            (user["id"], "ses_dedupe", "same.csv"),
        )
        assert len(rows) == 1
        assert rows[0]["id"] == first["id"]

    async def test_create_file_with_profile_duplicate_name_raises_and_keeps_one_row(
        self, store
    ):
        from core.errors import DuplicateError

        user = await store.create_user("dedupe2@example.com", "hash")
        await store.create_chat_session("ses_dedupe2", user["id"], "Dedupe 2")

        kwargs = {
            "user_id": user["id"],
            "chat_session": "ses_dedupe2",
            "filename": "profile.csv",
            "size_bytes": 10,
            "format_val": "csv",
            "schema_json": "{}",
            "stats_json": "{}",
            "sample_json": "[]",
            "row_count": 1,
        }
        first = await store.create_file_with_profile(
            storage_path="/tmp/profile.csv", **kwargs
        )
        with pytest.raises(DuplicateError, match="already exists"):
            await store.create_file_with_profile(
                storage_path="/tmp/profile.csv", **kwargs
            )

        rows = await store.conn.execute_fetchall(
            "SELECT id FROM files WHERE user_id = ? AND chat_session = ? AND filename = ?",
            (user["id"], "ses_dedupe2", "profile.csv"),
        )
        assert len(rows) == 1
        assert rows[0]["id"] == first["id"]


class TestReselectSheet:
    """``reselect_sheet`` atomically swaps files.sheet_name/row_count and the
    single profile row in one transaction, enforcing ownership in the WHERE."""

    async def _seed(self, store, email: str, session_id: str, filename: str):
        user = await store.create_user(email, "hash")
        await store.create_chat_session(session_id, user["id"], "S")
        file = await store.create_file_with_profile(
            user_id=user["id"],
            chat_session=session_id,
            filename=filename,
            storage_path=f"/tmp/{filename}",
            size_bytes=10,
            format_val="xlsx",
            sheet_name="Data",
            row_count=1,
            schema_json='{"columns": [{"name": "a"}]}',
            stats_json="{}",
            sample_json="[]",
        )
        return user, file

    async def test_reselect_updates_sheet_and_replaces_profile(self, store):
        user, file = await self._seed(
            store, "reselect@example.com", "ses_reselect", "book.xlsx"
        )

        updated = await store.reselect_sheet(
            file_id=file["id"],
            user_id=user["id"],
            sheet_name="Meta",
            row_count=2,
            schema_json='{"columns": [{"name": "b"}]}',
            stats_json="{}",
            sample_json="[]",
        )

        assert updated is not None
        assert updated["id"] == file["id"]
        assert updated["sheet_name"] == "Meta"
        assert updated["row_count"] == 2

        profile = await store.get_profile_with_ownership(file["id"], user["id"])
        assert json.loads(profile["schema_json"]) == {"columns": [{"name": "b"}]}

        # Still exactly one files row and one profile row.
        file_rows = await store.conn.execute_fetchall(
            "SELECT id FROM files WHERE user_id = ?", (user["id"],)
        )
        assert len(file_rows) == 1
        profile_rows = await store.conn.execute_fetchall(
            "SELECT file_id FROM profiles WHERE file_id = ?", (file["id"],)
        )
        assert len(profile_rows) == 1

    async def test_reselect_wrong_user_returns_none_and_keeps_state(self, store):
        user, file = await self._seed(
            store, "reselect_owner@example.com", "ses_reselect2", "book2.xlsx"
        )
        other = await store.create_user("reselect_other@example.com", "hash")

        result = await store.reselect_sheet(
            file_id=file["id"],
            user_id=other["id"],
            sheet_name="Meta",
            row_count=9,
            schema_json="{}",
            stats_json="{}",
            sample_json="[]",
        )

        assert result is None
        unchanged = await store.get_file(file["id"], user["id"])
        assert unchanged["sheet_name"] == "Data"
        assert unchanged["row_count"] == 1
        profile = await store.get_profile_with_ownership(file["id"], user["id"])
        assert json.loads(profile["schema_json"]) == {"columns": [{"name": "a"}]}

    async def test_reselect_missing_file_returns_none(self, store):
        user = await store.create_user("reselect_missing@example.com", "hash")

        result = await store.reselect_sheet(
            file_id=99999,
            user_id=user["id"],
            sheet_name="X",
            row_count=1,
            schema_json="{}",
            stats_json="{}",
            sample_json="[]",
        )

        assert result is None

    async def test_reselect_failure_after_update_rolls_back_both_rows(
        self, store, monkeypatch
    ):
        """A failure INSIDE the transaction (after the files UPDATE) must
        leave the files row AND the profile row exactly as they were.

        The profile INSERT is forced to raise, which is the only way to prove
        the rollback path: the pre-DB parse failure never reaches the store,
        and a wrong-user reselect returns before writing. Monkeypatching the
        connection's ``execute`` keeps the test at the real transaction
        boundary instead of mocking the store method itself.
        """
        user, file = await self._seed(
            store, "reselect_rollback@example.com", "ses_reselect3", "book3.xlsx"
        )
        before_file = await store.get_file(file["id"], user["id"])
        before_profile = await store.get_profile_with_ownership(
            file["id"], user["id"]
        )
        original_execute = store.conn.execute

        async def flaky_execute(sql, *args, **kwargs):
            if "INSERT INTO profiles" in sql:
                raise RuntimeError("forced failure after files UPDATE")
            return await original_execute(sql, *args, **kwargs)

        monkeypatch.setattr(store.conn, "execute", flaky_execute)

        with pytest.raises(RuntimeError, match="forced failure"):
            await store.reselect_sheet(
                file_id=file["id"],
                user_id=user["id"],
                sheet_name="Meta",
                row_count=99,
                schema_json='{"columns": [{"name": "b"}]}',
                stats_json="{}",
                sample_json="[]",
            )

        after_file = await store.get_file(file["id"], user["id"])
        after_profile = await store.get_profile_with_ownership(
            file["id"], user["id"]
        )
        # The UPDATE was issued inside the transaction, then rolled back.
        assert after_file["sheet_name"] == "Data"
        assert after_file["row_count"] == 1
        assert after_file["sheet_name"] == before_file["sheet_name"]
        assert after_file["row_count"] == before_file["row_count"]
        # The profile JSON is byte-identical to before the failed switch.
        assert after_profile["schema_json"] == before_profile["schema_json"]
        assert json.loads(after_profile["schema_json"]) == {"columns": [{"name": "a"}]}
