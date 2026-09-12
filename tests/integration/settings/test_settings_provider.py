"""Integration tests for the settings provider wizard endpoints (POST /api/settings/models)."""

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


class TestFetchModels:
    """Tests for POST /api/settings/models endpoint."""
    
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
    
    def test_fetch_models_success(self, client, auth_client, monkeypatch):
        """Successful model fetch returns 200 with models list and null error."""
        cookie = auth_client
        
        # Mock fetch_models to return a successful result
        async def mock_fetch_models(provider_type, api_key, base_url):
            return {
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
                ],
                "error": None,
            }
        
        monkeypatch.setattr(
            "server.api.routers.settings.fetch_models",
            mock_fetch_models
        )
        
        # First, set up provider settings
        client.put(
            "/api/settings",
            json={
                "provider_type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test-key",
            },
            headers={"Cookie": cookie},
        )
        
        # Then fetch models
        resp = client.post(
            "/api/settings/models",
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "error" in data
        assert data["error"] is None
        assert len(data["models"]) == 2
        assert data["models"][0]["id"] == "gpt-4o"
        assert data["models"][0]["name"] == "GPT-4o"
        assert data["models"][1]["id"] == "gpt-4o-mini"
        assert data["models"][1]["name"] == "GPT-4o Mini"
    
    def test_fetch_models_no_provider(self, client, auth_client):
        """No provider configured returns 200 with empty models and error."""
        cookie = auth_client
        
        resp = client.post(
            "/api/settings/models",
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "error" in data
        assert data["models"] == []
        assert data["error"] is not None
        assert data["error"]["code"] == "no_provider"
        assert "No provider configured" in data["error"]["message"]
    
    def test_fetch_models_provider_error(self, client, auth_client, monkeypatch):
        """Provider error returns 200 with empty models and error details."""
        cookie = auth_client
        
        # Mock fetch_models to return an error
        async def mock_fetch_models(provider_type, api_key, base_url):
            return {
                "models": [],
                "error": {
                    "code": "provider_error",
                    "message": "Failed to fetch models: timeout",
                },
            }
        
        monkeypatch.setattr(
            "server.api.routers.settings.fetch_models",
            mock_fetch_models
        )
        
        # Set up provider settings
        client.put(
            "/api/settings",
            json={
                "provider_type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test-key",
            },
            headers={"Cookie": cookie},
        )
        
        resp = client.post(
            "/api/settings/models",
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "error" in data
        assert data["models"] == []
        assert data["error"] is not None
        assert data["error"]["code"] == "provider_error"
        assert "Failed to fetch models" in data["error"]["message"]
    
    def test_fetch_models_requires_auth(self, client):
        """POST /api/settings/models requires authentication."""
        resp = client.post("/api/settings/models")
        assert resp.status_code == 401
    
    def test_fetch_models_not_filtered_by_allowed_models(self, client, auth_client, monkeypatch):
        """Returned models are NOT filtered by DATARA_ALLOWED_MODELS."""
        cookie = auth_client
        
        # Mock fetch_models to return models not in the allowed list
        async def mock_fetch_models(provider_type, api_key, base_url):
            return {
                "models": [
                    {"id": "custom-model-1", "name": "Custom Model 1"},
                    {"id": "custom-model-2", "name": "Custom Model 2"},
                ],
                "error": None,
            }
        
        monkeypatch.setattr(
            "server.api.routers.settings.fetch_models",
            mock_fetch_models
        )
        
        # Set up provider settings
        client.put(
            "/api/settings",
            json={
                "provider_type": "custom",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test-key",
            },
            headers={"Cookie": cookie},
        )
        
        resp = client.post(
            "/api/settings/models",
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Models should be returned even if not in ALLOWED_MODELS
        assert len(data["models"]) == 2
        assert data["models"][0]["id"] == "custom-model-1"
        assert data["models"][1]["id"] == "custom-model-2"


class TestWizardSaveFlow:
    """Tests for the wizard save flow (provider → model → get reflects all)."""
    
    def test_wizard_save_flow(self, client, auth_client):
        """Complete wizard flow: save provider, then model, then verify GET."""
        cookie = auth_client
        
        # Step 1: Save provider credentials
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "ollama",
                "base_url": "http://localhost:11434/v1",
                "api_key": None,  # No API key for Ollama
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "ollama"
        assert data["base_url"] == "http://localhost:11434/v1"
        assert data["has_api_key"] is False
        
        # Step 2: Save default model
        resp = client.put(
            "/api/settings",
            json={
                "default_model": "llama3.2:latest",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_model"] == "llama3.2:latest"
        
        # Step 3: Verify GET reflects all fields
        resp = client.get("/api/settings", headers={"Cookie": cookie})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "ollama"
        assert data["base_url"] == "http://localhost:11434/v1"
        assert data["default_model"] == "llama3.2:latest"
        assert data["has_api_key"] is False
    
    def test_wizard_partial_saves(self, client, auth_client):
        """Partial saves: provider first, model later, GET reflects both."""
        cookie = auth_client
        
        # Save only provider fields
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "openrouter"
        assert data["base_url"] == "https://openrouter.ai/api/v1"
        assert data["default_model"] is None  # Not set yet
        
        # Save only model later
        resp = client.put(
            "/api/settings",
            json={
                "default_model": "gpt-4o",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_model"] == "gpt-4o"
        assert data["provider_type"] == "openrouter"  # Should be unchanged
        assert data["base_url"] == "https://openrouter.ai/api/v1"  # Should be unchanged
        
        # Final GET verification
        resp = client.get("/api/settings", headers={"Cookie": cookie})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "openrouter"
        assert data["base_url"] == "https://openrouter.ai/api/v1"
        assert data["default_model"] == "gpt-4o"
    
    def test_wizard_save_with_api_key(self, client, auth_client):
        """Save provider with API key, verify has_api_key is True."""
        cookie = auth_client
        
        resp = client.put(
            "/api/settings",
            json={
                "provider_type": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": "sk-groq-test-key",
            },
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "groq"
        assert data["base_url"] == "https://api.groq.com/openai/v1"
        assert data["has_api_key"] is True
        
        # Verify GET also shows has_api_key
        resp = client.get("/api/settings", headers={"Cookie": cookie})
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_api_key"] is True
        # Key material should not be exposed
        assert "api_key" not in data
        assert "sk-groq-test-key" not in str(data)