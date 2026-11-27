"""Declared privacy levels and the outgoing-payload redaction (F6).

The stored profile is the complete local truth. This module builds the
redacted copy that leaves the machine. The same functions feed both the chat
prompt and the "this is what is sent" preview, so the two can never drift.

A dataset profile travels in the ``_serialize_profile`` shape::

    {
        "columns": [{"name": str, "dtype": str}, ...],
        "stats": {column_name: {"null_count", "unique_count",
                                "sample_values", "min", "max", "mean", "std"}},
        "sample": [{"column_name": value}, ...],
    }

``redact_profile`` returns that same shape, redacted for the chosen level.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

PRIVACY_LEVELS: tuple[str, ...] = ("full", "aggregates", "schema", "masked")
DEFAULT_PRIVACY_LEVEL = "full"


class PrivacyError(ValueError):
    """An invalid privacy level or column alias map."""


def validate_level(level: str | None) -> str:
    """Return a known level; ``None`` resolves to the default."""
    resolved = DEFAULT_PRIVACY_LEVEL if level is None else level
    if resolved not in PRIVACY_LEVELS:
        raise PrivacyError(
            f"Unknown privacy level: {resolved!r}. "
            f"Supported: {', '.join(PRIVACY_LEVELS)}"
        )
    return resolved


def effective_level(file_level: str | None, session_level: str | None) -> str:
    """The file's own level when set, else the session's, else the default."""
    return validate_level(file_level or session_level)


def _mask_text(text: str) -> str:
    """Shape-preserving placeholder: letters become x/X, digits become 9."""
    masked: list[str] = []
    for char in text:
        if char.isdigit():
            masked.append("9")
        elif char.isalpha():
            masked.append("X" if char.isupper() else "x")
        else:
            masked.append(char)
    return "".join(masked)


def mask_value(value: Any) -> Any:
    """Mask one cell value with a fixed, leak-free placeholder.

    ``None`` stays ``None``. Booleans become ``"***"`` because their truth
    value is content even when the type is not. Any integer becomes ``"9"``
    and any float becomes ``"9.9"``: no magnitude, no digit count and no
    exponent form survives, and the sign is dropped (F6-advisories S2/D2).
    Text keeps its shape (letters and digits replaced in place).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "***"
    if isinstance(value, int):
        return "9"
    if isinstance(value, float):
        return "9.9"
    if isinstance(value, str):
        return _mask_text(value)
    return _mask_text(str(value))


def validate_aliases(
    aliases: dict[str, str] | None,
    columns: list[str],
) -> dict[str, str]:
    """Check an alias map against the real column names.

    Every source must be a real column and every target must be unique, so a
    typo cannot silently leave a column unaliased and two columns cannot
    collapse into one key.
    """
    if not aliases:
        return {}
    if not isinstance(aliases, dict):
        raise PrivacyError("Column aliases must be an object mapping name to alias.")
    targets: set[str] = set()
    for source, alias in aliases.items():
        if not isinstance(source, str) or not source:
            raise PrivacyError("Column alias keys must be non-empty strings.")
        if not isinstance(alias, str) or not alias.strip():
            raise PrivacyError(f"Alias for {source!r} must be a non-empty string.")
        if source not in columns:
            raise PrivacyError(
                f"Alias source {source!r} is not a column of this file."
            )
        if alias in targets:
            raise PrivacyError(f"Duplicate alias {alias!r}.")
        targets.add(alias)
    return dict(aliases)


def parse_aliases(raw: str | None) -> dict[str, Any]:
    """Parse the stored column-alias JSON into an alias map.

    The single parser for the app (F6-advisories S4): ``chat_context`` imports
    this instead of keeping its own copy. Legacy or corrupt rows are ignored
    (an empty map). Values are returned exactly as stored -- a JSON ``null``
    stays ``None`` and is later rejected by :func:`validate_aliases`, never
    silently coerced into the string ``"None"`` (D4).
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid column_aliases_json")
        return {}
    if not isinstance(parsed, dict):
        return {}
    return dict(parsed)


def redact_profile(
    profile: dict[str, Any],
    level: str | None,
    aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the outgoing copy of one dataset profile.

    ``level`` follows the F6 ladder: ``full`` keeps today's payload, ``aggregates``
    drops the sample values and rows, ``schema`` keeps only name and dtype, and
    ``masked`` keeps masked values while dropping the aggregates that would
    disclose them. Aliases are applied at every level, in the outgoing copy only.
    """
    resolved = validate_level(level)
    columns = [dict(column) for column in profile.get("columns", [])]
    stats = {
        name: dict(values) for name, values in (profile.get("stats") or {}).items()
    }
    sample = [dict(row) for row in (profile.get("sample") or [])]

    if resolved == "schema":
        stats = {}
        sample = []
    elif resolved == "aggregates":
        for values in stats.values():
            values.pop("sample_values", None)
        sample = []
    elif resolved == "masked":
        for values in stats.values():
            if "sample_values" in values:
                values["sample_values"] = [
                    mask_value(value) for value in values["sample_values"]
                ]
            for key in ("min", "max", "mean", "std"):
                values.pop(key, None)
        sample = [
            {key: mask_value(value) for key, value in row.items()} for row in sample
        ]

    alias_map = validate_aliases(
        aliases, [column["name"] for column in columns]
    )
    if alias_map:
        for column in columns:
            column["name"] = alias_map.get(column["name"], column["name"])
        stats = {
            alias_map.get(name, name): values for name, values in stats.items()
        }
        sample = [
            {alias_map.get(key, key): value for key, value in row.items()}
            for row in sample
        ]

    return {"columns": columns, "stats": stats, "sample": sample}


def stage_dataset_names(
    datasets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Replace each real filename and storage path with a neutral staged name.

    ``datasets`` entries carry ``filename``, ``format`` and ``path`` (the real
    storage path). Returns ``(outgoing, staged)``: outgoing copies with both
    ``path`` and ``filename`` set to the staged name (F6-advisories S1/D1), so
    no human label reaches the provider, and the ``staged -> storage_path`` map
    the sandbox needs to materialize the files.
    """
    outgoing: list[dict[str, Any]] = []
    staged: dict[str, str] = {}
    for index, dataset in enumerate(datasets, start=1):
        suffix = str(dataset.get("format") or "csv").lower().lstrip(".")
        name = f"dataset_{index}.{suffix}"
        copy = dict(dataset)
        copy["path"] = name
        copy["filename"] = name
        outgoing.append(copy)
        storage_path = dataset.get("path")
        if storage_path:
            staged[name] = storage_path
    return outgoing, staged
