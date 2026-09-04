"""Integration tests for the settings router (GET/PUT user preferences)."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.settings import router as settings_router
from server.services.sqlite_store import SqliteStore

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
INIT_SQL_PATH = MIGRATIONS_DIR / "0001_init.sql"


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(settings_router)

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
    resp = client.post("/api/auth/register", json={"email": "alice@example.com", "password": "password123"})
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


class TestGetSettings:
    def test_get_defaults(self, client, auth_client):
        cookie = auth_client
        resp = client.get("/api/settings", headers={"Cookie": cookie})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] is not None
        assert data["has_api_key"] is False
        assert data["default_model"] is None
        assert "gpt-4o" in data["allowed_models"]
        assert len(data["allowed_models"]) >= 5

    def test_get_requires_auth(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 401

    def test_get_never_returns_key_material(self, client, auth_client):
        """Regression: GET must expose only has_api_key, never the key."""
        cookie = auth_client
        client.put(
            "/api/settings",
            json={"api_key": "sk-secret-value", "default_model": "gpt-4o"},
            headers={"Cookie": cookie},
        )
        resp = client.get("/api/settings", headers={"Cookie": cookie})
        assert resp.status_code == 200
        assert resp.json()["has_api_key"] is True
        assert "api_key_enc" not in resp.json()
        assert "sk-secret-value" not in resp.text


class TestUpdateSettings:
    def test_update_all_fields(self, client, auth_client):
        cookie = auth_client
        resp = client.put(
            "/api/settings",
            json={"api_key": "sk-abc123", "default_model": "gpt-4o"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_api_key"] is True
        assert "sk-abc123" not in resp.text
        assert data["default_model"] == "gpt-4o"

    def test_update_partial(self, client, auth_client):
        cookie = auth_client
        # Set both fields
        client.put(
            "/api/settings",
            json={"api_key": "sk-orig", "default_model": "gpt-4o"},
            headers={"Cookie": cookie},
        )
        # Update only default_model
        resp = client.put(
            "/api/settings",
            json={"default_model": "gpt-4o-mini"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_model"] == "gpt-4o-mini"
        # api_key should be unchanged (kept server-side, still not leaked)
        assert data["has_api_key"] is True
        assert "sk-orig" not in resp.text

    def test_update_requires_auth(self, client):
        resp = client.put("/api/settings", json={"default_model": "gpt-4o"})
        assert resp.status_code == 401

    def test_multiple_users_isolated(self, client):
        """Settings for user A should not affect user B."""
        resp_a = client.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"})
        cookie_a = resp_a.headers["set-cookie"]
        resp_b = client.post("/api/auth/register", json={"email": "b@example.com", "password": "password123"})
        cookie_b = resp_b.headers["set-cookie"]

        client.put("/api/settings", json={"default_model": "gpt-4o"}, headers={"Cookie": cookie_a})
        client.put("/api/settings", json={"default_model": "gpt-4o-mini"}, headers={"Cookie": cookie_b})

        settings_a = client.get("/api/settings", headers={"Cookie": cookie_a}).json()
        settings_b = client.get("/api/settings", headers={"Cookie": cookie_b}).json()
        assert settings_a["default_model"] == "gpt-4o"
        assert settings_b["default_model"] == "gpt-4o-mini"

    def test_update_rejects_unknown_model(self, client, auth_client):
        """Unknown default_model must 422 and leave the stored value intact."""
        cookie = auth_client
        client.put("/api/settings", json={"default_model": "gpt-4o"}, headers={"Cookie": cookie})

        resp = client.put(
            "/api/settings",
            json={"default_model": "gpt-inventado-9000"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        assert "unknown model" in resp.text
        assert "gpt-4o" in resp.text  # allowed models listed in the error

        # Stored value unchanged after the rejected update.
        data = client.get("/api/settings", headers={"Cookie": cookie}).json()
        assert data["default_model"] == "gpt-4o"

    def test_update_empty_model_treated_as_unset(self, client, auth_client):
        cookie = auth_client
        client.put("/api/settings", json={"default_model": "gpt-4o"}, headers={"Cookie": cookie})

        resp = client.put("/api/settings", json={"default_model": "  "}, headers={"Cookie": cookie})
        assert resp.status_code == 200
        data = client.get("/api/settings", headers={"Cookie": cookie}).json()
        assert data["default_model"] == "gpt-4o"

    def test_update_keeps_stored_model_even_if_not_whitelisted(self, client, auth_client, monkeypatch):
        """Re-saving an unchanged default_model must not 422 when the
        whitelist shrank (e.g. reboot without DATARA_ALLOWED_MODELS) —
        otherwise saving a new API key becomes impossible."""
        from server.api.routers import settings as settings_module

        cookie = auth_client
        # Stored yesterday under an extended whitelist.
        monkeypatch.setattr(
            settings_module,
            "ALLOWED_MODELS",
            frozenset({"gpt-4o", "z-ai/glm-5.3-flash"}),
        )
        client.put(
            "/api/settings",
            json={"default_model": "z-ai/glm-5.3-flash"},
            headers={"Cookie": cookie},
        )
        # Today's boot: whitelist shrank, stored model no longer allowed.
        monkeypatch.setattr(
            settings_module,
            "ALLOWED_MODELS",
            frozenset({"gpt-4o", "gpt-4o-mini"}),
        )

        # User only saves a new API key; the unchanged model must pass.
        resp = client.put(
            "/api/settings",
            json={"api_key": "sk-new-key", "default_model": "z-ai/glm-5.3-flash"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = client.get("/api/settings", headers={"Cookie": cookie}).json()
        assert data["default_model"] == "z-ai/glm-5.3-flash"
        assert data["has_api_key"] is True

        # A genuinely different unknown model is still rejected.
        resp = client.put(
            "/api/settings",
            json={"default_model": "gpt-inventado-9000"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422


class TestEnvExtendedWhitelist:
    def test_env_extension_accepts_custom_backend_model(self, client, auth_client, monkeypatch):
        """DATARA_ALLOWED_MODELS extends the whitelist (OpenRouter slugs etc.)."""
        from server.api.routers import settings as settings_module

        monkeypatch.setattr(
            settings_module,
            "ALLOWED_MODELS",
            frozenset({"gpt-4o", "z-ai/glm-4.7-flash"}),
        )
        cookie = auth_client

        resp = client.put(
            "/api/settings",
            json={"default_model": "z-ai/glm-4.7-flash"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = client.get("/api/settings", headers={"Cookie": cookie}).json()
        assert data["default_model"] == "z-ai/glm-4.7-flash"
        assert set(data["allowed_models"]) == {"gpt-4o", "z-ai/glm-4.7-flash"}

        # Whitelist still enforced for anything outside the extension.
        resp = client.put(
            "/api/settings",
            json={"default_model": "gpt-inventado-9000"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422