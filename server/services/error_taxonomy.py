"""Error taxonomy: single mapping source from internal errors to frontend codes.

Every terminal SSE ``error`` event in the chat flow carries a ``code`` from
this module. The taxonomy is the single contract between ``core/errors.py``
/ sandbox payload types and the UI; mapping tables must not be duplicated
elsewhere.

Normative code table (spec error-taxonomy + Enmienda 1):

    sandbox/runtime_error     runtime_error payload (incl. hard-crash)
    sandbox/syntax_error      syntax_error payload
    sandbox/import_error      blocked_import payload
    sandbox/memory            memory_limit_exceeded payload
    sandbox/timeout           timeout payload
    llm/invalid_json          LLMInvalidJSONError
    llm/timeout               LLMTimeoutError
    llm/rate_limit            LLMRateLimitError
    auth/invalid_key          provider HTTP 401 (AuthenticationError)
    auth/no_credits           provider HTTP 402 (Payment Required)
    model/not_allowed         422 detail {"code": "model_not_allowed"}
    internal/error            catch-all: the plain-LLMError empty-choices
                              path (llm_openai.py) and the defensive
                              ``except Exception`` in chat.py

    model/inadequate          RESERVED: registered for the frontend but
                              never emitted by any runtime path in this
                              change (model adequacy is decided at
                              configuration time via the bench; no emitter
                              exists).
    session/no_dataset        chat router no-dataset guard: the model
                              generated code but the session has no
                              attached files, so the sandbox is never
                              invoked (deterministic refusal, nothing
                              persisted).
"""

from __future__ import annotations

from core.errors import (
    AuthInvalidKeyError,
    AuthNoCreditsError,
    LLMError,
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMTimeoutError,
)

INTERNAL_ERROR_CODE = "internal/error"

# Emitted by the chat router when the model produces code for a session
# with no attached files. The no-dataset guard refuses to run the sandbox
# (and never repairs) instead of letting improvised code fail with a
# cryptic import/runtime error.
NO_DATASET_CODE = "session/no_dataset"

# Actual sandbox payload type (server/services/sandbox_local.py run_code
# docstring) → frontend taxonomy code.
SANDBOX_CODE_MAP: dict[str, str] = {
    "runtime_error": "sandbox/runtime_error",
    "syntax_error": "sandbox/syntax_error",
    "blocked_import": "sandbox/import_error",
    "memory_limit_exceeded": "sandbox/memory",
    "timeout": "sandbox/timeout",
}

# Most-specific-first dispatch table for llm_code(). Auth entries MUST be
# checked against plain LLMError before the fallback: the auth exceptions
# also inherit from LLMError, so ordering matters (see core/errors.py).
_LLM_CODE_MAP: tuple[tuple[type[Exception], str], ...] = (
    (LLMInvalidJSONError, "llm/invalid_json"),
    (LLMTimeoutError, "llm/timeout"),
    (LLMRateLimitError, "llm/rate_limit"),
    (AuthInvalidKeyError, "auth/invalid_key"),
    (AuthNoCreditsError, "auth/no_credits"),
)


def sandbox_code(payload_type: str) -> str:
    """Map a sandbox payload type to its taxonomy code.

    Unknown payload types degrade to ``sandbox/runtime_error`` so no
    terminal sandbox error goes out without a code.
    """
    return SANDBOX_CODE_MAP.get(payload_type, SANDBOX_CODE_MAP["runtime_error"])


def llm_code(exc: LLMError) -> str:
    """Map an LLM exception to its taxonomy code (MRO dispatch, specific first).

    Plain ``LLMError`` (e.g. the empty-choices path in llm_openai.py) and
    any unrecognized exception map to ``internal/error`` per spec
    Enmienda 1 — no terminal error is emitted without a code.
    """
    for cls, code in _LLM_CODE_MAP:
        if isinstance(exc, cls):
            return code
    return INTERNAL_ERROR_CODE
