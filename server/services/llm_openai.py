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
from typing import Any, AsyncIterator

import openai
from openai import AsyncOpenAI

from core.errors import (
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from core.protocols.llm_provider import LLMProvider, LLMResponse, LLMUsage

logger = logging.getLogger(__name__)

# Default timeout for the LLM call (seconds). Non-streamed json_schema
# responses on routed backends (e.g. OpenRouter) can be slow; configurable
# via OPENAI_TIMEOUT in the environment / .env.
_DEFAULT_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "120.0"))

# Rate-limit backoff schedule (seconds)
_RETRY_BACKOFFS = [2.0, 4.0, 8.0]


class OpenAIProvider:
    """OpenAI LLM provider.

    Wraps ``openai.AsyncOpenAI`` to produce structured responses.

    Args:
        api_key: OpenAI API key. If ``None``, falls back to the
            ``OPENAI_API_KEY`` environment variable.
        model: Model name (default: ``gpt-4o-2024-08-06``).
        timeout: Request timeout in seconds (default: 60).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-2024-08-06",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)

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
            except openai.APITimeoutError:
                raise LLMTimeoutError(
                    f"OpenAI call timed out after {self._timeout}s"
                ) from None
            except asyncio.TimeoutError:
                raise LLMTimeoutError(
                    f"OpenAI call timed out after {self._timeout}s"
                ) from None

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
                    structured_data = json.loads(content)
                except json.JSONDecodeError:
                    if attempts < 2:  # one retry for invalid JSON
                        logger.warning(
                            "Invalid JSON from OpenAI (attempt %d), retrying",
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
        except (openai.APITimeoutError, asyncio.TimeoutError):
            raise LLMTimeoutError(
                f"Streaming call timed out after {self._timeout}s"
            ) from None


# ── Cost estimation ──────────────────────────────────────────────────────────

# Approximate cost per 1K tokens (USD) for common models
_MODEL_COST_MAP: dict[str, tuple[float, float]] = {
    "gpt-4o-2024-08-06": (2.50 / 1000, 10.00 / 1000),       # input, output
    "gpt-4o-mini-2024-07-18": (0.150 / 1000, 0.600 / 1000),
    "gpt-4o": (2.50 / 1000, 10.00 / 1000),
    "gpt-4o-mini": (0.150 / 1000, 0.600 / 1000),
    "z-ai/glm-5.3-flash": (0.05 / 1_000_000, 0.30 / 1_000_000),
}


def _estimate_cost(
    tokens_in: int,
    tokens_out: int,
    model: str,
) -> float:
    """Estimate the cost in USD for a model call.

    Falls back to gpt-4o pricing if the model is not recognised.
    """
    rates = _MODEL_COST_MAP.get(model, (2.50 / 1000, 10.00 / 1000))
    return (tokens_in * rates[0]) + (tokens_out * rates[1])