"""LLM provider abstraction for Datara.

Defines the Protocol that all LLM providers must implement,
plus shared response and usage types.

NOTE (v1): tools= / function-calling is intentionally NOT in the surface.
No v1 capability requires it; structured-output-only flow covers chat code
generation. Add tools= when a v1+ feature actually needs it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMUsage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    structured_data: dict | None = None
    model: str = ""
    provider: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw: dict = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Async LLM provider protocol.

    Implementations wrap a provider SDK (e.g., OpenAI, Anthropic)
    and return structured responses.
    """

    async def complete(
        self,
        messages: list[dict],
        *,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> LLMResponse:
        """Send a complete (non-streaming) request to the LLM.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            response_format: Optional JSON schema format specification.
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            seed: Optional sampling seed for deterministic experiments;
                forwarded to the backend when set, omitted otherwise.

        Returns:
            An LLMResponse with the full model output.
        """
        ...

    async def stream(
        self,
        messages: list[dict],
        *,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        """Send a streaming request to the LLM.

        Yields text deltas as they arrive. Structured output is NOT
        streamed incrementally — use ``complete()`` for json_schema calls.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            response_format: Optional JSON schema format specification.
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            seed: Optional sampling seed for deterministic experiments;
                forwarded to the backend when set, omitted otherwise.

        Yields:
            String deltas of response text.
        """
        ...