"""OpenAI LLM provider implementation.

Implements the ``LLMProvider`` protocol using ``openai.AsyncOpenAI``.
Handles structured output via ``response_format=json_schema``, error
mapping to the ``core/errors.py`` taxonomy, and retry policies per
design decisions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator

import openai
from openai import AsyncOpenAI

from core.errors import (
    AuthInvalidKeyError,
    AuthNoCreditsError,
    LLMError,
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from core.protocols.llm_provider import LLMProvider, LLMResponse, LLMUsage

logger = logging.getLogger(__name__)

# Some models escape json_schema enforcement intermittently and wrap the
# payload in markdown fences (```json ... ```). Parse must tolerate it —
# the retry policy alone surfaced a raw LLMInvalidJSONError to users
# (Rigor mov-2 live validation, B2-R / bench Q3).
_JSON_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", re.DOTALL)


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences around a JSON payload, if present."""
    t = text.strip()
    match = _JSON_FENCE_RE.match(t)
    return match.group(1).strip() if match else t

# Default timeout for the LLM call (seconds). Non-streamed json_schema
# responses on routed backends (e.g. OpenRouter) can be slow; configurable
# via OPENAI_TIMEOUT in the environment / .env.
_DEFAULT_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "120.0"))

# Rate-limit backoff schedule (seconds)
_RETRY_BACKOFFS = [2.0, 4.0, 8.0]

# Feedback appended as a user message when the provider's json_schema
# payload fails to parse (automatic-repair: "JSON repair with feedback,
# bounded"). English: it is LLM-directed prompt content, not UI copy.
# The 2-total-attempt bound is enforced by a dedicated json_retried flag,
# independent of the rate-limit retry counter (the old shared counter let
# a rate-limit retry on attempt 1 skip the JSON retry entirely).
_JSON_RETRY_FEEDBACK = (
    "Your previous response was not valid JSON and could not be parsed "
    "(error: {msg} at line {lineno}, column {colno}). "
    "Respond again with a single valid JSON object that matches the "
    "required schema. Do not wrap it in Markdown code fences and do not "
    "add any text outside the JSON."
)


class OpenAIProvider:
    """OpenAI LLM provider.

    Wraps ``openai.AsyncOpenAI`` to produce structured responses.

    Args:
        api_key: OpenAI API key. If ``None``, falls back to the
            ``OPENAI_API_KEY`` environment variable.
        model: Model name (default: ``gpt-4o-2024-08-06``).
        timeout: Request timeout in seconds (default: 60).
        base_url: Custom base URL. If ``None``, falls back to the
            ``OPENAI_BASE_URL`` environment variable, then OpenAI default.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-2024-08-06",
        timeout: float = _DEFAULT_TIMEOUT,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout, base_url=base_url)

    # ── LLMProvider protocol ─────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        *,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> LLMResponse:
        """Send a non-streaming request to OpenAI with optional JSON schema.

        Implements the retry policies from ``core/errors.py``:

        - ``LLMInvalidJSONError``: one retry with the same prompt, then
          surface the error.
        - ``LLMTimeoutError``: ``asyncio.wait_for`` around the call,
          no retry.
        - ``LLMRateLimitError``: exponential backoff (2s, 4s, 8s), max 3
          total attempts.

        Args:
            messages: Conversation messages.
            response_format: JSON schema format (e.g.
                ``{"type": "json_schema", "json_schema": {...}}``).
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            seed: Optional sampling seed, forwarded to the API for
                deterministic experiments; omitted from the request
                when ``None``.

        Returns:
            An ``LLMResponse`` with the parsed result.

        Raises:
            LLMInvalidJSONError: After one retry on invalid JSON.
            LLMTimeoutError: If the call exceeds the timeout.
            LLMRateLimitError: After exhausting retries on 429.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if seed is not None:
            kwargs["seed"] = seed

        attempts = 0
        max_attempts = 3  # for rate-limit retries
        json_retried = False  # JSON retry bound — independent of `attempts`

        while True:
            attempts += 1
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        **kwargs,  # type: ignore[arg-type]
                    ),
                    timeout=self._timeout,
                )
            except openai.RateLimitError:
                if attempts <= max_attempts and attempts <= len(_RETRY_BACKOFFS):
                    backoff = _RETRY_BACKOFFS[attempts - 1]
                    logger.warning(
                        "OpenAI rate-limited (attempt %d/%d), retrying in %.1fs",
                        attempts,
                        max_attempts,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise LLMRateLimitError(
                    f"Rate-limited after {attempts - 1} retries"
                ) from None
            except openai.AuthenticationError as e:
                # Invalid/expired API key (401): retrying cannot help.
                # Surface a typed auth error (AuthError + LLMError) so
                # the existing ``except LLMError`` boundaries catch it
                # and the taxonomy emits auth/invalid_key.
                raise AuthInvalidKeyError(f"Authentication failed: {e}") from None
            except openai.APITimeoutError:
                raise LLMTimeoutError(
                    f"OpenAI call timed out after {self._timeout}s"
                ) from None
            except asyncio.TimeoutError:
                raise LLMTimeoutError(
                    f"OpenAI call timed out after {self._timeout}s"
                ) from None
            except openai.APIStatusError as e:
                # Trailing catch for unexpected provider HTTP statuses —
                # AFTER the specific excepts (RateLimitError and
                # AuthenticationError subclass APIStatusError, so order
                # matters). The OpenAI SDK has no dedicated 402 class:
                # status-code inspection on the typed exception object is
                # the status-based mechanism the spec mandates (no
                # exception-text parsing anywhere).
                if getattr(e, "status_code", None) == 402:
                    raise AuthNoCreditsError(f"Payment required: {e}") from None
                raise LLMError(str(e)) from None

            # Parse the response
            choices = getattr(response, "choices", None) or []
            if not choices:
                # OpenRouter backends can return an empty choices list on
                # transient upstream failures — retry, then fail with a
                # clear message instead of a cryptic TypeError.
                if attempts <= max_attempts and attempts <= len(_RETRY_BACKOFFS):
                    backoff = _RETRY_BACKOFFS[attempts - 1]
                    logger.warning(
                        "Empty choices from provider (attempt %d), retrying in %.1fs",
                        attempts,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise LLMError(
                    "Provider returned an empty response (no choices). "
                    "Please try again."
                ) from None
            choice = choices[0]
            content = choice.message.content or ""
            finish_reason = choice.finish_reason

            usage = LLMUsage(
                tokens_in=response.usage.prompt_tokens if response.usage else 0,
                tokens_out=response.usage.completion_tokens if response.usage else 0,
                cost_usd=_estimate_cost(
                    response.usage.prompt_tokens if response.usage else 0,
                    response.usage.completion_tokens if response.usage else 0,
                    self._model,
                ),
            )

            # If using response_format, attempt to parse the structured data
            structured_data: dict | None = None
            if response_format is not None:
                try:
                    structured_data = json.loads(_strip_json_fences(content))
                except json.JSONDecodeError as parse_error:
                    if not json_retried:
                        json_retried = True
                        # Copy-on-write: append the parse-error feedback
                        # as a new user message WITHOUT mutating the
                        # caller's list (chat.py reuses nothing, but the
                        # bench may).
                        kwargs["messages"] = [
                            *kwargs["messages"],
                            {
                                "role": "user",
                                "content": _JSON_RETRY_FEEDBACK.format(
                                    msg=parse_error.msg,
                                    lineno=parse_error.lineno,
                                    colno=parse_error.colno,
                                ),
                            },
                        ]
                        logger.warning(
                            "Invalid JSON from provider (attempt %d), "
                            "retrying with parse feedback",
                            attempts,
                        )
                        continue
                    raise LLMInvalidJSONError(
                        f"OpenAI returned invalid JSON after {attempts - 1} retries: "
                        f"{content[:200]}"
                    ) from None

            return LLMResponse(
                text=content,
                structured_data=structured_data,
                model=response.model or self._model,
                provider="openai",
                usage=usage,
                raw=response.to_dict() if hasattr(response, "to_dict") else {},
            )

        # Unreachable — but return a fallback to satisfy the type checker
        raise LLMRateLimitError("Max retries exceeded")

    async def stream(
        self,
        messages: list[dict],
        *,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        """Send a streaming request to OpenAI.

        Yields text deltas as they arrive. Structured output is NOT
        streamed incrementally — use ``complete()`` for json_schema calls.

        Args:
            messages: Conversation messages.
            response_format: Ignored in streaming mode (OpenAI does not
                support streaming JSON schema).
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            seed: Optional sampling seed, forwarded to the API for
                deterministic experiments; omitted from the request
                when ``None``.

        Yields:
            String deltas of response text.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if seed is not None:
            kwargs["seed"] = seed

        try:
            stream = await asyncio.wait_for(
                self._client.chat.completions.create(
                    **kwargs,  # type: ignore[arg-type]
                ),
                timeout=self._timeout,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except openai.RateLimitError:
            raise LLMRateLimitError("Rate-limited during streaming") from None
        except openai.AuthenticationError as e:
            # Invalid/expired API key (401): typed auth error (AuthError +
            # LLMError) so ``except LLMError`` boundaries catch it and the
            # taxonomy emits auth/invalid_key.
            raise AuthInvalidKeyError(f"Authentication failed: {e}") from None
        except (openai.APITimeoutError, asyncio.TimeoutError):
            raise LLMTimeoutError(
                f"Streaming call timed out after {self._timeout}s"
            ) from None
        except openai.APIStatusError as e:
            # Trailing catch AFTER the specific excepts (RateLimitError
            # and AuthenticationError subclass APIStatusError). No
            # dedicated 402 class in the SDK — status-code inspection on
            # the typed exception object, no exception-text parsing.
            if getattr(e, "status_code", None) == 402:
                raise AuthNoCreditsError(f"Payment required: {e}") from None
            raise LLMError(str(e)) from None


# ── Cost estimation ──────────────────────────────────────────────────────────

# Published prices in USD per 1M tokens, as (input, output). Stored per-token
# because _estimate_cost multiplies each rate by a token count.
_PER_MILLION_TOKENS = 1_000_000

_MODEL_COST_MAP: dict[str, tuple[float, float]] = {
    "gpt-4o-2024-08-06": (2.50 / _PER_MILLION_TOKENS, 10.00 / _PER_MILLION_TOKENS),
    "gpt-4o-mini-2024-07-18": (0.15 / _PER_MILLION_TOKENS, 0.60 / _PER_MILLION_TOKENS),
    "gpt-4o": (2.50 / _PER_MILLION_TOKENS, 10.00 / _PER_MILLION_TOKENS),
    "gpt-4o-mini": (0.15 / _PER_MILLION_TOKENS, 0.60 / _PER_MILLION_TOKENS),
    "gpt-4.1": (2.00 / _PER_MILLION_TOKENS, 8.00 / _PER_MILLION_TOKENS),
    "gpt-4.1-mini": (0.40 / _PER_MILLION_TOKENS, 1.60 / _PER_MILLION_TOKENS),
    "gpt-4.1-nano": (0.10 / _PER_MILLION_TOKENS, 0.40 / _PER_MILLION_TOKENS),
    "z-ai/glm-5.3-flash": (0.05 / _PER_MILLION_TOKENS, 0.30 / _PER_MILLION_TOKENS),
}

# gpt-4o is the app default; used when a model id is not in the map.
_FALLBACK_COST_RATES = (2.50 / _PER_MILLION_TOKENS, 10.00 / _PER_MILLION_TOKENS)


def _cost_rates(model: str) -> tuple[float, float]:
    """Resolve per-token (input, output) USD rates for a model id.

    Accepts both bare ids ("gpt-4.1-mini") and provider-prefixed slugs
    ("openai/gpt-4.1-mini") so OpenRouter-style names reuse one price entry.
    Unknown models fall back to gpt-4o pricing (with a warning).
    """
    rates = _MODEL_COST_MAP.get(model)
    if rates is None and "/" in model:
        rates = _MODEL_COST_MAP.get(model.rsplit("/", 1)[-1])
    if rates is None:
        logger.warning(
            "Unknown model %r has no price entry; falling back to gpt-4o rates "
            "(the persisted cost_usd will not match this model's real price). "
            "Add it to _MODEL_COST_MAP.",
            model,
        )
        return _FALLBACK_COST_RATES
    return rates


def _estimate_cost(
    tokens_in: int,
    tokens_out: int,
    model: str,
) -> float:
    """Estimate the cost in USD for a model call.

    Falls back to gpt-4o pricing if the model is not recognised.
    """
    rates = _cost_rates(model)
    return (tokens_in * rates[0]) + (tokens_out * rates[1])