"""Integration tests for the settings router (GET/PUT user preferences)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.settings import router as settings_router
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(settings_router)

    import asyncio

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


class TestProviderSettings:
    """Tests for provider_type and base_url fields (Work Unit 2)."""

    @pytest.fixture(autouse=True)
    def mock_dns(self, monkeypatch):
        """Mock DNS resolution to avoid network calls in tests."""
        async def mock_resolve_hostname(hostname):
            import ipaddress
            # Map test hostnames to IPs
            if hostname == "api.example.com":
                return [ipaddress.ip_address("93.184.216.34")]  # example.com
            elif hostname == "openrouter.ai":
                return [ipaddress.ip_address("172.67.74.16")]  # real-ish
            elif hostname == "api.groq.com":
                return [ipaddress.ip_address("104.21.22.207")]  # cloudflare
            elif hostname == "localhost":
                return [ipaddress.ip_address("127.0.0.1")]
            elif hostname == "192.168.1.50":
                return [ipaddress.ip_address("192.168.1.50")]
            else:
                # Default public IP for any other hostname
                return [ipaddress.ip_address("93.184.216.34")]
        
        monkeypatch.setattr(
            "server.services.base_url_guard._resolve_hostname",
            mock_resolve_hostname
        )

    def test_update_provider_type_and_base_url(self, client, auth_client):
        """Basic update of provider_type and base_url."""
        cookie = auth_client
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1"
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "openrouter"
        assert data["base_url"] == "https://openrouter.ai/api/v1"

        # Verify GET returns the same values
        get_resp = client.get("/api/settings", headers={"Cookie": cookie})
        get_data = get_resp.json()
        assert get_data["provider_type"] == "openrouter"
        assert get_data["base_url"] == "https://openrouter.ai/api/v1"

    def test_update_partial_keeps_other_fields(self, client, auth_client):
        """Updating only provider_type should keep existing base_url."""
        cookie = auth_client
        # Set both fields
        client.put(
            "/api/settings",
            json={
                "provider_type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "default_model": "gpt-4o",
            },
            headers={"Cookie": cookie},
        )
        # Update only provider_type
        resp = client.put(
            "/api/settings",
            json={"provider_type": "custom"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "custom"
        assert data["base_url"] == "https://openrouter.ai/api/v1"  # unchanged
        assert data["default_model"] == "gpt-4o"

    def test_clear_base_url_with_empty_string(self, client, auth_client):
        """Empty string for base_url should clear it to null."""
        cookie = auth_client
        # Set base_url
        client.put(
            "/api/settings",
            json={
                "provider_type": "custom",
                "base_url": "https://api.example.com/v1",
            },
            headers={"Cookie": cookie},
        )
        # Clear with empty string
        resp = client.put(
            "/api/settings",
            json={"base_url": ""},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_url"] is None
        assert data["provider_type"] == "custom"  # unchanged

    def test_clear_provider_type_with_null(self, client, auth_client):
        """null for provider_type should clear it."""
        cookie = auth_client
        # Set provider_type
        client.put(
            "/api/settings",
            json={
                "provider_type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
            },
            headers={"Cookie": cookie},
        )
        # Clear with null
        resp = client.put(
            "/api/settings",
            json={"provider_type": None},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] is None
        assert data["base_url"] == "https://openrouter.ai/api/v1"  # unchanged

    def test_omit_fields_keeps_current_values(self, client, auth_client):
        """Omitted fields (not in JSON) should keep current values."""
        cookie = auth_client
        # Set initial values - use a whitelisted model
        resp1 = client.put(
            "/api/settings",
            json={
                "provider_type": "ollama",
                "base_url": "http://localhost:11434/v1",
                "default_model": "gpt-4o",
            },
            headers={"Cookie": cookie},
        )
        assert resp1.status_code == 200, f"First PUT failed: {resp1.text}"
        # Update only api_key, provider fields omitted
        resp = client.put(
            "/api/settings",
            json={"api_key": "sk-new-key"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_api_key"] is True
        assert data["provider_type"] == "ollama"  # unchanged
        assert data["base_url"] == "http://localhost:11434/v1"  # unchanged
        assert data["default_model"] == "gpt-4o"  # unchanged

    def test_rejects_http_for_custom_provider(self, client, auth_client):
        """Custom provider requires HTTPS."""
        cookie = auth_client
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "custom",
                "base_url": "http://api.example.com/v1",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "detail" in data
        assert "code" in data["detail"]
        assert data["detail"]["code"] == "invalid_base_url"
        assert "HTTPS" in data["detail"]["message"]

    def test_allows_http_for_ollama_localhost(self, client, auth_client):
        """Ollama permits HTTP localhost (loopback exemption)."""
        cookie = auth_client
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "ollama",
                "base_url": "http://localhost:11434/v1",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "ollama"
        assert data["base_url"] == "http://localhost:11434/v1"

    def test_rejects_localhost_for_custom_provider(self, client, auth_client):
        """Custom provider cannot use localhost."""
        cookie = auth_client
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "custom",
                "base_url": "https://localhost:8000/v1",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["detail"]["code"] == "invalid_base_url"

    def test_rejects_lan_for_ollama(self, client, auth_client):
        """Ollama on LAN IP (192.168.x.x) is rejected (only loopback exempt)."""
        cookie = auth_client
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "ollama",
                "base_url": "http://192.168.1.50:11434/v1",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["detail"]["code"] == "invalid_base_url"

    def test_concurrent_updates_atomic(self, client, auth_client):
        """Concurrent PUTs should produce a merged row, not corruption."""
        import threading
        import queue
        
        cookie = auth_client
        results = queue.Queue()
        
        def put_provider_type():
            resp = client.put(
                "/api/settings",
                json={"provider_type": "openrouter"},
                headers={"Cookie": cookie},
            )
            results.put(("provider_type", resp.status_code))
        
        def put_base_url():
            resp = client.put(
                "/api/settings",
                json={"base_url": "https://openrouter.ai/api/v1"},
                headers={"Cookie": cookie},
            )
            results.put(("base_url", resp.status_code))
        
        t1 = threading.Thread(target=put_provider_type)
        t2 = threading.Thread(target=put_base_url)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # Collect results
        status_codes = {}
        while not results.empty():
            field, code = results.get()
            status_codes[field] = code
        
        assert status_codes.get("provider_type") == 200
        assert status_codes.get("base_url") == 200
        
        # Final state should have both fields
        final = client.get("/api/settings", headers={"Cookie": cookie}).json()
        assert final["provider_type"] == "openrouter"
        assert final["base_url"] == "https://openrouter.ai/api/v1"