"""Chat context builder.

Builds the LLM context for a chat turn: profile JSON for files in the
session (ownership enforced via JOIN files, Decision #14) plus a sliding
window of the last N messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from server.services.profile_cache import get_profile
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

# Sliding window: default number of previous messages included in context
DEFAULT_MESSAGE_WINDOW = 20


def _serialize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Build a compact, LLM-friendly profile dict from the stored profile.

    Only schema + stats + a small sample are included (never the full
    dataset rows), per the spec's "Profile used in LLM context" scenario.
    """
    return {
        "columns": profile.get("schema_data", {}).get("columns", []),
        "stats": profile.get("stats", {}),
        "sample": profile.get("sample", [])[:5],
    }


async def _ensure_profile(
    store: SqliteStore,
    file_row: dict[str, Any],
    user_id: int,
) -> dict[str, Any] | None:
    """Return a file's profile, lazily re-profiling it from disk if missing.

    A file row can lack a profile row (legacy rows, or a failure before the
    atomic upload path existed). Instead of silently dropping it — which
    produced the false ``session/no_dataset`` — re-parse the stored file and
    cache its profile. Returns None only when the file cannot be read or
    profiling fails again.
    """
    profile = await get_profile(store, file_row["id"], user_id)
    if profile is not None:
        return profile

    path = file_row.get("storage_path")
    if not path or not os.path.exists(path):
        return None
    try:
        from core.data.parser import parse_upload, parse_upload_sheet  # noqa: PLC0415
        from core.data.profiler import build_profile  # noqa: PLC0415
        from server.services.profile_cache import save_profile  # noqa: PLC0415

        file_format = file_row.get("format")
        sheet_name = file_row.get("sheet_name")
        if file_format == "xlsx" and sheet_name:
            # Re-profile the file's ACTIVE sheet, not the first one: the
            # upload/lazy path must not silently analyze a different sheet
            # than the profile describes (F3).
            df, _meta = await asyncio.to_thread(
                parse_upload_sheet, path, sheet_name
            )
        else:
            df, _meta = await asyncio.to_thread(
                parse_upload, path, file_format
            )
        rebuilt = await asyncio.to_thread(
            build_profile, df, size_bytes=os.path.getsize(path)
        )
        await save_profile(store, file_row["id"], rebuilt)
        return await get_profile(store, file_row["id"], user_id)
    except Exception:
        logger.warning(
            "Lazy re-profile failed for file %s", file_row.get("id"), exc_info=True
        )
        return None


async def build_chat_context(
    store: SqliteStore,
    *,
    user_id: int,
    chat_session: str,
    message_window: int = DEFAULT_MESSAGE_WINDOW,
) -> dict[str, Any]:
    """Build the context object passed to the LLM.

    Args:
        store: The SQLite store.
        user_id: The current user id (ownership scoping).
        chat_session: The chat session id.
        message_window: How many prior messages to include.

    Returns:
        A dict with keys ``profiles`` (list), ``unprofiled_files`` (list)
        and ``messages`` (list of role/content dicts, oldest first).
    """
    # 1. Profile JSON for files in this session (ownership via JOIN files)
    profiles: list[dict[str, Any]] = []
    unprofiled_files: list[dict[str, Any]] = []
    files = await store.list_files(user_id, chat_session=chat_session)
    for f in files:
        profile = await _ensure_profile(store, f, user_id)
        if profile is not None:
            profiles.append(
                {
                    "file_id": f["id"],
                    "filename": f["filename"],
                    "format": f["format"],
                    # Absolute server-side path: the sandbox reads uploads
                    # by exact path (its cwd is a fresh temp dir).
                    "path": f["storage_path"],
                    # Authoritative dataset size, from the files table. The
                    # per-column profile stats (unique_count etc.) describe
                    # single columns and MUST NOT be read as dataset size —
                    # without this field the model once cited a column's
                    # unique_count as the row count.
                    "row_count": f.get("row_count"),
                    # Active sheet for XLSX; ``None`` for CSV/TSV/JSON. The
                    # system prompt uses this to tell the model to read the
                    # workbook with pd.read_excel(..., sheet_name=...).
                    "sheet_name": f.get("sheet_name"),
                    "profile": _serialize_profile(profile),
                }
            )
        else:
            unprofiled_files.append(
                {"file_id": f["id"], "filename": f["filename"], "format": f["format"]}
            )

    # 2. Sliding window of the last N messages (newest first from store)
    recent = await store.list_messages(
        user_id,
        chat_session,
        limit=message_window,
    )
    # Reverse to oldest-first for LLM context ordering
    recent.reverse()

    messages: list[dict[str, str]] = []
    for m in recent:
        role = m["role"]
        content = m["content_text"]
        # Prepend the assistant's code to its explanation for context
        if m.get("code"):
            content = f"{content}\n\n```python\n{m['code']}\n```"
        messages.append({"role": role, "content": content})

    return {
        "profiles": profiles,
        "unprofiled_files": unprofiled_files,
        "messages": messages,
    }
