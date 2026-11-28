"""Privacy router: declared privacy levels and the outgoing-payload preview (F6).

A session carries the level its files inherit; a file may override it. The
preview endpoint returns the EXACT dataset block the chat turn sends, built by
the same ``build_outgoing_datasets`` function, so the "this is what is sent"
viewer can never drift from the real payload.

All endpoints enforce ownership via the ``current_user`` dependency and the
store's user_id filters (Decision #14).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.api.deps import current_user, get_store
from server.services.chat_context import build_outgoing_datasets
from server.services.privacy import (
    PRIVACY_LEVELS,
    PrivacyError,
    effective_level,
    parse_aliases,
    validate_aliases,
    validate_level,
)
from server.services.profile_cache import get_profile
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api", tags=["privacy"])


class SessionPrivacyUpdate(BaseModel):
    privacy_level: str = Field(min_length=1)


class FilePrivacyUpdate(BaseModel):
    privacy_level: str | None = None
    column_aliases: dict[str, str] | None = None


class FilePrivacyEntry(BaseModel):
    file_id: int
    filename: str
    privacy_level: str | None
    effective_level: str
    column_aliases: dict[str, str] | None


class SessionPrivacyResponse(BaseModel):
    session_id: str
    privacy_level: str
    levels: list[str]
    files: list[FilePrivacyEntry]


def _level_error(exc: PrivacyError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "invalid_privacy_level", "message": str(exc)},
    )


async def _require_session(
    store: SqliteStore, session_id: str, user_id: int
) -> str:
    """Return the session's privacy level or 404 when it is not the user's."""
    session = await store.get_session_privacy(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session["privacy_level"]


@router.get(
    "/sessions/{session_id}/privacy",
    response_model=SessionPrivacyResponse,
)
async def get_session_privacy(
    session_id: str,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Read the session level and each file's effective level."""
    session_level = await _require_session(store, session_id, user["id"])
    files = await store.list_files(user["id"], chat_session=session_id)
    entries = [
        FilePrivacyEntry(
            file_id=row["id"],
            filename=row["filename"],
            privacy_level=row.get("privacy_level"),
            effective_level=effective_level(
                row.get("privacy_level"), session_level
            ),
            column_aliases=parse_aliases(row.get("column_aliases_json")) or None,
        )
        for row in files
    ]
    return SessionPrivacyResponse(
        session_id=session_id,
        privacy_level=session_level,
        levels=list(PRIVACY_LEVELS),
        files=entries,
    )


@router.put(
    "/sessions/{session_id}/privacy",
    response_model=SessionPrivacyResponse,
)
async def update_session_privacy(
    session_id: str,
    body: SessionPrivacyUpdate,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Set the session's default level."""
    try:
        level = validate_level(body.privacy_level)
    except PrivacyError as exc:
        raise _level_error(exc) from exc
    await _require_session(store, session_id, user["id"])
    updated = await store.set_session_privacy(user["id"], session_id, level)
    if updated is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return await get_session_privacy(session_id, store, user)


@router.patch(
    "/files/{file_id}/privacy",
    response_model=FilePrivacyEntry,
)
async def update_file_privacy(
    file_id: int,
    body: FilePrivacyUpdate,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Set a file's privacy override and optional column aliases.

    ``privacy_level = null`` clears the override (the file inherits its
    session). ``column_aliases = null`` clears the aliases. An omitted field
    leaves the stored value untouched.
    """
    file_row = await store.get_file(file_id, user["id"])
    if file_row is None:
        raise HTTPException(status_code=404, detail="File not found")

    provided = body.model_fields_set
    level: str | None = file_row.get("privacy_level")
    aliases_raw: str | None = file_row.get("column_aliases_json")

    if "privacy_level" in provided:
        if body.privacy_level is None:
            level = None
        else:
            try:
                level = validate_level(body.privacy_level)
            except PrivacyError as exc:
                raise _level_error(exc) from exc

    if "column_aliases" in provided:
        if body.column_aliases is None:
            aliases_raw = None
        else:
            profile = await get_profile(store, file_id, user["id"])
            if profile is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "profile_unavailable",
                        "message": "El archivo todavía no tiene perfil.",
                    },
                )
            columns = [
                column.get("name")
                for column in profile.get("schema_data", {}).get("columns", [])
                if column.get("name")
            ]
            try:
                validate_aliases(body.column_aliases, columns)
            except PrivacyError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "invalid_column_alias", "message": str(exc)},
                ) from exc
            aliases_raw = (
                json.dumps(body.column_aliases) if body.column_aliases else None
            )

    updated = await store.set_file_privacy(
        file_id, user["id"], level, aliases_raw
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="File not found")

    session = await store.get_session_privacy(
        user["id"], file_row["chat_session"]
    )
    session_level = session["privacy_level"] if session else "full"
    return FilePrivacyEntry(
        file_id=file_id,
        filename=file_row["filename"],
        privacy_level=updated.get("privacy_level"),
        effective_level=effective_level(
            updated.get("privacy_level"), session_level
        ),
        column_aliases=parse_aliases(updated.get("column_aliases_json")) or None,
    )


@router.get("/sessions/{session_id}/privacy/preview")
async def preview_outgoing_payload(
    session_id: str,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
) -> dict[str, Any]:
    """Return the exact dataset block the next chat turn would send.

    ``sandbox_files`` is deliberately omitted: it maps staged names to real
    storage paths and never leaves the server.
    """
    await _require_session(store, session_id, user["id"])
    outgoing = await build_outgoing_datasets(
        store, user_id=user["id"], chat_session=session_id
    )
    return {
        "profiles": outgoing["profiles"],
        "unprofiled_files": outgoing["unprofiled_files"],
    }
