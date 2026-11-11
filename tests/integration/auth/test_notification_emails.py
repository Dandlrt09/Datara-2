"""Alert mails for sensitive account events end to end (F9/S6, S10).

The maintainer scoped exactly three events (S10): a password change
(``POST /password``), a completed password reset (``POST /reset-password``) and
a new session opened while another live session exists (``POST /login``).

What these probes pin for every event: exactly one mail reaches the account's
address with the expected subject and body, and a mailer that raises never
changes the HTTP response nor the side effect the request already applied.

Uses FastAPI TestClient with a fresh in-memory SQLite store per test. The mail
recorder comes from the integration suite's autouse ``conftest`` and the
authentication walk from ``tests.integration.auth.conftest``.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.services.mailer import (
    render_new_session_email,
    render_password_changed_email,
    render_password_reset_email,
)
from server.services.sqlite_store import SqliteStore
from tests.integration.auth.conftest import register_verified
from tests.test_helpers import apply_all_migrations

PASSWORD = "password123"
NEW_PASSWORD = "newpassword456"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0"


class _RaisingMailer:
    """A mailer that always fails, to prove delivery is best effort (S10)."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        raise RuntimeError("smtp is down")


@pytest.fixture
def store():
    """Fresh in-memory store wired into ``server.api.store._store``."""
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


def _install_failing_mailer(monkeypatch) -> None:
    """Make every route's mailer raise, after any setup that needs the mail."""
    monkeypatch.setattr(
        "server.services.mailer.resolve_mailer", lambda: _RaisingMailer()
    )


def _login(client, email: str, password: str = PASSWORD, user_agent: str = FIREFOX):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": user_agent},
    )


def _change_password(client, cookie: str, new_password: str = NEW_PASSWORD):
    return client.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": new_password},
        headers={"Cookie": cookie},
    )


class TestPasswordChangedMail:
    def test_sends_exactly_one_alert_to_the_account(self, client, recorder):
        email = "changed@example.com"
        cookie = register_verified(client, email).headers["set-cookie"]
        recorder.clear()

        resp = _change_password(client, cookie)

        assert resp.status_code == 204
        subject, body = render_password_changed_email()
        assert recorder.messages == [{"to": email, "subject": subject, "body": body}]

    def test_a_failing_mailer_leaves_the_response_and_the_password_unchanged(
        self, client, recorder, monkeypatch
    ):
        email = "changed-fail@example.com"
        cookie = register_verified(client, email).headers["set-cookie"]
        _install_failing_mailer(monkeypatch)

        resp = _change_password(client, cookie)

        assert resp.status_code == 204
        # The change the request applied survives the mail failure.
        assert _login(client, email, NEW_PASSWORD).status_code == 200
        assert _login(client, email, PASSWORD).status_code == 401


class TestPasswordResetMail:
    def test_sends_exactly_one_alert_to_the_account(self, client, recorder):
        email = "reset-done@example.com"
        register_verified(client, email)
        forgot = client.post("/api/auth/forgot-password", json={"email": email})
        assert forgot.status_code == 202
        token = recorder.last_token(email)
        assert token is not None
        recorder.clear()

        resp = client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": NEW_PASSWORD},
        )

        assert resp.status_code == 204
        subject, body = render_password_reset_email()
        assert recorder.messages == [{"to": email, "subject": subject, "body": body}]

    def test_a_failing_mailer_leaves_the_response_and_the_password_unchanged(
        self, client, recorder, monkeypatch
    ):
        email = "reset-fail@example.com"
        register_verified(client, email)
        forgot = client.post("/api/auth/forgot-password", json={"email": email})
        assert forgot.status_code == 202
        token = recorder.last_token(email)
        assert token is not None
        _install_failing_mailer(monkeypatch)

        resp = client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": NEW_PASSWORD},
        )

        assert resp.status_code == 204
        assert _login(client, email, NEW_PASSWORD).status_code == 200
        assert _login(client, email, PASSWORD).status_code == 401


class TestNewSessionMail:
    def test_the_first_login_does_not_alert(self, client, recorder):
        register_verified(client, "first-login@example.com", user_agent=CHROME)

        subjects = [message["subject"] for message in recorder.messages]
        assert render_new_session_email()[0] not in subjects

    def test_a_second_login_alerts_once_and_names_the_browser(self, client, recorder):
        email = "second-login@example.com"
        register_verified(client, email, user_agent=CHROME)
        recorder.clear()

        resp = _login(client, email, user_agent=FIREFOX)

        assert resp.status_code == 200
        subject, body = render_new_session_email(user_agent=FIREFOX)
        assert recorder.messages == [{"to": email, "subject": subject, "body": body}]

    def test_a_failing_mailer_does_not_block_the_new_session(
        self, client, recorder, monkeypatch
    ):
        email = "second-login-fail@example.com"
        register_verified(client, email, user_agent=CHROME)
        _install_failing_mailer(monkeypatch)

        resp = _login(client, email, user_agent=FIREFOX)

        assert resp.status_code == 200
        assert resp.headers["set-cookie"]
        assert client.get("/api/auth/me").status_code == 200
