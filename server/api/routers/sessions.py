"""Chat sessions router (v1: GET list / POST create / DELETE only, per Decision #16)."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import AsyncIterator

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.api import event_bus as _event_bus_module
from server.api.deps import current_user, get_store
from server.api.routers import files as files_router
from server.services.events import EventBus, SessionEvent, SessionEventType
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

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

    # Best-effort: the DB rows (files → profiles, messages) cascade via FK,
    # but the uploaded files on disk would be orphaned. Cleanup must never
    # fail the delete.
    try:
        files_router.remove_session_uploads(user["id"], session_id)
    except Exception:  # pragma: no cover — remove_session_uploads never raises
        logger.warning(
            "Session upload cleanup failed for session %s (best-effort)",
            session_id,
            exc_info=True,
        )
    return None


def _serialize_sse(event: SessionEvent) -> str:
    """Serialize a ``SessionEvent`` into one SSE frame (text/event-stream).

    Format per design (hand-rolled, no external SSE library)::

        event: <type>
        id: <session_id>:<timestamp>
        data: {\\"type\\":\\"...\\",\\"session_id\\":\\"...\\",\\"timestamp\\":...,\\"payload\\":{...}}

    The blank line separator ``\\n\\n`` is added by the caller.
    """
    data = json.dumps(
        {
            "type": event.type.value,
            "session_id": event.session_id,
            "timestamp": event.timestamp,
            "payload": event.payload,
        },
        default=str,
    )
    return (
        f"event: {event.type.name}\n"
        f"id: {event.session_id}:{event.timestamp}\n"
        f"data: {data}"
    )


@router.get("/events")
async def session_events(
    user: dict = Depends(current_user),
):
    """Server-Sent Events endpoint for real-time session updates.

    Subscribes this caller to the per-user event bus and streams each
    event as a ``text/event-stream`` frame. On ``CancelledError`` (client
    disconnect) the subscriber is removed from the bus before re-raising.

    Returns:
        ``StreamingResponse`` with ``text/event-stream`` media type.
    """
    bus = _event_bus_module.bus
    if bus is None:
        return StreamingResponse(
            content=iter(["data: {\"error\":\"event bus not ready\"}\n\n"]),
            media_type="text/event-stream",
            status_code=503,
        )

    user_id: int = user["id"]
    q = await bus.subscribe(user_id)

    return StreamingResponse(
        _sse_event_stream(bus, user_id, q),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_event_stream(
    bus: EventBus,
    user_id: int,
    q: asyncio.Queue[SessionEvent],
) -> AsyncIterator[str]:
    """Asynchronous generator that reads from a subscriber queue and yields
    SSE frames. Extracted for independent testability.

    On ``CancelledError`` (client disconnect via Starlette) the subscriber
    is removed from the bus registry before re-raising.

    Yields:
        One ``text/event-stream`` frame per event, including the blank
        line separator (``\\n\\n``).
    """
    try:
        while True:
            event = await q.get()
            yield _serialize_sse(event) + "\n\n"
    except asyncio.CancelledError:
        bus.unsubscribe(user_id, q)
        raise