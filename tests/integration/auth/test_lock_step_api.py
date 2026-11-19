"""Integration tests for the optional lock step on the onboarding path (F1 / T3, S3, D1).

The lock step is mandatory on the path but the lock itself stays optional (D4):
after the local profile is created and before the API-key setup, the screen
explains what the lock protects and offers it. The analyst either turns the
lock on or says "not now" explicitly. The answer is persisted so the step does
not come back.

``GET /api/auth/local-profile`` reports ``lock_step_pending``. The existing
lock route counts as answering (turning the lock on is an answer), and
``POST /api/auth/local-profile/lock-step/decline`` records the explicit
decline. Every route stays mode gated: outside local mode the answer is 403.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.services.auth_service import (
    generate_raw_token,
    hash_password,
    hash_token,
)
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations

PASSWORD = "correct horse battery"
MODE_DETAIL = "Local profile is only available in local mode"
DECLINE_URL = "/api/auth/local-profile/lock-step/decline"


@pytest.fixture
def store():
    """A fresh in-memory store injected into ``server.api.store._store``."""
    from server.api import store as api_store  # noqa: PLC0415

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    api_store._store = s

    yield s

    asyncio.run(s.close())
    api_store._store = None


@pytest.fixture
def app(store):
    """Create a minimal FastAPI app with the auth router wired up."""
    application = FastAPI()
    application.include_router(auth_router)
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


def _create_local(client, monkeypatch, name: str = "Ana") -> None:
    """Create the profile in local mode, leaving the client's session cookie set."""
    monkeypatch.setenv("DATARA_MODE", "local")
    created = client.post("/api/auth/local-profile", json={"name": name})
    assert created.status_code == 201


def _lock(client, password: str = PASSWORD):
    """Turn the lock on with the client's current session cookie."""
    return client.post("/api/auth/local-profile/lock", json={"password": password})


def _decline(client):
    """Decline the step with the client's current session cookie."""
    return client.post(DECLINE_URL)


def _status(client):
    return client.get("/api/auth/local-profile")


def _step_answered(store: SqliteStore) -> int | None:
    """Read the persisted answer straight from the row.

    This is the one place a test looks under the public interface, and only to
    prove that the answer was actually persisted (the API is the contract).
    """

    async def _fetch():
        rows = await store.conn.execute_fetchall(
            "SELECT lock_step_answered FROM users WHERE kind = 'local'"
        )
        return rows[0][0] if rows else None

    return asyncio.run(_fetch())


def _seed_hosted_session(store: SqliteStore) -> str:
    """Create a hosted account and one session; return its raw cookie token."""

    async def _seed() -> str:
        user = await store.create_user(
            "ana@example.com", hash_password(PASSWORD), name="Ana"
        )
        raw = generate_raw_token()
        await store.create_auth_session(user["id"], hash_token(raw))
        return raw

    return asyncio.run(_seed())


class TestPending:
    def test_a_fresh_local_profile_has_the_step_pending(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)

        resp = _status(client)

        assert resp.status_code == 200
        assert resp.json()["lock_step_pending"] is True
        # Nothing answered yet: the column still reads the default.
        assert _step_answered(store) == 0

    def test_turning_the_lock_on_answers_the_step(self, client, store, monkeypatch):
        _create_local(client, monkeypatch)
        assert _status(client).json()["lock_step_pending"] is True

        locked = _lock(client)
        assert locked.status_code == 200

        after = _status(client)
        assert after.status_code == 200
        assert after.json()["locked"] is True
        assert after.json()["lock_step_pending"] is False
        # The lock route is an answer, so the persisted flag is set too.
        assert _step_answered(store) == 1

    def test_declining_answers_the_step(self, client, store, monkeypatch):
        _create_local(client, monkeypatch)
        assert _status(client).json()["lock_step_pending"] is True

        declined = _decline(client)
        assert declined.status_code == 204

        after = _status(client)
        assert after.status_code == 200
        assert after.json()["locked"] is False
        assert after.json()["lock_step_pending"] is False
        assert _step_answered(store) == 1

    def test_declining_is_idempotent(self, client, store, monkeypatch):
        _create_local(client, monkeypatch)

        assert _decline(client).status_code == 204
        assert _decline(client).status_code == 204

        assert _status(client).json()["lock_step_pending"] is False
        assert _step_answered(store) == 1

    def test_declining_a_locked_profile_keeps_the_lock(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)
        assert _lock(client).status_code == 200

        assert _decline(client).status_code == 204

        after = _status(client)
        assert after.json()["locked"] is True
        assert after.json()["lock_step_pending"] is False


class TestModeGate:
    def test_the_status_is_still_refused_in_hosted_mode(self, client, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "hosted")

        resp = _status(client)

        assert resp.status_code == 403
        assert resp.json()["detail"] == MODE_DETAIL

    def test_decline_outside_local_mode_is_forbidden(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)

        monkeypatch.setenv("DATARA_MODE", "hosted")
        resp = _decline(client)

        assert resp.status_code == 403
        assert resp.json()["detail"] == MODE_DETAIL
        # The refusal wrote nothing: the step is still pending.
        assert _step_answered(store) == 0

    def test_decline_requires_a_session(self, client, monkeypatch):
        _create_local(client, monkeypatch)
        client.cookies.clear()

        resp = _decline(client)

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Not authenticated"

    def test_decline_for_a_hosted_session_is_not_found(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)
        client.cookies.clear()
        token = _seed_hosted_session(store)

        resp = client.post(DECLINE_URL, headers={"Cookie": f"session_id={token}"})

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Local profile not found"
        # The hosted session did not answer the local profile's step.
        assert _step_answered(store) == 0
