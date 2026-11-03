"""Password recovery end to end (T4: S4, D6, D7, D8, D12).

These probes pin the recovery contract: ``forgot-password`` never confirms who
exists (a non-enumeration 202 either way), the mailed reset token is single-use
and expires, a short password is refused before the token is spent, and a
completed reset kills every prior session while proving the address.

Uses FastAPI TestClient with a fresh in-memory SQLite store per test. The
mailer recorder comes from the integration suite's autouse ``conftest``.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.integration.auth.conftest import register_verified
from tests.test_helpers import apply_all_migrations

PASSWORD = "password123"
NEW_PASSWORD = "newpassword456"


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


def _register(client, email: str, password: str = PASSWORD):
    return client.post(
        "/api/auth/register",
        json={
            "terms_version": TERMS_VERSION,
            "email": email,
            "password": password,
        },
    )


def _forgot(client, email: str):
    return client.post("/api/auth/forgot-password", json={"email": email})


def _reset(client, token: str, new_password: str = NEW_PASSWORD):
    return client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )


def _login(client, email: str, password: str):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


class TestForgotPasswordNoEnumeration:
    def test_unknown_email_is_202_and_sends_no_mail(self, client, recorder):
        resp = _forgot(client, "nobody-forgot@example.com")

        assert resp.status_code == 202
        assert recorder.messages == []

    def test_unknown_and_existing_answers_are_byte_identical(self, client, recorder):
        register_verified(client, "known-forgot@example.com")

        unknown = _forgot(client, "nobody-forgot@example.com")
        existing = _forgot(client, "known-forgot@example.com")

        assert unknown.status_code == 202
        assert existing.status_code == 202
        assert unknown.content == existing.content

    def test_wrong_shaped_email_is_still_202_and_no_422(self, client, recorder):
        resp = _forgot(client, "not-an-email")

        assert resp.status_code == 202
        assert recorder.messages == []

    def test_forgot_is_rate_limited(self, client, recorder):
        email = "forgot-limit@example.com"
        for _ in range(5):
            assert _forgot(client, email).status_code == 202

        resp = _forgot(client, email)
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) > 0


class TestResetPassword:
    def test_forgot_mail_token_resets_the_password(self, client, recorder):
        register_verified(client, "reset-happy@example.com")
        assert _forgot(client, "reset-happy@example.com").status_code == 202

        token = recorder.last_token("reset-happy@example.com")
        assert token is not None

        assert _reset(client, token).status_code == 204
        assert _login(client, "reset-happy@example.com", PASSWORD).status_code == 401
        assert (
            _login(client, "reset-happy@example.com", NEW_PASSWORD).status_code == 200
        )

    def test_unknown_token_is_400(self, client):
        resp = _reset(client, "not-a-real-token")

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid or expired token"

    def test_used_token_is_400(self, client, recorder):
        register_verified(client, "reset-reuse@example.com")
        _forgot(client, "reset-reuse@example.com")
        token = recorder.last_token("reset-reuse@example.com")
        assert token is not None

        assert _reset(client, token).status_code == 204
        second = _reset(client, token)
        assert second.status_code == 400
        assert second.json()["detail"] == "Invalid or expired token"

    def test_short_password_is_422_and_does_not_burn_the_token(
        self, client, recorder
    ):
        register_verified(client, "reset-short@example.com")
        _forgot(client, "reset-short@example.com")
        token = recorder.last_token("reset-short@example.com")
        assert token is not None

        short = _reset(client, token, "short")
        assert short.status_code == 422

        # The rejected attempt spent nothing: the same token still resets.
        assert _reset(client, token).status_code == 204

    def test_reset_kills_every_prior_session(self, client, recorder):
        login = register_verified(client, "reset-sessions@example.com")
        assert login.headers["set-cookie"] is not None
        assert client.get("/api/auth/me").status_code == 200

        _forgot(client, "reset-sessions@example.com")
        token = recorder.last_token("reset-sessions@example.com")
        assert token is not None
        assert _reset(client, token).status_code == 204

        assert client.get("/api/auth/me").status_code == 401

    def test_reset_proves_the_address_for_an_unverified_account(
        self, client, recorder
    ):
        email = "reset-unverified@example.com"
        assert _register(client, email).status_code == 200

        assert _forgot(client, email).status_code == 202
        token = recorder.last_token(email)
        assert token is not None

        assert _reset(client, token).status_code == 204
        assert _login(client, email, NEW_PASSWORD).status_code == 200
