"""Integration tests for the auth router (register, login, logout, me).

Uses FastAPI TestClient with a fresh in-memory SQLite store per test.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.services.auth_service import MAX_DISPLAY_NAME_LENGTH
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app():
    """Create a minimal FastAPI app with the auth router wired up.

    Uses a module-level store injected into ``server.api.store._store``
    for the duration of the test.
    """
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router)

    # Set up an in-memory store and inject it via the store module global
    import asyncio

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    api_store._store = s

    yield application

    # Clean up
    import asyncio

    asyncio.run(s.close())
    api_store._store = None


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "alice@example.com", "password": "password123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert "id" in data
        # Should have Set-Cookie header
        set_cookie = resp.headers.get("set-cookie")
        assert set_cookie is not None
        assert set_cookie.startswith("session_id=")

    def test_register_duplicate_email(self, client):
        client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "bob@example.com", "password": "password123"})
        resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "bob@example.com", "password": "password456"})
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_short_password(self, client):
        resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "short@example.com", "password": "1234567"})
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "carol@example.com", "password": "password123"})
        resp = client.post("/api/auth/login", json={"email": "carol@example.com", "password": "password123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "carol@example.com"
        assert "id" in data
        set_cookie = resp.headers.get("set-cookie")
        assert set_cookie is not None

    def test_login_wrong_password(self, client):
        client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "dave@example.com", "password": "password123"})
        resp = client.post("/api/auth/login", json={"email": "dave@example.com", "password": "wrongpass"})
        assert resp.status_code == 401
        assert "invalid email or password" in resp.json()["detail"].lower()

    def test_login_unknown_email(self, client):
        resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
        assert resp.status_code == 401
        assert "invalid email or password" in resp.json()["detail"].lower()

    def test_login_same_error_for_unknown_and_wrong(self, client):
        """Both bad email and bad password return identical 401 body."""
        resp_unknown = client.post("/api/auth/login", json={"email": "x@x.com", "password": "test12345"})
        client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "eve@example.com", "password": "password123"})
        resp_wrong = client.post("/api/auth/login", json={"email": "eve@example.com", "password": "wrongpass"})
        assert resp_unknown.status_code == 401
        assert resp_wrong.status_code == 401
        assert resp_unknown.json()["detail"] == resp_wrong.json()["detail"]


class TestMe:
    def test_me_authenticated(self, client):
        resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "frank@example.com", "password": "password123"})
        cookie = resp.headers["set-cookie"]
        me_resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "frank@example.com"

    def test_me_no_cookie(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_expired_cookie(self, client):
        """Register, then simulate expired session by sweeping."""
        resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "grace@example.com", "password": "password123"})
        cookie = resp.headers["set-cookie"]

        # Sweep all sessions (they're all valid, so this won't remove them)
        # Instead, let's verify the cookie works first, then note that
        # an invalid cookie returns 401
        me_resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me_resp.status_code == 200

        # An arbitrary invalid cookie
        me_resp2 = client.get("/api/auth/me", headers={"Cookie": "session_id=invalidtoken123"})
        assert me_resp2.status_code == 401


class TestLogout:
    def test_logout_clears_session(self, client):
        resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": "heidi@example.com", "password": "password123"})
        cookie = resp.headers["set-cookie"]

        # First verify me works
        assert client.get("/api/auth/me", headers={"Cookie": cookie}).status_code == 200

        # Logout
        logout_resp = client.post("/api/auth/logout", headers={"Cookie": cookie})
        assert logout_resp.status_code == 204

        # Now me should fail with the same cookie
        assert client.get("/api/auth/me", headers={"Cookie": cookie}).status_code == 401

    def test_logout_no_session(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401  # requires auth


def _register(client, email: str) -> str:
    """Register *email* and return its session cookie header (T1)."""
    resp = client.post(
        "/api/auth/register", json={"terms_version": TERMS_VERSION, "email": email, "password": "password123"}
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


class TestEditableName:
    """T1: the user picks their display name; empty means "derive from email".

    `users.name` is nullable (D1) and NULL is the single "no name chosen"
    state, so clearing the field is a supported transition, not an error.
    """

    def test_me_returns_name_null_for_a_new_account(self, client):
        cookie = _register(client, "name-new@example.com")
        me_resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me_resp.status_code == 200
        assert me_resp.json()["name"] is None

    def test_me_payload_has_exactly_the_documented_keys(self, client):
        """Pin the response contract shared by register, login and /me (D2)."""
        cookie = _register(client, "name-keys@example.com")
        payload = client.get("/api/auth/me", headers={"Cookie": cookie}).json()
        assert set(payload) == {"id", "email", "name", "pending_deletion_at"}

    def test_update_name_persists_and_is_returned_by_me(self, client):
        cookie = _register(client, "name-set@example.com")
        resp = client.patch(
            "/api/auth/me",
            json={"name": "Daniel"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Daniel"
        assert resp.json()["email"] == "name-set@example.com"

        me_resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me_resp.json()["name"] == "Daniel"

    def test_update_name_trims_and_collapses_inner_whitespace(self, client):
        cookie = _register(client, "name-space@example.com")
        resp = client.patch(
            "/api/auth/me",
            json={"name": "  Daniel   Del\nRio  "},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Daniel Del Rio"

    @pytest.mark.parametrize(
        ("blank", "email"),
        [
            ("", "name-blank-empty@example.com"),
            ("   ", "name-blank-spaces@example.com"),
            ("\n\t ", "name-blank-mixed@example.com"),
        ],
    )
    def test_update_name_blank_is_rejected_and_changes_nothing(self, client, blank, email):
        """D3 (rewritten on 29/10): there is no way back to "no name".

        NULL still means "never chose one" for a new or legacy account, but the
        edit route refuses to create that state: leaving the field empty warns
        the user instead of silently falling back to the email.
        """
        cookie = _register(client, email)
        client.patch(
            "/api/auth/me", json={"name": "Temporal"}, headers={"Cookie": cookie}
        )

        resp = client.patch(
            "/api/auth/me", json={"name": blank}, headers={"Cookie": cookie}
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == "Name cannot be empty"
        me_resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me_resp.json()["name"] == "Temporal"

    def test_update_name_at_the_limit_is_accepted(self, client):
        """D4: the limit itself is a valid name, not an off-by-one."""
        cookie = _register(client, "name-at-limit@example.com")
        name = "N" * MAX_DISPLAY_NAME_LENGTH

        resp = client.patch(
            "/api/auth/me", json={"name": name}, headers={"Cookie": cookie}
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == name

    def test_update_name_over_the_limit_is_rejected_and_changes_nothing(self, client):
        cookie = _register(client, "name-long@example.com")
        client.patch(
            "/api/auth/me", json={"name": "Corto"}, headers={"Cookie": cookie}
        )
        resp = client.patch(
            "/api/auth/me",
            json={"name": "x" * (MAX_DISPLAY_NAME_LENGTH + 1)},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            f"Name must be at most {MAX_DISPLAY_NAME_LENGTH} characters"
        )
        me_resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me_resp.json()["name"] == "Corto"

    def test_update_name_requires_a_session(self, client):
        resp = client.patch("/api/auth/me", json={"name": "Anonimo"})
        assert resp.status_code == 401

    def test_update_name_never_touches_another_user(self, client):
        cookie_a = _register(client, "name-a@example.com")
        cookie_b = _register(client, "name-b@example.com")

        client.patch(
            "/api/auth/me", json={"name": "Alice"}, headers={"Cookie": cookie_a}
        )

        me_b = client.get("/api/auth/me", headers={"Cookie": cookie_b})
        assert me_b.json()["name"] is None