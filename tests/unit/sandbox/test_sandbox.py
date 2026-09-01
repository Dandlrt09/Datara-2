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