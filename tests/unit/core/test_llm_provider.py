"""Tests for LLM provider protocol and types."""

from core.protocols.llm_provider import LLMProvider, LLMResponse, LLMUsage


class TestLLMUsage:
    def test_defaults(self):
        u = LLMUsage()
        assert u.tokens_in == 0
        assert u.tokens_out == 0
        assert u.cost_usd == 0.0

    def test_frozen(self):
        u = LLMUsage(tokens_in=10, tokens_out=20, cost_usd=0.001)
        assert u.tokens_in == 10
        assert u.tokens_out == 20
        assert u.cost_usd == 0.001
        try:
            u.tokens_in = 99
            assert False, "should be frozen"
        except AttributeError:
            pass


class TestLLMResponse:
    def test_minimal(self):
        r = LLMResponse(text="Hello")
        assert r.text == "Hello"
        assert r.structured_data is None
        assert r.model == ""

    def test_full(self):
        r = LLMResponse(
            text="Result",
            structured_data={"key": "value"},
            model="gpt-4o",
            provider="openai",
            usage=LLMUsage(tokens_in=10, tokens_out=20, cost_usd=0.001),
        )
        assert r.structured_data == {"key": "value"}
        assert r.model == "gpt-4o"


class TestLLMProviderProtocol:
    """Verify LLMProvider is a proper Protocol without tools param."""

    def test_is_protocol(self):
        import inspect
        assert inspect.isclass(LLMProvider)
        # Should be a Protocol per runtime_checkable
        assert hasattr(LLMProvider, "__protocol__") or hasattr(LLMProvider, "_is_protocol")

    def test_complete_signature(self):
        import inspect
        sig = inspect.signature(LLMProvider.complete)
        params = list(sig.parameters.keys())
        # Must NOT have 'tools' in the signature
        assert 'tools' not in params, "tools param must NOT be in v1 LLMProvider protocol"
        # Must have messages, response_format, max_tokens, temperature
        assert 'messages' in params
        assert 'response_format' in params
        assert 'max_tokens' in params
        assert 'temperature' in params

    def test_stream_signature(self):
        import inspect
        sig = inspect.signature(LLMProvider.stream)
        params = list(sig.parameters.keys())
        assert 'tools' not in params, "tools param must NOT be in v1 stream signature"