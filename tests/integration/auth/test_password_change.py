"""Integration tests for ``POST /api/auth/password``.

Covers the password-change contract end to end through the HTTP routes:
the caller's current session survives, every other session dies, the old
password stops working, the new one starts working, and a rejected request
changes nothing (stored hash and both sessions untouched).

Uses FastAPI TestClient with a fresh in-memory SQLite store per test.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations

OLD_PASSWORD = "password123"
NEW_PASSWORD = "newpassword456"


@pytest.fixture
def store():
    """Fresh in-memory store wired into ``server.api.store._store``."""
    from server.api import store as api_store

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    previous = api_store._store
    api_store._store = s

    yield s

    asyncio.run(s.close())
    api_store._store = previous


@pytest.fixture
def client(store):
    application = FastAPI()
    application.include_router(auth_router)
    return TestClient(application)


def _register(client, email= "user@example.com", password=OLD_PASSWORD):
    """Register and return the session cookie of the first session (A)."""
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


def _login(client, email="user@example.com", password=OLD_PASSWORD):
    """Log in and return the session cookie of an additional session (B)."""
    resp = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


class TestPasswordChange:
    def test_change_password_rotates_and_closes_other_sessions(self, client):
        cookie_a = _register(client)
        cookie_b = _login(client)

        resp = client.post(
            "/api/auth/password",
            json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            headers={"Cookie": cookie_a},
        )
        assert resp.status_code == 204

        # Old password no longer logs in, new one does.
        old_login = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": OLD_PASSWORD},
        )
        assert old_login.status_code == 401
        new_login = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": NEW_PASSWORD},
        )
        assert new_login.status_code == 200

        # The session that made the change survives; the other one is gone.
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_a}).status_code
            == 200
        )
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_b}).status_code
            == 401
        )

    def test_short_new_password_rejects_and_changes_nothing(self, client, store):
        cookie_a = _register(client)
        cookie_b = _login(client)
        before = asyncio.run(store.get_user_by_id(1))["password_hash"]

        resp = client.post(
            "/api/auth/password",
            json={"current_password": OLD_PASSWORD, "new_password": "1234567"},
            headers={"Cookie": cookie_a},
        )
        assert resp.status_code == 422

        after = asyncio.run(store.get_user_by_id(1))["password_hash"]
        assert after == before

        # Both sessions still work and the old password still logs in.
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_a}).status_code
            == 200
        )
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_b}).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": OLD_PASSWORD},
            ).status_code
            == 200
        )

    def test_wrong_current_password_rejects_and_changes_nothing(self, client, store):
        cookie_a = _register(client)
        cookie_b = _login(client)
        before = asyncio.run(store.get_user_by_id(1))["password_hash"]

        resp = client.post(
            "/api/auth/password",
            json={"current_password": "wrongpassword", "new_password": NEW_PASSWORD},
            headers={"Cookie": cookie_a},
        )
        assert resp.status_code == 401

        after = asyncio.run(store.get_user_by_id(1))["password_hash"]
        assert after == before

        # Both sessions still work and the old password still logs in.
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_a}).status_code
            == 200
        )
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_b}).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": OLD_PASSWORD},
            ).status_code
            == 200
        )

    def test_no_cookie_is_rejected(self, client):
        _register(client)
        client.cookies.clear()

        resp = client.post(
            "/api/auth/password",
            json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert resp.status_code == 401

    def test_change_from_second_session_keeps_caller(self, client):
        """S4: the purge keeps whichever session made the call, not just the first."""
        cookie_a = _register(client)
        cookie_b = _login(client)

        resp = client.post(
            "/api/auth/password",
            json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            headers={"Cookie": cookie_b},
        )
        assert resp.status_code == 204
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_b}).status_code
            == 200
        )
        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie_a}).status_code
            == 401
        )

    def test_second_rotation_with_new_password(self, client):
        """S4: the new password is immediately usable as the current one."""
        cookie_a = _register(client)

        assert (
            client.post(
                "/api/auth/password",
                json={
                    "current_password": OLD_PASSWORD,
                    "new_password": NEW_PASSWORD,
                },
                headers={"Cookie": cookie_a},
            ).status_code
            == 204
        )
        assert (
            client.post(
                "/api/auth/password",
                json={
                    "current_password": NEW_PASSWORD,
                    "new_password": "newestpass789",
                },
                headers={"Cookie": cookie_a},
            ).status_code
            == 204
        )
