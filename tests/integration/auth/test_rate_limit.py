"""Attempt limiting on register and login (S1-S3).

Five attempts inside fifteen minutes per IP and per email; the sixth answers 429
with a ``Retry-After`` header. A successful login clears the counter.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.rate_limit import auth_attempt_limiter
from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    api_store._store = s

    yield application

    asyncio.run(s.close())
    api_store._store = None


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def store():
    return api_store._store


def _register(client, email: str):
    return client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )


def _login(client, email: str, password: str = "wrongpass"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


class TestLoginRateLimit:
    def test_sixth_failed_login_is_rate_limited(self, client):
        _register(client, "limit-login@example.com")

        for _ in range(5):
            assert _login(client, "limit-login@example.com").status_code == 401

        resp = _login(client, "limit-login@example.com")
        assert resp.status_code == 429

    def test_rate_limited_response_carries_retry_after(self, client):
        _register(client, "limit-header@example.com")
        for _ in range(5):
            _login(client, "limit-header@example.com")

        resp = _login(client, "limit-header@example.com")
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) > 0

    def test_successful_login_clears_the_counter(self, client):
        _register(client, "limit-clear@example.com")
        for _ in range(4):
            _login(client, "limit-clear@example.com")

        assert _login(client, "limit-clear@example.com", "password123").status_code == 200

        # The clear resets the window, so the next mistake is a 401, not a 429.
        assert _login(client, "limit-clear@example.com").status_code == 401

    def test_email_key_alone_blocks_login(self, client):
        _register(client, "keyed-email@example.com")
        for _ in range(5):
            auth_attempt_limiter.record("login:email:keyed-email@example.com")
        assert _login(client, "keyed-email@example.com").status_code == 429

    def test_ip_key_alone_blocks_login(self, client):
        _register(client, "keyed-ip@example.com")
        for _ in range(5):
            auth_attempt_limiter.record("login:ip:testclient")
        assert _login(client, "fresh@example.com").status_code == 429

    def test_success_then_five_more_failures_before_lockout(self, client):
        _register(client, "route-clear@example.com")
        for _ in range(4):
            assert _login(client, "route-clear@example.com").status_code == 401
        assert _login(client, "route-clear@example.com", "password123").status_code == 200
        for _ in range(5):
            assert _login(client, "route-clear@example.com").status_code == 401
        assert _login(client, "route-clear@example.com").status_code == 429


class TestRegisterRateLimit:
    def test_sixth_register_attempt_is_rate_limited(self, client):
        for index in range(5):
            assert _register(client, f"limit-reg-{index}@example.com").status_code == 200

        resp = _register(client, "limit-reg-5@example.com")
        assert resp.status_code == 429

    def test_rate_limited_register_creates_no_account(self, client, store):
        for index in range(5):
            _register(client, f"limit-none-{index}@example.com")
        _register(client, "limit-none-5@example.com")

        async def _count():
            rows = await store.conn.execute_fetchall(
                "SELECT COUNT(*) FROM users WHERE email = ?",
                ("limit-none-5@example.com",),
            )
            return rows[0][0]

        assert asyncio.run(_count()) == 0
