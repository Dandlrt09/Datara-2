"""Integration tests for the local-mode guard on the email flows (F1 / T2, S2, D2).

The desktop build runs with ``DATARA_MODE=local`` and has no mailbox at all, so
registration, verification and recovery cannot work there. Hiding the screens in
the frontend is the UX, not the enforcement: a direct call to those endpoints
used to be served anyway, and a hosted account created in a local install flips
``hosted_accounts`` and sends every later boot to ``/login`` with no way back to
the local profile (S2). These tests pin the backend answer -- 403 before any
validation, brake or row -- and pin that hosted mode is untouched (D2/D3).

``login`` is deliberately NOT guarded: an install that already holds email
accounts keeps its login (D3).
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.test_helpers import apply_all_migrations

REFUSAL = "Email flows are only available in hosted mode"

# Every endpoint that exists to send or redeem mail. ``resend-verification`` is
# here for the same reason as the other four: it sends mail, so local mode has
# nothing to offer it either (the approved finding named only the first four).
EMAIL_FLOW_CALLS = [
    pytest.param(
        "/api/auth/register",
        {
            "email": "ana@example.com",
            "password": "password123",
            "terms_version": TERMS_VERSION,
        },
        id="register",
    ),
    pytest.param("/api/auth/verify-email", {"token": "a" * 32}, id="verify-email"),
    pytest.param(
        "/api/auth/resend-verification",
        {"email": "ana@example.com"},
        id="resend-verification",
    ),
    pytest.param(
        "/api/auth/forgot-password", {"email": "ana@example.com"}, id="forgot-password"
    ),
    pytest.param(
        "/api/auth/reset-password",
        {"token": "a" * 32, "new_password": "password123"},
        id="reset-password",
    ),
]


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


def _count(store: SqliteStore, table: str) -> int:
    """Count rows of *table* on an already-created schema; never creates any."""

    async def _count_rows() -> int:
        rows = await store.conn.execute_fetchall(f"SELECT COUNT(*) FROM {table}")
        return rows[0][0]

    return asyncio.run(_count_rows())


@pytest.fixture
def db_counts():
    """The three tables a refused email flow must leave untouched."""

    def _snapshot(store: SqliteStore) -> dict[str, int]:
        return {
            table: _count(store, table)
            for table in ("users", "auth_tokens", "auth_attempts")
        }

    return _snapshot


class TestLocalModeRefuses:
    @pytest.mark.parametrize("path, body", EMAIL_FLOW_CALLS)
    def test_the_endpoint_answers_403_and_writes_nothing(
        self, client, store, db_counts, monkeypatch, path, body
    ):
        monkeypatch.setenv("DATARA_MODE", "local")
        before = db_counts(store)

        resp = client.post(path, json=body)

        assert resp.status_code == 403
        assert resp.json()["detail"] == REFUSAL
        # No account, no token, and no attempt brake spent (the guard runs
        # before the limiter, so a refused call costs the caller nothing).
        assert db_counts(store) == before
        assert before == {"users": 0, "auth_tokens": 0, "auth_attempts": 0}

    @pytest.mark.parametrize("path, _body", EMAIL_FLOW_CALLS)
    def test_the_refusal_comes_before_the_body_is_validated(
        self, client, store, db_counts, monkeypatch, path, _body
    ):
        """A malformed body still gets the mode answer, not a 422.

        The point of the order is that the mode, not the payload, decides: an
        empty body must never produce a validation answer that implies the
        endpoint is available here.
        """
        monkeypatch.setenv("DATARA_MODE", "local")
        before = db_counts(store)

        resp = client.post(path, json={})

        assert resp.status_code == 403
        assert resp.json()["detail"] == REFUSAL
        assert db_counts(store) == before

    def test_resend_is_refused_before_it_could_send_mail(
        self, client, store, recorder, monkeypatch
    ):
        """An unverified account exists, so the resend WOULD have mailed (D6)."""
        monkeypatch.setenv("DATARA_MODE", "hosted")
        registered = client.post(
            "/api/auth/register",
            json={
                "email": "ana@example.com",
                "password": "password123",
                "terms_version": TERMS_VERSION,
            },
        )
        assert registered.status_code == 200
        mails_before = len(recorder.messages)
        tokens_before = _count(store, "auth_tokens")
        assert mails_before == 1

        monkeypatch.setenv("DATARA_MODE", "local")
        resp = client.post(
            "/api/auth/resend-verification", json={"email": "ana@example.com"}
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == REFUSAL
        # Nothing was mailed and no fresh token was issued (D1/D6).
        assert len(recorder.messages) == mails_before
        assert _count(store, "auth_tokens") == tokens_before


class TestHostedModeIsUnchanged:
    def test_register_still_creates_the_account_and_mails_the_link(
        self, client, store, recorder, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "hosted")

        resp = client.post(
            "/api/auth/register",
            json={
                "email": "ana@example.com",
                "password": "password123",
                "terms_version": TERMS_VERSION,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["email"] == "ana@example.com"
        assert _count(store, "users") == 1
        assert _count(store, "auth_tokens") == 1
        assert recorder.last_token("ana@example.com") is not None
        # Register still opens no session (D4/S3).
        assert resp.headers.get("set-cookie") is None

    def test_the_whole_email_walk_still_works_including_login(
        self, client, store, recorder, monkeypatch
    ):
        """D3: login stays available, so the hosted flows must survive too."""
        monkeypatch.setenv("DATARA_MODE", "hosted")
        registered = client.post(
            "/api/auth/register",
            json={
                "email": "ana@example.com",
                "password": "password123",
                "terms_version": TERMS_VERSION,
            },
        )
        assert registered.status_code == 200
        token = recorder.last_token("ana@example.com")
        assert token is not None

        verified = client.post("/api/auth/verify-email", json={"token": token})
        assert verified.status_code == 204

        login = client.post(
            "/api/auth/login",
            json={"email": "ana@example.com", "password": "password123"},
        )
        assert login.status_code == 200
        assert login.headers.get("set-cookie") is not None

        recovered = client.post(
            "/api/auth/forgot-password", json={"email": "ana@example.com"}
        )
        assert recovered.status_code == 202
        assert recorder.last_token("ana@example.com") is not None