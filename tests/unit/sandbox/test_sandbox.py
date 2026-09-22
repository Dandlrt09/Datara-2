"""Tests for sandbox runner and sandbox_local parent wiring."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from server.services.sandbox_local import run_code

# Path to the sandbox runner script
SANDBOX_RUNNER = str(
    Path(__file__).resolve().parents[3] / "server" / "sandbox_runner.py"
)

_SKIP_SLOW = os.environ.get("DATARA_SKIP_SLOW_TESTS", "").lower() in ("1", "true", "yes")


# ── Unit tests: direct sandbox_runner.py subprocess ────────────────────────


def _run_direct(code: str, limits: dict | None = None) -> dict:
    """Run sandbox_runner.py directly and return parsed JSON output."""
    import asyncio  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    request = {
        "code": code,
        "dataframes": {},
        "limits": limits or {"cpu_seconds": 10, "memory_mb": 512, "timeout_seconds": 10},
    }
    tmpdir = tempfile.mkdtemp(prefix="datara-sandbox-test-")
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-B", SANDBOX_RUNNER],
            input=json.dumps(request).encode("utf-8"),
            capture_output=True,
            cwd=tmpdir,
            timeout=30,
        )
        raw = proc.stdout.decode("utf-8") or ""
        if not raw:
            return {"status": "error", "error": {"type": "runtime_error", "message": "empty stdout"}}
        return json.loads(raw)
    finally:
        import shutil  # noqa: PLC0415
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestSandboxExecution:
    def test_valid_code_simple(self):
        """Simple Python code should execute and return output."""
        result = _run_direct("print('hello from sandbox')")
        assert result["status"] == "ok"
        assert "hello from sandbox" in result["text"]

    def test_valid_code_pandas(self):
        """Code using pandas should work."""
        result = _run_direct("import pandas as pd\ndf = pd.DataFrame({'a': [1, 2]})\nprint(df.shape)")
        assert result["status"] == "ok"

    def test_valid_code_numpy(self):
        result = _run_direct("import numpy as np\nprint(np.array([1, 2, 3]).sum())")
        assert result["status"] == "ok"

    def test_single_df_result_renders_one_table(self):
        """A lone df_result renders exactly one table named df_result."""
        result = _run_direct(
            "import pandas as pd\n"
            "df_result = pd.DataFrame({'a': [1, 2]})\n"
        )
        assert result["status"] == "ok"
        assert [t["name"] for t in result["tables"]] == ["df_result"]

    def test_df_result_wins_over_distinct_other_table(self):
        """df_cat + df_result with DIFFERENT content renders only df_result.

        The sandbox surfaces ONE authoritative table: df_result takes
        precedence over any other df_ frame regardless of content.
        """
        result = _run_direct(
            "import pandas as pd\n"
            "df_cat = pd.DataFrame({'a': [1, 2]})\n"
            "df_result = pd.DataFrame({'b': [3, 4]})\n"
        )
        assert result["status"] == "ok"
        assert [t["name"] for t in result["tables"]] == ["df_result"]

    def test_last_assigned_df_wins_without_df_result(self):
        """Two df_ names, no df_result: the LAST assignment wins."""
        result = _run_direct(
            "import pandas as pd\n"
            "df_first = pd.DataFrame({'a': [1, 2]})\n"
            "df_second = pd.DataFrame({'b': [3, 4]})\n"
        )
        assert result["status"] == "ok"
        assert [t["name"] for t in result["tables"]] == ["df_second"]

    def test_identical_frame_under_two_df_names_renders_one_table(self):
        """Same frame assigned to df_cat + df_result renders ONE table.

        rigor-mov2 live validation: the model created df_cat + df_result
        with identical content and both rendered as separate tables.
        """
        result = _run_direct(
            "import pandas as pd\n"
            "df_result = pd.DataFrame({'a': [1, 2]})\n"
            "df_cat = df_result\n"
        )
        assert result["status"] == "ok"
        assert [t["name"] for t in result["tables"]] == ["df_result"]

    def test_df_result_wins_over_df_other(self):
        """df_result + df_other distinct content renders only df_result."""
        result = _run_direct(
            "import pandas as pd\n"
            "df_result = pd.DataFrame({'a': [1, 2]})\n"
            "df_other = pd.DataFrame({'b': [3, 4]})\n"
        )
        assert result["status"] == "ok"
        assert [t["name"] for t in result["tables"]] == ["df_result"]

    def test_figure_collection(self):
        """Plotly figure should be collected in the result (px is pre-imported)."""
        code = """
fig = px.bar(x=[1, 2, 3], y=[4, 5, 6])
fig.to_json()
"""
        result = _run_direct(code, limits={"cpu_seconds": 10, "memory_mb": 768, "timeout_seconds": 10})
        # plotly import is heavy on memory — may still hit rlimit in constrained env
        if result["status"] == "error" and result["error"]["type"] == "memory_limit_exceeded":
            pytest.skip("Plotly memory allocation exceeds available rlimit in this environment")
        assert result["status"] == "ok"

    def test_syntax_error(self):
        """Invalid Python syntax should return syntax_error."""
        result = _run_direct("this is not valid python @@@")
        assert result["status"] == "error"
        assert result["error"]["type"] == "syntax_error"


# ── RED Tests (Task 3.7) ────────────────────────────────────────────────────


class TestREDSandbox:
    """Task 3.7: 8 RED tests for sandbox security boundaries."""

    def test_red_pickle_payload(self):
        """RED: pickle payload → blocked_import."""
        code = """
import pickle
pickle.dumps({"a": 1})
"""
        result = _run_direct(code)
        assert result["status"] == "error"
        assert result["error"]["type"] == "blocked_import"

    def test_red_os_system(self):
        """RED: os.system → blocked_import (os not in allowlist)."""
        code = """
import os
os.system("echo boom")
"""
        result = _run_direct(code)
        assert result["status"] == "error"
        assert result["error"]["type"] == "blocked_import"

    @pytest.mark.slow
    @pytest.mark.skipif(_SKIP_SLOW, reason="Skipped: DATARA_SKIP_SLOW_TESTS is set")
    def test_red_memory_exceeded(self):
        """RED: >512MB allocation → memory_limit_exceeded."""
        code = """
import numpy as np
# ~800MB allocation (should exceed 512MB rlimit)
x = np.ones((10000, 10000), dtype=np.float64)
print(x.shape)
"""
        result = _run_direct(code, limits={"cpu_seconds": 30, "memory_mb": 512, "timeout_seconds": 30})
        # The process may be killed by RLIMIT_AS (empty stdout) or catch MemoryError
        assert result["error"]["type"] in ("memory_limit_exceeded", "runtime_error")

    @pytest.mark.slow
    @pytest.mark.skipif(_SKIP_SLOW, reason="Skipped: DATARA_SKIP_SLOW_TESTS is set")
    @pytest.mark.asyncio
    async def test_red_timeout(self):
        """RED: 60s loop → timeout."""
        result = await run_code(
            "import time\nfor i in range(600):\n    time.sleep(0.1)\nprint('done')",
            limits={"cpu_seconds": 30, "memory_mb": 512, "timeout_seconds": 3},
        )
        assert result["status"] == "error"
        assert result["error"]["type"] == "timeout"

    def test_red_invalid_syntax(self):
        """RED: invalid Python syntax → syntax_error."""
        code = "def foo(:\n    pass"
        result = _run_direct(code)
        assert result["status"] == "error"
        assert result["error"]["type"] == "syntax_error"

    def test_dataframe_table_rows_are_json_safe_arrays(self):
        """Tables must serialize as arrays of arrays with strict-JSON cells.

        Regression: rows were dicts (to_dict(orient="records")) and NaN cells
        serialized as bare `NaN` — browsers' JSON.parse rejects both, which
        poisoned the SSE artifact event and crashed the chat view.
        """
        code = """
import pandas as pd
df_result = pd.DataFrame({
    "a": [1.5, float("nan")],
    "b": ["x", None],
    "c": [float("inf"), -float("inf")],
})
"""
        result = _run_direct(code)
        assert result["status"] == "ok"
        assert len(result["tables"]) == 1
        tbl = result["tables"][0]
        assert tbl["columns"] == ["a", "b", "c"]
        assert all(isinstance(r, list) for r in tbl["rows"])
        # NaN/±Inf → None; the payload must survive strict JSON round-trip.
        assert tbl["rows"][0] == [1.5, "x", None]
        assert tbl["rows"][1] == [None, None, None]
        json.dumps(result, allow_nan=False)  # must not raise

    def test_datetime_columns_serialize(self):
        """Timestamp/datetime cells must become ISO strings.

        Regression: mutating df with pd.to_datetime made the table
        collector emit Timestamp objects; json.dumps in main() then died
        with empty stdout, which the parent misreported as hard OOM.
        """
        code = """
import pandas as pd
df_result = pd.DataFrame({
    "fecha": pd.to_datetime(["2026-01-05", "2026-01-06"]),
    "monto": [10.5, 20.0],
})
df_result["anio_mes"] = df_result["fecha"].dt.to_period("M")
"""
        result = _run_direct(code)
        assert result["status"] == "ok"
        tbl = result["tables"][0]
        assert tbl["rows"][0][0] == "2026-01-05T00:00:00"  # Timestamp → ISO
        json.dumps(result, allow_nan=False)  # whole payload must be strict

    def test_import_usable_inside_function(self):
        """Top-level imports/assignments must resolve inside function bodies.

        Regression: exec(code, globals, locals) with two separate dicts
        bound imports and top-level names into locals while function
        bodies resolved against globals — so `import unicodedata` plus a
        helper function crashed with NameError ('unicodedata' is not
        defined). This was the flaky unicodedata chat failure.
        """
        code = """
import unicodedata

def sin_tildes(texto):
    normalizada = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizada if not unicodedata.combining(c))

resultado = sin_tildes("Bogotá")
print(resultado)
fig_aux = None
"""
        result = _run_direct(code)
        assert result["status"] == "ok", result.get("error")
        assert "Bogota" in result["text"]

    def test_raw_df_variable_is_not_captured_as_table(self):
        """The raw load variable 'df' must NOT render as a table.

        The system prompt tells the model to load datasets into 'df';
        auto-capturing it echoed the untouched dataset as a table on every
        answer. Result tables use df_<name> (df_result, ...) — those render.
        """
        code = """
import pandas as pd
df = pd.DataFrame({"a": [1, 2]})
df_result = pd.DataFrame({"resumen": ["total"], "valor": [3]})
"""
        result = _run_direct(code)
        assert result["status"] == "ok"
        assert [t["name"] for t in result["tables"]] == ["df_result"]

    def test_class_definitions_execute(self):
        """`class` statements must work in the sandbox.

        Regression: `object` and `__build_class__` were absent from the
        safe-builtins allowlist, so ANY LLM-generated code defining a
        helper class died with NameError (found by bench smoke test 4.2
        on Q1). Classes are inert in this jail: dunder attribute access
        is blocked, open() is cwd-jailed, no subprocess.
        """
        code = """
class Resumen:
    def __init__(self, nombre, valor):
        self.nombre = nombre
        self.valor = valor

    def linea(self):
        return f"{self.nombre}: {self.valor}"

r = Resumen("total", 123.5)
print(r.linea())
"""
        result = _run_direct(code)
        assert result["status"] == "ok", result.get("error")
        assert "total: 123.5" in result["text"]

    def test_red_write_html(self):
        """RED: fig.write_html with ABSOLUTE path → blocked_import.

        ``builtins.open`` is patched at the process level to allow reads
        and writes ONLY under the sandbox cwd (a temp dir). An absolute
        path like /tmp/fig.html is outside the cwd, so Plotly's internal
        ``open()`` call raises PermissionError, which the runner maps to
        the typed ``blocked_import`` error (Decision #17).
        """
        code = """
fig = go.Figure()
fig.write_html("/tmp/fig.html")
"""
        result = _run_direct(code, limits={"cpu_seconds": 10, "memory_mb": 768, "timeout_seconds": 10})
        if result["status"] == "error" and result["error"]["type"] == "memory_limit_exceeded":
            pytest.skip("Plotly memory allocation exceeds rlimit in this environment")
        assert result["status"] == "error", f"Expected error, got ok: {result}"
        assert result["error"]["type"] == "blocked_import", (
            f"Expected blocked_import for absolute-path write_html, "
            f"got {result['error']['type']}: {result['error']['message']}"
        )

    def test_red_open_etc_passwd(self):
        """RED: open('etc/passwd') with absolute path → blocked_import.

        ``open`` is in the safe builtins allowlist but is replaced with
        a cwd-restricted wrapper. Accessing a path outside the temp-cwd
        sandbox raises PermissionError → blocked_import.
        """
        code = """
f = open("/etc/passwd")
print(f.read())
"""
        result = _run_direct(code)
        assert result["status"] == "error"
        assert result["error"]["type"] == "blocked_import"

    def test_red_allowed_write_in_cwd(self):
        """Write to a relative path inside the sandbox cwd succeeds.

        This demonstrates that file I/O is NOT globally blocked — it is
        *scoped* to the sandbox temp directory. Relative paths and paths
        under cwd are permitted.
        """
        code = """
with open("scratch.txt", "w") as f:
    f.write("hello sandbox")
with open("scratch.txt") as f:
    data = f.read()
print(data)
"""
        result = _run_direct(code)
        assert result["status"] == "ok"
        assert result["text"].strip() == "hello sandbox"

    def test_red_blocked_builtins(self):
        """RED: exec/eval/compile should be blocked (NameError → runtime_error).

        ``open`` is intentionally excluded from this list — it is now in
        the safe builtins but jailed to the sandbox cwd (see
        test_red_open_etc_passwd for the jailed-open RED test).
        """
        for dangerous in ["eval", "exec", "compile"]:
            code = f"{dangerous}('print(1)')"
            result = _run_direct(code, limits={"cpu_seconds": 5, "memory_mb": 256, "timeout_seconds": 5})
            assert result["status"] == "error", f"{dangerous} should be blocked"
            assert result["error"]["type"] == "runtime_error", f"{dangerous} should cause NameError"


# ── Async tests via sandbox_local ────────────────────────────────────────────


@pytest.mark.asyncio
class TestSandboxLocal:
    async def test_run_code_simple(self):
        result = await run_code("print('hi')")
        assert result["status"] == "ok"
        assert "hi" in result["text"]

    async def test_run_code_error(self):
        result = await run_code("1/0")
        assert result["status"] == "error"
        assert result["error"]["type"] == "runtime_error"

    async def test_run_code_syntax_error(self):
        result = await run_code("def foo(:\n    pass")
        assert result["status"] == "error"
        assert result["error"]["type"] == "syntax_error"

    async def test_run_code_import_blocked(self):
        result = await run_code("import os\nos.system('echo boo')")
        assert result["status"] == "error"
        assert result["error"]["type"] == "blocked_import"

    @pytest.mark.slow
    @pytest.mark.skipif(_SKIP_SLOW, reason="Skipped: DATARA_SKIP_SLOW_TESTS is set")
    async def test_run_code_timeout(self):
        result = await run_code(
            "import time\ntime.sleep(60)",
            limits={"cpu_seconds": 30, "memory_mb": 512, "timeout_seconds": 2},
        )
        assert result["status"] == "error"
        assert result["error"]["type"] == "timeout"

    @pytest.mark.skipif(_SKIP_SLOW, reason="Skipped: DATARA_SKIP_SLOW_TESTS is set")
    async def test_run_code_hard_oom(self):
        """RED: hard OOM (uncatchable allocation) → runtime_error fallback.

        This approximates the "hard OOM empty stdout" scenario by allocating
        a very large numpy array that may kill the process via RLIMIT_AS
        before a MemoryError can be raised.
        """
        result = await run_code(
            "import numpy as np\nx = np.ones((20000, 20000), dtype=np.float64)\nprint(x.shape)",
            limits={"cpu_seconds": 30, "memory_mb": 128, "timeout_seconds": 15},
        )
        # The process gets killed by RLIMIT_AS → empty stdout → runtime_error fallback
        # OR it catches MemoryError → memory_limit_exceeded
        assert result["status"] == "error"
        assert result["error"]["type"] in ("memory_limit_exceeded", "runtime_error")


@pytest.mark.asyncio
class TestSandboxCancellation:
    async def test_run_code_cancelled_kills_subprocess_and_cleans_tmpdir(self):
        """Cancelling run_code must kill the sandbox subprocess — no orphans.

        Regression: the SSE task is cancelled when the client aborts the
        turn or disconnects mid-sandbox. run_code only handled TimeoutError,
        so the spawned subprocess survived as an orphan for up to ~35s
        (timeout+5). It must be killed and reaped promptly, and the tmpdir
        must still be removed by the finally block on the cancel path.
        """
        import asyncio  # noqa: PLC0415
        import glob  # noqa: PLC0415
        import unittest.mock  # noqa: PLC0415

        created: list[asyncio.subprocess.Process] = []
        real_create = asyncio.create_subprocess_exec

        async def spy_create_subprocess(*args, **kwargs):
            proc = await real_create(*args, **kwargs)
            created.append(proc)
            return proc

        tmp_parent = tempfile.gettempdir()
        before = set(glob.glob(os.path.join(tmp_parent, "datara-sandbox-*")))

        with unittest.mock.patch("asyncio.create_subprocess_exec", spy_create_subprocess):
            task = asyncio.create_task(
                run_code(
                    "import time\ntime.sleep(60)",
                    limits={"cpu_seconds": 30, "memory_mb": 512, "timeout_seconds": 30},
                )
            )
            # Wait until the subprocess is actually spawned (bounded wait).
            for _ in range(250):
                if created:
                    break
                await asyncio.sleep(0.02)
            assert created, "sandbox subprocess was not spawned within 5s"
            assert created[0].returncode is None  # runner alive (sleeping)

            task.cancel()
            # Must settle promptly through the kill+reap path — bounded by
            # the 5s reaper wait, NOT the ~35s timeout budget. A broken
            # implementation surfaces as TimeoutError here, not a hung test.
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=10)

        # The subprocess was killed and reaped (negative returncode = signal).
        assert created[0].returncode is not None
        assert created[0].returncode < 0

        # finally-block tmpdir cleanup also ran on the cancellation path.
        after = set(glob.glob(os.path.join(tmp_parent, "datara-sandbox-*")))
        assert not (after - before)