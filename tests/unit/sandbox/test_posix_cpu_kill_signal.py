"""Measured, not assumed (D7): the signal a CPU-capped sandbox child dies with.

The other CPU tests drive the parent with a faked returncode. This is the only
one that starts a real child through the runner's own ``RLIMIT_CPU`` setting,
so a revert of ``_set_rlimits`` to ``soft == hard`` fails here even if the
parent-side tests keep passing: the kernel then delivers SIGKILL (-9) instead
of SIGXCPU (-24), and the parent cannot tell -9 apart from an OOM.
"""

from __future__ import annotations

import platform
import signal
import subprocess
import sys
from pathlib import Path

import pytest

# tests/unit/sandbox/ -> the repository root, where ``server`` is importable.
_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(platform.system() != "Linux", reason="POSIX RLIMIT_CPU probe")
def test_runner_cpu_cap_kills_the_child_with_sigxcpu():
    """The runner's own cap must deliver SIGXCPU so the parent can name it."""
    code = (
        "import server.sandbox_runner as runner\n"
        "runner._set_rlimits({'cpu_seconds': 1})\n"
        "x = 0\n"
        "while True:\n"
        "    x += 1\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        returncode = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail("the CPU cap did not kill the child within 30 s")

    assert returncode == -signal.SIGXCPU, (
        f"expected SIGXCPU ({-signal.SIGXCPU}), got {returncode}; with "
        "RLIMIT_CPU soft == hard the kernel sends SIGKILL, which the parent "
        "cannot distinguish from an OOM (decision D7)"
    )
