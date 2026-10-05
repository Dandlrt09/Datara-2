"""Archive router: create, list, and retrieve archives.

Archives snapshot a chat session's messages and file references for
later review. All endpoints enforce user ownership.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/archives", tags=["archives"])

# Validation bounds (mirror SESSION_TITLE_MAX_LENGTH in sessions.py).
ARCHIVE_NAME_MAX_LENGTH = 200
# Sanity ceiling for the serialized snapshot payload (32 MiB). Not truncation:
# an oversized snapshot is rejected, never silently cut.
ARCHIVE_PAYLOAD_MAX_BYTES = 32 * 1024 * 1024
# Human-readable label for the same ceiling. Kept as its own constant so the
# 413 copy stays correct even when tests monkeypatch the byte cap above.
_ARCHIVE_PAYLOAD_MAX_MB = ARCHIVE_PAYLOAD_MAX_BYTES // (1024 * 1024)


# ── Schemas ─────────────────────────────────────────────────────────────────


class CreateArchiveRequest(BaseModel):
    chat_session: str
    name: str


class RenameArchiveRequest(BaseModel):
    name: str


class ArchiveListItem(BaseModel):
    id: int
    name: str
    chat_session: str | None = None
    created_at: str | None = None
    files: list[str] = []
    row_count: int | None = None
    column_count: int | None = None


class ArchiveDetail(BaseModel):
    id: int
    name: str
    chat_session: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str | None = None


# ── Card-field derivation ───────────────────────────────────────────────────


def _derive_card_fields(
    payload_json: str,
) -> tuple[list[str], int | None, int | None]:
    """Derive the list-card metadata from a stored snapshot payload.

    Returns ``(files, row_count, column_count)``:

    - ``files``: the snapshot's ``files[].filename`` string values, in order.
    - ``row_count``: the row count of the LAST ``kind == "table"`` artifact
      (``total_rows`` when it is an ``int``, otherwise ``len(rows)``); when no
      table artifact exists it falls back to the first ``files[].row_count``.
    - ``column_count``: ``len(columns)`` of that same table artifact, else
      ``None``.

    Locale-neutral and guarded: a malformed ``payload_json`` yields
    ``([], None, None)`` instead of raising, so the list endpoint never 500s on
    bad data.
    """
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError):
        return ([], None, None)

    if not isinstance(payload, dict):
        return ([], None, None)

    files: list[str] = []
    first_file_row_count: int | None = None
    raw_files = payload.get("files")
    if isinstance(raw_files, list):
        for entry in raw_files:
            if not isinstance(entry, dict):
                continue
            filename = entry.get("filename")
            if isinstance(filename, str):
                files.append(filename)
            row_count = entry.get("row_count")
            if first_file_row_count is None and isinstance(row_count, int):
                first_file_row_count = row_count

    # The last table artifact in snapshot order is the final rendered result.
    table_artifact: dict[str, Any] | None = None
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            artifacts = message.get("artifacts")
            if not isinstance(artifacts, list):
                continue
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                if artifact.get("kind") != "table":
                    continue
                artifact_payload = artifact.get("payload")
                if isinstance(artifact_payload, dict):
                    table_artifact = artifact_payload

    row_count: int | None = None
    column_count: int | None = None
    if table_artifact is not None:
        total_rows = table_artifact.get("total_rows")
        rows = table_artifact.get("rows")
        if isinstance(total_rows, int):
            row_count = total_rows
        elif isinstance(rows, list):
            row_count = len(rows)
        columns = table_artifact.get("columns")
        if isinstance(columns, list):
            column_count = len(columns)
    else:
        row_count = first_file_row_count

    return (files, row_count, column_count)


def _load_payload(payload_json: str) -> dict[str, Any] | None:
    """Parse a stored snapshot payload without ever raising.

    A malformed (``TypeError``/``ValueError``) or non-dict ``payload_json``
    yields ``None`` so the create and detail responses never 500 on bad
    stored data.
    """
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _try_load_json(raw: Any) -> Any | None:
    """Parse a stored JSON string without ever raising.

    Used for message ``artifacts_json``, whose valid value is a list (so
    ``_load_payload``'s dict-only contract does not apply). Empty or malformed
    input degrades to ``None``; valid data is returned unchanged.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


# ── Validation ───────────────────────────────────────────────────────────────

def _validate_archive_name(name: str) -> str:
    """Trim and validate an archive name, raising 422 ``invalid_name``.

    Single source of truth for the create and rename paths: the name is
    trimmed, must be non-empty, and must fit ``ARCHIVE_NAME_MAX_LENGTH``.
    Returns the trimmed name.
    """
    name = name.strip()
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
    return name


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

    name = _validate_archive_name(body.name)

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
                "artifacts": _try_load_json(m.get("artifacts_json")),
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
                    f"({_ARCHIVE_PAYLOAD_MAX_MB} MB). No se guardó."
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
        payload=_load_payload(archive["payload_json"]),
        created_at=archive["created_at"],
    )


@router.get("", response_model=list[ArchiveListItem])
async def list_archives(
    limit: int = Query(50, ge=1, le=200),
    before: int | None = Query(None),
    after: int | None = Query(None),
    q: str | None = Query(None, max_length=200),
    order: Literal["newest", "oldest"] = Query("newest"),
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """List archives for the current user, with search and order.

    Cursor-based pagination mirroring the chat-history/files keyset contract:

    - ``order="newest"`` (default): ``before=<id>`` returns older archives
      (``id < before``), newest-first.
    - ``order="oldest"``: ``after=<id>`` returns newer archives
      (``id > after``), oldest-first.

    ``q`` is a case- and accent-insensitive name substring; blank queries are
    ignored. The cursor/order combination is validated (422 ``invalid_cursor``)
    so ``before`` is only valid for newest-first and ``after`` only for
    oldest-first. The response stays a bare list; the client infers ``hasMore``
    from ``len === limit``.
    """
    if before is not None and after is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_cursor",
                "message": "No se pueden usar los cursores 'before' y 'after' a la vez.",
            },
        )
    if before is not None and order == "oldest":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_cursor",
                "message": "El cursor 'before' solo es válido con el orden más reciente.",
            },
        )
    if after is not None and order == "newest":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_cursor",
                "message": "El cursor 'after' solo es válido con el orden más antiguo.",
            },
        )

    query_text = q.strip() if q is not None else None
    if not query_text:
        query_text = None

    archives = await store.list_archives(
        user["id"],
        limit=limit,
        before_id=before,
        after_id=after,
        query=query_text,
        newest_first=(order == "newest"),
    )
    items: list[ArchiveListItem] = []
    for a in archives:
        # Derive card metadata from the snapshot, then DISCARD the payload —
        # the list endpoint never returns it (only GET /{id} does).
        files, row_count, column_count = _derive_card_fields(a["payload_json"])
        items.append(
            ArchiveListItem(
                id=a["id"],
                name=a["name"],
                chat_session=a["chat_session"],
                created_at=a["created_at"],
                files=files,
                row_count=row_count,
                column_count=column_count,
            )
        )
    return items


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
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    return ArchiveDetail(
        id=archive["id"],
        name=archive["name"],
        chat_session=archive["chat_session"],
        payload=_load_payload(archive["payload_json"]),
        created_at=archive["created_at"],
    )


@router.patch("/{archive_id}", response_model=ArchiveListItem)
async def rename_archive(
    archive_id: int,
    body: RenameArchiveRequest,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Rename an archive owned by the current user.

    The name is validated with ``_validate_archive_name`` (422 on empty or
    over-long). Ownership is enforced by the store; a foreign or unknown id
    returns 404.
    """
    name = _validate_archive_name(body.name)
    archive = await store.rename_archive(archive_id, user["id"], name)
    if archive is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")

    files, row_count, column_count = _derive_card_fields(archive["payload_json"])
    return ArchiveListItem(
        id=archive["id"],
        name=archive["name"],
        chat_session=archive["chat_session"],
        created_at=archive["created_at"],
        files=files,
        row_count=row_count,
        column_count=column_count,
    )


@router.delete("/{archive_id}", status_code=204)
async def delete_archive(
    archive_id: int,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Delete an archive owned by the current user.

    Ownership is enforced by the store; a foreign or unknown id returns 404.
    """
    deleted = await store.delete_archive(archive_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")