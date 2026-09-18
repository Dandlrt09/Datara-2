"""Tests for OpenAIProvider with mocked AsyncOpenAI (no network calls).

Tests cover:
- Valid structured JSON response
- Invalid JSON → parse-feedback retry → LLMInvalidJSONError (bound
  independent of the rate-limit retry counter)
- Timeout → LLMTimeoutError
- 429 rate limit → backoff sequence → LLMRateLimitError
- 401 → AuthInvalidKeyError; 402 → AuthNoCreditsError; other API status
  errors → plain LLMError
- Plain LLMError (empty-choices path) → internal/error taxonomy code
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from core.errors import (
    AuthError,
    AuthInvalidKeyError,
    AuthNoCreditsError,
    LLMError,
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from core.protocols.llm_provider import LLMUsage
from server.services.error_taxonomy import INTERNAL_ERROR_CODE, llm_code
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

    async def test_markdown_fenced_json_is_parsed(self, provider):
        """Models intermittently wrap the JSON payload in ```json fences
        despite json_schema enforcement; the parser must tolerate it
        (rigor-mov2 live validation: B2-R / bench Q3 surfaced raw
        LLMInvalidJSONError to users)."""
        expected = {"code": "print('x')", "explanation": "ok"}
        fenced = f"```json\n{json.dumps(expected)}\n```"
        fake = _make_fake_response(fenced)
        with patch.object(provider._client.chat.completions, "create", AsyncMock(return_value=fake)):
            result = await provider.complete(
                messages=[{"role": "user", "content": "write code"}],
                response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
            )
        assert result.structured_data == expected

    async def test_bare_fenced_json_is_parsed(self, provider):
        """Fences without the language tag also parse."""
        expected = {"code": "", "explanation": "narrative only"}
        fenced = f"```\n{json.dumps(expected)}\n```"
        fake = _make_fake_response(fenced)
        with patch.object(provider._client.chat.completions, "create", AsyncMock(return_value=fake)):
            result = await provider.complete(
                messages=[{"role": "user", "content": "write code"}],
                response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
            )
        assert result.structured_data == expected


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

    async def test_auth_error_maps_to_llm_error(self, provider):
        """401 AuthenticationError maps to a clean LLMError (no retry)."""
        auth_error = openai.AuthenticationError(
            "Error code: 401 - Missing Authentication Header",
            response=MagicMock(),
            body={"error": {"message": "Missing Authentication Header", "code": 401}},
        )
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock:
            mock.side_effect = auth_error
            with pytest.raises(LLMError, match="Authentication failed"):
                await provider.complete(
                    messages=[{"role": "user", "content": "hello"}],
                )
        assert mock.call_count == 1, "Auth errors must not be retried"

    async def test_empty_choices_exhausted_raises_llm_error(self, provider):
        """Persistent empty choices must raise LLMError, not NameError.

        Regression: the final raise referenced LLMError without importing
        it, so the 3rd empty response crashed with NameError instead.
        """
        empty = _make_fake_response("")
        empty.choices = []
        mock = AsyncMock(return_value=empty)
        with patch.object(provider._client.chat.completions, "create", mock):
            # Skip the 2s+4s+8s backoff sleeps
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(LLMError, match="empty response"):
                    await provider.complete(
                        messages=[{"role": "user", "content": "hello"}],
                    )
        assert mock.call_count == 4  # initial + 3 retries

    async def test_empty_choices_maps_to_internal_error_code(self, provider):
        """Enmienda 1: plain LLMError from the empty-choices path maps to
        internal/error at the emission boundary (chat.py calls llm_code)."""
        assert (
            llm_code(LLMError("Provider returned an empty response"))
            == INTERNAL_ERROR_CODE
        )

    async def test_auth_error_maps_to_auth_invalid_key_error(self, provider):
        """401 AuthenticationError raises the typed auth exception.

        AuthInvalidKeyError subclasses AuthError AND LLMError, so existing
        ``except LLMError`` boundaries (and this module's tests) keep
        catching it.
        """
        auth_error = openai.AuthenticationError(
            "Error code: 401 - Missing Authentication Header",
            response=MagicMock(),
            body={"error": {"message": "Missing Authentication Header", "code": 401}},
        )
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock:
            mock.side_effect = auth_error
            with pytest.raises(AuthInvalidKeyError, match="Authentication failed") as exc_info:
                await provider.complete(
                    messages=[{"role": "user", "content": "hello"}],
                )
            assert isinstance(exc_info.value, AuthError)
            assert isinstance(exc_info.value, LLMError)
        assert mock.call_count == 1, "Auth errors must not be retried"

    async def test_402_maps_to_auth_no_credits_error(self, provider):
        """HTTP 402 (Payment Required) maps to AuthNoCreditsError by
        status-code inspection on the typed exception — no text parsing."""
        response = MagicMock()
        response.status_code = 402
        payment_error = openai.APIStatusError(
            "Payment required", response=response, body=None
        )
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock:
            mock.side_effect = payment_error
            with pytest.raises(AuthNoCreditsError, match="Payment required") as exc_info:
                await provider.complete(
                    messages=[{"role": "user", "content": "hello"}],
                )
            assert isinstance(exc_info.value, AuthError)
            assert isinstance(exc_info.value, LLMError)
        assert mock.call_count == 1, "Auth errors must not be retried"

    async def test_other_api_status_error_maps_to_llm_error(self, provider):
        """APIStatusError with a non-402 status raises plain LLMError."""
        response = MagicMock()
        response.status_code = 500
        status_error = openai.APIStatusError(
            "internal provider error", response=response, body=None
        )
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock:
            mock.side_effect = status_error
            with pytest.raises(LLMError, match="internal provider error") as exc_info:
                await provider.complete(
                    messages=[{"role": "user", "content": "hello"}],
                )
            assert not isinstance(exc_info.value, AuthError), (
                "Only 402 maps to the auth family; other statuses stay plain LLMError"
            )
        assert mock.call_count == 1, "Unexpected status errors must not be retried"

    async def test_stream_402_maps_to_auth_no_credits_error(self, provider):
        """402 during streaming maps to AuthNoCreditsError."""

        async def _fake_stream(**kwargs):
            response = MagicMock()
            response.status_code = 402
            raise openai.APIStatusError(
                "Payment required", response=response, body=None
            )
            yield  # pragma: no cover — makes this an async generator

        with patch.object(provider._client.chat.completions, "create", AsyncMock(side_effect=_fake_stream)):
            with pytest.raises(AuthNoCreditsError, match="Payment required"):
                chunks = []
                async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}]):
                    chunks.append(chunk)

    async def test_stream_other_api_status_error_maps_to_llm_error(self, provider):
        """Non-402 APIStatusError during streaming maps to plain LLMError."""

        async def _fake_stream(**kwargs):
            response = MagicMock()
            response.status_code = 503
            raise openai.APIStatusError(
                "upstream unavailable", response=response, body=None
            )
            yield  # pragma: no cover — makes this an async generator

        with patch.object(provider._client.chat.completions, "create", AsyncMock(side_effect=_fake_stream)):
            with pytest.raises(LLMError, match="upstream unavailable"):
                chunks = []
                async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}]):
                    chunks.append(chunk)

    async def test_stream_auth_error_maps_to_llm_error(self, provider):
        """401 during streaming maps to a clean LLMError."""

        async def _fake_stream(**kwargs):
            raise openai.AuthenticationError(
                "Error code: 401 - Missing Authentication Header",
                response=MagicMock(),
                body={},
            )
            yield  # pragma: no cover — makes this an async generator

        with patch.object(provider._client.chat.completions, "create", AsyncMock(side_effect=_fake_stream)):
            with pytest.raises(LLMError, match="Authentication failed"):
                chunks = []
                async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}]):
                    chunks.append(chunk)


# ── JSON retry with parse feedback ──────────────────────────────────────────


class TestJsonRetryFeedback:
    async def test_first_invalid_json_second_call_carries_feedback(self, provider):
        """1st invalid JSON → the 2nd call's messages include the parse-error
        feedback user message; the caller's message list is NOT mutated
        (copy-on-write)."""
        first = _make_fake_response("bad json {{{")
        second = _make_fake_response(json.dumps({"code": "x=1", "explanation": "ok"}))
        captured: list[dict] = []

        async def _side_effect(**kwargs):
            captured.append(kwargs)
            if _side_effect.calls == 0:
                _side_effect.calls += 1
                return first
            return second
        _side_effect.calls = 0

        msgs = [{"role": "user", "content": "write code"}]
        mock = AsyncMock(side_effect=_side_effect)
        with patch.object(provider._client.chat.completions, "create", mock):
            result = await provider.complete(
                messages=msgs,
                response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
            )
        assert result.structured_data == {"code": "x=1", "explanation": "ok"}
        assert len(captured) == 2

        # Original messages intact + exactly one feedback user message
        second_msgs = captured[1]["messages"]
        assert second_msgs[:-1] == [{"role": "user", "content": "write code"}]
        feedback = second_msgs[-1]
        assert feedback["role"] == "user"
        assert "not valid JSON" in feedback["content"]
        # Parse error detail (msg/lineno/colno) is referenced
        assert "Expecting value" in feedback["content"]
        assert "line 1" in feedback["content"] and "column 1" in feedback["content"]
        # The retry forbids fences and out-of-JSON text
        assert "code fences" in feedback["content"]

        # Copy-on-write: the caller's list is untouched
        assert msgs == [{"role": "user", "content": "write code"}]

    async def test_second_invalid_json_is_terminal(self, provider):
        """2nd invalid JSON raises LLMInvalidJSONError (bound = 2 total
        attempts for the JSON retry)."""
        bad = _make_fake_response("still not json {{{")

        async def _side_effect(**kwargs):
            return bad

        mock = AsyncMock(side_effect=_side_effect)
        with patch.object(provider._client.chat.completions, "create", mock):
            with pytest.raises(LLMInvalidJSONError, match="invalid JSON"):
                await provider.complete(
                    messages=[{"role": "user", "content": "write code"}],
                    response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
                )
        assert mock.call_count == 2, "Exactly one JSON retry (two total calls)"

    async def test_json_retry_bound_independent_of_rate_limit_retry(self, provider):
        """Regression for the latent shared-counter bug: a rate-limit retry
        on attempt 1 must NOT skip the JSON retry. The old code shared the
        `attempts` counter between both retry kinds, so rate-limit +
        invalid-JSON raised after only 2 calls; the dedicated
        `json_retried` flag makes the JSON bound independent."""
        rate_errors = [_make_rate_limit_error()]

        async def _side_effect(**kwargs):
            _side_effect.calls += 1
            if _side_effect.calls <= len(rate_errors):
                raise rate_errors[_side_effect.calls - 1]
            return _make_fake_response("invalid after rate limit {{{")
        _side_effect.calls = 0

        mock = AsyncMock(side_effect=_side_effect)
        with patch.object(provider._client.chat.completions, "create", mock):
            # Skip the 2s rate-limit backoff sleep
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(LLMInvalidJSONError, match="invalid JSON"):
                    await provider.complete(
                        messages=[{"role": "user", "content": "write code"}],
                        response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": {"type": "object"}}},
                    )
        # 3 calls: rate-limit fail (1), invalid JSON (2, retried), invalid
        # JSON again (3, terminal). The old shared counter would stop at 2.
        assert _side_effect.calls == 3


# ── Cost estimation ──────────────────────────────────────────────────────────


class TestCostEstimate:
    """Costs are published USD per 1M tokens, applied per-token.

    Regression: the map used to divide gpt-4o prices by 1_000 instead of
    1_000_000, inflating every persisted cost_usd by 1000x — plus a further
    6.25x for provider-prefixed slugs like "openai/gpt-4.1-mini", which were
    absent from the map and fell back to the pricier gpt-4o default.
    """

    def test_known_model(self):
        # 1000 * (2.50/1M) + 500 * (10.00/1M) = 0.0025 + 0.005
        cost = _estimate_cost(tokens_in=1000, tokens_out=500, model="gpt-4o-2024-08-06")
        assert cost == pytest.approx(0.0075, rel=1e-9)

    def test_unknown_model_fallback(self):
        cost = _estimate_cost(tokens_in=1000, tokens_out=500, model="unknown-model")
        # Falls back to gpt-4o pricing
        assert cost == pytest.approx(0.0075, rel=1e-9)

    def test_provider_prefixed_slug_uses_bare_id_rates(self):
        """OpenRouter-style slugs share the bare id's price instead of
        falling back to gpt-4o."""
        prefixed = _estimate_cost(tokens_in=3004, tokens_out=595, model="openai/gpt-4.1-mini")
        bare = _estimate_cost(tokens_in=3004, tokens_out=595, model="gpt-4.1-mini")
        assert prefixed == bare
        # 3004 * (0.40/1M) + 595 * (1.60/1M) = 0.0012016 + 0.000952
        assert prefixed == pytest.approx(0.0021536, rel=1e-9)

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