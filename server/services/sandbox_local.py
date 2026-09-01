"""Parent-side sandbox runner: asyncio subprocess management.

Spawns ``sandbox_runner.py`` as a subprocess with JSON stdin/stdout protocol.
Handles timeout, memory limit normalization, and hard-OOM fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the sandbox runner script
SANDBOX_RUNNER_PATH = str(
    Path(__file__).resolve().parent.parent / "sandbox_runner.py"
)


async def run_code(
    code: str,
    *,
    dataframes: dict | None = None,
    limits: dict | None = None,
) -> dict:
    """Execute code in the sandbox subprocess.

    Args:
        code: Python source code to execute.
        dataframes: Dict of dataframe name -> file path or inlined data.
        limits: Dict with keys ``cpu_seconds``, ``memory_mb``, ``timeout_seconds``.

    Returns:
        Dict matching the sandbox stdout protocol::

            {"status": "ok", "figures": [...], "tables": [...],
             "text": "...", "error": null}

        On error::

            {"status": "error",
             "error": {"type": "timeout|memory_limit_exceeded|syntax_error|blocked_import|runtime_error",
                       "message": "...", "traceback": "..."},
             "figures": [], "tables": [], "text": ""}

    Raises:
        RuntimeError: If the sandbox runner script is not found.
    """
    if not os.path.exists(SANDBOX_RUNNER_PATH):
        raise RuntimeError(f"Sandbox runner not found: {SANDBOX_RUNNER_PATH}")

    resolved_limits = limits or {}
    timeout = resolved_limits.get("timeout_seconds", 30) + 5

    # Build the request payload
    request = {
        "code": code,
        "dataframes": dataframes or {},
        "limits": {
            "cpu_seconds": resolved_limits.get("cpu_seconds", 30),
            "memory_mb": resolved_limits.get("memory_mb", 512),
            "timeout_seconds": resolved_limits.get("timeout_seconds", 30),
        },
    }

    tmpdir = tempfile.mkdtemp(prefix="datara-sandbox-")
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-B",
            SANDBOX_RUNNER_PATH,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmpdir,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=json.dumps(request).encode("utf-8")),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "error": {
                    "type": "timeout",
                    "message": f"Execution exceeded {resolved_limits.get('timeout_seconds', 30)}s",
                },
                "figures": [],
                "tables": [],
                "text": "",
            }

        raw = stdout.decode("utf-8") or ""
        if not raw:
            # Hard OOM / empty stdout fallback
            return {
                "status": "error",
                "error": {
                    "type": "runtime_error",
                    "message": "Sandbox process produced no output (possible hard OOM)",
                },
                "figures": [],
                "tables": [],
                "text": "",
            }

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {
                "status": "error",
                "error": {
                    "type": "runtime_error",
                    "message": f"Invalid JSON output from sandbox: {raw[:500]}",
                },
                "figures": [],
                "tables": [],
                "text": "",
            }

        # Normalize RLIMIT_AS kill into the structured error contract
        if (
            result.get("status") == "error"
            and result.get("error", {}).get("type") == "runtime_error"
            and "MemoryError" in (result["error"].get("message") or "")
        ):
            result["error"]["type"] = "memory_limit_exceeded"

        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)