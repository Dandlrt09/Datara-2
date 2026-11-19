"""Integration tests for ``POST /api/auth/local-profile`` (F1 / T2b, S1, D2, D5).

In local mode the first boot creates the profile on this machine: no email, a
required display name, and -- unlike register -- it immediately starts the
session, because there is no address to prove and a profile nobody could enter
would be a dead end. In hosted mode the route is a backstop that refuses with
403.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.services.auth_service import MAX_DISPLAY_NAME_LENGTH
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


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


def _user_count(store: SqliteStore) -> int:
    """Count rows in ``users``; there is no public surface that exposes it."""

    async def _count() -> int:
        rows = await store.conn.execute_fetchall("SELECT COUNT(*) FROM users")
        return rows[0][0]

    return asyncio.run(_count())


class TestLocalProfile:
    def test_local_mode_creates_the_profile_and_starts_a_session(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post("/api/auth/local-profile", json={"name": "Ana"})

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Ana"
        assert data["email"] is None
        assert data["pending_deletion_at"] is None
        set_cookie = resp.headers.get("set-cookie")
        assert set_cookie is not None

        me_resp = client.get("/api/auth/me", headers={"Cookie": set_cookie})
        assert me_resp.status_code == 200
        assert me_resp.json()["id"] == data["id"]
        assert me_resp.json()["name"] == "Ana"
        assert me_resp.json()["email"] is None

    def test_hosted_mode_refuses_and_creates_no_row(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "hosted")

        resp = client.post("/api/auth/local-profile", json={"name": "Ana"})

        assert resp.status_code == 403
        assert resp.json()["detail"] == (
            "Local profile is only available in local mode"
        )
        assert _user_count(store) == 0

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_blank_name_is_rejected_and_creates_no_row(
        self, client, store, monkeypatch, blank
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post("/api/auth/local-profile", json={"name": blank})

        assert resp.status_code == 422
        assert resp.json()["detail"] == "Name is required"
        assert _user_count(store) == 0

    def test_name_over_the_limit_is_rejected_and_creates_no_row(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post(
            "/api/auth/local-profile",
            json={"name": "x" * (MAX_DISPLAY_NAME_LENGTH + 1)},
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            f"Name must be at most {MAX_DISPLAY_NAME_LENGTH} characters"
        )
        assert _user_count(store) == 0

    def test_the_name_is_normalized_before_it_is_stored(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post("/api/auth/local-profile", json={"name": "  Ana   María  "})

        assert resp.status_code == 201
        assert resp.json()["name"] == "Ana María"

    def test_a_second_local_profile_is_refused(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")
        first = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert first.status_code == 201

        resp = client.post("/api/auth/local-profile", json={"name": "Otra"})

        assert resp.status_code == 409
        assert resp.json()["detail"] == "A local profile already exists"
        assert _user_count(store) == 1

    def test_a_bogus_mode_fails_closed_and_creates_no_row(
        self, client, store, monkeypatch
    ):
        """A typo in DATARA_MODE must never hand out a local profile.

        T1 makes an unknown value raise instead of guessing a mode, which is
        why ``GET /api/app-config`` fails the same way, so the error itself is
        the intended answer and is pinned here as such. What matters for this
        route is the other half of failing closed: no identity, no session,
        nothing written.
        """
        monkeypatch.setenv("DATARA_MODE", "locla")

        with pytest.raises(ValueError, match="DATARA_MODE"):
            client.post("/api/auth/local-profile", json={"name": "Ana"})

        assert _user_count(store) == 0
