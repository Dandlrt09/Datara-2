"""User settings router: GET/PUT per-user settings (default_model + API key
presence).

The stored API key material NEVER leaves the server: GET returns only a
boolean ``has_api_key``; PUT accepts a new key (empty/omitted keeps the
current one, via the store's COALESCE upsert).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Known OpenAI chat models accepted for default_model. The chat provider
# resolves this string per request, so an invalid value would only fail
# later (at chat time) — reject it here instead, at save time.
ALLOWED_MODELS = frozenset(
    {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
    }
)


class SettingsResponse(BaseModel):
    user_id: int
    has_api_key: bool = False
    default_model: str | None = None


class SettingsUpdateRequest(BaseModel):
    api_key: str | None = None
    default_model: str | None = None

    @field_validator("default_model")
    @classmethod
    def validate_default_model(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None  # treat empty as unset (keep current value)
        if v not in ALLOWED_MODELS:
            raise ValueError(
                f"unknown model '{v}'. Allowed: {', '.join(sorted(ALLOWED_MODELS))}"
            )
        return v


@router.get("", response_model=SettingsResponse)
async def get_settings(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Return the current user's settings (no key material)."""
    settings = await store.get_user_settings(user["id"])
    if settings is None:
        return SettingsResponse(user_id=user["id"])
    return SettingsResponse(
        user_id=settings["user_id"],
        has_api_key=bool(settings.get("api_key_enc")),
        default_model=settings["default_model"],
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
    """
    result = await store.upsert_user_settings(
        user["id"],
        api_key_enc=body.api_key or None,
        default_model=body.default_model,
    )
    return SettingsResponse(
        user_id=result["user_id"],
        has_api_key=bool(result.get("api_key_enc")),
        default_model=result["default_model"],
    )
