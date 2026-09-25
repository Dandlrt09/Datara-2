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
