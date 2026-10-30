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
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt


# Longest accepted display name, measured after normalization (T1/D4).
MAX_DISPLAY_NAME_LENGTH = 50

# Email shape limits (S5). RFC 5322 caps a full address at 254 chars and a
# local part at 64; we keep the same ceilings rather than inventing our own.
MAX_EMAIL_LENGTH = 254
MAX_EMAIL_LOCAL_LENGTH = 64

# Conservative shape rule for a login identity (S5): one "@", a non-empty local
# part and a dotted domain, no whitespace. Deliberately not RFC 5322 -- the goal
# is to reject obvious garbage ("hola", "a@b", "a b@c.com") without becoming a
# false authority on which exotic-but-legal addresses must be refused.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_display_name(raw: str) -> str | None:
    """Collapse a raw display name into the shape the app stores (T1/D3).

    Leading and trailing whitespace is dropped and any inner whitespace run --
    newlines included -- becomes a single space, because the name is rendered on
    one line in the profile card and in the sidebar user block. A name that ends
    up empty returns ``None``. ``None`` (stored as SQL NULL) is only the initial
    state of an account that never chose a name; since T1/D3 was rewritten the
    profile edit route refuses blank input, so it is no longer reachable from
    the profile. Readers fall back to the name derived from the email.
    """
    collapsed = " ".join(raw.split())
    return collapsed or None


def normalize_email(raw: str) -> str:
    """Collapse a raw email into the login identity the app stores (S4/S5).

    Lowercased and trimmed, so the account identity does not depend on how the
    person typed it: ``Alice@Example.COM`` and ``alice@example.com`` are one
    account, not two. Only outer whitespace is removed; the local part is not
    otherwise rewritten (a plus-address or a dot stays as typed). The store
    applies this on write, which is what makes it impossible for a caller to
    bypass.
    """
    return raw.strip().lower()


def is_valid_email(raw: str) -> bool:
    """Return True when *raw* has the shape of an email address (S5).

    The caller passes the normalized value (``normalize_email``), so this only
    judges shape: length ceilings, a non-empty local part, and a dotted domain
    with no whitespace anywhere.
    """
    if len(raw) > MAX_EMAIL_LENGTH:
        return False
    local, separator, _domain = raw.partition("@")
    if not separator or len(local) > MAX_EMAIL_LOCAL_LENGTH:
        return False
    return _EMAIL_PATTERN.match(raw) is not None


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