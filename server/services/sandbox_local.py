"""Parent-side sandbox runner: asyncio subprocess management.

Spawns the sandbox child as a subprocess with JSON stdin/stdout protocol.
Handles timeout, memory limit normalization, and hard-OOM fallback.
Also provides an orphan temp-dir sweep for the lifespan background task.

The child is ``server/sandbox_runner.py`` run by an interpreter when Datara runs
from source, and the executable itself wearing its worker hat when it runs
frozen -- see :func:`sandbox_child_command`.
"""

from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
import shutil
import sys
import tempfile
import time

from server.desktop import SANDBOX_RUNNER_FLAG
from server.resources import is_frozen, resource_path
from server.services import sandbox_win_job

logger = logging.getLogger(__name__)

# Path to the sandbox runner script. Resolved through server.resources so a
# frozen bundle finds the copy PyInstaller unpacked.
SANDBOX_RUNNER_PATH = str(resource_path("server", "sandbox_runner.py"))


def sandbox_child_command() -> list[str]:
    """The argv that starts the sandbox child.

    From source: a real interpreter, in isolated mode (``-I`` ignores PYTHONPATH
    and keeps the working directory off ``sys.path``), with bytecode writing off.

    Frozen: the executable itself. Inside a bundle ``sys.executable`` *is* the
    application, so there is no interpreter left to spawn; without the flag the
    child would start a second copy of the server instead of running code. The
    isolation is not lost in exchange: a frozen bundle carries its own standard
    library and ignores PYTHONPATH and user site-packages by construction.
    """
    if is_frozen():
        return [sys.executable, SANDBOX_RUNNER_FLAG]
    return [sys.executable, "-I", "-B", SANDBOX_RUNNER_PATH]


async def run_code(
    code: str,
    *,
    dataframes: dict | None = None,
    limits: dict | None = None,
    files: dict[str, str] | None = None,
) -> dict:
    """Execute code in the sandbox subprocess.

    Args:
        code: Python source code to execute.
        dataframes: Dict of dataframe name -> file path or inlined data.
        limits: Dict with keys ``cpu_seconds``, ``memory_mb``, ``timeout_seconds``.
        files: Optional mapping of basename -> absolute source path. Each file
            is staged into the sandbox working directory under its basename
            before execution, so generated code can read it by filename.

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
    if not is_frozen() and not os.path.exists(SANDBOX_RUNNER_PATH):
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
    # Windows Job Object handle; stays None on POSIX (no job, nothing to close).
    job: int | None = None
    try:
        # Stage session files into the sandbox cwd under their original
        # basename so generated code can read them by plain filename.
        for name, src in (files or {}).items():
            safe_name = os.path.basename(name)
            if safe_name and os.path.isfile(src):
                shutil.copy2(src, os.path.join(tmpdir, safe_name))

        # Windows has no in-child equivalent of resource.setrlimit, so the
        # parent enforces the caps through a Job Object. The job must exist
        # BEFORE the child is spawned: the child is created suspended and
        # assigned while it cannot yet run, closing the race where it would
        # spawn a grandchild outside the job.
        spawn_kwargs: dict = {}
        if sandbox_win_job.limits_supported():
            job = sandbox_win_job.create_job(resolved_limits.get("memory_mb", 512))
            if job is None:
                # No job handle means nothing to assign or resume: a suspended
                # child would hang until the timeout, so spawn it normally.
                logger.warning(
                    "Windows Job Object creation failed; sandbox runs without "
                    "parent-imposed limits"
                )
            else:
                # Only set on Windows -- POSIX subprocess rejects this kwarg.
                spawn_kwargs["creationflags"] = sandbox_win_job.CREATE_SUSPENDED

        proc = await asyncio.create_subprocess_exec(
            *sandbox_child_command(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmpdir,
            **spawn_kwargs,
        )

        if job is not None:
            if not sandbox_win_job.assign(job, proc.pid):
                logger.warning("Failed to assign sandbox child %s to job", proc.pid)
            # The child was spawned suspended, so it MUST be resumed on every
            # path once that happened -- even if assign failed. Skipping the
            # resume would leave the child frozen and the user would see a
            # mysterious timeout instead of an error.
            if not sandbox_win_job.resume(proc.pid):
                # It is still frozen, so waiting on it would burn the whole
                # timeout budget and then report "execution exceeded Ns" -- a
                # cause that names the wrong thing. End the run now instead.
                logger.error("Failed to resume sandbox child %s", proc.pid)
                proc.kill()
                await proc.wait()
                return {
                    "status": "error",
                    "error": {
                        "type": "runtime_error",
                        "message": (
                            "The sandbox process could not be started: resume "
                            "failed after the Windows job assignment."
                        ),
                    },
                    "figures": [],
                    "tables": [],
                    "text": "",
                }

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
        except asyncio.CancelledError:
            # The awaiting task was cancelled — the client aborted the turn
            # or disconnected mid-stream. Without this, the sandbox
            # subprocess lingers as an orphan until its full timeout budget
            # elapses. Cancellation is delivered once, so short awaits are
            # still legal here: kill, reap with a bounded wait, then
            # re-raise (the outer finally removes the tmpdir).
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning(
                    "Sandbox subprocess did not die within 5s of cancellation"
                )
            raise

        raw = stdout.decode("utf-8") or ""
        if not raw:
            # Hard crash (no stdout). Surface stderr so the real cause is
            # visible — it is NOT always OOM (e.g. unserializable result
            # objects crash the runner after successful execution).
            stderr_tail = (stderr.decode("utf-8", errors="replace") or "")[-400:]
            hint = " — " + stderr_tail.strip() if stderr_tail.strip() else ""
            return {
                "status": "error",
                "error": {
                    "type": "runtime_error",
                    "message": (
                        "Sandbox process produced no output "
                        "(crashed or hard OOM)" + hint
                    ),
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
        # Closing the job handle is what guarantees a sandbox child cannot
        # outlive the app: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (see
        # sandbox_win_job.close) kills everything still in the job when the
        # last handle closes. The tmpdir is removed right after, once no child
        # can still hold files open in it.
        if job is not None:
            sandbox_win_job.close(job)
        shutil.rmtree(tmpdir, ignore_errors=True)


def sweep_orphan_sandbox_dirs(*, max_age_seconds: int = 3600) -> int:
    """Remove orphan ``datara-sandbox-*`` temp dirs older than *max_age_seconds*.

    Designed to run as a lifespan background task (alongside the existing
    session sweep) to catch temp dirs that were left behind by a crashed
    or killed process (the ``try/finally rmtree`` in ``run_code`` covers
    the normal path).

    Returns the number of orphan directories removed.
    """
    now = time.time()
    cut_off = now - max_age_seconds

    pattern = os.path.join(tempfile.gettempdir(), "datara-sandbox-*")
    candidates = glob.glob(pattern)
    removed = 0

    for path in candidates:
        try:
            # stat the dir's mtime to check age
            mtime = os.path.getmtime(path)
            age = now - mtime
            if age > max_age_seconds:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
                logger.info("Removed orphan sandbox dir: %s (age: %.0fs)", path, age)
        except (FileNotFoundError, PermissionError, OSError) as exc:
            logger.warning("Could not sweep sandbox dir %s: %s", path, exc)

    if removed:
        logger.info("Swept %d orphan sandbox temp dir(s)", removed)
    return removed