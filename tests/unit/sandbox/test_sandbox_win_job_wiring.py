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
import logging
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
        self.killed = False
        self.waited = False

    async def communicate(self, input: bytes | None = None):  # noqa: A002
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.waited = True
        return 0


def _install_spawn_spy(
    monkeypatch,
    events: list,
    *,
    stdout: bytes = _OK_OUTPUT,
    stderr: bytes = b"",
    returncode: int = 0,
    argv: list | None = None,
) -> list:
    """Replace ``asyncio.create_subprocess_exec`` with a recording fake.

    Returns the list of fake processes that were spawned (empty when the
    parent refuses to spawn). The ``stdout``, ``stderr`` and ``returncode``
    arguments shape the fake child's result so the no-output and CPU-kill
    paths can be driven. Pass ``argv`` to also capture the exact argv the
    parent spawned, in its own list so the ``events`` stream keeps its shape.
    """
    spawned: list = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        events.append(("spawn", kwargs.get("creationflags")))
        if argv is not None:
            argv.append(list(args))
        proc = _FakeProcess(stdout=stdout, stderr=stderr)
        proc.returncode = returncode
        spawned.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return spawned


def _install_windows_job(
    monkeypatch,
    events: list,
    *,
    job: int | None = 123,
    assign_ok: bool = True,
    resume_ok: bool = True,
    requested_cpu: list | None = None,
) -> list:
    """Make the parent take the Windows Job Object path and record its calls.

    Returns the list of ``max_processes`` values the parent asked for, in a
    separate record so the 2-tuple ``events`` stream keeps its shape. Pass
    ``requested_cpu`` to also collect the ``cpu_seconds`` values, in their own
    list so existing callers keep their ``requested_caps`` shape.
    """

    monkeypatch.setattr(sandbox_win_job, "limits_supported", lambda: True)
    requested_caps: list = []

    def fake_create_job(
        memory_mb: int, max_processes: int = 1, cpu_seconds: int | None = None
    ):
        requested_caps.append(max_processes)
        if requested_cpu is not None:
            requested_cpu.append(cpu_seconds)
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
    return requested_caps


# ── POSIX path is untouched ──────────────────────────────────────────────────


def test_posix_child_command_unchanged():
    """The Linux argv is exactly the isolated interpreter + runner path."""
    assert sandbox_local.sandbox_child_command() == [
        sys.executable,
        "-I",
        "-B",
        sandbox_local.SANDBOX_RUNNER_PATH,
    ]


# ── Frozen path: the executable itself is the sandbox child ────────────────
# Advisory ``R3-frozen-command-untested``: ``sandbox_child_command`` has two
# branches and only the source one had a test. Inside a PyInstaller bundle
# there is no interpreter left to spawn, so the child *is* the executable
# wearing its ``--sandbox-runner`` hat -- the same token ``desktop.main``
# dispatches on to run the runner instead of starting a second server. If this
# argv drifts, a frozen build silently boots another app copy instead of
# running the model's code, and nothing else would catch it.


def test_frozen_child_command_is_the_executable_with_the_runner_flag(monkeypatch):
    """Frozen, the child argv is the exe plus the flag -- not the script path."""
    from server import desktop  # noqa: PLC0415

    monkeypatch.setattr(sandbox_local, "is_frozen", lambda: True)

    assert sandbox_local.sandbox_child_command() == [
        sys.executable,
        sandbox_local.SANDBOX_RUNNER_FLAG,
    ]
    # The flag is the exact token ``desktop.main`` dispatches on ...
    assert sandbox_local.SANDBOX_RUNNER_FLAG is desktop.SANDBOX_RUNNER_FLAG
    assert sandbox_local.SANDBOX_RUNNER_FLAG == "--sandbox-runner"
    # ... and the source-only arguments must not leak into the frozen argv.
    assert "-I" not in sandbox_local.sandbox_child_command()
    assert "-B" not in sandbox_local.sandbox_child_command()
    assert sandbox_local.SANDBOX_RUNNER_PATH not in sandbox_local.sandbox_child_command()


@pytest.mark.asyncio
async def test_frozen_spawn_uses_the_executable_and_skips_the_script_check(
    monkeypatch,
):
    """Frozen, ``run_code`` spawns that argv without requiring the script on disk."""
    events: list = []
    argv: list = []
    _install_spawn_spy(monkeypatch, events, argv=argv)
    monkeypatch.setattr(sandbox_local, "is_frozen", lambda: True)
    # No bundle unpacked a runner script here; the frozen guard must not raise.
    monkeypatch.setattr(
        sandbox_local, "SANDBOX_RUNNER_PATH", "/nonexistent/sandbox_runner.py"
    )

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "ok"
    assert events == [("spawn", None)]
    # What actually got spawned, not only what the helper returns.
    assert argv == [[sys.executable, sandbox_local.SANDBOX_RUNNER_FLAG]]


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
async def test_failed_assign_kills_the_suspended_child_instead_of_running_it(
    monkeypatch,
):
    """Fail closed: a child that could not join the job must die, not run.

    Resuming it (as before) would let the model's code run with no memory cap,
    no process cap and no KILL_ON_JOB_CLOSE. The suspended child is killed
    instead, so it is never left hanging to the timeout either.
    """
    events: list = []
    _install_windows_job(monkeypatch, events, assign_ok=False, resume_ok=False)
    spawned = _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "error"
    assert result["error"]["type"] == "runtime_error"
    message = result["error"]["message"].lower()
    assert "assign" in message
    assert "not allowed" in message
    # The suspended child was spawned but never resumed outside the job.
    assert events[1] == ("spawn", sandbox_win_job.CREATE_SUSPENDED)
    names = [name for name, _ in events]
    assert "assign" in names
    assert "resume" not in names, "a child outside the job must never resume"
    # It was killed, not left hanging, and nothing is still running.
    assert spawned and spawned[0].killed is True
    assert spawned[0].returncode == -9
    assert spawned[0].waited is True, "a killed child must also be reaped"
    # The job handle is still closed on this exit path like on every other.
    assert names[-1] == "close"


@pytest.mark.asyncio
async def test_no_job_refuses_to_spawn_the_child(monkeypatch):
    """Fail closed: without a job there is no confinement, so do not run."""
    events: list = []
    _install_windows_job(monkeypatch, events, job=None)
    spawned = _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "error"
    assert result["error"]["type"] == "runtime_error"
    message = result["error"]["message"].lower()
    assert "job" in message
    assert "not allowed" in message
    # Nothing was spawned, so nothing runs unconfined.
    assert spawned == []
    assert [name for name, _ in events] == ["create"]


@pytest.mark.asyncio
async def test_job_creation_failure_logs_an_error_and_leaves_no_process(
    monkeypatch, caplog
):
    """The refusal to run is logged at ERROR, not WARNING, and runs nothing."""
    events: list = []
    _install_windows_job(monkeypatch, events, job=None)
    spawned = _install_spawn_spy(monkeypatch, events)

    with caplog.at_level(logging.ERROR, logger=sandbox_local.__name__):
        result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "error"
    assert spawned == []
    assert any(
        record.levelno == logging.ERROR
        and "creation" in record.getMessage().lower()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_assign_failure_logs_an_error_and_leaves_no_process(
    monkeypatch, caplog
):
    """The refusal to run is logged at ERROR, and the child is killed."""
    events: list = []
    _install_windows_job(monkeypatch, events, assign_ok=False)
    spawned = _install_spawn_spy(monkeypatch, events)

    with caplog.at_level(logging.ERROR, logger=sandbox_local.__name__):
        result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "error"
    assert spawned and spawned[0].killed is True
    assert any(
        record.levelno == logging.ERROR
        and "assign" in record.getMessage().lower()
        for record in caplog.records
    )


# ── Job process cap depends on whether the child is a launcher ──────────────

def _set_native_interpreter(monkeypatch) -> None:
    """Make the runner look like a native interpreter (no venv redirector)."""
    monkeypatch.setattr(sandbox_local, "is_frozen", lambda: False)
    monkeypatch.setattr(sys, "_base_executable", sys.executable, raising=False)


def _set_venv_redirector(monkeypatch) -> None:
    """Make the runner look like a venv redirector (base != current)."""
    monkeypatch.setattr(sandbox_local, "is_frozen", lambda: False)
    monkeypatch.setattr(
        sys, "_base_executable", sys.executable + "-base", raising=False
    )


def test_job_process_cap_is_one_for_a_native_interpreter(monkeypatch):
    """A native child needs a single slot: itself, and nothing else."""
    monkeypatch.setattr(sandbox_local, "is_frozen", lambda: False)
    monkeypatch.delattr(sys, "_base_executable", raising=False)
    assert sandbox_local._job_process_cap() == 1

    # A base executable equal to the current one is still the native case.
    monkeypatch.setattr(sys, "_base_executable", sys.executable, raising=False)
    assert sandbox_local._job_process_cap() == 1


def test_job_process_cap_is_two_for_a_venv_redirector(monkeypatch):
    """A venv ``python.exe`` is a redirector: it spawns the real interpreter."""
    _set_venv_redirector(monkeypatch)
    assert sandbox_local._job_process_cap() == 2


def test_job_process_cap_is_one_when_frozen(monkeypatch):
    """The frozen exe is native even if a base executable is recorded."""
    monkeypatch.setattr(sandbox_local, "is_frozen", lambda: True)
    monkeypatch.setattr(
        sys, "_base_executable", sys.executable + "-base", raising=False
    )
    assert sandbox_local._job_process_cap() == 1


@pytest.mark.asyncio
async def test_redirector_child_gets_a_second_process_slot(monkeypatch):
    """Wiring: with the redirector present the parent asks ``create_job`` for 2."""
    events: list = []
    requested_caps = _install_windows_job(monkeypatch, events)
    _install_spawn_spy(monkeypatch, events)
    _set_venv_redirector(monkeypatch)

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "ok"
    assert requested_caps == [2]


@pytest.mark.asyncio
async def test_native_child_keeps_the_strict_process_cap(monkeypatch):
    """Wiring: a native interpreter still asks ``create_job`` for exactly 1."""
    events: list = []
    requested_caps = _install_windows_job(monkeypatch, events)
    _install_spawn_spy(monkeypatch, events)
    _set_native_interpreter(monkeypatch)

    result = await sandbox_local.run_code("print('hi')")

    assert result["status"] == "ok"
    assert requested_caps == [1]


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
    # The refusal states the policy, not only the cause: it is why the run was
    # ended instead of falling back to an unconfined child.
    assert "not allowed" in result["error"]["message"].lower()
    # The job is still closed on this exit path like on every other.
    assert events[-1] == ("close", 123)


# ── CPU limit: the cap is forwarded, and its kill is named ────────────────

# Measured on Windows (interop, Python 3.14.0, 2026-11-10): a job with
# JOB_OBJECT_LIMIT_PROCESS_TIME terminates the child with exit code 0xC0000044
# (STATUS_QUOTA_EXCEEDED). D6 forbids guessing this from documentation.
_WIN_CPU_KILL_EXIT_CODE = 0xC0000044


@pytest.mark.asyncio
async def test_wiring_passes_cpu_seconds_from_the_limits_dict(monkeypatch):
    """The parent must hand the request's ``cpu_seconds`` to the job."""
    events: list = []
    requested_cpu: list = []
    _install_windows_job(monkeypatch, events, requested_cpu=requested_cpu)
    _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code(
        "print('hi')", limits={"cpu_seconds": 4, "memory_mb": 256}
    )

    assert result["status"] == "ok"
    assert requested_cpu == [4]


@pytest.mark.asyncio
async def test_wiring_passes_no_cpu_seconds_when_absent(monkeypatch):
    """Without ``cpu_seconds`` the job gets ``None``: no CPU cap is imposed."""
    events: list = []
    requested_cpu: list = []
    _install_windows_job(monkeypatch, events, requested_cpu=requested_cpu)
    _install_spawn_spy(monkeypatch, events)

    result = await sandbox_local.run_code("print('hi')", limits={"memory_mb": 256})

    assert result["status"] == "ok"
    assert requested_cpu == [None]


@pytest.mark.asyncio
async def test_cpu_limit_kill_reports_the_cpu_limit(monkeypatch):
    """A CPU-limit kill must not be reported as a crash or a hard OOM."""
    events: list = []
    _install_windows_job(monkeypatch, events)
    _install_spawn_spy(
        monkeypatch, events, stdout=b"", returncode=_WIN_CPU_KILL_EXIT_CODE
    )

    result = await sandbox_local.run_code(
        "print('hi')", limits={"cpu_seconds": 4, "memory_mb": 256}
    )

    assert result["status"] == "error"
    # D2: reuses the existing ``timeout`` type, no taxonomy change.
    assert result["error"]["type"] == "timeout"
    assert result["error"]["message"] == "Execution exceeded the CPU limit (4s)"


@pytest.mark.asyncio
async def test_no_cpu_limit_keeps_the_produced_no_output_message(monkeypatch):
    """The measured exit code alone is not enough: no cap means no claim."""
    events: list = []
    _install_windows_job(monkeypatch, events)
    _install_spawn_spy(
        monkeypatch, events, stdout=b"", returncode=_WIN_CPU_KILL_EXIT_CODE
    )

    result = await sandbox_local.run_code("print('hi')", limits={"memory_mb": 256})

    assert result["status"] == "error"
    assert result["error"]["type"] == "runtime_error"
    assert "produced no output" in result["error"]["message"]


@pytest.mark.asyncio
async def test_other_exit_code_keeps_the_produced_no_output_message(monkeypatch):
    """A cap set but a different exit code keeps the pre-existing message."""
    events: list = []
    _install_windows_job(monkeypatch, events)
    _install_spawn_spy(monkeypatch, events, stdout=b"", returncode=1)

    result = await sandbox_local.run_code(
        "print('hi')", limits={"cpu_seconds": 4, "memory_mb": 256}
    )

    assert result["status"] == "error"
    assert result["error"]["type"] == "runtime_error"
    assert "produced no output" in result["error"]["message"]
