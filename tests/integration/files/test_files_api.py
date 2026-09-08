"""Integration tests for the files router (upload, list, profile, delete).

Uses FastAPI TestClient with a fresh in-memory SQLite store per test.
"""

from __future__ import annotations

import io
import json
import tempfile
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
def store():
    from server.api import store as api_store  # noqa: PLC0415
    return api_store._store


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
def session_id(auth_client):
    """Create a chat session and return its id."""
    resp = auth_client.post("/api/sessions", json={"title": "Test session"})
    assert resp.status_code == 201
    return resp.json()["id"]


class TestFileUpload:
    def test_upload_csv(self, auth_client, session_id):
        """Upload a CSV file."""
        csv_content = b"name,age\nAlice,30\nBob,25\n"
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"] == "test.csv"
        assert data["format"] == "csv"
        assert data["row_count"] == 2
        assert "id" in data
        assert "sheets" not in data or data["sheets"] is None

    def test_upload_xlsx(self, auth_client, session_id):
        """Upload an XLSX file."""
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        pd.DataFrame({"x": [1, 2]}).to_excel(tmp.name, sheet_name="Data", index=False)
        with open(tmp.name, "rb") as f:
            xlsx_content = f.read()
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("test.xlsx", xlsx_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["format"] == "xlsx"
        assert data["sheets"] == ["Data"]

    def test_upload_json(self, auth_client, session_id):
        """Upload a JSON file."""
        json_content = json.dumps([{"a": 1, "b": 2}, {"a": 3, "b": 4}]).encode()
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("test.json", json_content, "application/json")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["format"] == "json"
        assert data["row_count"] == 2

    def test_upload_invalid_format(self, auth_client, session_id):
        """Upload an unsupported file format."""
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "Unsupported file format" in resp.json()["detail"]

    def test_upload_requires_auth(self, client):
        """Unauthenticated upload should return 401.

        Note: uses a made-up session id since auth check fires first.
        """
        resp = client.post(
            "/api/sessions/fake-session/files",
            files={"file": ("test.csv", b"a,b\n1,2", "text/csv")},
        )
        assert resp.status_code == 401

    def test_upload_nonexistent_session(self, auth_client):
        """Upload to a non-existent session should return 404."""
        resp = auth_client.post(
            "/api/sessions/does-not-exist/files",
            files={"file": ("test.csv", b"a,b\n1,2", "text/csv")},
        )
        assert resp.status_code == 404

    def test_upload_empty_csv(self, auth_client, session_id):
        """Upload an empty CSV should fail."""
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("empty.csv", b"", "text/csv")},
        )
        assert resp.status_code == 400


class TestFileList:
    def test_list_files(self, auth_client, session_id):
        """List files for a session."""
        # Upload two files
        auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("a.csv", b"x\n1\n2\n", "text/csv")},
        )
        auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("b.csv", b"y\n3\n4\n", "text/csv")},
        )
        resp = auth_client.get(f"/api/sessions/{session_id}/files")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_files_empty(self, auth_client, session_id):
        """List files when none uploaded."""
        resp = auth_client.get(f"/api/sessions/{session_id}/files")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_files_requires_auth(self, client):
        resp = client.get("/api/sessions/fake/files")
        assert resp.status_code == 401


class TestFileProfile:
    def test_get_profile(self, auth_client, session_id):
        """Upload a file and get its profile."""
        csv_content = b"name,age\nAlice,30\nBob,25\nCharlie,35\n"
        upload_resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        file_id = upload_resp.json()["id"]

        prof_resp = auth_client.get(f"/api/files/{file_id}/profile")
        assert prof_resp.status_code == 200
        data = prof_resp.json()
        assert data["file_id"] == file_id
        # The API returns 'schema' as the JSON key (via Field alias)
        assert "schema" in data
        assert "stats" in data
        assert "sample" in data

    def test_get_profile_nonexistent(self, auth_client):
        """Get profile for non-existent file."""
        resp = auth_client.get("/api/files/99999/profile")
        assert resp.status_code == 404

    def test_get_profile_requires_auth(self, client):
        resp = client.get("/api/files/1/profile")
        assert resp.status_code == 401

    def test_get_profile_cross_user_blocked(self, auth_client, session_id, client):
        """RED: cross-user profile access should return 404."""
        # User A uploads
        csv_content = b"x,y\n1,2\n3,4\n"
        upload_resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("cross.csv", csv_content, "text/csv")},
        )
        file_id = upload_resp.json()["id"]

        # Register user B
        resp_b = client.post(
            "/api/auth/register",
            json={"email": "b@example.com", "password": "password123"},
        )
        cookie_b = resp_b.headers["set-cookie"]

        # User B tries to get A's profile → 404 (ownership enforced via JOIN)
        resp = client.get(
            f"/api/files/{file_id}/profile",
            headers={"Cookie": cookie_b},
        )
        assert resp.status_code == 404


class TestFileDelete:
    def test_delete_file(self, auth_client, session_id):
        """Upload then delete a file."""
        upload_resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("del.csv", b"a\n1\n", "text/csv")},
        )
        file_id = upload_resp.json()["id"]

        del_resp = auth_client.delete(f"/api/files/{file_id}")
        assert del_resp.status_code == 204

        # Verify list is empty
        list_resp = auth_client.get(f"/api/sessions/{session_id}/files")
        assert list_resp.json() == []

    def test_delete_nonexistent(self, auth_client):
        resp = auth_client.delete("/api/files/99999")
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client):
        resp = client.delete("/api/files/1")
        assert resp.status_code == 401

    def test_delete_cross_user(self, auth_client, session_id, client):
        """RED: User B cannot delete User A's file."""
        upload_resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("cross_del.csv", b"a\n1\n", "text/csv")},
        )
        file_id = upload_resp.json()["id"]

        resp_b = client.post(
            "/api/auth/register",
            json={"email": "bdel@example.com", "password": "password123"},
        )
        cookie_b = resp_b.headers["set-cookie"]

        resp = client.delete(
            f"/api/files/{file_id}",
            headers={"Cookie": cookie_b},
        )
        assert resp.status_code == 404


class TestFileRuntimeHarness:
    """Runtime harness: upload → profile endpoint smoke test."""

    def test_upload_then_profile(self, auth_client, session_id):
        """Upload a small CSV and retrieve its profile."""
        csv_content = b"city,population,area_km2\nNYC,8336817,783.8\nLA,3898747,1213.9\nChicago,2746388,588.7\n"
        upload = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("cities.csv", csv_content, "text/csv")},
        )
        assert upload.status_code == 201
        file_id = upload.json()["id"]

        # Profile endpoint returns stats
        prof = auth_client.get(f"/api/files/{file_id}/profile")
        assert prof.status_code == 200
        data = prof.json()
        assert data["file_id"] == file_id
        stats = data["stats"]
        # population column should have min/max/mean/std (numeric)
        assert "population" in stats
        assert stats["population"]["min"] is not None


class TestUploadCancel:
    """Client-aborted uploads must never persist a file row or orphan a file."""

    def test_disconnect_after_read_returns_499_without_persist(
        self, auth_client, session_id, monkeypatch
    ):
        """Disconnect noticed before persisting → 499 and no file row."""
        from starlette.requests import Request

        async def _disconnected(self):
            return True

        monkeypatch.setattr(Request, "is_disconnected", _disconnected)

        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("cancelled.csv", b"name,age\nAlice,30\n", "text/csv")},
        )
        assert resp.status_code == 499

        listing = auth_client.get(f"/api/sessions/{session_id}/files")
        assert listing.json() == []

    def test_disconnect_after_parse_cleans_up_file(
        self, auth_client, session_id, monkeypatch
    ):
        """Disconnect during the slow parse → file unlinked, no file row."""
        from starlette.requests import Request

        from server.api.routers import files as files_router

        calls = {"n": 0}

        async def _disconnected(self):
            calls["n"] += 1
            # 1st call: after body read (False); 2nd call: after parse (True)
            return calls["n"] >= 2

        monkeypatch.setattr(Request, "is_disconnected", _disconnected)

        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("cancelled_mid.csv", b"name,age\nAlice,30\n", "text/csv")},
        )
        assert resp.status_code == 499

        listing = auth_client.get(f"/api/sessions/{session_id}/files")
        assert listing.json() == []

        # The written file was cleaned up from the session upload dir
        session_dirs = list(files_router.UPLOADS_DIR.rglob(session_id))
        for d in session_dirs:
            assert list(d.iterdir()) == []

    def test_normal_upload_still_persists(self, auth_client, session_id, monkeypatch):
        """With no disconnect, the cancel checks are transparent no-ops."""
        from starlette.requests import Request

        async def _disconnected(self):
            return False

        monkeypatch.setattr(Request, "is_disconnected", _disconnected)

        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("normal.csv", b"name,age\nAlice,30\n", "text/csv")},
        )
        assert resp.status_code == 201
        assert resp.json()["filename"] == "normal.csv"


class TestSameNameReupload:
    """Same-name re-upload in the same session is rejected with 409.

    File deletion exists (DELETE /api/files/{id} and the Files UI delete
    button), so the chosen behavior is reject-and-keep: exactly one files
    row + one profile per basename, and the user deletes the old file
    before uploading a replacement. Re-upload used to overwrite the stored
    file and duplicate the files/profiles rows.
    """

    def test_same_name_reupload_rejected_with_409(self, auth_client, session_id):
        first = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("dup.csv", b"a\n1\n", "text/csv")},
        )
        assert first.status_code == 201
        first_id = first.json()["id"]

        second = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("dup.csv", b"a\n2\n3\n4\n", "text/csv")},
        )
        assert second.status_code == 409
        assert "already exists" in second.json()["detail"]
        assert "Delete" in second.json()["detail"]

        # Exactly one file row remains — the original, unmodified.
        listing = auth_client.get(f"/api/sessions/{session_id}/files")
        rows = listing.json()
        assert len(rows) == 1
        assert rows[0]["id"] == first_id
        assert rows[0]["size_bytes"] == len(b"a\n1\n")

    def test_rejected_reupload_keeps_original_profile(self, auth_client, session_id):
        first = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("dup.csv", b"v\n1\n2\n", "text/csv")},
        )
        first_id = first.json()["id"]

        rejected = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("dup.csv", b"v\n9\n", "text/csv")},
        )
        assert rejected.status_code == 409

        # Profile for the original file still resolves (no duplicate rows).
        profile = auth_client.get(f"/api/files/{first_id}/profile")
        assert profile.status_code == 200
        assert profile.json()["file_id"] == first_id

    def test_reupload_allowed_after_delete(self, auth_client, session_id):
        """Deleting the file frees the name for a new upload."""
        first = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("dup.csv", b"a\n1\n", "text/csv")},
        )
        file_id = first.json()["id"]
        assert auth_client.delete(f"/api/files/{file_id}").status_code == 204

        again = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("dup.csv", b"a\n2\n", "text/csv")},
        )
        assert again.status_code == 201

    def test_same_name_in_other_session_allowed(self, auth_client, session_id):
        """The guard is per-session, not per-user or global."""
        first = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("dup.csv", b"a\n1\n", "text/csv")},
        )
        assert first.status_code == 201

        resp = auth_client.post("/api/sessions", json={"title": "Other session"})
        other_session = resp.json()["id"]
        second = auth_client.post(
            f"/api/sessions/{other_session}/files",
            files={"file": ("dup.csv", b"a\n2\n", "text/csv")},
        )
        assert second.status_code == 201