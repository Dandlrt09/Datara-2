"""Tests for Datara error taxonomy."""

from core.errors import (
    AuthError,
    AuthInvalidKeyError,
    AuthNoCreditsError,
    DataraError,
    DuplicateError,
    LLMError,
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMTimeoutError,
    NotFoundError,
    SandboxError,
    SandboxImportError,
    SandboxMemoryError,
    SandboxRuntimeError,
    SandboxSyntaxError,
    SandboxTimeoutError,
    StorageError,
)


class TestBaseError:
    def test_datara_error_base(self):
        e = DataraError("something went wrong")
        assert str(e) == "something went wrong"
        assert isinstance(e, Exception)

    def test_hierarchy(self):
        """Verify all errors inherit from DataraError."""
        assert issubclass(LLMError, DataraError)
        assert issubclass(SandboxError, DataraError)
        assert issubclass(AuthError, DataraError)
        assert issubclass(StorageError, DataraError)


class TestLLMErrors:
    def test_invalid_json(self):
        e = LLMInvalidJSONError("bad json")
        assert isinstance(e, LLMError)

    def test_timeout(self):
        e = LLMTimeoutError("timed out")
        assert isinstance(e, LLMError)

    def test_rate_limit(self):
        e = LLMRateLimitError("too many requests")
        assert isinstance(e, LLMError)


class TestSandboxErrors:
    def test_timeout(self):
        e = SandboxTimeoutError("exceeded 30s")
        assert isinstance(e, SandboxError)

    def test_memory(self):
        e = SandboxMemoryError("exceeded 512MB")
        assert isinstance(e, SandboxError)

    def test_syntax(self):
        e = SandboxSyntaxError("invalid syntax at line 1")
        assert isinstance(e, SandboxError)

    def test_import_blocked(self):
        e = SandboxImportError("os is not allowed")
        assert isinstance(e, SandboxError)

    def test_runtime(self):
        e = SandboxRuntimeError("ZeroDivisionError")
        assert isinstance(e, SandboxError)


class TestAuthErrors:
    def test_invalid_key_is_both_families(self):
        """AuthInvalidKeyError extends the orphan AuthError AND keeps the
        ``except LLMError`` catch boundary working (REQ-3)."""
        e = AuthInvalidKeyError("401")
        assert isinstance(e, AuthError)
        assert isinstance(e, LLMError)
        assert isinstance(e, DataraError)

    def test_no_credits_is_both_families(self):
        e = AuthNoCreditsError("402")
        assert isinstance(e, AuthError)
        assert isinstance(e, LLMError)
        assert isinstance(e, DataraError)

    def test_mro_orders_auth_before_llm(self):
        """MRO: AuthInvalidKeyError → AuthError → LLMError → DataraError —
        the auth family is checked first, no bases conflict."""
        mro = [c.__name__ for c in AuthInvalidKeyError.__mro__]
        assert mro.index("AuthError") < mro.index("LLMError")
        assert mro.index("LLMError") < mro.index("DataraError")


class TestStorageErrors:
    def test_not_found(self):
        e = NotFoundError("resource not found")
        assert isinstance(e, StorageError)

    def test_duplicate(self):
        e = DuplicateError("email already exists")
        assert isinstance(e, StorageError)

    def test_not_found_not_sandbox(self):
        """NotFoundError is a storage error, not a sandbox error."""
        e = NotFoundError("x")
        assert not isinstance(e, SandboxError)
        assert not isinstance(e, LLMError)