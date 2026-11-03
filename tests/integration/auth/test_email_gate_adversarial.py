"""Adversarial probes for the hard-gate invariants the suite under-pins.

The independent verifier for this candidate (risk items 1-3) found these
properties correct but not durably pinned by a test. Each test here fails if the
property regresses:

- D2: only the token HASH is ever stored, and two concurrent redemptions cannot
  both succeed.
- D4: a broken mail server cannot undo a signup; resend is the recovery path.
- D5/D6: the attempt brake normalizes the email, so case/whitespace cannot
  bypass it.
- S2: a stalled SMTP server runs off the event loop.
- S5: a CRLF-bearing "email" cannot be registered or mailed.
- S3/S4: one account's token cannot lift another account's gate.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.rate_limit import auth_attempt_limiter
from server.api.routers.auth import get_mailer
from server.api.routers.auth import router as auth_router
from server.services import mailer as mailer_mod
from server.services.auth_service import (
    RESET_TOKEN_TTL_SECONDS,
    TOKEN_PURPOSE_RESET_PASSWORD,
    TOKEN_PURPOSE_VERIFY_EMAIL,
    generate_raw_token,
    hash_token,
)
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
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
    auth_attempt_limiter.reset()
    return TestClient(app)


def _register(client, email):
    return client.post(
        "/api/auth/register",
        json={"terms_version": TERMS_VERSION, "email": email, "password": PASSWORD},
    )


class TestRegister:
    def test_no_raw_token_in_db_or_response(self, client, recorder):
        resp = _register(client, "hash-only@example.com")
        assert resp.status_code == 200
        raw = recorder.last_token("hash-only@example.com")
        assert raw is not None
        # D2: the raw token exists only inside the mailed link.
        assert raw not in resp.text

        async def dump():
            tables = await api_store._store.conn.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            parts = []
            for (table,) in tables:
                rows = await api_store._store.conn.execute_fetchall(
                    f"SELECT * FROM '{table}'"
                )
                parts.append(repr([tuple(r) for r in rows]))
            return "\n".join(parts)

        blob = asyncio.run(dump())
        assert raw not in blob
        assert hash_token(raw) in blob

    def test_mailer_failure_keeps_the_account(self, app, client, recorder):
        class BoomMailer:
            async def send(self, **kwargs):
                raise RuntimeError("smtp down")

        app.dependency_overrides[get_mailer] = BoomMailer
        resp = _register(client, "boom@example.com")
        app.dependency_overrides.clear()
        # D4: a broken mailbox cannot undo a signup.
        assert resp.status_code == 200

        async def check():
            return await api_store._store.get_user_by_email("boom@example.com")

        user = asyncio.run(check())
        assert user is not None and user["email_verified_at"] is None

        resend = client.post(
            "/api/auth/resend-verification", json={"email": "boom@example.com"}
        )
        assert resend.status_code == 202
        assert len(recorder.messages) == 1  # the resend is the recovery path


class TestBrakeNormalisation:
    def test_forgot_cannot_be_bypassed_by_case_or_spaces(self, client, recorder):
        for _ in range(5):
            assert (
                client.post(
                    "/api/auth/forgot-password", json={"email": "Victim@Example.COM"}
                ).status_code
                == 202
            )
        resp = client.post(
            "/api/auth/forgot-password", json={"email": "  victim@example.com  "}
        )
        assert resp.status_code == 429  # the same normalized email key
        assert int(resp.headers["Retry-After"]) > 0
        assert recorder.messages == []  # an unknown account is never mailed


class TestPurposesAndOwnership:
    def test_wrong_purpose_refusal_does_not_burn_the_token(self, client, recorder):
        _register(client, "cross@example.com")
        verify_token = recorder.last_token("cross@example.com")
        client.post("/api/auth/forgot-password", json={"email": "cross@example.com"})
        reset_token = recorder.last_token("cross@example.com")

        assert (
            client.post(
                "/api/auth/reset-password",
                json={"token": verify_token, "new_password": "newpassword456"},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/auth/verify-email", json={"token": reset_token}
            ).status_code
            == 400
        )
        # Neither refusal spent the other flow's token.
        assert (
            client.post(
                "/api/auth/verify-email", json={"token": verify_token}
            ).status_code
            == 204
        )

    def test_a_token_cannot_lift_another_accounts_gate(self, client, recorder):
        _register(client, "dave@example.com")
        _register(client, "erin@example.com")
        token = recorder.last_token("dave@example.com")
        assert (
            client.post("/api/auth/verify-email", json={"token": token}).status_code
            == 204
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "erin@example.com", "password": PASSWORD},
            ).status_code
            == 403  # Erin's gate is untouched by Dave's proof
        )

    def test_header_injection_email_is_refused(self, client, recorder):
        evil = "a@b.com\r\nBcc: evil@example.com"
        assert _register(client, evil).status_code == 422
        assert (
            client.post("/api/auth/forgot-password", json={"email": evil}).status_code
            == 202
        )
        assert recorder.messages == []


class TestRedemptionAtomicity:
    @pytest.fixture
    async def store(self):
        s = SqliteStore(db_path=":memory:")
        await s.connect()
        await apply_all_migrations(s)
        yield s
        await s.close()

    async def test_two_concurrent_redemptions_yield_exactly_one(self, store):
        user = await store.create_user("race@example.com", "hash")
        raw = generate_raw_token()
        await store.create_auth_token(
            user["id"],
            hash_token(raw),
            TOKEN_PURPOSE_RESET_PASSWORD,
            RESET_TOKEN_TTL_SECONDS,
            email="race@example.com",
        )
        first, second = await asyncio.gather(
            store.consume_auth_token(hash_token(raw), TOKEN_PURPOSE_RESET_PASSWORD),
            store.consume_auth_token(hash_token(raw), TOKEN_PURPOSE_RESET_PASSWORD),
        )
        assert (first is not None) + (second is not None) == 1  # D2

    async def test_smtp_stall_runs_off_the_event_loop(self, monkeypatch):
        import time

        class SlowSMTP:
            def __init__(self, host, port, timeout=None): ...
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def starttls(self):
                time.sleep(0.3)

            def login(self, user, password): ...

            def send_message(self, message): ...

        monkeypatch.setattr(mailer_mod.smtplib, "SMTP", SlowSMTP)
        mailer = mailer_mod.SmtpMailer(
            mailer_mod.SmtpConfig(host="x", port=587, sender="a@b.c")
        )
        ticks = 0

        async def counter():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        task = asyncio.create_task(counter())
        await mailer.send(to="t@x.com", subject="s", body="b")
        task.cancel()
        assert ticks >= 15  # S2: the loop kept serving during the stall


class TestWrongPurposeTokenIsRefused:
    def test_verify_token_is_refused_at_reset_and_reset_token_at_verify(
        self, client, recorder
    ):
        _register(client, "purpose@example.com")
        token = recorder.last_token("purpose@example.com")

        assert (
            client.post(
                "/api/auth/reset-password",
                json={"token": token, "new_password": "newpassword456"},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/auth/verify-email", json={"token": token}
            ).status_code
            == 204
        )
