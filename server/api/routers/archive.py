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


# ── Schemas ─────────────────────────────────────────────────────────────────


class CreateArchiveRequest(BaseModel):
    chat_session: str
    name: str


class ArchiveListItem(BaseModel):
    id: int
    name: str
    chat_session: str
    created_at: str | None = None


class ArchiveDetail(BaseModel):
    id: int
    name: str
    chat_session: str
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
    """
    user_id = user["id"]

    # Verify the session exists and belongs to the user
    session = await store.get_chat_session(body.chat_session, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Build the payload: messages + file refs
    messages = await store.list_messages(user_id, body.chat_session, limit=500)
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
    }

    archive = await store.create_archive(
        user_id=user_id,
        name=body.name,
        chat_session=body.chat_session,
        payload_json=json.dumps(payload),
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