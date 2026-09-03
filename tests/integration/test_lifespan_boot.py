"""Regression: the app must boot through its REAL lifespan on a fresh machine.

Bug history: startup hardcoded the DB path to a repo-local ``data/`` directory,
ignored ``DATARA_DB_PATH``, and never created the parent directory — so the
first ``uvicorn`` boot always failed with ``OperationalError: unable to open
database file``. The integration suite never caught it because ``TestClient``
was used without entering its context manager, which skips the lifespan.

This test enters the lifespan via ``with TestClient(app)`` against a DB path
whose parent directory does not exist yet.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.api.main import app


def test_lifespan_boots_and_creates_fresh_db_dir(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh" / "datara.db"  # parent intentionally missing
    monkeypatch.setenv("DATARA_DB_PATH", str(db_path))

    with TestClient(app) as client:
        # App is up: protected endpoint answers 401 without credentials.
        assert client.get("/api/auth/me").status_code == 401

        # Full auth roundtrip through the lifespan-provided store.
        resp = client.post(
            "/api/auth/register",
            json={"email": "boot@datara.local", "password": "boot-test-123"},
        )
        assert resp.status_code == 200
        assert "session_id" in resp.headers.get("set-cookie", "")

        assert client.get("/api/auth/me").status_code == 200

    # The DB was created at the env-configured path, parent dir included.
    assert db_path.exists()


def test_spa_fallback_serves_app_shell_for_client_routes(tmp_path, monkeypatch):
    """Full reload on a client-side route (/login, /app/...) must return the
    SPA shell, not a 404 — the server has no such files on disk."""
    import os

    from fastapi.testclient import TestClient

    from server.api.main import app

    if not (os.path.exists("web/dist/index.html")):
        return  # frontend not built in this environment; nothing to assert

    db_path = tmp_path / "fresh2" / "datara.db"
    monkeypatch.setenv("DATARA_DB_PATH", str(db_path))

    with TestClient(app) as client:
        for route in ("/login", "/app/files", "/app/chat"):
            resp = client.get(route)
            assert resp.status_code == 200, route
            assert 'id="root"' in resp.text, route
            assert "application/json" not in resp.headers.get("content-type", "")

        # Unknown API paths keep their JSON 404 (no SPA fallback there).
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404
