"""Authentication service: bcrypt hashing, session token generation,
and HTTP cookie building.

Token model (per design):
- Raw token: 32-byte URL-safe random (``secrets.token_urlsafe(32)``)
- Cookie carries the raw token
- DB stores only SHA-256(raw_token), unique indexed
- ``auth_sessions.id`` is internal bookkeeping, never shared
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash for *password*."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time comparison of *password* against *password_hash*.

    Uses ``hmac.compare_digest`` on the raw bcrypt hash output to
    provide timing-safe verification.
    """
    try:
        return hmac.compare_digest(
            bcrypt.hashpw(password.encode("utf-8"), password_hash.encode("utf-8")),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def generate_raw_token() -> str:
    """Return a 32-byte URL-safe random token (43 chars base64-encoded)."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of *raw_token*."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def build_set_cookie_header(
    raw_token: str,
    *,
    ttl_seconds: int = 28800,
    secure: bool = False,
    domain: str | None = None,
) -> str:
    """Build a ``Set-Cookie`` header value for the session cookie.

    Cookie name: ``session_id``
    Flags: HttpOnly, SameSite=Lax, Path=/
    Secure is OFF by default (local HTTP dev); set True in production.
    """
    parts = [
        f"session_id={raw_token}",
        "HttpOnly",
        "SameSite=Lax",
        "Path=/",
        f"Max-Age={ttl_seconds}",
    ]
    if secure:
        parts.append("Secure")
    if domain:
        parts.append(f"Domain={domain}")
    return "; ".join(parts)


def build_expire_cookie_header() -> str:
    """Build a ``Set-Cookie`` header that clears the session cookie."""
    return (
        "session_id=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
    )


def compute_session_ttl(ttl_seconds: int = 28800) -> str:
    """Return an ISO-8601 timestamp string ``now + ttl_seconds``."""
    return (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()