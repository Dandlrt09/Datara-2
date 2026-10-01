"""Archive router: create, list, and retrieve archives.

Archives snapshot a chat session's messages and file references for
later review. All endpoints enforce user ownership.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/archives", tags=["archives"])

# Validation bounds (mirror SESSION_TITLE_MAX_LENGTH in sessions.py).
ARCHIVE_NAME_MAX_LENGTH = 200
# Sanity ceiling for the serialized snapshot payload (8 MiB). Not truncation:
# an oversized snapshot is rejected, never silently cut.
ARCHIVE_PAYLOAD_MAX_BYTES = 8 * 1024 * 1024


# ── Schemas ─────────────────────────────────────────────────────────────────


class CreateArchiveRequest(BaseModel):
    chat_session: str
    name: str


class ArchiveListItem(BaseModel):
    id: int
    name: str
    chat_session: str | None = None
    created_at: str | None = None


class ArchiveDetail(BaseModel):
    id: int
    name: str
    chat_session: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str | None = None


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=ArchiveDetail)
async def create_archive(
    body: CreateArchiveRequest,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Create an archive from a chat session.

    Snapshot the session's messages and file references as the payload.
    Validation: the name is trimmed and must be non-empty and at most
    ``ARCHIVE_NAME_MAX_LENGTH`` characters (422 otherwise). The serialized
    payload must fit ``ARCHIVE_PAYLOAD_MAX_BYTES`` (413 otherwise).
    """
    user_id = user["id"]

    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_name",
                "message": "El nombre no puede estar vacío.",
            },
        )
    if len(name) > ARCHIVE_NAME_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_name",
                "message": (
                    "El nombre no puede superar los "
                    f"{ARCHIVE_NAME_MAX_LENGTH} caracteres."
                ),
            },
        )

    # Verify the session exists and belongs to the user
    session = await store.get_chat_session(body.chat_session, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Build the payload: messages + file refs. ASC + no LIMIT = a complete
    # chronological snapshot (not the newest-first, last-500 view the UI pages).
    messages = await store.list_messages(
        user_id, body.chat_session, limit=None, ascending=True
    )
    files = await store.list_files(user_id, chat_session=body.chat_session)

    payload: dict[str, Any] = {
        "session": {
            "id": session["id"],
            "title": session["title"],
            "created_at": session["created_at"],
        },
        "messages": [
            {
                "id": m["id"],
                "role": m["role"],
                "content_text": m["content_text"],
                "code": m.get("code"),
                "artifacts": json.loads(m["artifacts_json"]) if m.get("artifacts_json") else None,
                "created_at": m.get("created_at"),
            }
            for m in messages
        ],
        "files": [
            {
                "id": f["id"],
                "filename": f["filename"],
                "format": f["format"],
                "row_count": f.get("row_count"),
            }
            for f in files
        ],
        "message_count": len(messages),
        "truncated": False,
    }

    payload_json = json.dumps(payload)
    if len(payload_json.encode("utf-8")) > ARCHIVE_PAYLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "payload_too_large",
                "message": (
                    "El análisis supera el tamaño máximo permitido "
                    f"({ARCHIVE_PAYLOAD_MAX_BYTES} bytes)."
                ),
            },
        )

    archive = await store.create_archive(
        user_id=user_id,
        name=name,
        chat_session=body.chat_session,
        payload_json=payload_json,
    )

    return ArchiveDetail(
        id=archive["id"],
        name=archive["name"],
        chat_session=archive["chat_session"],
        payload=json.loads(archive["payload_json"]),
        created_at=archive["created_at"],
    )


@router.get("", response_model=list[ArchiveListItem])
async def list_archives(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """List all archives for the current user, newest first."""
    archives = await store.list_archives(user["id"])
    return [
        ArchiveListItem(
            id=a["id"],
            name=a["name"],
            chat_session=a["chat_session"],
            created_at=a["created_at"],
        )
        for a in archives
    ]


@router.get("/{archive_id}", response_model=ArchiveDetail)
async def get_archive(
    archive_id: int,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Get a single archive with its full payload.

    Ownership is enforced by the store query.
    """
    archive = await store.get_archive(archive_id, user["id"])
    if archive is None:
        raise HTTPException(status_code=404, detail="Archive not found")

    return ArchiveDetail(
        id=archive["id"],
        name=archive["name"],
        chat_session=archive["chat_session"],
        payload=json.loads(archive["payload_json"]),
        created_at=archive["created_at"],
    )