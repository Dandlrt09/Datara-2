"""User settings router: GET/PUT per-user settings (api_key_enc, default_model)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    user_id: int
    api_key_enc: str | None = None
    default_model: str | None = None


class SettingsUpdateRequest(BaseModel):
    api_key: str | None = None
    default_model: str | None = None


@router.get("", response_model=SettingsResponse)
async def get_settings(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Return the current user's settings."""
    settings = await store.get_user_settings(user["id"])
    if settings is None:
        return SettingsResponse(user_id=user["id"])
    return SettingsResponse(
        user_id=settings["user_id"],
        api_key_enc=settings["api_key_enc"],
        default_model=settings["default_model"],
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateRequest,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Update the current user's settings.

    Only provided fields are updated; omitted fields keep their current value.
    """
    result = await store.upsert_user_settings(
        user["id"],
        api_key_enc=body.api_key,
        default_model=body.default_model,
    )
    return SettingsResponse(
        user_id=result["user_id"],
        api_key_enc=result["api_key_enc"],
        default_model=result["default_model"],
    )