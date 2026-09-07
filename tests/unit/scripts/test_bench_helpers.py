"""Unit tests for bench.py pure helpers (no network, no sandbox).

Tests cover ``_normalize_number``, ``_mape_check``, ``_cache_key``,
and ``BenchQuestion`` data model.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, ".")
from scripts.bench import (
    _cache_key,
    _mape_check,
    _normalize_number,
    BenchQuestion,
    _QUESTIONS,
)


class TestNormalizeNumber:
    def test_strips_currency(self):
        assert _normalize_number("$5,035,600.021") == 5035600.021

    def test_strips_percent(self):
        assert _normalize_number("99.5%") == 99.5

    def test_handles_unicode_minus(self):
        assert _normalize_number("−42.5") == -42.5

    def test_handles_en_dash(self):
        assert _normalize_number("–3.14") == -3.14

    def test_thousands_separator(self):
        assert _normalize_number("5,035,600") == 5035600.0

    def test_simple_integer(self):
        assert _normalize_number("5035600") == 5035600.0

    def test_tiny_value(self):
        assert _normalize_number("0.001") == 0.001

    def test_float_without_commas(self):
        assert _normalize_number("125890.0005") == 125890.0005

    def test_returns_none_on_empty(self):
        assert _normalize_number("") is None

    def test_returns_none_on_garbage(self):
        assert _normalize_number("abc") is None

    def test_strips_whitespace(self):
        assert _normalize_number("  5035600.021  ") == 5035600.021

    def test_strips_usd_prefix(self):
        assert _normalize_number("USD 500") == 500.0

    def test_negative_with_thousands(self):
        assert _normalize_number("-$1,234.56") == -1234.56


class TestMapeCheck:
    def test_exact_match(self):
        passed, err = _mape_check(100.0, 100.0)
        assert passed is True
        assert err == 0.0

    def test_within_one_percent(self):
        passed, err = _mape_check(101.0, 100.0)
        assert passed is True
        assert err == 1.0

    def test_exceeds_one_percent(self):
        passed, err = _mape_check(102.0, 100.0)
        assert passed is False
        assert err == 2.0

    def test_custom_tolerance(self):
        passed, _ = _mape_check(105.0, 100.0, pct=0.05)
        assert passed is True

    def test_abs_tolerance_bypasses_pct(self):
        passed, _ = _mape_check(0.005, 0.001, pct=0.01, abs_tol=0.005)
        assert passed is True

    def test_abs_tolerance_exact_boundary(self):
        """diff == abs_tol is inclusive — should pass."""
        passed, _ = _mape_check(0.006, 0.001, pct=0.01, abs_tol=0.005)
        assert passed is True

    def test_zero_expected_zero_actual(self):
        passed, err = _mape_check(0.0, 0.0)
        assert passed is True
        assert err == 0.0

    def test_zero_expected_nonzero_actual(self):
        passed, err = _mape_check(0.1, 0.0)
        assert passed is False
        assert err == float("inf")

    def test_large_numbers_small_diff(self):
        passed, _ = _mape_check(5000001.0, 5000000.0)
        assert passed is True


class TestCacheKey:
    def test_deterministic(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert _cache_key("model-x", msgs) == _cache_key("model-x", msgs)

    def test_different_model_different_key(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert _cache_key("model-a", msgs) != _cache_key("model-b", msgs)

    def test_different_messages_different_key(self):
        assert _cache_key("m", [{"role": "user", "content": "hello"}]) != _cache_key(
            "m", [{"role": "user", "content": "world"}]
        )

    def test_is_sha256_hex(self):
        key = _cache_key("m", [{"role": "user", "content": "hello"}])
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_key_order_matters(self):
        """Message list order is significant for LLM context."""
        msgs = [
            {"role": "system", "content": "you are"},
            {"role": "user", "content": "hello"},
        ]
        assert _cache_key("m", msgs) != _cache_key("m", list(reversed(msgs)))


class TestQuestionSuite:
    def test_has_10_questions(self):
        assert len(_QUESTIONS) == 10

    def test_all_questions_have_unique_ids(self):
        ids = [q.id for q in _QUESTIONS]
        assert len(ids) == len(set(ids))

    def test_all_questions_have_expected_artifact_types(self):
        for q in _QUESTIONS:
            assert q.expected_artifact_types, f"Q{q.id} missing artifacts"

    def test_all_questions_have_csv(self):
        for q in _QUESTIONS:
            assert q.csv_basename

    def test_q1_tolerance_abs(self):
        q1 = next(q for q in _QUESTIONS if q.id == 1)
        assert q1.tolerance_abs is not None
        assert "min" in q1.tolerance_abs

    def test_q10_no_number_assertions(self):
        """Q10 is artifact-checked only (figures) — no numeric assertions.

        The old has_figures=1.0 sentinel was treated as a number to find
        in the explanation text and hard-failed correct answers citing
        real numbers.
        """
        q10 = next(q for q in _QUESTIONS if q.id == 10)
        import pandas as pd

        df = pd.DataFrame({"a": [1]})
        expected = q10.compute_expected(df)
        assert expected == {}

    @pytest.mark.parametrize("qid", [2, 3, 4, 5, 6, 7, 8, 9])
    def test_q2_to_q9_have_compute_expected(self, qid):
        q = next(qq for qq in _QUESTIONS if qq.id == qid)
        assert q.compute_expected is not None, f"Q{qid} missing compute_expected"