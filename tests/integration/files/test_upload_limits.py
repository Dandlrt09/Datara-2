"""Integration tests for upload limits (Files F1 hardening).

Covers the per-file byte cap, the Content-Length fast reject, session and
user quotas, the XLSX expansion cap, partial-file cleanup, and the
regression that an under-limit upload still succeeds.

Mirrors the app/auth/tmp-uploads fixture pattern of ``test_files_api.py``.
Limits are read at call time, so ``monkeypatch.setenv`` controls them.
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
    resp = client.post(
        "/api/auth/register",
        json={"email": "limits@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    client.headers["Cookie"] = resp.headers["set-cookie"]
    return client


@pytest.fixture
def session_id(auth_client):
    resp = auth_client.post("/api/sessions", json={"title": "Limits session"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _files_on_disk(tmp_path: Path) -> list[Path]:
    """Every regular file left under the per-test uploads root."""
    root = tmp_path / "uploads"
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file()]


def _xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    pd.DataFrame({"x": [1, 2, 3]}).to_excel(
        buf, sheet_name="Data", index=False, engine="openpyxl"
    )
    return buf.getvalue()


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TestPerFileCap:
    def test_over_cap_rejected_without_row_or_orphan(
        self, auth_client, session_id, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MAX_UPLOAD_BYTES", "1000")
        big_csv = b"a,b\n" + b"1,2\n" * 500  # ~2000 bytes, over the cap

        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("big.csv", big_csv, "text/csv")},
        )

        assert resp.status_code == 413
        assert "limit" in resp.json()["detail"]
        # No row persisted and no file left behind.
        assert auth_client.get(f"/api/sessions/{session_id}/files").json() == []
        assert _files_on_disk(tmp_path) == []

    def test_no_partial_file_after_cap(self, auth_client, session_id, tmp_path, monkeypatch):
        # Cap just over one 1 MB chunk but under cap + 1 MB margin, so the
        # Content-Length fast reject does NOT fire and the streaming cap must
        # trip on a later chunk.
        monkeypatch.setenv("DATARA_MAX_UPLOAD_BYTES", "1200000")
        big_csv = b"a\n" + b"x" * 1_500_000

        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("chunky.csv", big_csv, "text/csv")},
        )

        assert resp.status_code == 413
        assert _files_on_disk(tmp_path) == []


class TestContentLengthFastReject:
    def test_fast_reject_before_touching_disk(
        self, auth_client, session_id, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MAX_UPLOAD_BYTES", "1000")

        calls = {"ensure_dir": 0}
        original = files_router._ensure_upload_dir

        def _spy(*args, **kwargs):
            calls["ensure_dir"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(files_router, "_ensure_upload_dir", _spy)

        # Body well over max_upload_bytes + 1 MB margin, so the header check
        # fires before any directory/file work.
        big_csv = b"a\n" + b"x" * (2 * 1024 * 1024)
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("huge.csv", big_csv, "text/csv")},
        )

        assert resp.status_code == 413
        assert calls["ensure_dir"] == 0


class TestQuotas:
    def test_session_quota_exceeded(self, auth_client, session_id, monkeypatch):
        first = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("first.csv", b"a\n1\n2\n", "text/csv")},
        )
        assert first.status_code == 201

        monkeypatch.setenv("DATARA_MAX_SESSION_BYTES", "1")
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("second.csv", b"a\n3\n4\n", "text/csv")},
        )

        assert resp.status_code == 413
        assert "Session storage quota" in resp.json()["detail"]

    def test_user_quota_exceeded(self, auth_client, session_id, monkeypatch):
        first = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("first.csv", b"a\n1\n2\n", "text/csv")},
        )
        assert first.status_code == 201

        monkeypatch.setenv("DATARA_MAX_USER_BYTES", "1")
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("second.csv", b"a\n3\n4\n", "text/csv")},
        )

        assert resp.status_code == 413
        assert "User storage quota" in resp.json()["detail"]


class TestXlsxExpansion:
    def test_expansion_over_cap_rejected(
        self, auth_client, session_id, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MAX_EXPANDED_BYTES", "1")

        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("small.xlsx", _xlsx_bytes(), XLSX_MIME)},
        )

        assert resp.status_code == 413
        # "XLSX expands" is only produced by the pre-parse zip guard; the
        # post-parse footprint backstop says "Parsed data uses". Asserting the
        # specific message proves the zip-bomb guard fired, not the backstop.
        assert "XLSX expands" in resp.json()["detail"]
        assert auth_client.get(f"/api/sessions/{session_id}/files").json() == []
        assert _files_on_disk(tmp_path) == []


class TestHappyPathRegression:
    def test_under_limit_upload_still_succeeds(self, auth_client, session_id):
        resp = auth_client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("ok.csv", b"name,age\nAlice,30\nBob,25\n", "text/csv")},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["row_count"] == 2

        profile = auth_client.get(f"/api/files/{data['id']}/profile")
        assert profile.status_code == 200
        assert profile.json()["file_id"] == data["id"]