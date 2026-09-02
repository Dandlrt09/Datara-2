"""User settings router: GET/PUT per-user settings (default_model + API key
presence).

The stored API key material NEVER leaves the server: GET returns only a
boolean ``has_api_key``; PUT accepts a new key (empty/omitted keeps the
current one, via the store's COALESCE upsert).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    user_id: int
    has_api_key: bool = False
    default_model: str | None = None


class SettingsUpdateRequest(BaseModel):
    api_key: str | None = None
    default_model: str | None = None


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
