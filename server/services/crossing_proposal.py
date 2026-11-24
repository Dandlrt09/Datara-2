"""LLM-guided crossing proposal (F5 / T4, S3).

S3 — *"guided by the LLM"* — says Datara reads every profile, **proposes** the
key columns and the join kind, and the analyst confirms or adjusts before
anything is crossed. This module is that proposal and only that proposal: it
builds its OWN prompt from the profiles of the two files (never from the raw
files), asks the provider for one JSON answer, and validates that answer
against those profiles. It never touches the store, so proposing leaves the
session exactly as it was — the analyst still confirms through
``POST /sessions/{id}/crossings``.

The provider call reuses the chat path (``server.services.llm_openai``),
including its fence stripping and JSON parse: this module never re-parses the
model's text. Per AGENTS.md this call carries its own system prompt; nothing
propagates between calls.

Decision A4's spirit applies here too: a key the model invents is refused, so a
proposal that names a column the dataset does not have is returned as NO
proposal, never silently accepted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from server.services.llm_openai import OpenAIProvider

logger = logging.getLogger(__name__)

# The join kinds pandas offers and the recipe router accepts. Kept in step
# with ``crossings.JoinKind``.
JOIN_KINDS: tuple[str, ...] = ("inner", "left", "right", "outer")

# Machine-readable discriminators for a null proposal (S3 follow-up). The T5 UI
# writes its own neutral-Spanish copy per code, so the English prose in
# ``reason`` is never shown verbatim.
#   proposal_unavailable: the provider could not be consulted (missing key,
#       provider call failure).
#   proposal_not_found: the provider answered but no usable proposal came out
#       (no shared column, unparseable JSON, invented key).
PROPOSAL_UNAVAILABLE_CODE = "proposal_unavailable"
PROPOSAL_NOT_FOUND_CODE = "proposal_not_found"

# Own system prompt for this single call (AGENTS.md: one system prompt per
# LLM call — the profile-formatting rules of the chat prompt do not travel
# here and vice versa).
_SYSTEM_PROMPT = (
    "You are a data analysis assistant. You are given the profiles of two "
    "datasets that may be crossed with a pandas merge. Each dataset entry "
    "carries its 'filename', its 'columns' (each with a 'name' and a 'dtype') "
    "and a few 'sample' rows. "
    "Propose how to cross them: the key column on the LEFT dataset "
    "('left_key'), the key column on the RIGHT dataset ('right_key') and the "
    "join kind ('how'). "
    "Reply with a single JSON object with exactly these fields: 'left_key', "
    "'right_key', 'how' and 'reason'. 'how' must be one of 'inner', 'left', "
    "'right' or 'outer'. 'reason' is one short sentence explaining the choice. "
    "Only propose keys that appear in the 'columns' listed for that dataset — "
    "never invent a column. "
    "If the two datasets share no column that can be joined, answer with null "
    "for 'left_key' and 'right_key', and explain why in 'reason'."
)

# The JSON contract of the proposal call. Nullable keys let the model say
# "there is no shared column" without inventing one.
PROPOSAL_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "crossing_proposal",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "left_key": {"type": ["string", "null"]},
                "right_key": {"type": ["string", "null"]},
                "how": {
                    "type": "string",
                    "enum": ["inner", "left", "right", "outer"],
                },
                "reason": {"type": "string"},
            },
            "required": ["left_key", "right_key", "how", "reason"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class ProposalDataset:
    """One side of the proposal, as its stored profile describes it.

    Built from a profile row (``profile_cache.get_profile``), never by opening
    the file again: the proposal must agree with what the prompt already tells
    the model a dataset contains.
    """

    filename: str
    columns: list[dict[str, Any]]
    sample: list[dict[str, Any]]

    @classmethod
    def from_profile(
        cls, filename: str, profile: dict[str, Any]
    ) -> "ProposalDataset":
        """Build the side from a stored profile dict."""
        return cls(
            filename=filename,
            columns=list(profile.get("schema_data", {}).get("columns", [])),
            sample=list(profile.get("sample", [])),
        )

    def as_prompt_payload(self) -> dict[str, Any]:
        """The JSON-safe entry that travels into the prompt."""
        return {
            "filename": self.filename,
            "columns": self.columns,
            "sample": self.sample,
        }

    def column_names(self) -> list[str]:
        return [column["name"] for column in self.columns]


@dataclass(frozen=True)
class CrossingProposal:
    """A usable proposal: keys that both exist, a valid join kind and a why."""

    left_key: str
    right_key: str
    how: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {
            "left_key": self.left_key,
            "right_key": self.right_key,
            "how": self.how,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProposalOutcome:
    """Either a proposal or the reason there is none — never both."""

    proposal: CrossingProposal | None
    reason: str


def build_proposal_messages(
    left: ProposalDataset, right: ProposalDataset
) -> list[dict[str, str]]:
    """Assemble the single call's messages from both profiles.

    The profiles travel as a JSON payload in the user message; the system
    prompt carries only the instructions. Kept pure so the prompt is testable
    without a provider.
    """
    payload = {"left": left.as_prompt_payload(), "right": right.as_prompt_payload()}
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Profiles of the two datasets to cross:\n"
                + json.dumps(payload, indent=2, ensure_ascii=False)
            ),
        },
    ]


async def propose_crossing(
    provider: OpenAIProvider,
    *,
    left: ProposalDataset,
    right: ProposalDataset,
) -> ProposalOutcome:
    """Ask the model to propose a crossing and validate its answer.

    The provider's ``response_format`` parse (including fence stripping) is
    the only JSON parser involved. Provider errors propagate to the caller,
    which turns them into the same refusal shape the chat path uses.
    """
    response = await provider.complete(
        messages=build_proposal_messages(left, right),
        response_format=PROPOSAL_JSON_SCHEMA,
        max_tokens=1024,
        temperature=0.1,
    )
    return _validate_proposal(response.structured_data, left=left, right=right)


def _validate_proposal(
    structured: Any,
    *,
    left: ProposalDataset,
    right: ProposalDataset,
) -> ProposalOutcome:
    """Accept the answer only when every named key is a column of its dataset.

    An answer that is not a JSON object, a null/absent key, an unknown join
    kind, or a key that is not a column of the dataset it names all yield NO
    proposal. The reason a null/absent key carries is the model's own sentence
    (it is telling us it found no shared column); every other refusal gets a
    server-authored reason naming what was wrong.
    """
    if not isinstance(structured, dict):
        return ProposalOutcome(
            None, "The model did not return a usable JSON proposal."
        )

    reason = structured.get("reason")
    model_reason = reason.strip() if isinstance(reason, str) else ""
    left_key = structured.get("left_key")
    right_key = structured.get("right_key")
    how = structured.get("how")

    if not left_key or not right_key:
        return ProposalOutcome(
            None,
            model_reason
            or "The model found no column the two datasets can share.",
        )

    if how not in JOIN_KINDS:
        return ProposalOutcome(
            None,
            model_reason or f"The model proposed an unknown join kind '{how}'.",
        )

    if left_key not in left.column_names():
        return ProposalOutcome(
            None,
            f"Column '{left_key}' is not in '{left.filename}'. "
            f"Available columns: {', '.join(left.column_names())}.",
        )

    if right_key not in right.column_names():
        return ProposalOutcome(
            None,
            f"Column '{right_key}' is not in '{right.filename}'. "
            f"Available columns: {', '.join(right.column_names())}.",
        )

    return ProposalOutcome(
        CrossingProposal(
            left_key=str(left_key),
            right_key=str(right_key),
            how=str(how),
            reason=model_reason,
        ),
        "",
    )
