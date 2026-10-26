"""Integration tests for the active-sessions endpoints (T2).

Covers the contract end to end through the HTTP routes: the list is owner-scoped
and marks the caller's own row, one session or every other session can be closed,
the closed cookie dies on its next request, the caller's own session is never
closable, the browser captured at login is reported, rejected requests change
nothing, and the new-session notice shows once and can be acknowledged.

Uses FastAPI TestClient with a fresh in-memory SQLite store per test. Two
"browsers" are simulated with two cookies passed explicitly, the same way
``test_password_change.py`` does it.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations

PASSWORD = "password123"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0"
SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"


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


def _register(client, email="user@example.com", user_agent=CHROME):
    """Register (first session) and return its cookie."""
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD},
        headers={"User-Agent": user_agent},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


def _login(client, email="user@example.com", user_agent=FIREFOX):
    """Log in (additional session) and return its cookie."""
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"User-Agent": user_agent},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


def _list(client, cookie):
    resp = client.get("/api/auth/sessions", headers={"Cookie": cookie})
    assert resp.status_code == 200
    return resp.json()


def _other_session(body):
    """The only non-current session in a listing."""
    others = [s for s in body["sessions"] if not s["is_current"]]
    assert len(others) == 1
    return others[0]


def _other_id(body):
    return _other_session(body)["id"]


class TestListActiveSessions:
    def test_requires_authentication(self, client):
        assert client.get("/api/auth/sessions").status_code == 401

    def test_lists_the_callers_sessions_with_the_captured_browser(self, client):
        chrome_cookie = _register(client)
        _login(client)

        body = _list(client, chrome_cookie)

        assert len(body["sessions"]) == 2
        current = [s for s in body["sessions"] if s["is_current"]]
        assert len(current) == 1
        assert current[0]["user_agent"] == CHROME
        # Most recent activity first; ties break on the newest row.
        seen = [s["last_seen_at"] for s in body["sessions"]]
        assert seen == sorted(seen, reverse=True)
        assert set(body["sessions"][0]) == {
            "id",
            "user_agent",
            "created_at",
            "last_seen_at",
            "is_current",
        }

    def test_never_leaks_the_token_hash(self, client):
        cookie = _register(client)

        resp = client.get("/api/auth/sessions", headers={"Cookie": cookie})

        assert resp.status_code == 200
        assert "token_hash" not in resp.text

    def test_lists_only_the_callers_sessions(self, client):
        alice_cookie = _register(client, email="alice@example.com")
        _register(client, email="bob@example.com")

        body = _list(client, alice_cookie)

        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["user_agent"] == CHROME

    def test_activity_is_recorded_after_the_threshold(self, client, store):
        cookie = _register(client)
        asyncio.run(
            store.conn.execute(
                "UPDATE auth_sessions SET last_seen_at = datetime('now', '-10 minutes')"
            )
        )
        asyncio.run(store.conn.commit())

        client.get("/api/auth/me", headers={"Cookie": cookie})

        body = _list(client, cookie)
        touched = asyncio.run(
            store.conn.execute_fetchall(
                "SELECT last_seen_at, datetime('now', '-5 minutes') AS stale "
                "FROM auth_sessions"
            )
        )[0]
        assert touched["last_seen_at"] > touched["stale"]


class TestCloseSession:
    def test_closing_another_session_kills_its_cookie(self, client):
        chrome_cookie = _register(client)
        firefox_cookie = _login(client)
        other = _other_id(_list(client, chrome_cookie))

        resp = client.request(
            "DELETE",
            f"/api/auth/sessions/{other}",
            headers={"Cookie": chrome_cookie},
        )

        assert resp.status_code == 204
        assert (
            client.get("/api/auth/me", headers={"Cookie": firefox_cookie}).status_code
            == 401
        )
        assert (
            client.get("/api/auth/me", headers={"Cookie": chrome_cookie}).status_code
            == 200
        )
        assert len(_list(client, chrome_cookie)["sessions"]) == 1

    def test_the_current_session_cannot_be_closed(self, client):
        chrome_cookie = _register(client)
        current = [s for s in _list(client, chrome_cookie)["sessions"] if s["is_current"]]

        resp = client.request(
            "DELETE",
            f"/api/auth/sessions/{current[0]['id']}",
            headers={"Cookie": chrome_cookie},
        )

        assert resp.status_code == 409
        assert (
            client.get("/api/auth/me", headers={"Cookie": chrome_cookie}).status_code
            == 200
        )

    def test_another_users_session_is_not_closable(self, client):
        alice_cookie = _register(client, email="alice@example.com")
        bob_cookie = _register(client, email="bob@example.com")
        bob_id = _list(client, bob_cookie)["sessions"][0]["id"]

        resp = client.request(
            "DELETE",
            f"/api/auth/sessions/{bob_id}",
            headers={"Cookie": alice_cookie},
        )

        assert resp.status_code == 404
        assert (
            client.get("/api/auth/me", headers={"Cookie": bob_cookie}).status_code == 200
        )

    def test_an_unknown_session_is_404(self, client):
        cookie = _register(client)

        resp = client.request(
            "DELETE", "/api/auth/sessions/9999", headers={"Cookie": cookie}
        )

        assert resp.status_code == 404
        assert len(_list(client, cookie)["sessions"]) == 1

    def test_a_foreign_session_id_is_indistinguishable_from_a_missing_one(self, client):
        """D5: the route must not confirm that another user's id is real."""
        alice_cookie = _register(client, email="alice@example.com")
        bob_cookie = _register(client, email="bob@example.com")
        bob_id = _list(client, bob_cookie)["sessions"][0]["id"]
        before = _list(client, alice_cookie)

        foreign = client.request(
            "DELETE", f"/api/auth/sessions/{bob_id}", headers={"Cookie": alice_cookie}
        )
        missing = client.request(
            "DELETE", "/api/auth/sessions/999999", headers={"Cookie": alice_cookie}
        )

        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
        assert _list(client, alice_cookie) == before

    def test_closing_requires_authentication(self, client):
        assert client.request("DELETE", "/api/auth/sessions/1").status_code == 401

    def test_closing_every_other_session_keeps_the_caller(self, client):
        chrome_cookie = _register(client)
        firefox_cookie = _login(client)
        safari_cookie = _login(client, user_agent=SAFARI)

        resp = client.request(
            "DELETE", "/api/auth/sessions", headers={"Cookie": chrome_cookie}
        )

        assert resp.status_code == 204
        assert (
            client.get("/api/auth/me", headers={"Cookie": chrome_cookie}).status_code
            == 200
        )
        for dead in (firefox_cookie, safari_cookie):
            assert client.get("/api/auth/me", headers={"Cookie": dead}).status_code == 401
        assert len(_list(client, chrome_cookie)["sessions"]) == 1

    def test_closing_every_other_session_without_others_is_a_noop(self, client):
        cookie = _register(client)

        resp = client.request("DELETE", "/api/auth/sessions", headers={"Cookie": cookie})

        assert resp.status_code == 204
        assert len(_list(client, cookie)["sessions"]) == 1


class TestSessionRecording:
    def test_a_failing_activity_write_never_breaks_the_request(self, client, store):
        """D8: activity is bookkeeping, not authorization."""
        cookie = _register(client)

        async def boom(*args, **kwargs):
            raise RuntimeError("activity write exploded")

        store.touch_auth_session = boom

        assert (
            client.get("/api/auth/me", headers={"Cookie": cookie}).status_code == 200
        )

    def test_the_user_agent_is_truncated_at_the_route(self, client, store):
        """D2/S5: the header is caller-controlled and unbounded."""
        _register(client, user_agent="x" * 500)

        rows = asyncio.run(
            store.conn.execute_fetchall("SELECT user_agent FROM auth_sessions")
        )

        assert rows[0]["user_agent"] == "x" * 120


class TestNewSessionNotice:
    def test_no_notice_with_a_single_session(self, client):
        cookie = _register(client)

        assert _list(client, cookie)["new_session_at"] is None

    def test_a_second_login_arms_the_notice(self, client):
        chrome_cookie = _register(client)
        _login(client)

        body = _list(client, chrome_cookie)

        assert body["new_session_at"] == _other_session(body)["created_at"]

    def test_the_newest_session_is_not_warned_about_older_ones(self, client):
        _register(client)
        firefox_cookie = _login(client)

        assert _list(client, firefox_cookie)["new_session_at"] is None

    def test_acknowledging_clears_the_notice(self, client):
        chrome_cookie = _register(client)
        _login(client)
        notice = client.post(
            "/api/auth/sessions/notice-ack", headers={"Cookie": chrome_cookie}
        )

        assert notice.status_code == 204
        assert _list(client, chrome_cookie)["new_session_at"] is None
        # The acknowledged session is still alive: acknowledging is not closing.
        assert len(_list(client, chrome_cookie)["sessions"]) == 2

    def test_a_later_login_arms_the_notice_again(self, client):
        chrome_cookie = _register(client)
        _login(client)
        client.post("/api/auth/sessions/notice-ack", headers={"Cookie": chrome_cookie})

        _login(client, user_agent=SAFARI)

        assert _list(client, chrome_cookie)["new_session_at"] is not None

    def test_the_notice_is_per_user(self, client):
        alice_cookie = _register(client, email="alice@example.com")
        _register(client, email="bob@example.com")
        _login(client, email="alice@example.com")

        client.post("/api/auth/sessions/notice-ack", headers={"Cookie": alice_cookie})

        assert _list(client, alice_cookie)["new_session_at"] is None

    def test_acknowledging_requires_authentication(self, client):
        assert client.post("/api/auth/sessions/notice-ack").status_code == 401
