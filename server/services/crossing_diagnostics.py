"""Crossing diagnostics: how a merge came out, counted on the server (F5 / T2, S6).

Spec S6 — *"report the imbalance and continue"* — says that when the analyst
confirms a crossing, Datara tells them how many rows fell out of each side and
how the result came out, without stopping the session. Per Decision A2 those
counts are computed here with pandas at confirm time: deterministic, testable,
and never asked of the model (a model that miscounts would lie quietly).

The counting is one outer merge per crossing. pandas' ``indicator=True`` column
labels every merged row as ``both``, ``left_only`` or ``right_only``, and the
three totals are read straight off it, so an inner join that hides the orphans
still reports them. ``result_rows`` is then derived arithmetically from those
three numbers, from the join kind the analyst chose: no second merge.

Two failures are typed here instead of escaping as tracebacks, because the route
turns both into an explicit 422: a dataset that cannot be parsed (the recipe is
refused now, not at query time) and two keys pandas cannot compare (an int64
column against an object column), which is a refusal, never a silently empty
crossing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class CrossingDiagnosticsError(Exception):
    """Base class: a crossing the server refuses to diagnose."""


class DatasetUnreadableError(CrossingDiagnosticsError):
    """One of the two datasets could not be parsed from disk."""

    def __init__(self, filename: str, reason: str) -> None:
        self.filename = filename
        super().__init__(f"Dataset '{filename}' could not be read: {reason}")


class KeysNotComparableError(CrossingDiagnosticsError):
    """The two keys cannot be merged: different dtypes, or a column vanished."""

    def __init__(
        self,
        *,
        left_key: str,
        right_key: str,
        left_description: str,
        right_description: str,
    ) -> None:
        self.left_key = left_key
        self.right_key = right_key
        super().__init__(
            f"Keys '{left_key}' and '{right_key}' cannot be compared: "
            f"{left_description}; {right_description}."
        )


@dataclass(frozen=True)
class DatasetRef:
    """Where one side of a crossing lives, as the stored file row describes it."""

    filename: str
    path: str
    format: str | None
    sheet_name: str | None

    @classmethod
    def from_file_row(cls, file_row: dict[str, Any]) -> DatasetRef:
        """Build the reference from a ``files`` row of the store."""
        return cls(
            filename=file_row["filename"],
            path=file_row.get("storage_path") or "",
            format=file_row.get("format"),
            sheet_name=file_row.get("sheet_name"),
        )


async def compute_crossing_diagnostics(
    *,
    left: DatasetRef,
    right: DatasetRef,
    left_key: str,
    right_key: str,
    how: str,
) -> dict[str, int]:
    """Count how the crossing came out, off the event loop.

    Returns ``left_rows``, ``right_rows``, ``matched_rows``, ``left_only_rows``,
    ``right_only_rows`` and ``result_rows``.

    Raises:
        DatasetUnreadableError: a dataset is missing or cannot be parsed.
        KeysNotComparableError: the two keys cannot be merged.
    """
    # Parsing and merging are both blocking pandas work: one thread hop keeps
    # the event loop free (same pattern as ``chat_context._ensure_profile``).
    return await asyncio.to_thread(
        _diagnose,
        left=left,
        right=right,
        left_key=left_key,
        right_key=right_key,
        how=how,
    )


def _diagnose(
    *,
    left: DatasetRef,
    right: DatasetRef,
    left_key: str,
    right_key: str,
    how: str,
) -> dict[str, int]:
    """Blocking half of :func:`compute_crossing_diagnostics`."""
    left_frame = _read_dataset(left)
    right_frame = _read_dataset(right)

    try:
        merged = left_frame.merge(
            right_frame,
            left_on=left_key,
            right_on=right_key,
            how="outer",
            indicator=True,
        )
    except (ValueError, KeyError) as exc:
        # pandas refuses to merge an int64 column with an object column, and a
        # key named by the profile but absent from the file is just as
        # unmergeable. Both are refusals with the same code.
        raise KeysNotComparableError(
            left_key=left_key,
            right_key=right_key,
            left_description=_describe_key(left_frame, left, left_key),
            right_description=_describe_key(right_frame, right, right_key),
        ) from exc

    labels = merged["_merge"].value_counts()
    matched_rows = int(labels.get("both", 0))
    left_only_rows = int(labels.get("left_only", 0))
    right_only_rows = int(labels.get("right_only", 0))

    return {
        "left_rows": int(len(left_frame)),
        "right_rows": int(len(right_frame)),
        "matched_rows": matched_rows,
        "left_only_rows": left_only_rows,
        "right_only_rows": right_only_rows,
        "result_rows": _result_rows(
            how,
            matched=matched_rows,
            left_only=left_only_rows,
            right_only=right_only_rows,
        ),
    }


def _read_dataset(dataset: DatasetRef) -> pd.DataFrame:
    """Parse one dataset the way the rest of the app does, or refuse it.

    An XLSX is read from its ACTIVE ``sheet_name`` — never silently the first
    sheet — so the crossing counts the same rows the profile describes (F3).
    """
    from core.data.parser import parse_upload, parse_upload_sheet  # noqa: PLC0415

    try:
        if dataset.format == "xlsx" and dataset.sheet_name:
            frame, _meta = parse_upload_sheet(dataset.path, dataset.sheet_name)
        else:
            frame, _meta = parse_upload(dataset.path, dataset.format)
    except Exception as exc:  # noqa: BLE001 - every parse failure is one refusal
        logger.warning(
            "Crossing cannot read dataset %s (%s): %s",
            dataset.filename,
            dataset.path,
            exc,
        )
        raise DatasetUnreadableError(dataset.filename, str(exc) or type(exc).__name__) from exc
    return frame


def _describe_key(frame: pd.DataFrame, dataset: DatasetRef, key: str) -> str:
    """Name the key, its dataset and its dtype, for the refusal message."""
    if key not in frame.columns:
        return f"'{key}' is not a column of '{dataset.filename}'"
    return f"'{key}' holds {frame[key].dtype} values in '{dataset.filename}'"


def _result_rows(how: str, *, matched: int, left_only: int, right_only: int) -> int:
    """How many rows the chosen join kind yields, from the outer counts alone.

    inner keeps the matched pairs; left adds the unmatched left rows; right adds
    the unmatched right rows; outer keeps all three.
    """
    if how == "inner":
        return matched
    if how == "left":
        return matched + left_only
    if how == "right":
        return matched + right_only
    return matched + left_only + right_only