"""Tests for wiring the Windows Job Object limiter into the sandbox parent.

These tests run on Linux. The Windows-only behaviour (creating/assigning/
resuming/closing a job object) is exercised by monkeypatching the
``sandbox_win_job`` gates, so the ordering guarantees that would otherwise
need a Windows runtime -- assign the suspended child *before* it runs, and
close the handle on every exit path -- are asserted here.

The subprocess is faked too: the ordering, not process I/O, is under test,
and faking it keeps each test instant instead of paying the ~5-18s cost of a
real ``python -I -B`` spawn on this mount.
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

import server.sandbox_runner as sandbox_runner
from server.services import sandbox_local, sandbox_win_job

# A valid protocol reply, so the faked child always returns a normal result.
_OK_OUTPUT = json.dumps(
    {"status": "ok", "figures": [], "tables": [], "text": "", "error": None}
).encode("utf-8")


class _FakeProcess:
    """Minimal stand-in for the asyncio subprocess used by ``run_code``."""

    def __init__(self, stdout: bytes = _OK_OUTPUT, stderr: bytes = b"") -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode: int | None = 0
        self.pid = 4242

    async def communicate(self, input: bytes | None = None):  # noqa: A002
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return 0


def _install_spawn_spy(monkeypatch, events: list) -> None:
    """Replace ``asyncio.create_subprocess_exec`` with a recording fake."""

    async def fake_create_subprocess_exec(*args, **kwargs):
        events.append(("spawn", kwargs.get("creationflags")))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)


def _install_windows_job(
    monkeypatch,
    events: list,
    *,
    job: int | None = 123,
    assign_ok: bool = True,
    resume_ok: bool = True,
) -> None:
    """Make the parent take the Windows Job Object path and record its calls."""

    monkeypatch.setattr(sandbox_win_job, "limits_supported", lambda: True)

    def fake_create_job(memory_mb: int, max_processes: int = 1):
        events.append(("create", memory_mb))
        return job

    def fake_assign(handle: int | None, pid: int) -> bool:
        events.append(("assign", pid))
        return assign_ok

    def fake_resume(pid: int) -> bool:
        events.append(("resume", pid))
        return resume_ok

    def fake_close(handle: int | None) -> None:
        events.append(("close", handle))

    monkeypatch.setattr(sandbox_win_job, "create_job", fake_create_job)
    monkeypatch.setattr(sandbox_win_job, "assign", fake_assign)
    monkeypatch.setattr(sandbox_win_job, "resume", fake_resume)
    monkeypatch.setattr(sandbox_win_job, "close", fake_close)


# ── POSIX path is untouched ──────────────────────────────────────────────────


def test_posix_child_command_unchanged():
    """The Linux argv is exactly the isolated interpreter + runner path."""
    assert sandbox_local.sandbox_child_command() == [
        sys.executable,
        "-I",
        "-B",
        sandbox_local.SANDBOX_RUNNER_PATH,
    ]


@pytest.mark.asyncio
async def test_posix_spawn_passes_no_creationflags(monkeypatch):
    """Regression: ``creationflags`` is Windows-only; POSIX subprocess rejects it.

    This is the bug that would break every Linux install, so the guard is
    explicit even though the POSIX branch also never creates a job.
    """
    events: list = []
    _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "ok"
    assert events == [("spawn", None)]


# ── The child no longer requires the POSIX ``resource`` module ──────────────


def test_set_rlimits_is_noop_without_resource(monkeypatch):
    """On Windows ``import resource`` fails; the limits come from the parent."""
    import resource as resource_mod  # noqa: PLC0415

    calls: list = []
    monkeypatch.setattr(sandbox_runner, "resource", None)
    monkeypatch.setattr(resource_mod, "setrlimit", lambda *a: calls.append(a))

    # Must return early without raising and without touching setrlimit.
    sandbox_runner._set_rlimits({"memory_mb": 128, "cpu_seconds": 5})

    assert calls == []


# ── Windows Job Object ordering (no Windows runtime available here) ─────────


@pytest.mark.asyncio
async def test_windows_job_ordering(monkeypatch):
    """The child must be inside the job before it runs: suspend, assign, resume."""
    events: list = []
    _install_windows_job(monkeypatch, events)
    _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code("print('hi')", limits={"memory_mb": 256})

    assert result["status"] == "ok"
    assert [name for name, _ in events] == [
        "create",
        "spawn",
        "assign",
        "resume",
        "close",
    ]
    # The child was spawned suspended and told the job the request's memory cap.
    assert events[1] == ("spawn", sandbox_win_job.CREATE_SUSPENDED)
    assert events[0] == ("create", 256)


@pytest.mark.asyncio
async def test_failed_assign_still_resumes_and_closes(monkeypatch):
    """A failed assign must not leave a suspended child hanging to the timeout."""
    events: list = []
    _install_windows_job(monkeypatch, events, assign_ok=False)
    _install_spawn_spy(monkeypatch, events)

    await sandbox_local.run_code("print('hi')")

    names = [name for name, _ in events]
    assert "resume" in names, "resume must run even when assign failed"
    assert "close" in names, "the job handle must be closed on every path"
    assert names.index("resume") > names.index("assign")
    assert names[-1] == "close"


@pytest.mark.asyncio
async def test_no_job_falls_back_to_normal_spawn(monkeypatch):
    """No job handle -> spawn normally. Never suspend a child nothing resumes."""
    events: list = []
    _install_windows_job(monkeypatch, events, job=None)
    _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "ok"
    names = [name for name, _ in events]
    assert names == ["create", "spawn"]
    assert events[1] == ("spawn", None)
    assert "assign" not in names
    assert "resume" not in names
    assert "close" not in names


@pytest.mark.asyncio
async def test_failed_resume_ends_the_run_instead_of_timing_out(monkeypatch):
    """A child that could not be resumed is still frozen.

    Waiting on it would burn the whole timeout budget and then report a
    misleading "execution exceeded Ns". The run has to end immediately and say
    what actually happened.
    """
    events: list = []
    _install_windows_job(monkeypatch, events, resume_ok=False)
    _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "error"
    assert result["error"]["type"] == "runtime_error"
    assert "resume" in result["error"]["message"].lower()
    # The job is still closed on this exit path like on every other.
    assert events[-1] == ("close", 123)
