"""Origin/Referer CSRF guard for state-changing API requests (F9/S2).

WHY this exists
---------------
The session is a cookie. Any page the browser visits can make it fire a
cross-origin request at Datara -- a simple form POST needs no CORS preflight --
so a state-changing call would run with the victim's cookie. Browsers send an
``Origin`` header on every non-GET request and a page cannot forge it, so the
guard refuses a state-changing ``/api/*`` request whose ``Origin`` (or its
``Referer`` fallback) is not one of ours. This also covers the desktop build's
``http://localhost:<port>``, which any page in the same browser can reach.

A request with neither header is allowed: only non-browser clients (curl,
tests, servers) omit both, and they are not the cookie-theft threat. A present
but unparseable or non-trusted value is refused (``Origin: null`` included).

Pure ASGI (not ``BaseHTTPMiddleware``): a user middleware sits outside
Starlette's ``ExceptionMiddleware`` and must RETURN a response, never raise.
Register it BEFORE ``CORSMiddleware`` so CORS stays outermost and its headers
still apply to the guard's 403.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

# Methods that change state and therefore need CSRF protection.
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Origins always trusted: the Vite dev server and the port the app serves the
# built SPA from. main.py builds its CORS list from this same tuple so the two
# cannot drift.
DEVELOPMENT_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)

CSRF_ORIGIN_DETAIL = (
    "Cross-origin request rejected: the Origin/Referer is not an allowed "
    "Datara origin."
)


def _origin_of(url: str) -> str | None:
    """Return the ``scheme://host[:port]`` origin of *url*, or None if unusable.

    None covers everything that is not a trustworthy origin claim: an empty or
    opaque value (``null``), a missing scheme/host, or a ``file:`` URL.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def allowed_origins() -> frozenset[str]:
    """Resolve the trusted origins, reading the environment per call.

    ``DATARA_APP_URL`` is the deployed URL (the desktop build publishes its
    bound port there); ``DATARA_ALLOWED_ORIGINS`` is a comma-separated extra
    list for a hosted frontend on a different origin.
    """
    origins = set(DEVELOPMENT_ORIGINS)
    app_origin = _origin_of(os.environ.get("DATARA_APP_URL", "").strip())
    if app_origin:
        origins.add(app_origin)
    for item in os.environ.get("DATARA_ALLOWED_ORIGINS", "").split(","):
        origin = _origin_of(item.strip())
        if origin:
            origins.add(origin)
    return frozenset(origins)


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            try:
                return value.decode("latin-1").strip()
            except UnicodeDecodeError:
                return None
    return None


def origin_is_trusted(scope) -> bool:
    """True when the request claims no origin, or claims a trusted one.

    Prefers ``Origin``; falls back to the origin part of ``Referer`` (older
    browsers and some same-origin navigations omit ``Origin``). A header that
    is present but not a trusted origin is untrusted.
    """
    origin = _header(scope, b"origin")
    if origin is not None:
        return _origin_of(origin) in allowed_origins()
    referer = _header(scope, b"referer")
    if referer is not None:
        return _origin_of(referer) in allowed_origins()
    return True


class CsrfOriginGuard:
    """Refuse a state-changing ``/api/*`` request from an untrusted origin."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _applies(scope) -> bool:
        return (
            scope.get("type") == "http"
            and scope.get("method", "").upper() in STATE_CHANGING_METHODS
            and scope.get("path", "").startswith("/api/")
        )

    async def __call__(self, scope, receive, send) -> None:
        if not self._applies(scope) or origin_is_trusted(scope):
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            status_code=403, content={"detail": CSRF_ORIGIN_DETAIL}
        )
        await response(scope, receive, send)


def install_csrf_origin_guard(app) -> None:
    """Register the guard on ``app``.

    Call this BEFORE adding ``CORSMiddleware``: Starlette's most-recently-added
    middleware is the outermost, so registering the guard first leaves CORS
    outermost and its headers still apply to the guard's 403.
    """
    app.add_middleware(CsrfOriginGuard)
