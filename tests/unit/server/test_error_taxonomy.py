"""Unit tests for the error taxonomy mapping module.

Verifies the normative mapping (spec error-taxonomy + Enmienda 1):
5 sandbox payload types → codes, LLM exception classes → codes via MRO
dispatch, plain LLMError → internal/error, and the reserved code
model/inadequate is never emitted by any mapper.
"""

from __future__ import annotations

import pytest

from core.errors import (
    AuthInvalidKeyError,
    AuthNoCreditsError,
    LLMError,
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from server.services.error_taxonomy import (
    INTERNAL_ERROR_CODE,
    SANDBOX_CODE_MAP,
    llm_code,
    sandbox_code,
)


class TestSandboxCode:
    @pytest.mark.parametrize(
        ("payload_type", "expected"),
        [
            ("runtime_error", "sandbox/runtime_error"),
            ("syntax_error", "sandbox/syntax_error"),
            ("blocked_import", "sandbox/import_error"),
            ("memory_limit_exceeded", "sandbox/memory"),
            ("timeout", "sandbox/timeout"),
        ],
    )
    def test_known_payload_types(self, payload_type, expected):
        assert sandbox_code(payload_type) == expected

    def test_unknown_payload_type_degrades_to_runtime_error(self):
        """Unknown payload types still carry a code (REQ-1: no terminal
        error without one)."""
        assert sandbox_code("some_future_type") == "sandbox/runtime_error"

    def test_normative_table_has_exactly_five_entries(self):
        assert set(SANDBOX_CODE_MAP) == {
            "runtime_error",
            "syntax_error",
            "blocked_import",
            "memory_limit_exceeded",
            "timeout",
        }


class TestLLMCode:
    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            (LLMInvalidJSONError("bad json"), "llm/invalid_json"),
            (LLMTimeoutError("timed out"), "llm/timeout"),
            (LLMRateLimitError("429"), "llm/rate_limit"),
        ],
    )
    def test_specific_llm_classes(self, exc, expected):
        assert llm_code(exc) == expected

    def test_auth_invalid_key(self):
        """Auth subclasses must map before the plain-LLMError fallback
        even though they also inherit from LLMError."""
        assert llm_code(AuthInvalidKeyError("401")) == "auth/invalid_key"

    def test_auth_no_credits(self):
        assert llm_code(AuthNoCreditsError("402")) == "auth/no_credits"

    def test_plain_llm_error_maps_to_internal_error(self):
        """Enmienda 1: the empty-choices path raises plain LLMError and
        maps to internal/error at the emission boundary."""
        assert llm_code(LLMError("empty response")) == INTERNAL_ERROR_CODE

    def test_internal_error_code_value(self):
        assert INTERNAL_ERROR_CODE == "internal/error"


class TestReservedCode:
    def test_model_inadequate_is_never_emitted(self):
        """model/inadequate is reserved: no runtime mapper may produce it."""
        assert "model/inadequate" not in SANDBOX_CODE_MAP.values()
        for payload_type in SANDBOX_CODE_MAP:
            assert sandbox_code(payload_type) != "model/inadequate"
        for exc in (
            LLMError("x"),
            LLMInvalidJSONError("x"),
            LLMTimeoutError("x"),
            LLMRateLimitError("x"),
            AuthInvalidKeyError("x"),
            AuthNoCreditsError("x"),
        ):
            assert llm_code(exc) != "model/inadequate"
