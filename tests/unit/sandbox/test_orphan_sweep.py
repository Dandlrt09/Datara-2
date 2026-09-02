"""Tests for orphan sandbox temp dir sweep (Phase 5, task 5.2).

Verifies that ``sweep_orphan_sandbox_dirs()`` removes stale ``datara-sandbox-*``
temp dirs while preserving recent dirs and non-matching prefixes.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time

from server.services.sandbox_local import sweep_orphan_sandbox_dirs


class TestOrphanSweep:
    """Task 5.2: Orphan sandbox temp dir sweep.

    All tests are deterministic — they create known temp dirs, age them
    with ``os.utime`` where needed, run the sweep with a short-enough
    threshold, and assert the right dirs survive or are removed.
    Each test cleans up after itself.
    """

    def test_sweep_removes_old_orphan_dir(self):
        """An old ``datara-sandbox-*`` dir should be removed by the sweep."""
        tmpdir = tempfile.mkdtemp(prefix="datara-sandbox-")
        try:
            # Age the dir to be older than the sweep threshold
            old_mtime = time.time() - 7200  # 2 hours ago
            os.utime(tmpdir, (old_mtime, old_mtime))

            removed = sweep_orphan_sandbox_dirs(max_age_seconds=3600)
            assert removed >= 1, (
                f"Expected at least 1 orphan dir removed, got {removed}"
            )
            assert not os.path.exists(tmpdir), (
                "Orphan dir should have been removed by sweep"
            )
        finally:
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)

    def test_fresh_dir_survives_sweep(self):
        """A recently created ``datara-sandbox-*`` dir should survive."""
        tmpdir = tempfile.mkdtemp(prefix="datara-sandbox-")
        try:
            sweep_orphan_sandbox_dirs(max_age_seconds=3600)
            assert os.path.exists(tmpdir), (
                "Fresh dir should survive the sweep"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_non_matching_prefix_survives_sweep(self):
        """A temp dir with a different prefix should survive the sweep."""
        tmpdir = tempfile.mkdtemp(prefix="other-prefix-")
        try:
            # Age it to be old — even so, it should NOT be removed because
            # the glob pattern only matches ``datara-sandbox-*``
            old_mtime = time.time() - 7200
            os.utime(tmpdir, (old_mtime, old_mtime))

            sweep_orphan_sandbox_dirs(max_age_seconds=3600)
            assert os.path.exists(tmpdir), (
                "Non-matching prefix dir should survive the sweep"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)