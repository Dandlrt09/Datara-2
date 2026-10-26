"""Per-user display preferences: allowed values, defaults and normalization.

The database stores NULL for "not chosen"; every reader resolves NULL (or an
unknown legacy value) to the effective default here, so the settings API and
the chat prompt builders agree on one value per user.
"""

from __future__ import annotations

from typing import Any

NUMBER_FORMAT_ES = "es"
NUMBER_FORMAT_INTL = "intl"
DATE_FORMAT_RELATIVE = "relative"
DATE_FORMAT_ABSOLUTE = "absolute"
OPEN_BEHAVIOR_NEW = "new_session"
OPEN_BEHAVIOR_LAST = "last_session"

#: Allowed values per preference. The settings request model mirrors these
#: with ``Literal`` types, so an unknown value is rejected with 422 on write.
ALLOWED: dict[str, tuple[str, ...]] = {
    "number_format": (NUMBER_FORMAT_ES, NUMBER_FORMAT_INTL),
    "date_format": (DATE_FORMAT_RELATIVE, DATE_FORMAT_ABSOLUTE),
    "currency_symbol": ("US$", "$", "USD", "none"),
    "open_behavior": (OPEN_BEHAVIOR_NEW, OPEN_BEHAVIOR_LAST),
}

#: Effective value for each preference when the user has not chosen one.
#: Every default reproduces the behavior that existed before preferences.
DEFAULTS: dict[str, str] = {
    "number_format": NUMBER_FORMAT_ES,
    "date_format": DATE_FORMAT_RELATIVE,
    "currency_symbol": "US$",
    "open_behavior": OPEN_BEHAVIOR_NEW,
}


def effective_preferences(settings: dict[str, Any] | None) -> dict[str, str]:
    """Resolve every preference to a valid value, defaulting when unset.

    ``settings`` may be a store row (extra keys are ignored) or ``None`` when
    the user has no settings row yet.
    """
    resolved = dict(DEFAULTS)
    if settings:
        for key, default in DEFAULTS.items():
            value = settings.get(key)
            if value in ALLOWED[key]:
                resolved[key] = value
            else:
                resolved[key] = default
    return resolved


#: Exact sentence appended to the main system prompt, per convention. The
#: Spanish entry is byte-identical to the literal that predates preferences,
#: so the default prompt (and the SHA-256 pinned by its test) does not change.
NARRATIVE_NUMBER_INSTRUCTION = {
    NUMBER_FORMAT_ES: (
        "Format numeric values in Spanish convention: dot as thousands separator "
        "and comma as decimal separator, \u22646 decimal places (e.g. 5.035.600,021 "
        "\u2014 never full-precision floats like 2500.8230981333336). Drop "
        "unnecessary trailing zeros (write 5.020.000, not 5.020.000,0). "
    ),
    NUMBER_FORMAT_INTL: (
        "Format numeric values in international convention: comma as thousands "
        "separator and dot as decimal separator, \u22646 decimal places "
        "(e.g. 5,035,600.021 \u2014 never full-precision floats like "
        "2500.8230981333336). Drop unnecessary trailing zeros "
        "(write 5,020,000, not 5,020,000.0). "
    ),
}

#: Exact sentence used in the second-pass grounding prompt. Same byte-identity
#: guarantee for the Spanish entry.
GROUNDING_NUMBER_INSTRUCTION = {
    NUMBER_FORMAT_ES: (
        "Format numbers in Spanish convention: dot thousands separator, comma "
        "decimal separator (e.g. 76.036.762,77), dropping unnecessary trailing "
        "zeros. "
    ),
    NUMBER_FORMAT_INTL: (
        "Format numbers in international convention: comma thousands separator, "
        "dot decimal separator (e.g. 76,036,762.77), dropping unnecessary "
        "trailing zeros. "
    ),
}


def narrative_number_instruction(number_format: str) -> str:
    """Number-format sentence for the main system prompt."""
    return NARRATIVE_NUMBER_INSTRUCTION.get(
        number_format, NARRATIVE_NUMBER_INSTRUCTION[NUMBER_FORMAT_ES]
    )


def grounding_number_instruction(number_format: str) -> str:
    """Number-format sentence for the second-pass grounding prompt."""
    return GROUNDING_NUMBER_INSTRUCTION.get(
        number_format, GROUNDING_NUMBER_INSTRUCTION[NUMBER_FORMAT_ES]
    )
