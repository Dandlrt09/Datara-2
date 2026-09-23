"""Integration tests for the sessions router (list, create, rename, delete)."""

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import event_bus as api_event_bus
from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.sessions import router as sessions_router
from server.services.events import EventBus, SessionEvent, SessionEventType
from server.services.sqlite_store import SqliteStore

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
INIT_SQL_PATH = MIGRATIONS_DIR / "0001_init.sql"


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(sessions_router)

    import asyncio

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        init_sql = INIT_SQL_PATH.read_text(encoding="utf-8")
        await s.conn.executescript(init_sql)
        await s.conn.commit()

    asyncio.run(_setup())
    api_store._store = s

    yield application

    asyncio.run(s.close())
    api_store._store = None


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """Register a user and return (client, cookie)."""
    resp = client.post("/api/auth/register", json={"email": "alice@example.com", "password": "password123"})
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"]
    return cookie


class TestListSessions:
    def test_list_empty(self, client, auth_client):
        cookie = auth_client
        resp = client.get("/api/sessions", headers={"Cookie": cookie})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_create(self, client, auth_client):
        cookie = auth_client
        client.post("/api/sessions", json={"title": "My chat"}, headers={"Cookie": cookie})
        resp = client.get("/api/sessions", headers={"Cookie": cookie})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "My chat"

    def test_list_requires_auth(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 401


class TestCreateSession:
    def test_create_default_title(self, client, auth_client):
        cookie = auth_client
        resp = client.post("/api/sessions", json={}, headers={"Cookie": cookie})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "New chat"
        assert data["id"].startswith("ses_")

    def test_create_custom_title(self, client, auth_client):
        cookie = auth_client
        resp = client.post("/api/sessions", json={"title": "Analysis 1"}, headers={"Cookie": cookie})
        assert resp.status_code == 201
        assert resp.json()["title"] == "Analysis 1"

    def test_create_requires_auth(self, client):
        resp = client.post("/api/sessions", json={})
        assert resp.status_code == 401


class TestDeleteSession:
    def test_delete_owned(self, client, auth_client):
        cookie = auth_client
        create_resp = client.post("/api/sessions", json={}, headers={"Cookie": cookie})
        session_id = create_resp.json()["id"]
        del_resp = client.delete(f"/api/sessions/{session_id}", headers={"Cookie": cookie})
        assert del_resp.status_code == 204
        # Verify it's gone
        list_resp = client.get("/api/sessions", headers={"Cookie": cookie})
        assert list_resp.json() == []

    def test_delete_nonexistent(self, client, auth_client):
        cookie = auth_client
        resp = client.delete("/api/sessions/ses_nonexistent", headers={"Cookie": cookie})
        assert resp.status_code == 204  # safe — 204 even for missing

    def test_delete_requires_auth(self, client):
        resp = client.delete("/api/sessions/ses_001")
        assert resp.status_code == 401


class TestRenameSession:
    def _create_session(self, client: TestClient, cookie: str) -> str:
        resp = client.post("/api/sessions", json={}, headers={"Cookie": cookie})
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_rename_owned_trims_title(self, client, auth_client):
        cookie = auth_client
        session_id = self._create_session(client, cookie)
        resp = client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "  Análisis de ventas  "},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == session_id
        assert data["title"] == "Análisis de ventas"
        # Persisted: the list reflects the new title.
        list_resp = client.get("/api/sessions", headers={"Cookie": cookie})
        assert list_resp.json()[0]["title"] == "Análisis de ventas"

    def test_rename_foreign_session_returns_404(self, client, auth_client):
        alice_cookie = auth_client
        session_id = self._create_session(client, alice_cookie)

        bob_resp = client.post(
            "/api/auth/register",
            json={"email": "bob@example.com", "password": "password123"},
        )
        assert bob_resp.status_code == 200
        bob_cookie = bob_resp.headers["set-cookie"]

        resp = client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "Hijacked"},
            headers={"Cookie": bob_cookie},
        )
        assert resp.status_code == 404
        # Alice's title is untouched.
        list_resp = client.get("/api/sessions", headers={"Cookie": alice_cookie})
        assert list_resp.json()[0]["title"] == "New chat"

    def test_rename_missing_session_returns_404(self, client, auth_client):
        cookie = auth_client
        resp = client.patch(
            "/api/sessions/ses_nonexistent",
            json={"title": "Whatever"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 404

    def test_rename_empty_title_rejected(self, client, auth_client):
        cookie = auth_client
        session_id = self._create_session(client, cookie)
        resp = client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "   "},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_title"

    def test_rename_too_long_title_rejected(self, client, auth_client):
        cookie = auth_client
        session_id = self._create_session(client, cookie)
        resp = client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "x" * 201},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_title"

    def test_rename_requires_auth(self, client):
        resp = client.patch("/api/sessions/ses_001", json={"title": "X"})
        assert resp.status_code == 401

    def test_rename_emits_titled_event_after_persist(self, client):
        # Register a user we can read the id from, then subscribe to the bus
        # BEFORE the PATCH: the event must arrive only after the rename is
        # committed (persist-then-emit).
        reg = client.post(
            "/api/auth/register",
            json={"email": "carol@example.com", "password": "password123"},
        )
        assert reg.status_code == 200
        cookie = reg.headers["set-cookie"]
        user_id = reg.json()["id"]
        session_id = self._create_session(client, cookie)

        api_event_bus.bus = EventBus()
        try:
            q = asyncio.run(api_event_bus.bus.subscribe(user_id))
            resp = client.patch(
                f"/api/sessions/{session_id}",
                json={"title": "Nuevo nombre"},
                headers={"Cookie": cookie},
            )
            assert resp.status_code == 200

            event = q.get_nowait()
            assert event.type is SessionEventType.TITLED
            assert event.session_id == session_id
            assert event.payload == {"title": "Nuevo nombre"}
        finally:
            api_event_bus.bus = None


class TestListSessionsIsStreaming:
    """``GET /api/sessions`` exposes the bus's streaming registry."""

    def test_list_marks_only_the_streaming_session(self, client):
        reg = client.post(
            "/api/auth/register",
            json={"email": "dave@example.com", "password": "password123"},
        )
        assert reg.status_code == 200
        cookie = reg.headers["set-cookie"]
        user_id = reg.json()["id"]

        first = client.post(
            "/api/sessions", json={"title": "First"}, headers={"Cookie": cookie}
        ).json()["id"]
        second = client.post(
            "/api/sessions", json={"title": "Second"}, headers={"Cookie": cookie}
        ).json()["id"]

        api_event_bus.bus = EventBus()
        try:
            # No subscribers: state must still be tracked from published events.
            api_event_bus.bus.publish(
                user_id,
                SessionEvent(
                    type=SessionEventType.STREAMING_STARTED,
                    session_id=first,
                    timestamp=0,
                ),
            )

            resp = client.get("/api/sessions", headers={"Cookie": cookie})
            assert resp.status_code == 200
            by_id = {s["id"]: s["is_streaming"] for s in resp.json()}
            assert by_id[first] is True
            assert by_id[second] is False

            api_event_bus.bus.publish(
                user_id,
                SessionEvent(
                    type=SessionEventType.STREAMING_ENDED,
                    session_id=first,
                    timestamp=0,
                ),
            )
            resp = client.get("/api/sessions", headers={"Cookie": cookie})
            by_id = {s["id"]: s["is_streaming"] for s in resp.json()}
            assert by_id[first] is False
        finally:
            api_event_bus.bus = None
