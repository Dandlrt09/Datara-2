"""RED tests for auth cross-cutting requirements.

Tests cover: cross-user access blocked, expired session, missing cookie,
duplicate email, and consistent 401 for bad credentials.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.sessions import router as sessions_router
from server.api.routers.settings import router as settings_router
from server.services.auth_service import generate_raw_token, hash_token, build_set_cookie_header
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(sessions_router)
    application.include_router(settings_router)

    import asyncio

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


class TestMissingCookie:
    """Task 2.9: Missing cookie → 401."""

    ENDPOINTS = [
        ("GET", "/api/auth/me"),
        ("GET", "/api/sessions"),
        ("POST", "/api/sessions"),
        ("DELETE", "/api/sessions/ses_001"),
        ("GET", "/api/settings"),
        ("PUT", "/api/settings"),
    ]

    def test_all_protected_endpoints_return_401_without_cookie(self, client):
        for method, path in self.ENDPOINTS:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should return 401, got {resp.status_code}"

    def test_invalid_cookie_returns_401(self, client):
        resp = client.get("/api/auth/me", headers={"Cookie": "session_id=garbage"})
        assert resp.status_code == 401


class TestExpiredSession:
    """Task 2.9: Expired session → 401."""

    async def test_expired_session_returns_401(self, client, store):
        """Create a user with an expired session, then verify 401."""
        # Create user and expired session via store
        user = await store.create_user("expired@example.com", "hash")
        raw_token = generate_raw_token()
        token_hash = hash_token(raw_token)
        # Negative TTL so session is expired immediately
        await store.create_auth_session(user["id"], token_hash, ttl_seconds=-1)
        cookie = build_set_cookie_header(raw_token)

        resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert resp.status_code == 401

    async def test_logout_invalidates_session(self, client, store):
        """After logout, the same cookie should return 401."""
        resp = client.post(
            "/api/auth/register",
            json={"email": "logout@example.com", "password": "password123"},
        )
        cookie = resp.headers["set-cookie"]

        # Logout
        client.post("/api/auth/logout", headers={"Cookie": cookie})

        # Same cookie should now return 401
        me_resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me_resp.status_code == 401


class TestDuplicateEmail:
    """Task 2.9: Duplicate email → 4xx."""

    def test_duplicate_email_returns_409(self, client):
        resp1 = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "password123"})
        assert resp1.status_code == 200
        resp2 = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "otherpass"})
        assert resp2.status_code == 409

    def test_duplicate_email_all_caps(self, client):
        """Email uniqueness should handle case-sensitive storage (SQLite default)."""
        client.post("/api/auth/register", json={"email": "CaseDup@example.com", "password": "password123"})
        # Same email but different case — this succeeds because SQLite's default
        # uniqueness is case-sensitive for TEXT values
        resp = client.post("/api/auth/register", json={"email": "casedup@example.com", "password": "password456"})
        assert resp.status_code == 200


class TestCrossUserAccess:
    """Task 2.9: Cross-user access blocked → 403/401."""

    async def test_cross_user_session_list(self, client, store):
        """User A's cookie should not see User B's sessions."""
        # Register user A
        resp_a = client.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"})
        cookie_a = resp_a.headers["set-cookie"]

        # Register user B
        resp_b = client.post("/api/auth/register", json={"email": "b@example.com", "password": "password123"})
        cookie_b = resp_b.headers["set-cookie"]

        # User B creates a session
        client.post("/api/sessions", json={"title": "B's session"}, headers={"Cookie": cookie_b})

        # User A lists sessions — should NOT see B's session
        resp = client.get("/api/sessions", headers={"Cookie": cookie_a})
        assert resp.status_code == 200
        sessions_a = resp.json()
        assert len(sessions_a) == 0, "User A should not see User B's sessions"

    async def test_cross_user_settings(self, client, store):
        """User A's settings should not be visible to User B."""
        resp_a = client.post("/api/auth/register", json={"email": "a2@example.com", "password": "password123"})
        cookie_a = resp_a.headers["set-cookie"]
        resp_b = client.post("/api/auth/register", json={"email": "b2@example.com", "password": "password123"})
        cookie_b = resp_b.headers["set-cookie"]

        # User A updates settings
        client.put("/api/settings", json={"default_model": "gpt-4o"}, headers={"Cookie": cookie_a})

        # User B gets settings — should NOT see A's settings
        b_settings = client.get("/api/settings", headers={"Cookie": cookie_b}).json()
        assert b_settings["default_model"] is None


class TestConsistent401:
    """Task 2.9: Consistent 401 for bad credentials."""

    def test_unknown_email_and_wrong_password_same_error(self, client):
        """Both bad email and bad password return identical 401 body."""
        # Register one user
        client.post("/api/auth/register", json={"email": "target@example.com", "password": "password123"})

        # Bad email
        resp_unknown = client.post("/api/auth/login", json={"email": "unknown@example.com", "password": "password123"})
        # Bad password
        resp_wrong = client.post("/api/auth/login", json={"email": "target@example.com", "password": "wrongpassword"})

        assert resp_unknown.status_code == 401
        assert resp_wrong.status_code == 401
        assert resp_unknown.json()["detail"] == resp_wrong.json()["detail"]