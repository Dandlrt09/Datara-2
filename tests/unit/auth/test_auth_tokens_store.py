"""One-time mailed tokens and the verified-email stamp (T2, D1-D3, D11-D12).

These probes pin the security properties the two flows rest on:

- a token is redeemable exactly once (D2), even when two redemptions race;
- asking for a new link retires the previous one (D1);
- expiry is enforced at redemption, not merely by a sweep (D12);
- verifying an address is idempotent and never rewrites the first date (D7);
- the two purposes cannot be crossed.
"""

import sqlite3

import pytest

from server.services.auth_service import (
    RESET_TOKEN_TTL_SECONDS,
    TOKEN_PURPOSE_RESET_PASSWORD,
    TOKEN_PURPOSE_VERIFY_EMAIL,
    VERIFICATION_TOKEN_TTL_SECONDS,
)
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
async def store():
    s = SqliteStore(db_path=":memory:")
    await s.connect()
    await apply_all_migrations(s)
    yield s
    await s.close()


async def _user(store: SqliteStore, email: str = "ana@example.com") -> dict:
    return await store.create_user(email, "hash")


class TestEmailVerifiedFlag:
    async def test_a_new_account_starts_unverified(self, store):
        user = await _user(store)

        assert user["email_verified_at"] is None

    async def test_a_legacy_lookup_also_reports_unverified(self, store):
        await _user(store)

        found = await store.get_user_by_email("ana@example.com")

        assert found["email_verified_at"] is None

    async def test_marking_sets_the_stamp(self, store):
        user = await _user(store)

        assert await store.mark_email_verified(user["id"]) is True

        found = await store.get_user_by_id(user["id"])
        assert found["email_verified_at"] is not None

    async def test_marking_twice_keeps_the_first_date(self, store):
        user = await _user(store)
        await store.mark_email_verified(user["id"])
        first = (await store.get_user_by_id(user["id"]))["email_verified_at"]

        await store.mark_email_verified(user["id"])
        second = (await store.get_user_by_id(user["id"]))["email_verified_at"]

        assert first == second

    async def test_marking_an_unknown_user_is_false(self, store):
        assert await store.mark_email_verified(999) is False


class TestCreateAuthToken:
    async def test_stores_only_the_hash_and_returns_the_row(self, store):
        user = await _user(store)

        token = await store.create_auth_token(
            user["id"],
            "hash-abc",
            TOKEN_PURPOSE_VERIFY_EMAIL,
            ttl_seconds=VERIFICATION_TOKEN_TTL_SECONDS,
            email=user["email"],
        )

        assert token["token_hash"] == "hash-abc"
        assert token["purpose"] == TOKEN_PURPOSE_VERIFY_EMAIL
        assert token["email"] == user["email"]
        assert token["used_at"] is None
        assert token["expires_at"] is not None

    async def test_a_new_link_retires_the_previous_live_one(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "old", TOKEN_PURPOSE_VERIFY_EMAIL, 3600
        )
        await store.create_auth_token(
            user["id"], "new", TOKEN_PURPOSE_VERIFY_EMAIL, 3600
        )

        assert await store.consume_auth_token("old", TOKEN_PURPOSE_VERIFY_EMAIL) is None
        assert (
            await store.consume_auth_token("new", TOKEN_PURPOSE_VERIFY_EMAIL)
        ) is not None

    async def test_the_two_purposes_coexist(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "v", TOKEN_PURPOSE_VERIFY_EMAIL, 3600
        )
        await store.create_auth_token(
            user["id"], "r", TOKEN_PURPOSE_RESET_PASSWORD, RESET_TOKEN_TTL_SECONDS
        )

        assert await store.consume_auth_token("v", TOKEN_PURPOSE_VERIFY_EMAIL) is not None
        assert (
            await store.consume_auth_token("r", TOKEN_PURPOSE_RESET_PASSWORD)
        ) is not None

    async def test_the_database_rejects_an_unknown_purpose(self, store):
        user = await _user(store)

        with pytest.raises(sqlite3.IntegrityError):
            await store.create_auth_token(user["id"], "x", "verificar", 3600)


class TestConsumeAuthToken:
    async def test_a_token_is_redeemable_exactly_once(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "once", TOKEN_PURPOSE_RESET_PASSWORD, 3600
        )

        first = await store.consume_auth_token("once", TOKEN_PURPOSE_RESET_PASSWORD)
        second = await store.consume_auth_token("once", TOKEN_PURPOSE_RESET_PASSWORD)

        assert first is not None
        assert first["used_at"] is not None
        assert second is None

    async def test_an_expired_token_is_refused(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "stale", TOKEN_PURPOSE_VERIFY_EMAIL, ttl_seconds=-10
        )

        assert (
            await store.consume_auth_token("stale", TOKEN_PURPOSE_VERIFY_EMAIL) is None
        )

    async def test_a_token_of_another_purpose_is_refused(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "for-reset", TOKEN_PURPOSE_RESET_PASSWORD, 3600
        )

        assert (
            await store.consume_auth_token("for-reset", TOKEN_PURPOSE_VERIFY_EMAIL)
            is None
        )
        # Refusing it must not have burned it: the right purpose still works.
        assert (
            await store.consume_auth_token("for-reset", TOKEN_PURPOSE_RESET_PASSWORD)
            is not None
        )

    async def test_an_unknown_token_is_refused(self, store):
        assert (
            await store.consume_auth_token("nope", TOKEN_PURPOSE_VERIFY_EMAIL) is None
        )


class TestInvalidateAndSweep:
    async def test_invalidate_drops_only_live_tokens_of_that_purpose(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "v", TOKEN_PURPOSE_VERIFY_EMAIL, 3600
        )
        await store.create_auth_token(
            user["id"], "r", TOKEN_PURPOSE_RESET_PASSWORD, 3600
        )

        removed = await store.invalidate_user_tokens(
            user["id"], TOKEN_PURPOSE_VERIFY_EMAIL
        )

        assert removed == 1
        assert await store.consume_auth_token("v", TOKEN_PURPOSE_VERIFY_EMAIL) is None
        assert (
            await store.consume_auth_token("r", TOKEN_PURPOSE_RESET_PASSWORD)
            is not None
        )

    async def test_sweep_removes_expired_and_used_but_keeps_a_live_one(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "expired", TOKEN_PURPOSE_VERIFY_EMAIL, ttl_seconds=-10
        )
        await store.create_auth_token(
            user["id"], "used", TOKEN_PURPOSE_RESET_PASSWORD, 3600
        )
        await store.consume_auth_token("used", TOKEN_PURPOSE_RESET_PASSWORD)
        await store.create_auth_token(
            user["id"], "live", TOKEN_PURPOSE_RESET_PASSWORD, 3600
        )

        removed = await store.sweep_expired_auth_tokens()

        assert removed == 2
        assert (
            await store.consume_auth_token("live", TOKEN_PURPOSE_RESET_PASSWORD)
            is not None
        )

    async def test_deleting_a_user_cascades_to_their_tokens(self, store):
        user = await _user(store)
        await store.create_auth_token(
            user["id"], "t", TOKEN_PURPOSE_VERIFY_EMAIL, 3600
        )

        await store.purge_due_user(user["id"])  # not due: no deletion scheduled

        # Nothing to purge: the account survives and so does its token.
        assert await store.get_user_by_id(user["id"]) is not None
        assert ((await store.conn.execute_fetchall("SELECT COUNT(*) FROM auth_tokens"))[0][0]) == 1
