"""F9/S2: the Origin/CSRF guard on state-changing API requests.

The session lives in a cookie, so any page the browser visits can make it fire
a cross-origin request at Datara (a simple form POST needs no preflight). These
tests pin the guard's contract: a state-changing ``/api/*`` request is refused
unless it comes from a trusted origin; reads and non-API paths are untouched.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.csrf_guard import (
    CSRF_ORIGIN_DETAIL,
    CsrfOriginGuard,
    install_csrf_origin_guard,
)


def _guarded_app() -> FastAPI:
    """A tiny app with the guard and one write/read route each."""
    app = FastAPI()

    @app.post("/api/thing")
    async def _post_thing():
        return {"ok": True}

    @app.get("/api/thing")
    async def _get_thing():
        return {"ok": True}

    @app.post("/elsewhere")
    async def _post_elsewhere():
        return {"ok": True}

    install_csrf_origin_guard(app)
    return app


def _client() -> TestClient:
    return TestClient(_guarded_app())


def test_same_origin_state_change_is_allowed():
    response = _client().post("/api/thing", headers={"Origin": "http://localhost:8000"})
    assert response.status_code == 200


def test_foreign_origin_state_change_is_rejected():
    response = _client().post("/api/thing", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert response.json()["detail"] == CSRF_ORIGIN_DETAIL


def test_missing_origin_and_referer_is_allowed():
    # Only non-browser clients (curl, tests, servers) omit both; they are not
    # the cookie-theft threat the guard exists for.
    assert _client().post("/api/thing").status_code == 200


def test_foreign_referer_fallback_is_rejected():
    response = _client().post("/api/thing", headers={"Referer": "http://evil.example/page"})
    assert response.status_code == 403


def test_trusted_referer_fallback_is_allowed():
    response = _client().post("/api/thing", headers={"Referer": "http://localhost:8000/app"})
    assert response.status_code == 200


def test_null_origin_is_rejected():
    # A sandboxed iframe / opaque origin sends ``Origin: null``; it is not ours.
    response = _client().post("/api/thing", headers={"Origin": "null"})
    assert response.status_code == 403


def test_reads_are_not_guarded():
    response = _client().get("/api/thing", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200


def test_non_api_state_change_is_not_guarded():
    response = _client().post("/elsewhere", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200


def test_configured_app_origin_is_allowed(monkeypatch):
    # The desktop build binds a free port and publishes it via DATARA_APP_URL;
    # a hosted deployment sets it to its public URL.
    monkeypatch.setenv("DATARA_APP_URL", "https://datara.example")
    response = _client().post("/api/thing", headers={"Origin": "https://datara.example"})
    assert response.status_code == 200


def test_extra_allowed_origins_env(monkeypatch):
    monkeypatch.setenv("DATARA_ALLOWED_ORIGINS", "https://app.example, https://alt.example")
    assert _client().post("/api/thing", headers={"Origin": "https://alt.example"}).status_code == 200


def test_real_app_installs_the_guard():
    from server.api.main import app

    assert any(middleware.cls is CsrfOriginGuard for middleware in app.user_middleware)


def test_real_app_rejects_foreign_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "csrf" / "datara.db"))
    from server.api.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={"email": "csrf@datara.local", "password": "csrf-test-123"},
            headers={"Origin": "http://evil.example"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == CSRF_ORIGIN_DETAIL
