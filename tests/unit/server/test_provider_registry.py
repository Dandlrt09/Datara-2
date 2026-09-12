"""Unit tests for provider_registry."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from server.services.provider_registry import (
    PROVIDER_PRESETS,
    ProviderPreset,
    build_provider,
    fetch_models,
)


class TestProviderRegistry:
    """Test provider preset mapping and model fetch adapters."""

    def test_presets_defined(self):
        """Verify all 5 provider presets are defined with correct defaults."""
        assert set(PROVIDER_PRESETS.keys()) == {
            "openrouter", "ollama", "lmstudio", "groq", "custom"
        }
        
        # Check default base URLs
        assert PROVIDER_PRESETS["openrouter"].default_base_url == "https://openrouter.ai/api/v1"
        assert PROVIDER_PRESETS["ollama"].default_base_url == "http://localhost:11434/v1"
        assert PROVIDER_PRESETS["lmstudio"].default_base_url == "http://localhost:1234/v1"
        assert PROVIDER_PRESETS["groq"].default_base_url == "https://api.groq.com/openai/v1"
        assert PROVIDER_PRESETS["custom"].default_base_url is None
        
        # Check key requirements
        assert PROVIDER_PRESETS["openrouter"].requires_key is True
        assert PROVIDER_PRESETS["ollama"].requires_key is False
        assert PROVIDER_PRESETS["lmstudio"].requires_key is False
        assert PROVIDER_PRESETS["groq"].requires_key is True
        assert PROVIDER_PRESETS["custom"].requires_key is True

    @pytest.mark.asyncio
    async def test_fetch_models_openrouter_success(self):
        """Test OpenRouter model fetch with successful response."""
        mock_response = {
            "data": [
                {"id": "openai/gpt-4o", "name": "GPT-4o"},
                {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct"},
            ]
        }
        
        # Create a mock response with a synchronous json() method
        mock_http_response = MagicMock(spec=httpx.Response)
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        
        # Mock the async client context manager
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_http_response
        
        # Mock AsyncClient to return our mock client
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="openrouter",
                api_key="test-key",
                base_url="https://openrouter.ai/api/v1",
            )
            
        assert result["error"] is None
        assert len(result["models"]) == 2
        assert result["models"][0] == {"id": "openai/gpt-4o", "name": "GPT-4o"}
        assert result["models"][1] == {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct"}

    @pytest.mark.asyncio
    async def test_fetch_models_ollama_success(self):
        """Test Ollama model fetch with /api/tags endpoint."""
        mock_response = {
            "models": [
                {"name": "llama3.2:latest", "model": "llama3.2"},
                {"name": "mistral:instruct", "model": "mistral"},
            ]
        }
        
        # Create a mock response with synchronous json() method
        mock_http_response = MagicMock(spec=httpx.Response)
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = MagicMock()
        
        # Mock the async client context manager
        mock_inner_client = AsyncMock()
        mock_inner_client.get.return_value = mock_http_response
        
        # Mock AsyncClient to return our mock client
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_inner_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="ollama",
                api_key=None,
                base_url="http://localhost:11434/v1",
            )
            
        assert result["error"] is None
        assert len(result["models"]) == 2
        # Should use 'name' field as id, 'model' field as name (or name as fallback)
        assert result["models"][0] == {"id": "llama3.2:latest", "name": "llama3.2"}
        assert result["models"][1] == {"id": "mistral:instruct", "name": "mistral"}

    @pytest.mark.asyncio
    async def test_fetch_models_ollama_name_vs_model_variance_red(self):
        """RED test: name-vs-model payload variance in Ollama response."""
        # Test case 1: Some OpenAI-compatible servers return 'name' key
        mock_response_name = {
            "data": [
                {"id": "model1", "name": "Model One"},
                {"id": "model2", "name": "Model Two"},
            ]
        }
        
        # Test case 2: Others return 'model' key (like Ollama's /api/tags)
        mock_response_model = {
            "data": [
                {"id": "model1", "model": "Model One"},
                {"id": "model2", "model": "Model Two"},
            ]
        }
        
        # Test case 3: Mixed or missing keys
        mock_response_mixed = {
            "data": [
                {"id": "model1", "name": "Model One"},
                {"id": "model2"},  # No name/model key
                {"id": "model3", "model": "Model Three"},
            ]
        }
        
        # Test with name key
        mock_http_response_name = MagicMock(spec=httpx.Response)
        mock_http_response_name.status_code = 200
        mock_http_response_name.json.return_value = mock_response_name
        mock_http_response_name.raise_for_status = MagicMock()
        
        # Mock the async client context manager
        mock_inner_client = AsyncMock()
        mock_inner_client.get.return_value = mock_http_response_name
        
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_inner_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="lmstudio",  # Any OpenAI-compatible
                api_key=None,
                base_url="https://api.example.com/v1",
            )
            
        assert result["error"] is None
        assert result["models"][0] == {"id": "model1", "name": "Model One"}
        
        # Test with model key  
        mock_http_response_model = MagicMock(spec=httpx.Response)
        mock_http_response_model.status_code = 200
        mock_http_response_model.json.return_value = mock_response_model
        mock_http_response_model.raise_for_status = MagicMock()
        
        # Mock the async client context manager
        mock_inner_client = AsyncMock()
        mock_inner_client.get.return_value = mock_http_response_model
        
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_inner_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="lmstudio",
                api_key=None,
                base_url="https://api.example.com/v1",
            )
            
        assert result["error"] is None
        assert result["models"][0] == {"id": "model1", "name": "Model One"}
        
        # Test with mixed/missing keys
        mock_http_response_mixed = MagicMock(spec=httpx.Response)
        mock_http_response_mixed.status_code = 200
        mock_http_response_mixed.json.return_value = mock_response_mixed
        mock_http_response_mixed.raise_for_status = MagicMock()
        
        # Mock the async client context manager
        mock_inner_client = AsyncMock()
        mock_inner_client.get.return_value = mock_http_response_mixed
        
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_inner_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="lmstudio",
                api_key=None,
                base_url="https://api.example.com/v1",
            )
            
        assert result["error"] is None
        assert result["models"][0] == {"id": "model1", "name": "Model One"}
        assert result["models"][1] == {"id": "model2", "name": "model2"}  # id as fallback
        assert result["models"][2] == {"id": "model3", "name": "Model Three"}

    @pytest.mark.asyncio
    async def test_fetch_models_custom_no_fetch(self):
        """Test custom provider never fetches models."""
        result = await fetch_models(
            provider_type="custom",
            api_key="test-key",
            base_url="https://custom.example.com/v1",
        )
        
        assert result["error"] is None
        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_fetch_models_no_provider(self):
        """Test fetch with no provider settings."""
        result = await fetch_models(
            provider_type=None,
            api_key=None,
            base_url=None,
        )
        
        assert result["error"] is not None
        assert result["error"]["code"] == "no_provider"
        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_fetch_models_timeout(self):
        """Test timeout error."""
        # Mock the async client context manager
        mock_inner_client = AsyncMock()
        mock_inner_client.get.side_effect = httpx.TimeoutException("Timeout")
        
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_inner_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="openrouter",
                api_key="test-key",
                base_url="https://openrouter.ai/api/v1",
            )
            
        assert result["error"] is not None
        assert result["error"]["code"] == "timeout"
        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_fetch_models_network_error(self):
        """Test network error."""
        # Mock the async client context manager
        mock_inner_client = AsyncMock()
        mock_inner_client.get.side_effect = httpx.NetworkError("Connection refused")
        
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_inner_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="openrouter",
                api_key="test-key",
                base_url="https://openrouter.ai/api/v1",
            )
            
        assert result["error"] is not None
        assert result["error"]["code"] == "network"
        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_fetch_models_provider_error(self):
        """Test provider HTTP error."""
        # Create a mock response for 401 error
        mock_http_response = MagicMock(spec=httpx.Response)
        mock_http_response.status_code = 401
        mock_http_response.json.return_value = {"error": "Invalid API key"}
        mock_http_response.raise_for_status.side_effect = httpx.HTTPError("401 Unauthorized")
        
        # Mock the async client context manager
        mock_inner_client = AsyncMock()
        mock_inner_client.get.return_value = mock_http_response
        
        with patch("httpx.AsyncClient") as mock_async_client:
            # Set up the context manager chain
            mock_async_client_instance = AsyncMock()
            mock_async_client_instance.__aenter__.return_value = mock_inner_client
            mock_async_client_instance.__aexit__.return_value = None
            mock_async_client.return_value = mock_async_client_instance
            
            result = await fetch_models(
                provider_type="openrouter",
                api_key="invalid-key",
                base_url="https://openrouter.ai/api/v1",
            )
            
        assert result["error"] is not None
        assert result["error"]["code"] == "provider_error"
        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_build_provider_local_keyless_placeholder(self):
        """Test local keyless placeholder convention for ollama/lmstudio."""
        # Mock AsyncOpenAI to avoid actual API calls
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_openai:
            mock_instance = AsyncMock()
            mock_openai.return_value = mock_instance
            
            # ollama without key should use placeholder
            provider = build_provider(
                provider_type="ollama",
                api_key=None,
                model="llama3.2:latest",
                base_url="http://localhost:11434/v1",
            )
            # Verify AsyncOpenAI was called with placeholder key
            mock_openai.assert_called_with(api_key="local", timeout=120.0, base_url="http://localhost:11434/v1")
            
            # Reset mock for next test
            mock_openai.reset_mock()
            
            # lmstudio without key should use placeholder
            provider = build_provider(
                provider_type="lmstudio",
                api_key=None,
                model="local-model",
                base_url="http://localhost:1234/v1",
            )
            mock_openai.assert_called_with(api_key="local", timeout=120.0, base_url="http://localhost:1234/v1")
            
            # Reset mock
            mock_openai.reset_mock()
            
            # ollama with key should use the key
            provider = build_provider(
                provider_type="ollama",
                api_key="real-key",
                model="llama3.2:latest",
                base_url="http://localhost:11434/v1",
            )
            mock_openai.assert_called_with(api_key="real-key", timeout=120.0, base_url="http://localhost:11434/v1")
            
            # Reset mock
            mock_openai.reset_mock()
            
            # cloud providers without key should pass None (env fallback)
            # This will fail if OPENAI_API_KEY env var is not set, so we mock it
            with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
                provider = build_provider(
                    provider_type="openrouter",
                    api_key=None,
                    model="gpt-4o",
                    base_url="https://openrouter.ai/api/v1",
                )
                # Should pass None and let SDK read from env
                mock_openai.assert_called_with(api_key=None, timeout=120.0, base_url="https://openrouter.ai/api/v1")