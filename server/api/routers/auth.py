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


class UserResponse(BaseModel):
    id: int
    email: str


# ── Helper ─────────────────────────────────────────────────────────────────────


async def _mint_session(
    store: SqliteStore,
    user_id: int,
) -> tuple[str, str]:
    """Generate a raw token and create the corresponding auth session.

    Returns (raw_token, set_cookie_header).
    """
    raw_token = generate_raw_token()
    token_hash = hash_token(raw_token)
    await store.create_auth_session(user_id, token_hash)
    cookie = build_set_cookie_header(raw_token)
    return raw_token, cookie


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/register", status_code=200)
async def register(
    body: RegisterRequest,
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

    raw_token, cookie = await _mint_session(store, user["id"])
    response.headers["Set-Cookie"] = cookie
    return UserResponse(id=user["id"], email=user["email"])


@router.post("/login", status_code=200)
async def login(
    body: LoginRequest,
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

    raw_token, cookie = await _mint_session(store, user["id"])
    response.headers["Set-Cookie"] = cookie
    return UserResponse(id=user["id"], email=user["email"])


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
    return UserResponse(id=user["id"], email=user["email"])