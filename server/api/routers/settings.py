"""User settings router: GET/PUT per-user settings (default_model + API key
presence).

The stored API key material NEVER leaves the server: GET returns only a
boolean ``has_api_key``; PUT accepts a new key (empty/omitted keeps the
current one, via the store's COALESCE upsert).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from server.api.deps import current_user, get_store
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


class SettingsUpdateRequest(BaseModel):
    api_key: str | None = None
    default_model: str | None = None

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
    current value (the store upsert uses COALESCE).

    An unknown ``default_model`` is rejected with 422 — unless it equals
    the value already stored for this user, which is treated as "keep"
    (a stale whitelist must not brick unrelated updates such as saving
    a new API key).
    """
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
    result = await store.upsert_user_settings(
        user["id"],
        api_key_enc=body.api_key or None,
        default_model=body.default_model,
    )
    return SettingsResponse(
        user_id=result["user_id"],
        has_api_key=bool(result.get("api_key_enc")),
        default_model=result["default_model"],
        allowed_models=sorted(ALLOWED_MODELS),
    )
