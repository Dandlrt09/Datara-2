"""Integration tests for the sessions router (list, create, delete)."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.sessions import router as sessions_router
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