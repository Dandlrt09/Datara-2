"""Chat sessions router (v1: GET list / POST create / DELETE only, per Decision #16)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """List all chat sessions for the current user, newest first."""
    sessions = await store.list_chat_sessions(user["id"])
    return [
        SessionResponse(
            id=s["id"],
            title=s["title"],
            created_at=s["created_at"],
            updated_at=s["updated_at"],
        )
        for s in sessions
    ]


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Create a new chat session for the current user."""
    session_id = "ses_" + secrets.token_urlsafe(16)
    title = body.title or "New chat"
    session = await store.create_chat_session(session_id, user["id"], title)
    return SessionResponse(
        id=session["id"],
        title=session["title"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Delete a chat session owned by the current user.

    Returns 204 even if the session doesn't exist or doesn't belong
    to the user (be safe — don't reveal existence to other users).
    """
    await store.delete_chat_session(session_id, user["id"])
    return None