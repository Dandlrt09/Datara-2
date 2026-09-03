"""Chat context builder.

Builds the LLM context for a chat turn: profile JSON for files in the
session (ownership enforced via JOIN files, Decision #14) plus a sliding
window of the last N messages.
"""

from __future__ import annotations

import json
import logging
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
        A dict with keys ``profiles`` (list) and ``messages`` (list of
        role/content dicts, oldest first).
    """
    # 1. Profile JSON for files in this session (ownership via JOIN files)
    profiles: list[dict[str, Any]] = []
    files = await store.list_files(user_id, chat_session=chat_session)
    for f in files:
        profile = await get_profile(store, f["id"], user_id)
        if profile is not None:
            profiles.append(
                {
                    "file_id": f["id"],
                    "filename": f["filename"],
                    "format": f["format"],
                    # Absolute server-side path: the sandbox reads uploads
                    # by exact path (its cwd is a fresh temp dir).
                    "path": f["storage_path"],
                    "profile": _serialize_profile(profile),
                }
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

    return {"profiles": profiles, "messages": messages}