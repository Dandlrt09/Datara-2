"""The hard email gate end to end (T3: S3, S4, D4, D5, D6, D10).

These probes pin the contract change in letters: registration opens no session,
login refuses an unproven address, the mailed token is single-use, and the
resend path answers identically for every address so it cannot be used to
enumerate accounts.

Uses FastAPI TestClient with a fresh in-memory SQLite store per test. The
mailer recorder comes from this suite's autouse ``conftest`` fixture.
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


def _register(client, email: str):
    return client.post(
        "/api/auth/register",
        json={
            "terms_version": TERMS_VERSION,
            "email": email,
            "password": PASSWORD,
        },
    )


class TestRegisterOpensNoSession:
    def test_register_sends_the_verification_mail_and_sets_no_cookie(
        self, client, recorder
    ):
        resp = _register(client, "gate-register@example.com")

        assert resp.status_code == 200
        assert resp.headers.get("set-cookie") is None
        assert len(recorder.messages) == 1
        assert recorder.messages[0]["to"] == "gate-register@example.com"
        assert recorder.last_token("gate-register@example.com") is not None


class TestVerifyThenLogin:
    def test_mailed_token_verifies_and_then_login_returns_a_cookie(
        self, client, recorder
    ):
        _register(client, "gate-happy@example.com")
        token = recorder.last_token("gate-happy@example.com")
        assert token is not None

        verified = client.post("/api/auth/verify-email", json={"token": token})
        assert verified.status_code == 204

        login = client.post(
            "/api/auth/login",
            json={"email": "gate-happy@example.com", "password": PASSWORD},
        )
        assert login.status_code == 200
        cookie = login.headers.get("set-cookie")
        assert cookie is not None
        assert cookie.startswith("session_id=")

    def test_a_reused_token_is_refused(self, client, recorder):
        _register(client, "gate-reuse@example.com")
        token = recorder.last_token("gate-reuse@example.com")

        first = client.post("/api/auth/verify-email", json={"token": token})
        second = client.post("/api/auth/verify-email", json={"token": token})

        assert first.status_code == 204
        assert second.status_code == 400
        assert second.json()["detail"] == "Invalid or expired token"


class TestLoginRefusesUnverified:
    def test_correct_credentials_but_unverified_are_403_with_no_cookie(
        self, client, recorder
    ):
        _register(client, "gate-unverified@example.com")

        resp = client.post(
            "/api/auth/login",
            json={"email": "gate-unverified@example.com", "password": PASSWORD},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Email not verified"
        assert resp.headers.get("set-cookie") is None

    def test_wrong_credentials_stay_the_identical_401(self, client, recorder):
        _register(client, "gate-wrong@example.com")

        resp = client.post(
            "/api/auth/login",
            json={"email": "gate-wrong@example.com", "password": "wrongpass"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"


class TestResendVerification:
    def test_unknown_email_is_202_and_sends_nothing(self, client, recorder):
        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "nobody@example.com"},
        )

        assert resp.status_code == 202
        assert recorder.messages == []

    def test_known_unverified_email_sends_a_new_mail_that_kills_the_old_token(
        self, client, recorder
    ):
        _register(client, "gate-resend@example.com")
        old_token = recorder.last_token("gate-resend@example.com")

        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "gate-resend@example.com"},
        )

        assert resp.status_code == 202
        assert len(recorder.messages) == 2
        new_token = recorder.last_token("gate-resend@example.com")
        assert new_token is not None
        assert new_token != old_token

        assert (
            client.post("/api/auth/verify-email", json={"token": old_token}).status_code
            == 400
        )
        assert (
            client.post("/api/auth/verify-email", json={"token": new_token}).status_code
            == 204
        )

    def test_verified_email_is_202_and_sends_nothing(self, client, recorder):
        register_verified(client, "gate-already@example.com")
        recorder.messages.clear()

        resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "gate-already@example.com"},
        )

        assert resp.status_code == 202
        assert recorder.messages == []

    def test_resend_is_rate_limited(self, client, recorder):
        email = "gate-resend-limit@example.com"
        for _ in range(5):
            assert (
                client.post(
                    "/api/auth/resend-verification", json={"email": email}
                ).status_code
                == 202
            )

        resp = client.post("/api/auth/resend-verification", json={"email": email})
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) > 0


class TestVerifyEmailRateLimit:
    """The redemption endpoint is braked by origin (F9/S5).

    A token is 32 random bytes, so guessing one is not a real threat; the brake
    is the flood protection every other auth route already has. It is keyed on
    the source address only: the token is the secret being tried, so keying on
    it would give each attempt a fresh key and brake nothing.
    """

    def test_verify_email_is_rate_limited(self, client):
        for _ in range(5):
            resp = client.post("/api/auth/verify-email", json={"token": "nope"})
            assert resp.status_code == 400

        resp = client.post("/api/auth/verify-email", json={"token": "nope"})
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) > 0

    def test_the_brake_does_not_eat_a_valid_token(self, client, recorder):
        _register(client, "gate-brake-token@example.com")
        token = recorder.last_token("gate-brake-token@example.com")
        assert token is not None

        for _ in range(4):
            assert (
                client.post(
                    "/api/auth/verify-email", json={"token": "nope"}
                ).status_code
                == 400
            )

        # The fifth attempt is the real one: below the brake, it must verify.
        verified = client.post("/api/auth/verify-email", json={"token": token})
        assert verified.status_code == 204
