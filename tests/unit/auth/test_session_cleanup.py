"""Tests for session cleanup service."""

import pytest

from server.services.session_cleanup import sweep_expired
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
async def store():
    s = SqliteStore(db_path=":memory:")
    await s.connect()
    await apply_all_migrations(s)
    yield s
    await s.close()


class TestSweepExpired:
    async def test_sweep_none_expired(self, store):
        """No expired sessions should result in 0 count."""
        count = await sweep_expired(store)
        assert count == 0

    async def test_sweep_with_expired(self, store):
        """Create an expired session and verify sweep removes it."""
        user = await store.create_user("alice@example.com", "hash")
        # Create a session with negative TTL so it's immediately expired
        await store.create_auth_session(user["id"], "th_exp", ttl_seconds=-1)
        count = await sweep_expired(store)
        assert count >= 1
        assert await store.get_auth_session_by_token_hash("th_exp") is None

    async def test_sweep_leaves_valid(self, store):
        """Valid sessions should remain after sweep."""
        user = await store.create_user("bob@example.com", "hash")
        await store.create_auth_session(user["id"], "th_valid")
        await store.create_auth_session(user["id"], "th_exp2", ttl_seconds=-1)
        count = await sweep_expired(store)
        assert count >= 1
        # Valid session should still exist
        found = await store.get_auth_session_by_token_hash("th_valid")
        assert found is not None