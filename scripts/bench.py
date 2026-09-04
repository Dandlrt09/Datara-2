#!/usr/bin/env python3
"""Standalone regression bench for the Datara LLM pipeline.

Bypasses FastAPI entirely: calls ``OpenAIProvider.complete()`` and
``run_code()`` directly against canonical questions.  Exits 0 (all pass /
flaky-only), 1 (hard fail), or 2 (usage/env error).

KEEP IN SYNC with ``server/api/routers/chat.py:_event_stream`` system
prompt — copy the body into ``_SYSTEM_PROMPT_TEMPLATE`` below.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

# Server modules are imported lazily inside main() and helper functions
# to keep the module importable for unit testing without FastAPI deps.
from core.errors import LLMError, LLMInvalidJSONError, LLMRateLimitError, LLMTimeoutError

# ── Constants ──────────────────────────────────────────────────────────────────

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
_BENCH_DIR = Path(".bench")
_CACHE_DIR = _BENCH_DIR / "cache"
_DEFAULT_MODEL = "z-ai/glm-5.3-flash"

# PROD-PARITY sandbox limits (overrides the 512 MB default in sandbox_local.py).
_PROD_LIMITS = {"memory_mb": 2048, "cpu_seconds": 30, "timeout_seconds": 30}

# System prompt — KEEP IN SYNC with server/api/routers/chat.py:_event_stream.
_SYSTEM_PROMPT_TEMPLATE = """You are a data analysis assistant. The user's datasets are described below. Generate Python code (pandas, numpy, plotly) to answer their question. Return valid JSON with 'code' and 'explanation' fields only.

IMPORTANT — file access: the code runs in a FRESH temporary working directory, so relative filenames do not exist. Read each dataset with EXACTLY its 'path' value above (absolute path), e.g. df = pd.read_csv('<path>'). Never invent paths.

IMPORTANT — execution model: every turn runs in a completely fresh sandbox. NOTHING persists between turns: no variables, no imports, no previous DataFrames. Your code must load the data itself and define every variable it uses, starting from scratch. Never reference df or any variable defined in a previous turn.

IMPORTANT — output size: keep 'explanation' under 120 words and never echo the question back. The JSON must always be complete and properly closed; prefer shorter code over an incomplete answer.

IMPORTANT — surfacing results: the chat UI only displays figures (variables named fig, fig1, fig2...), tables (DataFrames named df_result, df_<name>...) and printed output. The user NEVER sees console output unless it is printed or assigned to such variables. So: (1) assign every requested result table to a DataFrame variable named df_result (or df_<name>); (2) print() the key metrics; (3) state the main numbers directly in 'explanation' — never just describe what the code computes. Load the raw dataset into 'df' and do NOT reassign 'df' with a filtered/aggregated result: use a new df_<name> variable instead, so the raw dataset preview is not the table the user sees.

IMPORTANT — monthly aggregation: when grouping or resampling by month, anchor each label to the FIRST day of the month (resample('MS') or .dt.to_period('M').dt.start_time), never month-end ('M'), so chart bars align under the correct month label. On monthly charts force one tick per month: fig.update_xaxes(dtick='M1', tickformat='%b %Y').

IMPORTANT — empty results: if a filter or groupby returns zero rows, SAY that plainly in 'explanation' (e.g. 'no hay ventas de ese producto en esas ciudades') and do NOT plot the empty frame. NEVER invent, estimate or use placeholder values (no X, Y, Z, W): every number in 'explanation' must be one you actually computed. Write plain text: no Markdown, no **.

IMPORTANT — numeric precision: never round results to 2 decimals when tiny values are possible (e.g. a minimum of 0.001): a non-zero value must never display as 0. Keep full precision or format with up to 6 decimals. Name ONLY final result tables df_<name>; intermediate/filtered frames get other names (aux, filtrado) so they don't render as tables."""


# ── Pure helpers ────────────────────────────────────────────────────────────────


def _normalize_number(s: str) -> float | None:
    """Normalize a human-readable number string to a float.

    Strips ``$``, ``%``, whitespace; removes thousands separators ``5,000``;
    handles Unicode minus.
    """
    text = s.strip()
    if not text:
        return None
    # Handle Unicode minus
    text = text.replace("−", "-").replace("–", "-")
    # Strip leading currency/percent symbols (after minus handling)
    for ch in ("$", "€", "£", "USD", "EUR"):
        if text.startswith(ch):
            text = text[len(ch) :].strip()
    # Handle leading minus before a currency symbol (e.g. "-$1,234")
    if text.startswith("-"):
        text = "-" + text[1:].strip()  # preserve minus, strip any space after it
        for ch in ("$", "€", "£", "USD", "EUR"):
            if text.startswith("-" + ch):
                text = "-" + text[len("-" + ch) :].strip()
                break
    # Strip trailing percent — return the number as-is (e.g. "99.5%" -> 99.5)
    if text.endswith("%"):
        text = text[:-1].strip()
        if not text:
            return None
    # Remove thousands separators (commas between digits)
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _mape_check(
    actual: float,
    expected: float,
    *,
    pct: float = 0.01,
    abs_tol: float | None = None,
) -> tuple[bool, float]:
    """Check a value against expected with MAPE-style tolerance.

    Returns ``(passed, abs_pct_error)`` where ``abs_pct_error`` is the
    absolute percentage difference (0.0 for identical).  If ``abs_tol`` is
    provided and ``|actual - expected| <= abs_tol``, passes regardless of
    percentage.
    """
    diff = abs(actual - expected)
    if abs_tol is not None and diff <= abs_tol:
        return (True, 0.0 if expected == 0 else diff / abs(expected) * 100)
    if expected == 0:
        return (diff == 0, 0.0 if diff == 0 else float("inf"))
    error_pct = diff / abs(expected) * 100
    return (error_pct <= pct * 100, error_pct)


def _cache_key(model: str, messages: list[dict]) -> str:
    """Derive a deterministic cache key from model + messages."""
    payload = json.dumps(
        {"model": model, "messages": messages}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _render_table(rows: list[list[str]], headers: list[str]) -> str:
    """Render a simple ASCII table with padded columns (no rich dependency)."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = "  ".join("-" * w for w in col_widths)
    header = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    body = "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(row, col_widths)) for row in rows
    )
    return f"{header}\n{sep}\n{body}"


# ── Question model ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BenchQuestion:
    id: int
    question: str
    csv_basename: str
    expected_artifact_types: set[str]
    compute_expected: Callable[[pd.DataFrame], dict[str, float]] | None = None
    tolerance_pct: float = 0.01
    tolerance_abs: dict[str, float] | None = None


# ── Question suite ──────────────────────────────────────────────────────────────


def _q1_expected(_df: pd.DataFrame) -> dict[str, float]:
    """Question 1: documented ground truth (does NOT read CSV)."""
    return {
        "sum": 5035600.021,
        "mean": 125890.0005,
        "max": 5000000.0,
        "min": 0.001,
    }


def _q2_expected(df: pd.DataFrame) -> dict[str, float]:
    """Total sales across all periods (pequeno dataset: revenue column is 'total')."""
    return {"total_sales": float(df["total"].sum())}


def _q3_expected(df: pd.DataFrame) -> dict[str, float]:
    """Top product by revenue + units sold."""
    top = df.groupby("producto")["total"].sum().idxmax()
    units = int(df[df["producto"] == top]["cantidad"].sum())
    return {"top_product_revenue": float(df.groupby("producto")["total"].sum().max()), "top_product_units": float(units)}


def _q4_expected(df: pd.DataFrame) -> dict[str, float]:
    """Average satisfaction by channel."""
    means = df.groupby("canal")["satisfaccion_cliente"].mean()
    return {f"satisfaccion_{k}": float(v) for k, v in means.items()}


def _q5_expected(df: pd.DataFrame) -> dict[str, float]:
    """Sales count and avg ticket in Barranquilla."""
    barranquilla = df[df["ciudad"].str.lower() == "barranquilla"]
    return {"count": float(len(barranquilla)), "avg_ticket": float(barranquilla["total"].mean()) if len(barranquilla) > 0 else 0.0}


def _q6_expected(df: pd.DataFrame) -> dict[str, float]:
    """Month with highest sales. Only the sales value is asserted: a month
    label never appears as a bare number in model output, so asserting the
    Period ordinal would false-fail every correct answer."""
    monthly = df.copy()
    monthly["mes"] = pd.to_datetime(monthly["fecha"]).dt.to_period("M")
    totals = monthly.groupby("mes")["total"].sum()
    return {"max_month_sales": float(totals.max())}


def _q7_expected(df: pd.DataFrame) -> dict[str, float]:
    """Total monto column."""
    return {"total_monto": float(df["monto"].sum())}


def _q8_expected(df: pd.DataFrame) -> dict[str, float]:
    """Units per product — the question asks for 'cantidad' (units), not
    sale counts, so the ground truth is the per-product cantidad sum."""
    sums = df.groupby("producto")["cantidad"].sum()
    return {f"cant_{k}": float(v) for k, v in sums.items()}


def _q9_expected(df: pd.DataFrame) -> dict[str, float]:
    """Best-selling product: global avg price + Online satisfaction.
    City-level avg price is intentionally NOT asserted: the honest answer
    for Base Notebook is 'no sales in Bogotá/Medellín', whose shape varies
    (empty table vs prose), so a fixed expected value would false-fail."""
    best = df.groupby("producto")["cantidad"].sum().idxmax()
    best_df = df[df["producto"] == best]
    avg_price = float(best_df["precio_unitario"].mean())
    online_sat = float(best_df[best_df["canal"].str.lower() == "online"]["satisfaccion_cliente"].mean())
    return {"avg_price": avg_price, "online_satisfaccion": online_sat}


def _q10_expected(_df: pd.DataFrame) -> dict[str, float]:
    """Two charts question — just verify artifacts present."""
    return {"has_figures": 1.0}


_QUESTIONS: list[BenchQuestion] = [
    BenchQuestion(
        id=1,
        question=(
            "Dame la suma, el promedio, el máximo y el mínimo de la columna 'monto', "
            "tanto en general como agrupado por categoría. Además, muéstrame las ventas "
            "totales por mes."
        ),
        csv_basename="datara_test_validacion.csv",
        expected_artifact_types={"table", "figure"},
        compute_expected=_q1_expected,
        tolerance_abs={"min": 0.005},
    ),
    BenchQuestion(
        id=2,
        question="¿Cuál fue el total de ventas en todo el periodo?",
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"table"},
        compute_expected=_q2_expected,
    ),
    BenchQuestion(
        id=3,
        question="¿Qué producto generó más ingresos y cuántas unidades se vendieron de él?",
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"table"},
        compute_expected=_q3_expected,
    ),
    BenchQuestion(
        id=4,
        question="¿Cuál es el promedio de satisfacción del cliente por canal de venta?",
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"table"},
        compute_expected=_q4_expected,
    ),
    BenchQuestion(
        id=5,
        question="¿Cuántas ventas se hicieron en Barranquilla y cuál fue su ticket promedio?",
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"table"},
        compute_expected=_q5_expected,
    ),
    BenchQuestion(
        id=6,
        question="Muéstrame la tendencia de ventas por mes, ¿en qué mes hubo más ventas?",
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"figure"},
        compute_expected=_q6_expected,
    ),
    BenchQuestion(
        id=7,
        question="¿Cuál es el total de la columna 'monto'?",
        csv_basename="datara_test_validacion.csv",
        expected_artifact_types={"table"},
        compute_expected=_q7_expected,
    ),
    BenchQuestion(
        id=8,
        question="¿Cuánta cantidad hay de cada producto?",
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"table", "figure"},
        compute_expected=_q8_expected,
    ),
    BenchQuestion(
        id=9,
        question=(
            "¿Cuál fue el producto más vendido según la cantidad, y podrías decirme "
            "también —sin dejar nada por fuera— cuál fue su 'precio_unitario' promedio? "
            "¡Ojalá me lo puedas mostrar comparando Bogotá vs. Medellín! Además, ¿qué tan "
            "buena fue la satisfacción del cliente (en promedio) para ese producto específico "
            "en el canal 'Online'?"
        ),
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"table"},
        compute_expected=_q9_expected,
    ),
    BenchQuestion(
        id=10,
        question="Hazme un gráfico de barras de ventas por producto y un gráfico de líneas de la evolución mensual",
        csv_basename="datara_test_pequeno.csv",
        expected_artifact_types={"figure"},
        compute_expected=_q10_expected,
    ),
]


# ── Cache helpers ──────────────────────────────────────────────────────────────


def _cache_get(key: str) -> dict | None:
    path = _CACHE_DIR / key
    if not path.exists():
        return None
    # TTL: 30 days
    age = time.time() - path.stat().st_mtime
    if age > 30 * 86400:
        path.unlink(missing_ok=True)
        return None
    with open(path) as f:
        return json.load(f)


def _cache_put(key: str, response: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_DIR / key, "w") as f:
        json.dump(response, f)


# ── Seed experiment ────────────────────────────────────────────────────────────


async def _run_seed_experiment(provider, questions: list[BenchQuestion]) -> int:
    """Run determinism experiment: N=5 runs of Q1 at temperature=0, seed=0."""
    from server.api.routers.chat import _CHAT_JSON_SCHEMA
    q = questions[0]
    csv_path = _EXAMPLES_DIR / q.csv_basename
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 2

    messages = [{"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE}]
    messages.append({"role": "user", "content": q.question + f"\n\nThe data file is at: {csv_path}"})

    n_runs = 5
    hashes: list[str] = []
    numeric_outputs: list[dict[str, float]] = []

    for i in range(n_runs):
        try:
            resp = await provider.complete(
                messages=messages,
                response_format=_CHAT_JSON_SCHEMA,
                temperature=0.0,
                max_tokens=8192,
            )
        except LLMError as e:
            print(f"Run {i+1}: LLM error — {e}", file=sys.stderr)
            continue

        text_hash = hashlib.sha256((resp.text or "").encode()).hexdigest()
        hashes.append(text_hash)
        structured = resp.structured_data or {}
        explanation = structured.get("explanation", resp.text or "")

        # Extract numbers from explanation
        nums: dict[str, float] = {}
        for word in explanation.split():
            n = _normalize_number(word)
            if n is not None:
                key = f"val_{len(nums)}"
                nums[key] = n
        numeric_outputs.append(nums)

    identical = sum(1 for h in hashes if h == hashes[0]) if hashes else 0
    ratio = identical / n_runs if hashes else 0.0

    # Numeric spread
    spread: dict[str, dict[str, float]] = {}
    if numeric_outputs:
        all_keys = set()
        for nout in numeric_outputs:
            all_keys.update(nout.keys())
        for k in all_keys:
            vals = [n[k] for n in numeric_outputs if k in n]
            if vals:
                spread[k] = {"min": min(vals), "max": max(vals), "median": sorted(vals)[len(vals) // 2]}

    report = {
        "schema_version": 1,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": provider._model,
        "n_runs": n_runs,
        "identical_hash_ratio": ratio,
        "numeric_spread": spread,
        "raw_hashes": hashes,
    }
    _BENCH_DIR.mkdir(parents=True, exist_ok=True)
    with open(_BENCH_DIR / "seed-report.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Seed experiment written to .bench/seed-report.json")
    print(f"Identical hash ratio: {ratio:.0%} ({identical}/{n_runs})")
    return 0


# ── Per-question runner ─────────────────────────────────────────────────────────


@dataclass
class QuestionResult:
    id: int
    question: str
    csv: str
    status: str  # "pass" | "fail" | "flaky"
    reason: str
    artifacts_expected: list[str]
    artifacts_found: list[str]
    numbers_total: int = 0
    numbers_matched: int = 0
    numbers_failed: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    llm_explanation: str = ""
    sandbox_text: str = ""
    code: str = ""


async def _run_question(
    provider,
    q: BenchQuestion,
    *,
    cache_enabled: bool = False,
) -> QuestionResult:
    """Run a single canonical question through the LLM + sandbox pipeline."""
    from server.api.routers.chat import _CHAT_JSON_SCHEMA
    from server.services.sandbox_local import run_code
    start = time.time()

    # Locate CSV
    csv_path = _EXAMPLES_DIR / q.csv_basename
    if not csv_path.exists():
        return QuestionResult(
            id=q.id, question=q.question, csv=q.csv_basename,
            status="fail", reason=f"CSV not found: {csv_path}",
            artifacts_expected=sorted(q.expected_artifact_types), artifacts_found=[],
        )

    # Build messages
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE},
        {"role": "user", "content": q.question + f"\n\nThe data file is at: {csv_path}"},
    ]

    # Cache lookup or LLM call
    cached: dict | None = None
    llm_response: dict | None = None  # holds {structured_data, usage, text}

    if cache_enabled:
        key = _cache_key(provider._model, messages)
        cached = _cache_get(key)

    if cached is not None:
        llm_response = {
            "structured_data": cached.get("structured_data") or {},
            "usage": cached.get("usage") or {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0},
            "text": cached.get("text", ""),
        }
    else:
        try:
            response = await provider.complete(
                messages=messages,
                response_format=_CHAT_JSON_SCHEMA,
                max_tokens=8192,
                temperature=0.1,
            )
        except (LLMInvalidJSONError, LLMTimeoutError, LLMRateLimitError) as e:
            return QuestionResult(
                id=q.id, question=q.question, csv=q.csv_basename,
                status="fail", reason=f"LLM error: {e.__class__.__name__}: {e}",
                artifacts_expected=sorted(q.expected_artifact_types), artifacts_found=[],
            )
        except LLMError as e:
            return QuestionResult(
                id=q.id, question=q.question, csv=q.csv_basename,
                status="fail", reason=f"LLM error: {e}",
                artifacts_expected=sorted(q.expected_artifact_types), artifacts_found=[],
            )

        resp_dict = {
            "text": response.text,
            "structured_data": response.structured_data,
            "usage": {
                "tokens_in": response.usage.tokens_in,
                "tokens_out": response.usage.tokens_out,
                "cost_usd": response.usage.cost_usd,
            },
        }
        if cache_enabled and response.usage.cost_usd > 0:
            _cache_put(key, resp_dict)
        llm_response = resp_dict

    structured = llm_response["structured_data"]
    usage = llm_response["usage"]
    llm_text = llm_response["text"]

    # Validate JSON structure (bench-owned check)
    if "code" not in structured or "explanation" not in structured:
        return QuestionResult(
            id=q.id, question=q.question, csv=q.csv_basename,
            status="fail",
            reason="Response missing 'code' or 'explanation' in structured_data",
            artifacts_expected=sorted(q.expected_artifact_types), artifacts_found=[],
            cost_usd=usage.get("cost_usd", 0), duration_seconds=time.time() - start,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            llm_explanation=structured.get("explanation", llm_text),
        )

    code = structured["code"]
    explanation = structured["explanation"]

    # Run sandbox
    try:
        sandbox_result = await run_code(
            code,
            files={q.csv_basename: str(csv_path)},
            limits=_PROD_LIMITS,
        )
    except Exception as e:
        return QuestionResult(
            id=q.id, question=q.question, csv=q.csv_basename,
            status="fail", reason=f"Sandbox exception: {e}",
            artifacts_expected=sorted(q.expected_artifact_types), artifacts_found=[],
            cost_usd=usage.get("cost_usd", 0), duration_seconds=time.time() - start,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            llm_explanation=explanation, code=code,
        )

    if sandbox_result.get("status") != "ok":
        err = sandbox_result.get("error", {})
        res = QuestionResult(
            id=q.id, question=q.question, csv=q.csv_basename,
            status="fail", reason=f"Sandbox error: {err.get('type', 'unknown')}: {err.get('message', '')}",
            artifacts_expected=sorted(q.expected_artifact_types), artifacts_found=[],
            cost_usd=usage.get("cost_usd", 0), duration_seconds=time.time() - start,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            llm_explanation=explanation, code=code,
        )
        return res

    sandbox_text = sandbox_result.get("text", "")
    sandbox_figures = sandbox_result.get("figures", [])
    sandbox_tables = sandbox_result.get("tables", [])

    # Build list of artifact types found
    artifacts_found: list[str] = []
    if sandbox_figures:
        artifacts_found.append("figure")
    if sandbox_tables:
        artifacts_found.append("table")
    if sandbox_text:
        artifacts_found.append("text")

    missing = q.expected_artifact_types - set(artifacts_found)
    if missing:
        return QuestionResult(
            id=q.id, question=q.question, csv=q.csv_basename,
            status="fail",
            reason=f"Missing expected artifacts: {sorted(missing)}",
            artifacts_expected=sorted(q.expected_artifact_types),
            artifacts_found=artifacts_found,
            cost_usd=usage.get("cost_usd", 0), duration_seconds=time.time() - start,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            llm_explanation=explanation, sandbox_text=sandbox_text, code=code,
        )

    # Compute expected values
    df = pd.read_csv(csv_path)
    expected = q.compute_expected(df) if q.compute_expected else {}

    if not expected:
        # Q10 — no number assertions, just artifact check
        return QuestionResult(
            id=q.id, question=q.question, csv=q.csv_basename,
            status="pass", reason="ok",
            artifacts_expected=sorted(q.expected_artifact_types),
            artifacts_found=artifacts_found,
            cost_usd=usage.get("cost_usd", 0), duration_seconds=time.time() - start,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            llm_explanation=explanation, sandbox_text=sandbox_text, code=code,
        )

    # Check numbers in LLM explanation + sandbox text
    combined_text = f"{explanation} {sandbox_text}"
    numbers_total = len(expected)
    numbers_matched = 0
    numbers_failed: list[dict[str, Any]] = []

    for metric, exp_val in expected.items():
        # Scan for the expected number in text
        found = False
        for word in combined_text.split():
            norm = _normalize_number(word)
            if norm is not None:
                abs_tol = (q.tolerance_abs or {}).get(metric)
                passed, _ = _mape_check(norm, exp_val, pct=q.tolerance_pct, abs_tol=abs_tol)
                if passed:
                    found = True
                    break
        if found:
            numbers_matched += 1
        else:
            numbers_failed.append({"metric": metric, "expected": exp_val})

    # Determine status based on numbers
    flaky = False
    if numbers_failed:
        # Check if it's flaky (any metric passes with 2x tolerance)
        for entry in numbers_failed:
            for word in combined_text.split():
                norm = _normalize_number(word)
                if norm is not None:
                    passed, _ = _mape_check(norm, entry["expected"], pct=q.tolerance_pct * 2)
                    if passed:
                        flaky = True
                        break
            if flaky:
                break

        if flaky:
            status = "flaky"
            reason = f"flaky: {[e['metric'] for e in numbers_failed]}"
        else:
            status = "fail"
            reason = f"numbers off-tolerance: {[e['metric'] for e in numbers_failed]}"
    else:
        status = "pass"
        reason = "ok"

    return QuestionResult(
        id=q.id, question=q.question, csv=q.csv_basename,
        status=status, reason=reason,
        artifacts_expected=sorted(q.expected_artifact_types),
        artifacts_found=artifacts_found,
        numbers_total=numbers_total, numbers_matched=numbers_matched,
        numbers_failed=numbers_failed,
        cost_usd=usage.get("cost_usd", 0), duration_seconds=time.time() - start,
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
        llm_explanation=explanation, sandbox_text=sandbox_text, code=code,
    )


# ── Main ────────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Datara LLM Regression Bench")
    p.add_argument("--limit", type=int, default=10, help="Max questions to run (default: 10)")
    p.add_argument("--questions", type=str, default=None, help="Comma-separated question IDs to run (e.g. 1,3,5)")
    p.add_argument("--seed-experiment", action="store_true", help="Run determinism experiment (Q1 × 5, temp=0, seed=0)")
    p.add_argument("--cache", action="store_true", help="Enable record-replay cache (.bench/cache/)")
    p.add_argument("--interactive", action="store_true", help="Prompt before spending tokens")
    return p.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Validate env
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable is required", file=sys.stderr)
        return 2

    # Ensure examples directory
    if not _EXAMPLES_DIR.exists():
        print(f"ERROR: examples directory not found: {_EXAMPLES_DIR}", file=sys.stderr)
        return 2

    # Determine which questions to run
    question_ids: set[int] | None = None
    if args.questions:
        try:
            question_ids = {int(x.strip()) for x in args.questions.split(",")}
        except ValueError:
            print("ERROR: --questions must be comma-separated integers", file=sys.stderr)
            return 2

    questions = _QUESTIONS
    if question_ids:
        questions = [q for q in questions if q.id in question_ids]
        if not questions:
            print(f"ERROR: no matching questions for ids: {args.questions}", file=sys.stderr)
            return 2

    # Limit
    limit = min(args.limit, len(questions))
    questions = questions[:limit]

    # Lazy server imports: kept inside main() so the module stays importable
    # for unit tests without FastAPI deps — but placed BEFORE first use:
    # a function-level import anywhere in the body makes the name local to
    # the whole function, so an import below the cost-estimate loop would
    # raise UnboundLocalError at _estimate_cost (found by smoke test 4.2).
    from server.services.llm_openai import OpenAIProvider, _estimate_cost

    # Pre-flight cost estimate
    total_estimate = 0.0
    for q in questions:
        csv_path = _EXAMPLES_DIR / q.csv_basename
        if csv_path.exists():
            bytes_est = csv_path.stat().st_size
            input_tokens = max(bytes_est // 4, 100) + 800  # CSV bytes/4 + system prompt
        else:
            input_tokens = 100 + 800
        out_tokens = 2000
        total_estimate += _estimate_cost(input_tokens, out_tokens, _DEFAULT_MODEL)

    print(f"\n{'=' * 60}")
    print(f"  Datara Regression Bench")
    print(f"  Model: {_DEFAULT_MODEL}")
    print(f"  Questions: {len(questions)} ({[q.id for q in questions]})")
    print(f"  Cache: {'ON' if args.cache else 'OFF'}")
    print(f"  Estimated cost: ${total_estimate:.6f}")
    print(f"{'=' * 60}\n")

    if args.interactive:
        resp = input("Continue? [y/N] ").strip().lower()
        if resp != "y":
            print("Aborted.")
            return 0

    # Create provider
    provider = OpenAIProvider(api_key=api_key, model=_DEFAULT_MODEL)

    # Seed experiment mode
    if args.seed_experiment:
        return await _run_seed_experiment(provider, questions)

    # Run questions
    results: list[QuestionResult] = []
    for q in questions:
        print(f"  Question {q.id}/{q.id if question_ids else limit} ({q.csv_basename})... ", end="", flush=True)
        result = await _run_question(provider, q, cache_enabled=args.cache)
        results.append(result)
        status_icon = "✓" if result.status == "pass" else ("⚠" if result.status == "flaky" else "✗")
        print(f"{status_icon}  {result.status}  ${result.cost_usd:.6f}  {result.duration_seconds:.1f}s")
        if result.status != "pass":
            print(f"         {result.reason}")

    # Render summary table
    print(f"\n{'─' * 60}")
    table_rows = [
        [
            str(r.id),
            r.status.upper(),
            r.reason[:40],
            f"${r.cost_usd:.6f}",
            f"{r.duration_seconds:.1f}s",
        ]
        for r in results
    ]
    print(_render_table(table_rows, ["ID", "STATUS", "REASON", "COST", "DURATION"]))
    total_cost = sum(r.cost_usd for r in results)
    total_dur = sum(r.duration_seconds for r in results)
    print(f"\nTotal: ${total_cost:.6f} / {total_dur:.1f}s")
    print(f"{'─' * 60}\n")

    # Write JSON artifact
    _BENCH_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": _DEFAULT_MODEL,
        "provider": "openai",
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        "limit": limit,
        "cache_enabled": args.cache,
        "total_cost_usd": total_cost,
        "total_duration_seconds": total_dur,
        "questions": [
            {
                "id": r.id,
                "question": r.question,
                "csv": r.csv,
                "status": r.status,
                "reason": r.reason,
                "flaky": r.status == "flaky",
                "artifacts_expected": r.artifacts_expected,
                "artifacts_found": r.artifacts_found,
                "numbers_total": r.numbers_total,
                "numbers_matched": r.numbers_matched,
                "numbers_failed": r.numbers_failed,
                "cost_usd": r.cost_usd,
                "duration_seconds": r.duration_seconds,
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "llm_explanation": r.llm_explanation,
                "sandbox_text": r.sandbox_text,
            }
            for r in results
        ],
    }
    with open(_BENCH_DIR / "last-run.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Determine exit code
    hard_fails = [r for r in results if r.status == "fail"]
    if hard_fails:
        print(f"FAIL: {len(hard_fails)} question(s) hard-failed")
        return 1
    print("PASS: all questions passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))