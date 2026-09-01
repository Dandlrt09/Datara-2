"""Data ingestion: encoding detection, delimiter sniffing, pandas parsing.

This module is CPU-bound (pandas operations) and MUST be called via
``loop.run_in_executor(ProcessPoolExecutor)`` from async routes to
keep the event loop responsive.
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ParseMeta:
    """Metadata about a parsed file."""

    encoding: str
    delimiter: str | None
    format: str  # csv | xlsx | json | tsv
    row_count: int
    sheet_name: str | None
    sheets: list[str] | None  # all sheet names (XLSX only)


_SUPPORTED_FORMATS = frozenset({"csv", "tsv", "xlsx", "json"})
_DELIMITER_CANDIDATES = [",", "\t", ";", "|"]


def _detect_encoding(path: str) -> str:
    """Detect file encoding using charset-normalizer.

    Falls back to UTF-8 if detection fails.
    """
    try:
        import charset_normalizer  # noqa: PLC0415

        result = charset_normalizer.from_path(path).best()
        if result is not None and result.encoding:
            return result.encoding
    except Exception:
        pass
    return "utf-8"


def _detect_delimiter(path: str, sample_size: int = 4096) -> str:
    """Detect delimiter using csv.Sniffer on a sample.

    Falls back to comma if sniffing fails.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(sample_size)
        dialect = csv.Sniffer().sniff(sample)
        return dialect.delimiter
    except Exception:
        # Try candidates
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                sample = f.read(sample_size)
            for delim in _DELIMITER_CANDIDATES:
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=delim)
                    return dialect.delimiter
                except Exception:
                    continue
        except Exception:
            pass
    return ","


def _list_xlsx_sheets(path: str) -> list[str]:
    """List sheet names in an XLSX file."""
    return pd.ExcelFile(path).sheet_names


def parse_upload(path: str, format_hint: str | None = None) -> tuple[pd.DataFrame, ParseMeta]:
    """Parse an uploaded data file.

    Args:
        path: Absolute path to the uploaded file.
        format_hint: Optional hint (csv, tsv, xlsx, json). Auto-detected
                     from extension if not provided.

    Returns:
        A tuple of (DataFrame, ParseMeta) on success.

    Raises:
        ValueError: If the format is unsupported or parsing fails.
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = (format_hint or path_obj.suffix.lstrip(".")).lower()
    if ext not in _SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {ext}. Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}")

    if ext in ("csv", "tsv"):
        encoding = _detect_encoding(path)
        delimiter = _detect_delimiter(path) if ext == "csv" else "\t"
        df = pd.read_csv(
            path,
            encoding=encoding,
            delimiter=delimiter,
            low_memory=False,
        )
        meta = ParseMeta(
            encoding=encoding,
            delimiter=delimiter,
            format=ext,
            row_count=len(df),
            sheet_name=None,
            sheets=None,
        )
    elif ext == "xlsx":
        sheets = _list_xlsx_sheets(path)
        sheet_name = sheets[0]  # default to first
        df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
        meta = ParseMeta(
            encoding="utf-8",
            delimiter=None,
            format="xlsx",
            row_count=len(df),
            sheet_name=sheet_name,
            sheets=sheets,
        )
    elif ext == "json":
        try:
            df = pd.read_json(path, orient="records", lines=False)
        except ValueError:
            df = pd.read_json(path, orient="records", lines=True)
        meta = ParseMeta(
            encoding="utf-8",
            delimiter=None,
            format="json",
            row_count=len(df),
            sheet_name=None,
            sheets=None,
        )
    else:
        raise ValueError(f"Unsupported format: {ext}")

    if df.empty:
        raise ValueError("Parsed file is empty (0 rows)")

    return df, meta


def parse_upload_sheet(path: str, sheet_name: str) -> tuple[pd.DataFrame, ParseMeta]:
    """Parse a specific sheet from an XLSX file.

    Args:
        path: Absolute path to the XLSX file.
        sheet_name: Name of the sheet to parse.

    Returns:
        A tuple of (DataFrame, ParseMeta).
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"File not found: {path}")

    df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    sheets = _list_xlsx_sheets(path)
    meta = ParseMeta(
        encoding="utf-8",
        delimiter=None,
        format="xlsx",
        row_count=len(df),
        sheet_name=sheet_name,
        sheets=sheets,
    )
    if df.empty:
        raise ValueError(f"Sheet '{sheet_name}' is empty (0 rows)")
    return df, meta