"""ASGI body-size guard for the session file-upload endpoint.

WHY this exists
---------------
``POST /api/sessions/{session_id}/files`` is the only endpoint that accepts a
multipart body. FastAPI must resolve the ``file: UploadFile`` parameter — which
makes Starlette parse and spool the multipart body to a temp file — *before*
the handler body runs, and therefore *before* ``current_user`` solves auth. An
oversized body from an unauthenticated client would reach ``/tmp`` and only
then be answered with 401. The in-handler Content-Length check in
``server/api/routers/files.py`` runs too late to prevent that spooling.

This middleware runs *outside* Starlette's routing and body parsing, so it can
reject an oversized upload from the declared ``Content-Length`` before a single
byte is spooled. It is a pure ASGI middleware (not ``BaseHTTPMiddleware``)
because a user middleware sits outside Starlette's ``ExceptionMiddleware``: it
must RETURN a response, never raise ``HTTPException``.
"""

from __future__ import annotations

import re

from starlette.responses import JSONResponse

from server.limits import get_limits

# Slack allowed over max_upload_bytes when interpreting Content-Length.
# Multipart bodies carry boundaries and part headers, so the raw body is
# slightly larger than the file: a 1 MB margin guarantees a file exactly at
# the cap is never falsely rejected. This is the single source of the slack;
# the route imports it so the two guard paths cannot drift.
CONTENT_LENGTH_MARGIN = 1024 * 1024

# Only the session file-upload route is guarded.
_UPLOAD_PATH_RE = re.compile(r"^/api/sessions/[^/]+/files/?$")

MISSING_LENGTH_DETAIL = (
    "Length Required: the upload route requires a Content-Length header."
)
MALFORMED_LENGTH_DETAIL = "Invalid Content-Length header."

# Distinguish "header absent" from a parsed integer without overloading None.
_MISSING = object()
_MALFORMED = object()


def oversize_upload_detail(declared_bytes: int, max_bytes: int) -> str:
    """Shared 413 detail for an over-cap declared body size.

    The middleware and the in-handler fallback both build their message here
    so the two paths can never drift apart.
    """
    return (
        f"File too large: request body of {declared_bytes} bytes exceeds "
        f"the {max_bytes}-byte per-file limit."
    )


async def _reply(
    status_code: int, detail: str, scope, receive, send
) -> None:
    """Send a JSON ``{"detail": ...}`` response, matching the route envelope."""
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    await response(scope, receive, send)


class UploadSizeGuard:
    """Reject oversized uploads from Content-Length before body parsing."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _applies(scope) -> bool:
        return (
            scope.get("type") == "http"
            and scope.get("method", "").upper() == "POST"
            and bool(_UPLOAD_PATH_RE.match(scope.get("path", "")))
        )

    @staticmethod
    def _declared_length(scope):
        """Return the declared length, or the ``_MISSING``/``_MALFORMED`` marker."""
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    text = value.decode("latin-1").strip()
                except UnicodeDecodeError:
                    return _MALFORMED
                if not text.isdigit():
                    return _MALFORMED
                return int(text)
        return _MISSING

    async def __call__(self, scope, receive, send) -> None:
        if not self._applies(scope):
            await self.app(scope, receive, send)
            return

        declared = self._declared_length(scope)
        if declared is _MISSING:
            # No Content-Length means the size cannot be bounded before
            # parsing; the upload route always requires one.
            await _reply(411, MISSING_LENGTH_DETAIL, scope, receive, send)
            return
        if declared is _MALFORMED:
            await _reply(400, MALFORMED_LENGTH_DETAIL, scope, receive, send)
            return

        # Read limits per-request: get_limits() resolves the environment at
        # call time, so tests and operators can change the cap without a
        # restart.
        limits = get_limits()
        if declared > limits.max_upload_bytes + CONTENT_LENGTH_MARGIN:
            await _reply(
                413,
                oversize_upload_detail(declared, limits.max_upload_bytes),
                scope,
                receive,
                send,
            )
            return

        await self.app(scope, receive, send)


def install_upload_guard(app) -> None:
    """Register the body-size guard on ``app``.

    Call this BEFORE adding CORSMiddleware: Starlette's most-recently-added
    middleware is the outermost, so registering the guard first leaves CORS
    outermost and its headers still apply to the guard's 413/411 responses.
    """
    app.add_middleware(UploadSizeGuard)
