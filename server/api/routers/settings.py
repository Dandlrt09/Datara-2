"""User settings router: GET/PUT per-user settings (default_model + API key
presence).

The stored API key material NEVER leaves the server: GET returns only a
boolean ``has_api_key``; PUT accepts a new key (empty/omitted keeps the
current one, via the store's COALESCE upsert).
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from server.api.deps import current_user, get_store
from server.services.base_url_guard import BaseUrlRejected, validate_base_url
from server.services.provider_registry import fetch_models
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Known OpenAI chat models accepted for default_model. The chat provider
# resolves this string per request, so an invalid value would only fail
# later (at chat time) — reject it here instead, at save time.
_BASE_MODELS = frozenset(
    {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
    }
)


def _load_allowed_models() -> frozenset[str]:
    """Base whitelist + DATARA_ALLOWED_MODELS (comma-separated).

    The extension supports alternative OpenAI-compatible backends (e.g.
    OpenRouter model slugs like ``z-ai/glm-4.7-flash``) pointed at via
    OPENAI_BASE_URL. Read once at import; restart the server to apply.
    """
    extra = os.environ.get("DATARA_ALLOWED_MODELS", "")
    return _BASE_MODELS | {m.strip() for m in extra.split(",") if m.strip()}


ALLOWED_MODELS = _load_allowed_models()


class SettingsResponse(BaseModel):
    user_id: int
    has_api_key: bool = False
    default_model: str | None = None
    allowed_models: list[str] = []
    provider_type: Literal["openrouter", "ollama", "lmstudio", "groq", "custom"] | None = None
    base_url: str | None = None


class SettingsUpdateRequest(BaseModel):
    api_key: str | None = None
    default_model: str | None = None
    provider_type: Literal["openrouter", "ollama", "lmstudio", "groq", "custom"] | None = None
    base_url: str | None = Field(default=None, min_length=0)  # empty string allowed → clear

    @field_validator("default_model")
    @classmethod
    def _normalize_default_model(cls, v: str | None) -> str | None:
        # Normalize only: empty/whitespace means "keep current value".
        # The whitelist check lives in update_settings (handler), where the
        # stored value is visible — re-saving an unchanged model that is no
        # longer whitelisted (e.g. server rebooted without
        # DATARA_ALLOWED_MODELS) must not block unrelated updates.
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ModelInfo(BaseModel):
    """Model information returned by POST /api/settings/models."""
    id: str
    name: str


class FetchModelsError(BaseModel):
    """Error information returned by POST /api/settings/models on failure."""
    code: Literal["no_provider", "provider_error", "timeout", "network"]
    message: str


class ModelsResponse(BaseModel):
    """Response for POST /api/settings/models."""
    models: list[ModelInfo]
    error: FetchModelsError | None


@router.get("", response_model=SettingsResponse)
async def get_settings(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Return the current user's settings (no key material)."""
    settings = await store.get_user_settings(user["id"])
    if settings is None:
        return SettingsResponse(
            user_id=user["id"], allowed_models=sorted(ALLOWED_MODELS)
        )
    return SettingsResponse(
        user_id=settings["user_id"],
        has_api_key=bool(settings.get("api_key_enc")),
        default_model=settings["default_model"],
        provider_type=settings["provider_type"],
        base_url=settings["base_url"],
        allowed_models=sorted(ALLOWED_MODELS),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateRequest,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Update the current user's settings.

    Only provided fields are updated; omitted/empty fields keep their
    current value (the store upsert uses COALESCE for api_key/default_model,
    CASE flags for provider_type/base_url).

    An unknown ``default_model`` is rejected with 422 — unless it equals
    the value already stored for this user, which is treated as "keep"
    (a stale whitelist must not brick unrelated updates such as saving
    a new API key).
    """
    # Keep the save-time default_model whitelist check (removed in Work Unit 4)
    if body.default_model is not None:
        current = await store.get_user_settings(user["id"])
        stored_model = current["default_model"] if current else None
        if body.default_model != stored_model and body.default_model not in ALLOWED_MODELS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"unknown model '{body.default_model}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_MODELS))}"
                ),
            )

    # Determine effective provider_type for SSRF guard: use provided value if
    # present, otherwise fetch current settings to know what's already stored.
    # Also need to preserve stored value for the upsert when omitted.
    effective_provider_type = body.provider_type
    stored_provider_type = None
    if "provider_type" not in body.model_fields_set:
        # provider_type omitted → need stored value for SSRF guard AND to keep it
        current = await store.get_user_settings(user["id"])
        stored_provider_type = current["provider_type"] if current else None
        effective_provider_type = stored_provider_type
    elif effective_provider_type is None and "provider_type" in body.model_fields_set:
        # provider_type was explicitly set to null → clear
        effective_provider_type = None
        stored_provider_type = None  # will be cleared

    # SSRF guard for base_url if provided (including empty string to clear)
    if "base_url" in body.model_fields_set:
        if body.base_url is not None and body.base_url != "":
            try:
                await validate_base_url(
                    body.base_url, provider_type=effective_provider_type
                )
            except BaseUrlRejected as e:
                raise HTTPException(
                    status_code=422,
                    detail={"code": e.code, "message": e.reason},
                )
        # empty string "" is normalized to None by the validator → clear

    # Determine which fields were provided for the CASE-flag upsert
    provider_type_provided = "provider_type" in body.model_fields_set
    base_url_provided = "base_url" in body.model_fields_set

    # Use stored_provider_type when omitted, otherwise body.provider_type
    upsert_provider_type = stored_provider_type if stored_provider_type is not None else body.provider_type

    result = await store.upsert_user_settings(
        user["id"],
        api_key_enc=body.api_key or None,
        default_model=body.default_model,
        provider_type=upsert_provider_type,
        base_url=body.base_url,  # None or normalized value
        provider_type_provided=provider_type_provided,
        base_url_provided=base_url_provided,
    )
    return SettingsResponse(
        user_id=result["user_id"],
        has_api_key=bool(result.get("api_key_enc")),
        default_model=result["default_model"],
        provider_type=result["provider_type"],
        base_url=result["base_url"],
        allowed_models=sorted(ALLOWED_MODELS),
    )


@router.post("/models", response_model=ModelsResponse)
async def fetch_available_models(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Fetch available models from the configured provider.
    
    Uses saved provider settings (provider_type, base_url, api_key) to
    query the provider's model list endpoint. Always returns HTTP 200
    with {models: [...], error: null|{code, message}} shape.
    
    The returned models are NOT filtered by DATARA_ALLOWED_MODELS.
    """
    settings = await store.get_user_settings(user["id"])
    if not settings:
        return ModelsResponse(
            models=[],
            error=FetchModelsError(
                code="no_provider",
                message="No provider configured",
            ),
        )
    
    provider_type = settings.get("provider_type")
    api_key = settings.get("api_key_enc")
    base_url = settings.get("base_url")
    
    result = await fetch_models(
        provider_type=provider_type,
        api_key=api_key,
        base_url=base_url,
    )
    
    return ModelsResponse(
        models=result["models"],
        error=FetchModelsError(**result["error"]) if result["error"] else None,
    )
