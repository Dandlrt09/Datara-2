"""Unit tests for bench.py pure helpers (no network, no sandbox).

Tests cover ``_normalize_number``, ``_mape_check``, ``_cache_key``,
and ``BenchQuestion`` data model.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, ".")
from scripts.bench import (
    _build_report,
    _cache_key,
    _mape_check,
    _normalize_number,
    _parse_args,
    _DEFAULT_MODEL,
    BenchQuestion,
    QuestionResult,
    _QUESTIONS,
)


class TestParseArgs:
    def test_model_defaults_to_default_model(self):
        args = _parse_args([])
        assert args.model == _DEFAULT_MODEL == "z-ai/glm-5.3-flash"

    def test_model_override(self):
        args = _parse_args(["--model", "gpt-4o-mini"])
        assert args.model == "gpt-4o-mini"

    def test_limit_default_unchanged(self):
        args = _parse_args([])
        assert args.limit == 10

    def test_existing_flags_unchanged(self):
        args = _parse_args(["--limit", "3", "--cache", "--seed-experiment"])
        assert args.limit == 3
        assert args.cache is True
        assert args.seed_experiment is True
        assert args.model == _DEFAULT_MODEL


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
    def test_has_11_questions(self):
        assert len(_QUESTIONS) == 11

    def test_all_questions_have_unique_ids(self):
        ids = [q.id for q in _QUESTIONS]
        assert len(ids) == len(set(ids))

    def test_all_questions_have_expected_artifact_types(self):
        for q in _QUESTIONS:
            # Q11 expects zero artifacts (empty set) - that's valid
            assert q.expected_artifact_types is not None, f"Q{q.id} missing artifacts"

    def test_all_questions_have_csv(self):
        for q in _QUESTIONS:
            assert q.csv_basename

    def test_q1_tolerance_abs(self):
        q1 = next(q for q in _QUESTIONS if q.id == 1)
        assert q1.tolerance_abs is not None
        assert "min" in q1.tolerance_abs

    def test_q10_and_q11_no_number_assertions(self):
        """Q10 and Q11 are artifact-checked only — no numeric assertions.
        
        Q10 expects figures, Q11 expects zero artifacts.
        The old has_figures=1.0 sentinel was treated as a number to find
        in the explanation text and hard-failed correct answers citing
        real numbers.
        """
        for qid in [10, 11]:
            q = next(q for q in _QUESTIONS if q.id == qid)
            import pandas as pd
            df = pd.DataFrame({"a": [1]})
            expected = q.compute_expected(df)
            assert expected == {}

    @pytest.mark.parametrize("qid", [2, 3, 4, 5, 6, 7, 8, 9, 10])
    def test_q2_to_q10_have_compute_expected(self, qid):
        q = next(qq for qq in _QUESTIONS if qq.id == qid)
        assert q.compute_expected is not None, f"Q{qid} missing compute_expected"


def _qr(qid: int, status: str = "pass", **overrides) -> QuestionResult:
    """Build a QuestionResult with required fields and optional overrides."""
    base = dict(
        id=qid,
        question=f"question {qid}",
        csv=f"q{qid}.csv",
        status=status,
        reason="ok" if status == "pass" else "something failed",
        artifacts_expected=["table"],
        artifacts_found=["table"],
    )
    base.update(overrides)
    return QuestionResult(**base)


def _build(results, **kwargs) -> dict:
    """Call _build_report with standard defaults overridable per test."""
    defaults = dict(
        model="z-ai/glm-5.3-flash",
        cache_enabled=False,
        limit=10,
        executed_ids=[r.id for r in results],
        total_suite=len(_QUESTIONS),
        total_cost=0.5,
        total_duration=12.0,
    )
    defaults.update(kwargs)
    return _build_report(results, **defaults)


class TestBuildReport:
    def test_model_field_is_effective_model(self):
        report = _build([_qr(1)], model="gpt-4o-mini")
        assert report["model"] == "gpt-4o-mini"

    def test_cache_and_limit_propagated(self):
        report = _build([_qr(1)], cache_enabled=True, limit=5)
        assert report["cache_enabled"] is True
        assert report["limit"] == 5

    def test_totals_propagated(self):
        report = _build([_qr(1)], total_cost=1.25, total_duration=30.5)
        assert report["total_cost_usd"] == 1.25
        assert report["total_duration_seconds"] == 30.5

    def test_total_suite_questions(self):
        report = _build([_qr(1)])
        assert report["total_suite_questions"] == len(_QUESTIONS) == 11

    def test_executed_ids_match_results(self):
        results = [_qr(i) for i in (1, 3, 5)]
        report = _build(results)
        assert report["executed_ids"] == [1, 3, 5]

    def test_full_suite_has_no_skipped(self):
        results = [_qr(q.id) for q in _QUESTIONS]
        report = _build(results)
        assert report["skipped_ids"] == []

    def test_subset_run_lists_skipped_ids(self):
        """Default --limit 10 run must visibly omit Q11 (AGENTS.md gotcha)."""
        results = [_qr(q.id) for q in _QUESTIONS if q.id != 11]
        report = _build(results)
        assert report["executed_ids"] == [q.id for q in _QUESTIONS if q.id != 11]
        assert report["skipped_ids"] == [11]

    def test_skipped_ids_exclude_executed_subset(self):
        results = [_qr(i) for i in (2, 5)]
        report = _build(results)
        assert report["skipped_ids"] == [1, 3, 4, 6, 7, 8, 9, 10, 11]

    def test_executed_ids_argument_is_authoritative(self):
        """executed_ids is passed in, not derived — a caller may pass ids
        for questions whose results were filtered elsewhere."""
        report = _build([_qr(1)], executed_ids=[1, 2])
        assert report["executed_ids"] == [1, 2]
        assert report["skipped_ids"] == [3, 4, 5, 6, 7, 8, 9, 10, 11]

    def test_per_question_fields_preserved(self):
        r = _qr(
            7,
            status="fail",
            reason="Sandbox error: runtime_error: boom",
            artifacts_found=[],
            cost_usd=0.01,
            duration_seconds=3.5,
            tokens_in=100,
            tokens_out=200,
            llm_explanation="explanation text",
            sandbox_text="sandbox text",
        )
        report = _build([r])
        entry = report["questions"][0]
        assert entry["id"] == 7
        assert entry["question"] == "question 7"
        assert entry["csv"] == "q7.csv"
        assert entry["status"] == "fail"
        assert entry["reason"] == "Sandbox error: runtime_error: boom"
        assert entry["flaky"] is False
        assert entry["artifacts_expected"] == ["table"]
        assert entry["artifacts_found"] == []
        assert entry["cost_usd"] == 0.01
        assert entry["duration_seconds"] == 3.5
        assert entry["tokens_in"] == 100
        assert entry["tokens_out"] == 200
        assert entry["llm_explanation"] == "explanation text"
        assert entry["sandbox_text"] == "sandbox text"

    def test_flaky_flag_true_on_flaky_status(self):
        report = _build([_qr(2, status="flaky")])
        assert report["questions"][0]["flaky"] is True

    def test_numbers_failed_serialized(self):
        failed = [{"metric": "sum", "expected": 100.0}]
        report = _build(
            [_qr(1, numbers_total=1, numbers_matched=0, numbers_failed=failed)]
        )
        entry = report["questions"][0]
        assert entry["numbers_total"] == 1
        assert entry["numbers_matched"] == 0
        assert entry["numbers_failed"] == failed

    def test_timestamp_is_iso_utc(self):
        report = _build([_qr(1)])
        assert report["timestamp"].endswith("Z")
        assert "T" in report["timestamp"]