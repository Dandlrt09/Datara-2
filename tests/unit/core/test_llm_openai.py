"""Tests for OpenAIProvider with mocked AsyncOpenAI (no network calls).

Tests cover:
- Valid structured JSON response
- Invalid JSON → exactly one retry → LLMInvalidJSONError
- Timeout → LLMTimeoutError
- 429 rate limit → backoff sequence → LLMRateLimitError
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from core.errors import LLMInvalidJSONError, LLMRateLimitError, LLMTimeoutError
from core.protocols.llm_provider import LLMUsage
from server.services.llm_openai import OpenAIProvider, _estimate_cost


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_fake_response(
    content: str,
    model: str = "gpt-4o-2024-08-06",
    *,
    finish_reason: str = "stop",
    prompt_tokens: int = 50,
    completion_tokens: int = 100,
) -> MagicMock:
    """Build a mock OpenAI chat completion response.

    This constructs an object with the same attribute shape as
    openai.types.chat.ChatCompletion so the provider can read
    response.choices[0].message.content, response.usage, etc.
    """
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = model
    response.to_dict = MagicMock(return_value={"id": "fake"})
    return response


@pytest.fixture
def provider():
    """Create an OpenAIProvider with a dummy key (never called)."""
    return OpenAIProvider(api_key="sk-test-fake-key", model="gpt-4o-2024-08-06")


def _make_rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        "rate limited",
        response=MagicMock(),
        body={"error": {"message": "rate limited"}},
    )


# ── Valid structured response ────────────────────────────────────────────────


class TestValidResponse:
    async def test_valid_structured_json(self, provider):
        """A well-formed JSON schema response is parsed correctly."""
        expected = {"code": "import pandas as pd\ndf = pd.DataFrame()", "explanation": "This code creates a DataFrame"}
        fake = _make_fake_response(json.dumps(expected))
        with patch.object(provider._client.chat.completions, "create", AsyncMock(return_value=fake)):
            result = await provider.complete(
                messages=[{"role": "user", "content": "write code"}],
                response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
            )
        assert result.text == json.dumps(expected)
        assert result.structured_data == expected
        assert result.model == "gpt-4o-2024-08-06"
        assert result.provider == "openai"
        assert isinstance(result.usage, LLMUsage)
        assert result.usage.tokens_in == 50
        assert result.usage.tokens_out == 100

    async def test_no_response_format(self, provider):
        """Without response_format, structured_data is None."""
        fake = _make_fake_response("plain text response")
        with patch.object(provider._client.chat.completions, "create", AsyncMock(return_value=fake)):
            result = await provider.complete(
                messages=[{"role": "user", "content": "hi"}],
            )
        assert result.text == "plain text response"
        assert result.structured_data is None


# ── Error handling ───────────────────────────────────────────────────────────


class TestErrorHandling:
    async def test_invalid_json_one_retry(self, provider):
        """Invalid JSON should trigger exactly one retry, then raise LLMInvalidJSONError.

        Uses a list side_effect to control mock return values across calls.
        """
        bad_response = _make_fake_response("this is not json {{{")
        calls = [0]

        async def _side_effect(**kwargs):
            calls[0] += 1
            return bad_response

        mock = AsyncMock(side_effect=_side_effect)
        with patch.object(provider._client.chat.completions, "create", mock):
            with pytest.raises(LLMInvalidJSONError, match="invalid JSON"):
                await provider.complete(
                    messages=[{"role": "user", "content": "write code"}],
                    response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
                )
        # Exactly one retry (two total calls)
        assert calls[0] == 2, f"Expected 2 calls, got {calls[0]}"

    async def test_invalid_json_then_valid(self, provider):
        """Invalid JSON on first call, valid on retry."""
        first = _make_fake_response("bad json {{{")
        second = _make_fake_response(json.dumps({"code": "x=1", "explanation": "ok"}))

        async def _side_effect(**kwargs):
            if _side_effect.calls == 0:
                _side_effect.calls += 1
                return first
            return second
        _side_effect.calls = 0

        mock = AsyncMock(side_effect=_side_effect)
        with patch.object(provider._client.chat.completions, "create", mock):
            result = await provider.complete(
                messages=[{"role": "user", "content": "write code"}],
                response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
            )
        assert result.structured_data == {"code": "x=1", "explanation": "ok"}

    async def test_timeout(self, provider):
        """API timeout should raise LLMTimeoutError."""
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock:
            mock.side_effect = openai.APITimeoutError("timeout")
            with pytest.raises(LLMTimeoutError, match="timed out"):
                await provider.complete(
                    messages=[{"role": "user", "content": "hello"}],
                )

    async def test_async_timeout(self, provider):
        """asyncio.TimeoutError should also raise LLMTimeoutError."""
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock:
            mock.side_effect = asyncio.TimeoutError()
            with pytest.raises(LLMTimeoutError, match="timed out"):
                await provider.complete(
                    messages=[{"role": "user", "content": "hello"}],
                )

    async def test_rate_limit_backoff(self, provider):
        """429 rate limit should backoff and retry, then succeed."""
        success = _make_fake_response(json.dumps({"code": "x=1", "explanation": "y"}))
        rate_errors = [_make_rate_limit_error()] * 3

        async def _side_effect(**kwargs):
            idx = _side_effect.idx
            _side_effect.idx += 1
            if idx < len(rate_errors):
                raise rate_errors[idx]
            return success
        _side_effect.idx = 0

        mock = AsyncMock(side_effect=_side_effect)
        with patch.object(provider._client.chat.completions, "create", mock):
            result = await provider.complete(
                messages=[{"role": "user", "content": "write code"}],
                response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
            )
        assert _side_effect.idx == 4, f"Expected 4 calls, got {_side_effect.idx}"
        assert result.structured_data == {"code": "x=1", "explanation": "y"}

    async def test_rate_limit_exhausted(self, provider):
        """If rate-limit errors continue, should raise LLMRateLimitError after retries."""

        async def _side_effect(**kwargs):
            raise _make_rate_limit_error()

        mock = AsyncMock(side_effect=_side_effect)
        with patch.object(provider._client.chat.completions, "create", mock):
            with pytest.raises(LLMRateLimitError, match="Rate-limited"):
                await provider.complete(
                    messages=[{"role": "user", "content": "write code"}],
                )


# ── Cost estimation ──────────────────────────────────────────────────────────


class TestCostEstimate:
    def test_known_model(self):
        cost = _estimate_cost(tokens_in=1000, tokens_out=500, model="gpt-4o-2024-08-06")
        assert cost == pytest.approx(2.50 + 5.00, abs=0.01)

    def test_unknown_model_fallback(self):
        cost = _estimate_cost(tokens_in=1000, tokens_out=500, model="unknown-model")
        # Falls back to gpt-4o pricing
        assert cost == pytest.approx(2.50 + 5.00, abs=0.01)

    def test_zero_tokens(self):
        cost = _estimate_cost(tokens_in=0, tokens_out=0, model="gpt-4o")
        assert cost == 0.0


# ── Seed kwarg passthrough ──────────────────────────────────────────────────


class TestSeedKwarg:
    async def test_complete_forwards_seed(self, provider):
        """When seed is provided, it is forwarded to the API call."""
        fake = _make_fake_response("ok")
        mock = AsyncMock(return_value=fake)
        with patch.object(provider._client.chat.completions, "create", mock):
            await provider.complete(
                messages=[{"role": "user", "content": "hi"}],
                seed=42,
            )
        assert mock.call_args.kwargs["seed"] == 42

    async def test_complete_omits_seed_by_default(self, provider):
        """Without seed, the API call carries no seed key (backwards compat)."""
        fake = _make_fake_response("ok")
        mock = AsyncMock(return_value=fake)
        with patch.object(provider._client.chat.completions, "create", mock):
            await provider.complete(
                messages=[{"role": "user", "content": "hi"}],
            )
        assert "seed" not in mock.call_args.kwargs

    async def test_stream_forwards_seed(self, provider):
        """When seed is provided to stream(), it is forwarded to the API call."""

        async def _fake_stream(**kwargs):
            choice = MagicMock()
            choice.delta = MagicMock()
            choice.delta.content = "x"
            yield MagicMock(choices=[choice])

        mock = AsyncMock(side_effect=_fake_stream)
        with patch.object(provider._client.chat.completions, "create", mock):
            _ = [chunk async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}], seed=7)]
        assert mock.call_args.kwargs["seed"] == 7


# ── Stream method ────────────────────────────────────────────────────────────


class TestStream:
    async def test_stream_yields_text_deltas(self, provider):
        """Stream should yield text deltas from completion chunks."""

        async def _fake_stream(**kwargs):
            for text in ["Hello", " ", "world"]:
                choice = MagicMock()
                choice.delta = MagicMock()
                choice.delta.content = text
                yield MagicMock(choices=[choice])

        mock = AsyncMock(side_effect=_fake_stream)
        with patch.object(provider._client.chat.completions, "create", mock):
            deltas = [chunk async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}])]
        assert deltas == ["Hello", " ", "world"]

    async def test_stream_empty_delta(self, provider):
        """Chunks with empty content should be skipped."""

        async def _fake_stream(**kwargs):
            choice = MagicMock()
            choice.delta = MagicMock()
            choice.delta.content = None
            yield MagicMock(choices=[choice])
            choice2 = MagicMock()
            choice2.delta = MagicMock()
            choice2.delta.content = "hello"
            yield MagicMock(choices=[choice2])

        mock = AsyncMock(side_effect=_fake_stream)
        with patch.object(provider._client.chat.completions, "create", mock):
            deltas = [chunk async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}])]
        assert deltas == ["hello"]