"""FastAPI dependencies for authentication and database access.

``current_user`` is the primary dependency — it reads the session cookie,
computes the token hash, looks up the session in SQLite, and returns
the authenticated user (or raises 401).
"""

from __future__ import annotations

from typing import Any

from fastapi import Cookie, Depends, HTTPException, Request, status

from server.api import store as api_store
from server.services.auth_service import hash_token
from server.services.sqlite_store import SqliteStore


async def get_store() -> SqliteStore:
    """Return the global SqliteStore instance.

    Set during app lifespan in ``server/api/main.py``.
    """
    s = api_store._store
    if s is None:
        raise HTTPException(status_code=503, detail="Database not ready")
    return s


async def current_user(
    request: Request,
    store: SqliteStore = Depends(get_store),
) -> dict[str, Any]:
    """Extract and validate the current user from the session cookie.

    Flow:
    1. Read ``session_id`` cookie
    2. SHA-256 the raw token
    3. SELECT user JOIN auth_sessions WHERE expires_at > now AND token_hash = ?
    4. Return user dict on success, raise 401 on failure

    Returns:
        User dict with keys ``id``, ``email``, ``password_hash``, ``created_at``.

    Raises:
        HTTPException(401) if the cookie is missing, expired, or invalid.
    """
    raw_token: str | None = request.cookies.get("session_id")
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token_hash = hash_token(raw_token)
    session = await store.get_auth_session_by_token_hash(token_hash)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )

    user = await store.get_user_by_id(session["user_id"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user