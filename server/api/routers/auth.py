"""Authentication router: register, login, logout, me.

All endpoints are unauthenticated except ``/logout`` and ``/me``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from core.errors import DuplicateError
from server.api.deps import current_user, get_store
from server.services.auth_service import (
    build_expire_cookie_header,
    build_set_cookie_header,
    generate_raw_token,
    hash_password,
    hash_token,
    verify_password,
)
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response schemas ─────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    confirmation: str
    current_password: str


class UserResponse(BaseModel):
    id: int
    email: str
    # Scheduled purge deadline, or None. Exposed so login and /me can render the
    # grace-period interstitial (S7) without a second request.
    pending_deletion_at: str | None = None


class AuthSessionResponse(BaseModel):
    """One row of the active-sessions list (T2).

    ``user_agent`` is the truncated header captured when that session was
    opened; ``is_current`` marks the row the request came from. The token hash
    is deliberately absent from this schema, not just from the response.
    """

    id: int
    user_agent: str | None = None
    created_at: str
    last_seen_at: str
    is_current: bool


class ActiveSessionsResponse(BaseModel):
    sessions: list[AuthSessionResponse]
    # When another live session was created and the user has not acknowledged
    # it yet; the frontend uses it to raise the in-app notice once (D4/D9).
    new_session_at: str | None = None


# ── Helper ─────────────────────────────────────────────────────────────────────


async def _mint_session(
    store: SqliteStore,
    user_id: int,
    user_agent: str | None,
) -> tuple[str, str]:
    """Generate a raw token and create the corresponding auth session.

    ``user_agent`` is the request header, stored truncated (D2) so the sessions
    list can name the browser; no IP is stored anywhere.

    Returns (raw_token, set_cookie_header).
    """
    raw_token = generate_raw_token()
    token_hash = hash_token(raw_token)
    await store.create_auth_session(user_id, token_hash, user_agent=user_agent)
    cookie = build_set_cookie_header(raw_token)
    return raw_token, cookie


def _current_token_hash(request: Request) -> str:
    """Hash of the caller's own session cookie.

    ``current_user`` already rejected a request without a valid cookie, so the
    cookie is present here. Hashing it is what lets the store flag and protect
    the caller's own row without ever handling a raw token twice.
    """
    return hash_token(request.cookies["session_id"])


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/register", status_code=200)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
):
    """Register a new user.

    On success: creates user row, mints an auth session, sets the session
    cookie, and returns the user payload.

    On duplicate email: returns 409 Conflict.
    On invalid data: returns 422.
    """
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    pw_hash = hash_password(body.password)
    try:
        user = await store.create_user(body.email, pw_hash)
    except DuplicateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    raw_token, cookie = await _mint_session(
        store, user["id"], request.headers.get("user-agent")
    )
    response.headers["Set-Cookie"] = cookie
    return UserResponse(
        id=user["id"],
        email=user["email"],
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.post("/login", status_code=200)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
):
    """Log in with email and password.

    On success: verifies bcrypt hash, mints session, sets cookie, returns user.

    On failure: returns consistent 401 (same response for unknown email
    and wrong password).
    """
    user = await store.get_user_by_email(body.email)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    raw_token, cookie = await _mint_session(
        store, user["id"], request.headers.get("user-agent")
    )
    response.headers["Set-Cookie"] = cookie
    return UserResponse(
        id=user["id"],
        email=user["email"],
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Log out the current user.

    Deletes the auth session row and clears the session cookie.
    """
    raw_token: str | None = request.cookies.get("session_id")
    if raw_token:
        token_hash = hash_token(raw_token)
        await store.delete_auth_session(token_hash)
    response.headers["Set-Cookie"] = build_expire_cookie_header()
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.get("/me", status_code=200)
async def me(
    user: dict = Depends(current_user),
):
    """Return the current authenticated user."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.get("/sessions", status_code=200)
async def list_active_sessions(
    request: Request,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """List the caller's live sessions, most recent activity first.

    Only the caller's own sessions are listed, the row the request came from is
    flagged ``is_current`` (D3), and no token hash ever leaves the server.
    ``new_session_at`` carries the new-session notice when another live session
    was created and the user has not acknowledged it yet (D4/D9).
    """
    token_hash = _current_token_hash(request)
    sessions = await store.list_auth_sessions(user["id"], token_hash)
    return ActiveSessionsResponse(
        sessions=[
            AuthSessionResponse(
                id=row["id"],
                user_agent=row["user_agent"],
                created_at=row["created_at"],
                last_seen_at=row["last_seen_at"],
                is_current=row["is_current"],
            )
            for row in sessions
        ],
        new_session_at=await store.pending_new_session_at(user["id"], token_hash),
    )


@router.delete("/sessions", status_code=204)
async def close_other_sessions(
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Close every session of the user except the caller's own (D7).

    Idempotent: with no other sessions it is a no-op that still answers 204.
    """
    await store.delete_other_auth_sessions(user["id"], _current_token_hash(request))
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/sessions/notice-ack", status_code=204)
async def acknowledge_new_session_notice(
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Mark the new-session notice as seen (D4/D9).

    Idempotent, and never closes anything: acknowledging is not logging out.
    """
    await store.mark_sessions_notice_seen(user["id"], _current_token_hash(request))
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.delete("/sessions/{session_id}", status_code=204)
async def close_active_session(
    session_id: int,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Close one session of the caller (D5/D7).

    A session owned by somebody else answers 404, exactly like an id that does
    not exist, so the route can never confirm that a foreign session id is
    real. The caller's own session is refused with 409 (D3): that is what
    ``POST /api/auth/logout`` is for.
    """
    target = await store.get_auth_session_by_id(user["id"], session_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if target["token_hash"] == _current_token_hash(request):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot close the current session",
        )

    await store.delete_auth_session_row(user["id"], session_id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Change the authenticated user's password.

    Verifies the current password, rejects a new password shorter than 8
    characters, re-hashes and persists the new one, then deletes every other
    session of the user while keeping the caller's session alive.

    On wrong current password: 401.
    On short new password: 422.
    On success: 204.
    """
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    await store.update_user_password(user["id"], hash_password(body.new_password))

    raw_token: str | None = request.cookies.get("session_id")
    if raw_token:
        await store.delete_other_auth_sessions(user["id"], hash_token(raw_token))

    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/account/delete", status_code=204)
async def request_account_deletion(
    body: DeleteAccountRequest,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Schedule the authenticated account for deletion after a grace period.

    Authorization is the same as ``/password`` (S9/D4): the current password is
    verified first (401 on mismatch), and only then is the ``ELIMINAR``
    confirmation word validated (422). On success the purge deadline is written
    seven days out (D1), every session of the user is closed (D3), and the
    session cookie is cleared — the caller lands back on ``/login`` (S5). The
    account and its data are left untouched until the deadline passes (S3).
    """
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if body.confirmation != "ELIMINAR":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Type ELIMINAR to confirm",
        )

    await store.request_user_deletion(user["id"])
    await store.delete_all_auth_sessions(user["id"])
    response.headers["Set-Cookie"] = build_expire_cookie_header()
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/account/cancel-deletion", status_code=204)
async def cancel_account_deletion(
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Cancel a scheduled deletion so the account survives (S3).

    Idempotent: cancelling with no schedule is a no-op that still returns 204.
    """
    await store.cancel_user_deletion(user["id"])
    response.status_code = status.HTTP_204_NO_CONTENT
    return None