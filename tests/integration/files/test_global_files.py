"""Integration tests for the global GET /api/files endpoint.

Tests the new list_files_with_session store method and the FileListItem
response model. Uploads go via the existing session-scoped endpoint.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import auth as auth_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.services.sqlite_store import SqliteStore

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
INIT_SQL_PATH = MIGRATIONS_DIR / "0001_init.sql"


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(files_router.router)

    # Isolation: uploads must land in a per-test tmp dir, never the real
    # server/uploads/ used by the live server.
    monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")

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
    """Register a user and return a client with valid session cookie."""
    resp = client.post(
        "/api/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"]
    client.headers["Cookie"] = cookie
    return client


@pytest.fixture
def second_user_cookie(client):
    """Register a second user and return its session cookie string."""
    resp = client.post(
        "/api/auth/register",
        json={"email": "b@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def session_id(auth_client):
    """Create a chat session and return its id."""
    resp = auth_client.post("/api/sessions", json={"title": "Test session"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload_csv(auth_client, session_id, name="test.csv", content=b"x\n1\n"):
    """Helper: upload a CSV to a session and return the response."""
    return auth_client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (name, content, "text/csv")},
    )


class TestGlobalFileList:
    """Tests for GET /api/files (global list)."""

    def test_global_list_roundtrip_with_session_title(self, auth_client, session_id):
        """Upload a file then verify it appears in the global list with title."""
        upload = _upload_csv(auth_client, session_id, "roundtrip.csv", b"a,b\n1,2\n")
        assert upload.status_code == 201
        file_id = upload.json()["id"]

        resp = auth_client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        match = [f for f in data if f["id"] == file_id]
        assert len(match) == 1
        assert match[0]["filename"] == "roundtrip.csv"
        assert match[0]["chat_session_id"] == session_id
        assert match[0]["session_title"] == "Test session"

    def test_global_list_cross_user_isolation(self, auth_client, client, second_user_cookie, session_id):
        """User B should not see User A's files."""
        _upload_csv(auth_client, session_id, "a_only.csv")
        resp = client.get("/api/files", headers={"Cookie": second_user_cookie})
        assert resp.status_code == 200
        data = resp.json()
        assert all(f["filename"] != "a_only.csv" for f in data)

    def test_global_list_requires_auth(self, client):
        """No-auth should return 401."""
        resp = client.get("/api/files")
        assert resp.status_code == 401

    def test_deleted_session_cascades_files(self, auth_client, session_id):
        """Delete the session; files are cascade-deleted (FK: ON DELETE CASCADE)."""
        upload = _upload_csv(auth_client, session_id, "orphan.csv", b"x\n1\n")
        assert upload.status_code == 201
        file_id = upload.json()["id"]

        # File visible before session delete
        resp = auth_client.get("/api/files")
        assert any(f["id"] == file_id for f in resp.json())

        # Delete the session → cascade deletes files
        resp = auth_client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

        # Files should not appear (cascade)
        resp = auth_client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        assert all(f["id"] != file_id for f in data)

    def test_delete_then_list_excludes(self, auth_client, session_id):
        """Delete a file then verify it's excluded from the global list."""
        upload = _upload_csv(auth_client, session_id, "todel.csv", b"x\n1\n")
        file_id = upload.json()["id"]

        resp = auth_client.delete(f"/api/files/{file_id}")
        assert resp.status_code == 204

        resp = auth_client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        assert all(f["id"] != file_id for f in data)


class TestSessionDeleteUploadCleanup:
    """Deleting a session removes its upload directory from disk.

    The DB rows (files → profiles, messages) cascade via FK; the stored
    files under uploads/<user_id>/<session_id>/ used to be orphaned.
    """

    def test_deleted_session_removes_upload_dir(self, auth_client, session_id):
        """Upload a file, delete the session, assert the directory is gone."""
        upload = _upload_csv(auth_client, session_id, "disk_cleanup.csv", b"x\n1\n")
        assert upload.status_code == 201

        session_dirs = list(files_router.UPLOADS_DIR.rglob(session_id))
        assert session_dirs and any(d.is_dir() for d in session_dirs)

        resp = auth_client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

        assert list(files_router.UPLOADS_DIR.rglob(session_id)) == []

    def test_session_delete_survives_cleanup_failure(
        self, auth_client, session_id, monkeypatch
    ):
        """A failing disk cleanup never fails the delete (log-and-continue)."""
        upload = _upload_csv(auth_client, session_id, "stuck.csv", b"x\n1\n")
        assert upload.status_code == 201
        file_id = upload.json()["id"]

        def _raise(user_id, chat_session):
            raise OSError("simulated disk failure")

        monkeypatch.setattr(files_router, "remove_session_uploads", _raise)

        resp = auth_client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

        # The DB cascade still applied despite the cleanup failure.
        resp = auth_client.get("/api/files")
        assert resp.status_code == 200
        assert all(f["id"] != file_id for f in resp.json())