"""Email normalization: the account identity is case- and space-insensitive (S4/S5).

``normalize_email`` is the single place the rule lives; the store applies it so
no caller can bypass it.
"""

import pytest

from server.services.auth_service import normalize_email
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
async def store():
    s = SqliteStore(db_path=":memory:")
    await s.connect()
    await apply_all_migrations(s)
    yield s
    await s.close()


class TestNormalizeEmail:
    def test_lowercases_and_trims(self):
        assert normalize_email("  Alice@Example.COM  ") == "alice@example.com"

    def test_already_normal_is_unchanged(self):
        assert normalize_email("alice@example.com") == "alice@example.com"


class TestStoreNormalizesEmail:
    async def test_create_user_stores_normalized_email(self, store):
        user = await store.create_user("  Alice@Example.COM  ", "hash")
        assert user["email"] == "alice@example.com"

    async def test_get_user_by_email_is_case_insensitive(self, store):
        created = await store.create_user("bob@example.com", "hash")
        found = await store.get_user_by_email("BOB@EXAMPLE.COM")
        assert found is not None
        assert found["id"] == created["id"]

    async def test_duplicate_across_case_is_rejected(self, store):
        from core.errors import DuplicateError

        await store.create_user("carol@example.com", "hash1")
        with pytest.raises(DuplicateError):
            await store.create_user("Carol@Example.com", "hash2")

    async def test_lookup_finds_a_row_written_outside_the_store(self, store):
        await store.conn.execute(
            "INSERT INTO users (email, password_hash) VALUES ('Hand@Edited.com', 'hash')"
        )
        await store.conn.commit()
        found = await store.get_user_by_email("hand@edited.com")
        assert found is not None
