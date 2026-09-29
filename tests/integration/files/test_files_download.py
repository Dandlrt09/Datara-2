"""Integration tests for GET /api/files/{file_id}/download (F11).

Re-download of the original uploaded bytes. Uses a real upload for the happy
path (seeded rows point at nonexistent storage paths) and direct store seeding
only for the traversal/missing-on-disk cases.
"""

from __future__ import annotations

import asyncio
import io

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import auth as auth_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.api.upload_guard import install_upload_guard
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations

_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Build an in-memory single-sheet XLSX payload."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data", index=False)
    return buffer.getvalue()


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(files_router.router)

    install_upload_guard(application)

    # Isolation: uploads must land in a per-test tmp dir, never the real
    # server/uploads/ used by the live server.
    monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")

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
    from server.api import store as api_store  # noqa: PLC0415
    return api_store._store


@pytest.fixture
def user_id(auth_client):
    """The authenticated user's id (for direct store seeding)."""
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    return resp.json()["id"]


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


def _seed_file(
    store,
    user_id,
    session_id,
    *,
    filename: str,
    storage_path: str,
    format_val: str = "csv",
) -> int:
    """Insert one file row directly and return its id (no bytes on disk)."""
    async def _run():
        row = await store.create_file_with_profile(
            user_id=user_id,
            chat_session=session_id,
            filename=filename,
            storage_path=storage_path,
            size_bytes=10,
            format_val=format_val,
            schema_json="{}",
            stats_json="{}",
            sample_json="[]",
        )
        return row["id"]

    return asyncio.run(_run())


class TestDownload:
    def test_owner_downloads_identical_bytes(self, auth_client, session_id):
        content = b"name,age\nAlice,30\nBob,25\n"
        upload = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("data.csv", content, "text/csv")},
        )
        assert upload.status_code == 201
        file_id = upload.json()["id"]

        resp = auth_client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 200
        assert resp.content == content

    def test_content_disposition_has_attachment_and_filename(
        self, auth_client, session_id
    ):
        upload = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("original.csv", b"a,b\n1,2\n", "text/csv")},
        )
        file_id = upload.json()["id"]

        resp = auth_client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 200
        disposition = resp.headers["content-disposition"]
        assert "attachment" in disposition
        assert "original.csv" in disposition

    def test_content_type_csv(self, auth_client, session_id):
        upload = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("t.csv", b"a,b\n1,2\n", "text/csv")},
        )
        file_id = upload.json()["id"]

        resp = auth_client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    def test_content_type_xlsx(self, auth_client, session_id):
        content = _xlsx_bytes(pd.DataFrame({"x": [1, 2]}))
        upload = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("book.xlsx", content, _XLSX_MIME)},
        )
        assert upload.status_code == 201
        file_id = upload.json()["id"]

        resp = auth_client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert resp.content == content

    def test_foreign_file_id_404(self, auth_client, session_id, client):
        upload = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("mine.csv", b"a,b\n1,2\n", "text/csv")},
        )
        file_id = upload.json()["id"]

        resp_b = client.post(
            "/api/auth/register",
            json={"email": "b_download@example.com", "password": "password123"},
        )
        cookie_b = resp_b.headers["set-cookie"]

        resp = client.get(
            f"/api/files/{file_id}/download", headers={"Cookie": cookie_b}
        )
        assert resp.status_code == 404

    def test_unknown_file_id_404(self, auth_client):
        resp = auth_client.get("/api/files/99999/download")
        assert resp.status_code == 404

    def test_missing_on_disk_404(self, auth_client, session_id):
        upload = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("gone.csv", b"a,b\n1,2\n", "text/csv")},
        )
        file_id = upload.json()["id"]

        # The row exists but its bytes were removed from disk.
        stored = list(files_router.UPLOADS_DIR.rglob("gone.csv"))
        assert len(stored) == 1
        stored[0].unlink()

        resp = auth_client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 404

    def test_path_outside_uploads_never_served(
        self, auth_client, session_id, store, user_id, tmp_path
    ):
        # A hostile/corrupted row whose path resolves outside UPLOADS_DIR.
        # The bytes exist on disk and are reachable, but must never be served.
        outside = tmp_path / "outside.csv"
        outside.write_bytes(b"secret\n1\n")
        file_id = _seed_file(
            store,
            user_id,
            session_id,
            filename="outside.csv",
            storage_path=str(outside),
        )

        resp = auth_client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 404
        assert resp.content != b"secret\n1\n"

    def test_missing_storage_path_404(
        self, auth_client, session_id, store, user_id
    ):
        # A row with no storage_path at all must not crash or serve anything.
        file_id = _seed_file(
            store,
            user_id,
            session_id,
            filename="nopath.csv",
            storage_path="",
        )

        resp = auth_client.get(f"/api/files/{file_id}/download")
        assert resp.status_code == 404

    def test_unauthenticated_401(self, client):
        resp = client.get("/api/files/1/download")
        assert resp.status_code == 401
