"""Integration tests for the tutorial "already seen" flag (first-boot-tutorial S3, D9).

The guided tour is for a NEW account, and the flag that says it was already
seen lives in the server, per profile (D2/S3): it survives shutting the app
down, locking and unlocking, and a second boot does not bring the tour back.

``GET /api/auth/me`` reports ``tutorial_seen`` so the app can decide whether to
show the tour on entering ``/app``, and ``POST /api/auth/tutorial-seen`` marks
the CALLER's own profile as seen. That route is authenticated and idempotent,
and it belongs to every profile -- the local one and a hosted account alike --
unlike the local-only lock routes (S3: "incluida una cuenta hospedada recién
creada").
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
TUTORIAL_SEEN_URL = "/api/auth/tutorial-seen"


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


def _seed_account(store: SqliteStore, email: str) -> tuple[int, str]:
    """Create a hosted account and one session; return (user id, raw token)."""

    async def _seed() -> tuple[int, str]:
        user = await store.create_user(
            email, hash_password(PASSWORD), name=email.split("@")[0]
        )
        raw = generate_raw_token()
        await store.create_auth_session(user["id"], hash_token(raw))
        return user["id"], raw

    return asyncio.run(_seed())


def _mark(client, token: str):
    return client.post(TUTORIAL_SEEN_URL, headers={"Cookie": f"session_id={token}"})


def _me(client, token: str):
    return client.get("/api/auth/me", headers={"Cookie": f"session_id={token}"})


def _tutorial_seen(store: SqliteStore, user_id: int) -> int | None:
    """Read the persisted flag straight from the row.

    This is the one place a test looks under the public interface, and only to
    prove that the flag was actually persisted (the API is the contract).
    """

    async def _fetch():
        rows = await store.conn.execute_fetchall(
            "SELECT tutorial_seen FROM users WHERE id = ?", (user_id,)
        )
        return rows[0][0] if rows else None

    return asyncio.run(_fetch())


class TestMarking:
    """POST /tutorial-seen marks the caller's own profile, once and only there."""

    def test_the_route_requires_a_session(self, client, store):
        user_id, _token = _seed_account(store, "ana@example.com")

        resp = client.post(TUTORIAL_SEEN_URL)

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Not authenticated"
        # The refusal wrote nothing: a fresh profile is still "unseen".
        assert _tutorial_seen(store, user_id) == 0

    def test_marking_reports_seen_and_me_reads_it(self, client, store):
        user_id, token = _seed_account(store, "ana@example.com")
        # A brand-new profile starts unseen, which is what opens the tour.
        assert _me(client, token).json()["tutorial_seen"] is False

        marked = _mark(client, token)

        assert marked.status_code == 204
        assert marked.content == b""
        assert _me(client, token).json()["tutorial_seen"] is True
        assert _tutorial_seen(store, user_id) == 1

    def test_marking_is_idempotent(self, client, store):
        user_id, token = _seed_account(store, "ana@example.com")

        assert _mark(client, token).status_code == 204
        assert _mark(client, token).status_code == 204

        assert _me(client, token).json()["tutorial_seen"] is True
        assert _tutorial_seen(store, user_id) == 1

    def test_marking_only_touches_the_callers_row(self, client, store):
        ana_id, ana_token = _seed_account(store, "ana@example.com")
        beto_id, beto_token = _seed_account(store, "beto@example.com")

        assert _mark(client, ana_token).status_code == 204

        # Each profile carries its own flag (S3): the other one is untouched.
        assert _me(client, ana_token).json()["tutorial_seen"] is True
        assert _me(client, beto_token).json()["tutorial_seen"] is False
        assert _tutorial_seen(store, ana_id) == 1
        assert _tutorial_seen(store, beto_id) == 0


class TestTruthfulPayloads:
    """Every payload that carries a user row reports the stored mark, not a default.

    The app reads the flag on entering /app (``GET /me``), but login and the
    "open an existing local profile" path build their payload from the same row
    kind. Leaving them at the model default would let one profile be "seen" in
    one response and "unseen" in the next.
    """

    def test_login_reports_the_stored_mark(self, client, store):
        user_id, token = _seed_account(store, "ana@example.com")

        async def _verify():
            await store.conn.execute(
                "UPDATE users SET email_verified_at = datetime('now') WHERE id = ?",
                (user_id,),
            )
            await store.conn.commit()

        asyncio.run(_verify())
        assert _mark(client, token).status_code == 204

        logged = client.post(
            "/api/auth/login",
            json={"email": "ana@example.com", "password": PASSWORD},
        )

        assert logged.status_code == 200
        assert logged.json()["tutorial_seen"] is True

    def test_opening_an_existing_local_profile_reports_the_stored_mark(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")
        created = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert created.status_code == 201
        assert client.post(TUTORIAL_SEEN_URL).status_code == 204
        locked = client.post(
            "/api/auth/local-profile/lock", json={"password": PASSWORD}
        )
        assert locked.status_code == 200
        client.cookies.clear()

        opened = client.post(
            "/api/auth/local-profile/open", json={"password": PASSWORD}
        )

        assert opened.status_code == 200
        assert opened.json()["tutorial_seen"] is True
