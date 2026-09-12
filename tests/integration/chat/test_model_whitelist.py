"""RED tests for chat-time model whitelist enforcement (Phase 3, task 3.4).

Tests verify:
- Non-whitelisted resolved model → 422 model_not_allowed
- No LLM call made when model is not whitelisted
- No persisted message when model is not whitelisted
- Whitelisted model proceeds normally
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import auth as auth_router
from server.api.routers import chat as chat_router
from server.api.routers import sessions as sessions_router
from server.api.routers import settings as settings_router
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(chat_router.router)
    application.include_router(settings_router.router)

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
def store():
    from server.api import store as api_store  # noqa: PLC0415
    return api_store._store


@pytest.fixture
def auth_cookie(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "whitelist@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def session_id(client, auth_cookie):
    resp = client.post(
        "/api/sessions",
        json={"title": "Whitelist test"},
        headers={"Cookie": auth_cookie},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestModelWhitelist:
    """Tests for chat-time model whitelist enforcement."""
    
    def test_non_whitelisted_model_422_no_llm_call(self, client, auth_cookie, session_id, monkeypatch):
        """Non-whitelisted resolved model → 422 model_not_allowed, no LLM call."""
        from server.api.routers import chat as chat_module
        from server.api.routers import settings as settings_module
        
        # Monkeypatch ALLOWED_MODELS in both modules
        whitelist = frozenset({"gpt-4o", "gpt-4o-mini"})
        monkeypatch.setattr(
            settings_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        monkeypatch.setattr(
            chat_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        
        # Save a non-whitelisted model via settings (PUT accepts any model)
        cookie = auth_cookie
        resp = client.put(
            "/api/settings",
            json={"default_model": "z-ai/glm-5.3-flash"},  # Not in whitelist
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        
        # Save a non-whitelisted model via settings (PUT accepts any model)
        cookie = auth_cookie
        resp = client.put(
            "/api/settings",
            json={"default_model": "z-ai/glm-5.3-flash"},  # Not in whitelist
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        
        # Mock OpenAIProvider.complete to ensure no LLM call is made
        mock_complete = AsyncMock()
        mock_complete.return_value = MagicMock(
            text="This should not be called",
            structured_data={"code": "", "explanation": "Test"},
            model="z-ai/glm-5.3-flash",
            provider="openai",
            usage=MagicMock(tokens_in=10, tokens_out=20, cost_usd=0.001)
        )
        
        with patch.object(chat_module.OpenAIProvider, 'complete', mock_complete):
            # Attempt chat with non-whitelisted model
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "What is 2+2?"},
                headers={"Cookie": cookie},
            )
            
            # Should get 422 with correct error code
            assert resp.status_code == 422
            data = resp.json()
            assert "detail" in data
            assert data["detail"]["code"] == "model_not_allowed"
            assert "no está permitido" in data["detail"]["message"]
            assert "z-ai/glm-5.3-flash" in data["detail"]["message"]
            
            # Verify LLM was NOT called
            mock_complete.assert_not_called()
            
            # Verify no new messages were persisted (check via list messages)
            list_resp = client.get(
                f"/api/sessions/{session_id}/messages",
                headers={"Cookie": cookie},
            )
            assert list_resp.status_code == 200
            messages = list_resp.json()
            # Only the session exists, no chat messages
            assert len(messages) == 0
    
    def test_whitelisted_model_proceeds_normally(self, client, auth_cookie, session_id, monkeypatch):
        """Whitelisted model should proceed normally with LLM call."""
        from server.api.routers import chat as chat_module
        from server.api.routers import settings as settings_module
        
        # Monkeypatch ALLOWED_MODELS in both modules
        whitelist = frozenset({"gpt-4o", "gpt-4o-mini"})
        monkeypatch.setattr(
            settings_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        monkeypatch.setattr(
            chat_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        
        # Save a whitelisted model AND an API key (required for OpenAIProvider)
        cookie = auth_cookie
        resp = client.put(
            "/api/settings",
            json={"default_model": "gpt-4o", "api_key": "sk-test-key"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        
        # Mock OpenAIProvider completely to avoid credential errors
        mock_provider = MagicMock()
        mock_complete = AsyncMock()
        mock_complete.return_value = MagicMock(
            text="Test explanation",
            structured_data={"code": "print(2+2)", "explanation": "The sum is 4"},
            model="gpt-4o",
            provider="openai",
            usage=MagicMock(tokens_in=10, tokens_out=20, cost_usd=0.001)
        )
        mock_provider.complete = mock_complete
        
        # Mock build_provider to return our mock provider
        mock_build_provider = MagicMock(return_value=mock_provider)
        
        # Mock run_code to avoid actual sandbox execution
        mock_run_code = AsyncMock()
        mock_run_code.return_value = {
            "status": "ok",
            "text": "4",
            "figures": [],
            "tables": [],
        }
        
        with patch.object(chat_module, 'build_provider', mock_build_provider), \
             patch('server.api.routers.chat.run_code', mock_run_code):
            
            # Chat with whitelisted model
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "What is 2+2?"},
                headers={"Cookie": cookie},
            )
            
            # Should get SSE stream
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            
            # Verify build_provider was called
            mock_build_provider.assert_called_once()
            
            # Verify LLM was called (called twice: main call + grounding pass)
            assert mock_complete.call_count >= 1
            
            # Read SSE events to verify completion
            content = resp.content.decode()
            assert "event: done" in content
            
            # Verify message was persisted (user message + assistant message)
            list_resp = client.get(
                f"/api/sessions/{session_id}/messages",
                headers={"Cookie": cookie},
            )
            assert list_resp.status_code == 200
            messages = list_resp.json()
            assert len(messages) == 2  # user message + assistant message
            # Find assistant message
            assistant_msgs = [m for m in messages if m["role"] == "assistant"]
            assert len(assistant_msgs) == 1
            assert assistant_msgs[0]["content_text"] == "Test explanation"
    
    def test_default_model_falls_back_to_whitelisted(self, client, auth_cookie, session_id, monkeypatch):
        """When no default_model is saved, fallback to _DEFAULT_MODEL (whitelisted)."""
        from server.api.routers import chat as chat_module
        from server.api.routers import settings as settings_module
        
        # _DEFAULT_MODEL is "gpt-4o-2024-08-06" in chat.py
        # Ensure it's in the whitelist
        whitelist = frozenset({"gpt-4o", "gpt-4o-mini", "gpt-4o-2024-08-06"})
        monkeypatch.setattr(
            settings_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        monkeypatch.setattr(
            chat_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        
        cookie = auth_cookie
        
        # Save an API key (required for OpenAIProvider)
        resp = client.put(
            "/api/settings",
            json={"api_key": "sk-test-key"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 200
        
        # Mock OpenAIProvider completely
        mock_provider = MagicMock()
        mock_complete = AsyncMock()
        mock_complete.return_value = MagicMock(
            text="Test explanation",
            structured_data={"code": "print(2+2)", "explanation": "The sum is 4"},
            model="gpt-4o-2024-08-06",
            provider="openai",
            usage=MagicMock(tokens_in=10, tokens_out=20, cost_usd=0.001)
        )
        mock_provider.complete = mock_complete
        
        # Mock build_provider to return our mock provider
        mock_build_provider = MagicMock(return_value=mock_provider)
        
        # Mock run_code
        mock_run_code = AsyncMock()
        mock_run_code.return_value = {
            "status": "ok",
            "text": "4",
            "figures": [],
            "tables": [],
        }
        
        with patch.object(chat_module, 'build_provider', mock_build_provider), \
             patch('server.api.routers.chat.run_code', mock_run_code):
            
            # Chat without setting default_model (should use _DEFAULT_MODEL)
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "What is 2+2?"},
                headers={"Cookie": cookie},
            )
            
            # Should succeed
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            mock_build_provider.assert_called_once()
            assert mock_complete.call_count >= 1  # main call + grounding pass
    
    def test_spanish_error_message_format(self, client, auth_cookie, session_id, monkeypatch):
        """Error message should be in Spanish as per spec table."""
        from server.api.routers import chat as chat_module
        from server.api.routers import settings as settings_module
        
        # Set small whitelist for predictable error message
        whitelist = frozenset({"gpt-4o", "gpt-4o-mini"})
        monkeypatch.setattr(
            settings_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        monkeypatch.setattr(
            chat_module,
            "ALLOWED_MODELS",
            whitelist,
        )
        
        # Save non-whitelisted model
        cookie = auth_cookie
        client.put(
            "/api/settings",
            json={"default_model": "z-ai/glm-5.3-flash"},
            headers={"Cookie": cookie},
        )
        
        # Attempt chat
        resp = client.post(
            f"/api/sessions/{session_id}/chat",
            json={"question": "Test"},
            headers={"Cookie": cookie},
        )
        
        assert resp.status_code == 422
        data = resp.json()
        assert data["detail"]["code"] == "model_not_allowed"
        message = data["detail"]["message"]
        
        # Check Spanish format from spec: "El modelo '{model}' no está permitido. Modelos permitidos: {allowed}."
        assert message.startswith("El modelo 'z-ai/glm-5.3-flash' no está permitido.")
        assert "Modelos permitidos:" in message
        assert "gpt-4o" in message
        assert "gpt-4o-mini" in message