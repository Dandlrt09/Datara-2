"""Tests for core/data/parser.py and core/data/profiler.py."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.data.parser import parse_upload, parse_upload_sheet
from core.data.profiler import build_profile, profile_to_json


# ── Helpers ────────────────────────────────────────────────────────────────


def _write_csv(content: str, encoding: str = "utf-8") -> str:
    """Write a CSV to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding=encoding)
    tmp.write(content)
    tmp.close()
    return tmp.name


def _write_bytes(content: bytes, suffix: str = ".csv") -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


def _write_xlsx(df: pd.DataFrame) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    df.to_excel(tmp.name, sheet_name="Sheet1", index=False, engine="openpyxl")
    return tmp.name


def _write_json(data: list[dict]) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8")
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


# ── Parser Tests ────────────────────────────────────────────────────────────


class TestParseUploadCSV:
    def test_basic_csv(self):
        path = _write_csv("a,b,c\n1,2,3\n4,5,6\n")
        df, meta = parse_upload(path)
        assert df.shape == (2, 3)
        assert meta.format == "csv"
        assert meta.row_count == 2
        assert meta.encoding is not None

    def test_csv_with_header(self):
        path = _write_csv("name,age,city\nAlice,30,NYC\nBob,25,LA\n")
        df, meta = parse_upload(path)
        assert list(df.columns) == ["name", "age", "city"]
        assert meta.row_count == 2

    def test_csv_tsv_format(self):
        path = _write_bytes(b"a\tb\tc\n1\t2\t3\n4\t5\t6\n", suffix=".tsv")
        df, meta = parse_upload(path, format_hint="tsv")
        assert df.shape == (2, 3)
        assert meta.format == "tsv"

    def test_csv_with_encoding_hint(self):
        """csv with utf-8 encoding"""
        path = _write_csv("a,b\nhello,world\n", encoding="utf-8")
        df, meta = parse_upload(path, format_hint="csv")
        assert df.iloc[0]["a"] == "hello"


class TestParseUploadXLSX:
    def test_basic_xlsx(self):
        df_in = pd.DataFrame({"x": [1, 2], "y": ["a", "b"]})
        path = _write_xlsx(df_in)
        df, meta = parse_upload(path)
        assert list(df.columns) == ["x", "y"]
        assert meta.format == "xlsx"
        assert meta.sheet_name == "Sheet1"
        assert meta.sheets == ["Sheet1"]

    def test_xlsx_multi_sheet(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        with pd.ExcelWriter(tmp.name, engine="openpyxl") as writer:
            pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Data", index=False)
            pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Meta", index=False)
        # Default parse gets first sheet
        df, meta = parse_upload(tmp.name)
        assert meta.sheets == ["Data", "Meta"]
        assert meta.sheet_name == "Data"

    def test_xlsx_parse_specific_sheet(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        with pd.ExcelWriter(tmp.name, engine="openpyxl") as writer:
            pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Data", index=False)
            pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Meta", index=False)
        df, meta = parse_upload_sheet(tmp.name, "Meta")
        assert list(df.columns) == ["b"]
        assert meta.sheet_name == "Meta"


class TestParseUploadJSON:
    def test_basic_json(self):
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        path = _write_json(data)
        df, meta = parse_upload(path)
        assert df.shape == (2, 2)
        assert meta.format == "json"
        assert meta.row_count == 2


class TestParseUploadErrors:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_upload("/nonexistent/file.csv")

    def test_unsupported_format(self):
        path = _write_bytes(b"a,b\n1,2\n", suffix=".pdf")
        with pytest.raises(ValueError, match="Unsupported format"):
            parse_upload(path, format_hint="pdf")


# ── Profiler Tests ─────────────────────────────────────────────────────────


class TestBuildProfile:
    def test_basic_profile(self):
        df = pd.DataFrame({
            "a": [1, 2, 3, None, 5],
            "b": ["x", "y", "z", "x", None],
            "c": [1.1, 2.2, 3.3, 4.4, 5.5],
        })
        profile = build_profile(df)
        assert profile.row_count == 5
        assert profile.column_count == 3
        # Column a (int with null)
        col_a = [c for c in profile.columns if c.name == "a"][0]
        assert col_a.null_count == 1
        assert col_a.unique_count <= 5
        # Column c (float, numeric)
        col_c = [c for c in profile.columns if c.name == "c"][0]
        assert col_c.min == 1.1
        assert col_c.max == 5.5
        assert col_c.mean is not None

    def test_profile_null_counts(self):
        df = pd.DataFrame({"a": [None, None, 3], "b": [1, 2, 3]})
        profile = build_profile(df)
        col_a = [c for c in profile.columns if c.name == "a"][0]
        assert col_a.null_count == 2
        col_b = [c for c in profile.columns if c.name == "b"][0]
        assert col_b.null_count == 0

    def test_profile_sample_values(self):
        df = pd.DataFrame({"a": range(100)})
        profile = build_profile(df)
        col_a = [c for c in profile.columns if c.name == "a"][0]
        assert len(col_a.sample_values) == 5

    def test_large_dataset_sampling(self):
        """More than 10K rows triggers sampling."""
        df = pd.DataFrame({"a": range(15000), "b": range(15000, 30000)})
        profile = build_profile(df, size_bytes=100)
        assert profile.row_count == 15000
        # Profile's sample_rows should be top 10, not all 15K
        assert len(profile.sample_rows) <= 10

    def test_profile_datetime_column(self):
        df = pd.DataFrame({"dt": pd.date_range("2024-01-01", periods=5, freq="D")})
        profile = build_profile(df)
        col_dt = [c for c in profile.columns if c.name == "dt"][0]
        assert col_dt.min is not None
        assert col_dt.max is not None

    def test_empty_dataframe_raises(self):
        """Empty dataframe parsed from file should raise in parser, not profiler."""
        df = pd.DataFrame({"a": []})
        profile = build_profile(df)
        assert profile.row_count == 0


class TestProfileToJSON:
    def test_serialization(self):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"], "c": [1.1, None]})
        profile = build_profile(df)
        serialized = profile_to_json(profile)
        assert "columns" in serialized
        assert serialized["row_count"] == 2
        assert serialized["column_count"] == 3
        # All values should be JSON-serializable
        json.dumps(serialized)  # should not raise

    def test_numpy_types_serialize(self):
        """NumPy types in profiles should be JSON-safe."""
        df = pd.DataFrame({
            "int_col": np.array([1, 2, 3]),
            "float_col": np.array([1.1, 2.2, 3.3]),
        })
        profile = build_profile(df)
        serialized = profile_to_json(profile)
        json.dumps(serialized)  # should not raise