"""Data profiling: column-level statistics for LLM context.

Generates per-column statistics (null count, unique count, sample values,
numeric stats) and caches them for profile-based LLM context.

This module is CPU-bound and should be called via
``loop.run_in_executor`` from async routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ColumnProfile:
    """Statistics for a single column."""

    name: str
    dtype: str
    null_count: int
    unique_count: int
    sample_values: list[Any] = field(default_factory=list)
    min: Any | None = None
    max: Any | None = None
    mean: float | None = None
    std: float | None = None


@dataclass
class DataProfile:
    """Full profile for a parsed dataset."""

    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    size_bytes: int
    sample_rows: list[dict[str, Any]] = field(default_factory=list)


_SAMPLE_ROWS = 10
_SAMPLE_VALUES = 5
_MAX_ROWS_FULL = 10_000
_MAX_BYTES_FULL = 50 * 1024 * 1024  # 50MB


def _should_sample(df: pd.DataFrame, size_bytes: int) -> bool:
    """Decide whether to sample the DataFrame.

    Samples if >10K rows or >50MB.
    """
    return len(df) > _MAX_ROWS_FULL or size_bytes > _MAX_BYTES_FULL


def _sample_dataframe(df: pd.DataFrame, random_state: int = 42) -> pd.DataFrame:
    """Return a representative sample of the DataFrame.

    Strategy: first 10K + random sample of up to 5K.
    """
    n = len(df)
    if n <= _SAMPLE_ROWS * 2:
        return df

    head = df.head(_MAX_ROWS_FULL)
    remainder_n = min(5000, max(0, n - _MAX_ROWS_FULL))
    if remainder_n > 0:
        tail = df.sample(n=min(remainder_n, n), random_state=random_state)
        return pd.concat([head, tail], ignore_index=True).drop_duplicates()
    return head


def build_profile(
    df: pd.DataFrame,
    *,
    max_sample: int = _MAX_ROWS_FULL,
    size_bytes: int | None = None,
) -> DataProfile:
    """Build a column-level profile for a DataFrame.

    Args:
        df: The parsed DataFrame to profile.
        max_sample: Maximum rows to consider for sampling (default 10K).
        size_bytes: Optional size hint for sampling threshold (default 50MB).

    Returns:
        A DataProfile dataclass with per-column stats.
    """
    actual_size = size_bytes or df.memory_usage(deep=True).sum()

    # Sample large datasets
    profile_df = _sample_dataframe(df, 42) if _should_sample(df, actual_size) else df

    columns: list[ColumnProfile] = []
    for col_name in df.columns:
        series = df[col_name]
        col_type = str(series.dtype)
        null_count = int(series.isna().sum())
        unique_count = int(series.nunique())

        # Sample values (non-null)
        non_null = series.dropna()
        if len(non_null) > _SAMPLE_VALUES:
            sample = list(non_null.head(_SAMPLE_VALUES))
        else:
            sample = list(non_null)

        col_profile = ColumnProfile(
            name=str(col_name),
            dtype=col_type,
            null_count=null_count,
            unique_count=unique_count,
            sample_values=sample,
        )

        # Numeric stats
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            col_profile.min = float(series.min()) if pd.notna(series.min()) else None
            col_profile.max = float(series.max()) if pd.notna(series.max()) else None
            col_profile.mean = float(series.mean()) if pd.notna(series.mean()) else None
            col_profile.std = float(series.std()) if pd.notna(series.std()) else None

        # Datetime stats
        elif pd.api.types.is_datetime64_any_dtype(series):
            col_profile.min = str(series.min()) if pd.notna(series.min()) else None
            col_profile.max = str(series.max()) if pd.notna(series.max()) else None

        columns.append(col_profile)

    # Sample rows (top 10)
    sample_rows = json_safe_records(df.head(_SAMPLE_ROWS))

    return DataProfile(
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
        size_bytes=int(actual_size),
        sample_rows=sample_rows,
    )


def profile_to_json(profile: DataProfile) -> dict[str, Any]:
    """Serialize a DataProfile to a JSON-safe dict."""
    return {
        "row_count": profile.row_count,
        "column_count": profile.column_count,
        "columns": [
            {
                "name": c.name,
                "dtype": c.dtype,
                "null_count": c.null_count,
                "unique_count": c.unique_count,
                "sample_values": [_json_safe(v) for v in c.sample_values],
                "min": _json_safe(c.min),
                "max": _json_safe(c.max),
                "mean": c.mean,
                "std": c.std,
            }
            for c in profile.columns
        ],
        "size_bytes": profile.size_bytes,
        "sample_rows": profile.sample_rows,
    }


def _json_safe(val: Any) -> Any:
    """Convert a value to a JSON-safe representation."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, (np.ndarray,)):
        return val.tolist()
    if isinstance(val, pd.Timestamp):
        return str(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val


def json_safe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert DataFrame head to JSON-safe list of dicts."""
    rows = df.to_dict(orient="records")
    return [
        {str(k): _json_safe(v) for k, v in row.items()}
        for row in rows
    ]