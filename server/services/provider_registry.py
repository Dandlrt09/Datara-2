"""Provider registry for LLM providers.

Centralizes preset definitions, provider construction, and per-provider
model-fetch adapters.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Literal, TypedDict
from urllib.parse import urlparse, urlunparse

import httpx

from server.services.llm_openai import OpenAIProvider

logger = logging.getLogger(__name__)

# Local API key placeholder for keyless local providers (ollama, lmstudio).
# Any non-empty string satisfies the OpenAI SDK; the value travels as a
# Bearer header only to loopback URLs (guaranteed by the SSRF guard at save).
_LOCAL_API_KEY_PLACEHOLDER = "local"

ProviderType = Literal["openrouter", "ollama", "lmstudio", "groq", "custom"]


@dataclass
class ProviderPreset:
    """Provider preset definition."""
    default_base_url: str | None
    requires_key: bool


# Preset definitions from spec/design.
PROVIDER_PRESETS: dict[ProviderType, ProviderPreset] = {
    "openrouter": ProviderPreset(
        default_base_url="https://openrouter.ai/api/v1",
        requires_key=True,
    ),
    "ollama": ProviderPreset(
        default_base_url="http://localhost:11434/v1",
        requires_key=False,
    ),
    "lmstudio": ProviderPreset(
        default_base_url="http://localhost:1234/v1",
        requires_key=False,
    ),
    "groq": ProviderPreset(
        default_base_url="https://api.groq.com/openai/v1",
        requires_key=True,
    ),
    "custom": ProviderPreset(
        default_base_url=None,
        requires_key=True,
    ),
}


class ModelInfo(TypedDict):
    """Model information returned by fetch_models."""
    id: str
    name: str


class FetchModelsError(TypedDict):
    """Error information returned by fetch_models on failure."""
    code: Literal["no_provider", "provider_error", "timeout", "network"]
    message: str


class FetchModelsResult(TypedDict):
    """Result of fetch_models."""
    models: list[ModelInfo]
    error: FetchModelsError | None


def build_provider(
    provider_type: ProviderType | None,
    api_key: str | None,
    model: str,
    base_url: str | None = None,
    timeout: float = 120.0,
) -> OpenAIProvider:
    """Build an OpenAIProvider instance for the given provider settings.
    
    Applies the local keyless placeholder convention (design D3): when
    provider_type is ollama or lmstudio and no api_key is provided,
    use _LOCAL_API_KEY_PLACEHOLDER so the SDK accepts the request.
    
    Args:
        provider_type: Provider type, or None for env fallback.
        api_key: API key (encrypted), or None for env fallback.
        model: Model name.
        base_url: Custom base URL, or None for env/default.
        timeout: Request timeout in seconds.
        
    Returns:
        Configured OpenAIProvider instance.
    """
    effective_api_key = api_key
    
    # Apply local keyless placeholder for ollama/lmstudio when no key
    if provider_type in ("ollama", "lmstudio") and not effective_api_key:
        effective_api_key = _LOCAL_API_KEY_PLACEHOLDER
    
    return OpenAIProvider(
        api_key=effective_api_key,
        model=model,
        timeout=timeout,
        base_url=base_url,
    )


async def fetch_models(
    provider_type: ProviderType | None,
    api_key: str | None,
    base_url: str | None,
) -> FetchModelsResult:
    """Fetch available models from a provider.
    
    Per-provider adapter pattern:
    - openrouter, lmstudio, groq: GET {base_url}/models (Bearer when key)
    - ollama: GET {server-root-of-base_url}/api/tags (no auth)
    - custom: never fetches (returns empty list)
    
    Always returns HTTP 200 shape: {models: [{id, name}], error}.
    Error codes: no_provider, provider_error, timeout, network.
    
    Args:
        provider_type: Provider type from settings.
        api_key: Encrypted API key from settings.
        base_url: Base URL from settings.
        
    Returns:
        FetchModelsResult with models and optional error.
    """
    # No provider configured
    if not provider_type:
        return {
            "models": [],
            "error": {
                "code": "no_provider",
                "message": "No provider configured",
            },
        }
    
    # Custom provider never fetches
    if provider_type == "custom":
        return {"models": [], "error": None}
    
    # Need base_url for fetching
    if not base_url:
        return {
            "models": [],
            "error": {
                "code": "provider_error",
                "message": "No base URL configured",
            },
        }
    
    # Determine fetch URL and headers
    url, headers = _prepare_fetch_request(provider_type, api_key, base_url)
    if not url:
        return {
            "models": [],
            "error": {
                "code": "provider_error", 
                "message": "Invalid base URL",
            },
        }
    
    # Perform the fetch
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            # Handle both real response and mocked response
            json_data = response.json()
            # Try to detect if json() returned a coroutine (AsyncMock)
            try:
                # First check if it's awaitable
                if hasattr(json_data, '__await__') or asyncio.iscoroutine(json_data):
                    # It might be a coroutine or AsyncMock
                    try:
                        json_data = await json_data
                    except TypeError:
                        # Not actually awaitable, treat as regular value
                        pass
            except Exception:
                # Any other issue, just proceed
                pass
                
            models = _parse_models_response(provider_type, json_data)
            return {"models": models, "error": None}
            
    except httpx.TimeoutException:
        logger.warning("Model fetch timeout for %s", provider_type)
        return {
            "models": [],
            "error": {
                "code": "timeout",
                "message": "Request timed out",
            },
        }
    except httpx.NetworkError:
        logger.warning("Model fetch network error for %s", provider_type)
        return {
            "models": [],
            "error": {
                "code": "network",
                "message": "Network error",
            },
        }
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Model fetch provider error for %s: %s", provider_type, e)
        return {
            "models": [],
            "error": {
                "code": "provider_error",
                "message": str(e),
            },
        }


def _prepare_fetch_request(
    provider_type: ProviderType,
    api_key: str | None,
    base_url: str,
) -> tuple[str | None, dict[str, str]]:
    """Prepare fetch URL and headers for a provider type."""
    headers = {}
    
    # Add Bearer header for providers that require auth
    if api_key and provider_type in ("openrouter", "groq"):
        headers["Authorization"] = f"Bearer {api_key}"
    
    # Special handling for ollama: fetch from server root /api/tags
    if provider_type == "ollama":
        try:
            parsed = urlparse(base_url)
            # Strip /v1 or any path component
            server_root = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            url = f"{server_root}/api/tags"
            return url, headers
        except Exception:
            return None, {}
    
    # OpenAI-compatible providers: use /models endpoint
    url = f"{base_url.rstrip('/')}/models"
    return url, headers


def _parse_models_response(
    provider_type: ProviderType,
    data: dict,
) -> list[ModelInfo]:
    """Parse provider response into normalized model list.
    
    Handles payload variance: some servers use 'name' key, others 'model'.
    Fallback to 'id' if neither present.
    """
    models = []
    
    # Extract model list based on provider
    if provider_type == "ollama":
        items = data.get("models", [])
    else:
        items = data.get("data", [])
    
    for item in items:
        if not isinstance(item, dict):
            continue
            
        # For Ollama, the /api/tags endpoint returns {"name": "...", "model": "..."}
        # without an "id" field. Use "name" as id when "id" is missing.
        model_id = item.get("id", "")
        if not model_id:
            # Try name or model as fallback id
            model_id = item.get("name") or item.get("model", "")
            if not model_id:
                continue
            
        # Try name, then model, then fallback to id
        # For Ollama, prefer model over name when both exist
        # (name is full tag like "llama3.2:latest", model is base "llama3.2")
        if provider_type == "ollama" and item.get("model"):
            name = item.get("model")
        else:
            name = item.get("name") or item.get("model") or model_id
        
        models.append({
            "id": model_id,
            "name": name,
        })
    
    return models