"""Domain error taxonomy for Datara.

All exceptions used across core and server layers.
"""

from __future__ import annotations


class DataraError(Exception):
    """Base error for all Datara domain exceptions."""


# ── LLM errors ──────────────────────────────────────────────────────────────────


class LLMError(DataraError):
    """Base error for LLM provider failures."""


class LLMInvalidJSONError(LLMError):
    """Provider returned content that doesn't parse against the schema.

    Retry policy: one retry with same prompt; on second failure
    surface LLMError to the client.
    """


class LLMTimeoutError(LLMError):
    """LLM call exceeded the configured timeout.

    Retry policy: no retry; surface immediately.
    """


class LLMRateLimitError(LLMError):
    """Provider returned a rate-limit response.

    Retry policy: exponential backoff (2s, 4s, 8s), max 3 attempts.
    """


# ── Sandbox errors ──────────────────────────────────────────────────────────────


class SandboxError(DataraError):
    """Base error for sandbox execution failures."""


class SandboxTimeoutError(SandboxError):
    """Code execution exceeded the timeout limit."""


class SandboxMemoryError(SandboxError):
    """Code execution exceeded the memory limit."""


class SandboxSyntaxError(SandboxError):
    """Code contains invalid Python syntax."""


class SandboxImportError(SandboxError):
    """Code attempted to use a blocked import."""


class SandboxRuntimeError(SandboxError):
    """Code raised an unhandled runtime exception."""


# ── Auth errors ──────────────────────────────────────────────────────────────────


class AuthError(DataraError):
    """Base error for authentication/authorization failures."""


class AuthInvalidKeyError(AuthError, LLMError):
    """Provider rejected the API key (HTTP 401). No retry can help.

    Subclasses BOTH families (documented dual inheritance): AuthError was
    previously orphaned (defined, never raised) — extending it gives the
    auth family a live, semantic marker; LLMError keeps the existing
    ``except LLMError`` catch boundaries (chat router, bench classifier)
    catching provider auth failures with zero catch-site changes. MRO:
    AuthInvalidKeyError → AuthError → LLMError → DataraError → Exception
    (both bases derive from DataraError; no conflict).
    """


class AuthNoCreditsError(AuthError, LLMError):
    """Provider account is out of credits (HTTP 402).

    Same dual-family rationale as AuthInvalidKeyError: AuthError for the
    auth semantics, LLMError so existing ``except LLMError`` boundaries
    keep catching it.
    """


# ── Storage errors ──────────────────────────────────────────────────────────────


class StorageError(DataraError):
    """Base error for storage/database operations."""


class NotFoundError(StorageError):
    """Requested resource was not found."""


class DuplicateError(StorageError):
    """Resource already exists (e.g., duplicate email)."""