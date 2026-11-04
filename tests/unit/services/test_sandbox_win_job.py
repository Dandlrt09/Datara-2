"""Tests for the Windows Job Object sandbox limiter.

The module under test must import cleanly on non-Windows hosts and degrade
every Windows-only entry point to a silent no-op. The pure ``build_limits``
builder and the ``ctypes`` struct layouts are portable, so they are asserted
here: a silently wrong layout is the riskiest failure mode because the
Windows kernel ignores a struct it cannot parse.
"""

from __future__ import annotations

import ctypes

from server.services import sandbox_win_job as jobmod


class TestPlatformGating:
    def test_limits_not_supported_on_linux(self):
        assert jobmod.limits_supported() is False

    def test_create_job_is_silent_noop_on_linux(self):
        assert jobmod.create_job(512, 1) is None

    def test_assign_close_resume_are_silent_noops_on_linux(self):
        assert jobmod.assign(None, 0) is False
        jobmod.close(None)  # must not raise
        assert jobmod.resume(0) is False


class TestStructLayout:
    def test_basic_limit_information_is_64_bytes(self):
        # Microsoft Win32 x64 JOBOBJECT_BASIC_LIMIT_INFORMATION.
        # Source: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information
        assert ctypes.sizeof(jobmod.JOBOBJECT_BASIC_LIMIT_INFORMATION) == 64

    def test_extended_limit_information_is_144_bytes(self):
        # Microsoft Win32 x64 JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        # (64-byte basic block + 48-byte IO_COUNTERS + four 8-byte SIZE_T).
        # Source: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
        assert ctypes.sizeof(jobmod.JOBOBJECT_EXTENDED_LIMIT_INFORMATION) == 144


class TestBuildLimits:
    def test_memory_and_process_flags_and_values(self):
        flags, info = jobmod.build_limits(512, 1)

        assert flags & jobmod.JOB_OBJECT_LIMIT_PROCESS_MEMORY
        assert flags & jobmod.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        assert flags & jobmod.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        assert info.ProcessMemoryLimit == 512 * 1024 * 1024
        assert info.BasicLimitInformation.ActiveProcessLimit == 1

    def test_fields_scale_with_arguments(self):
        flags, info = jobmod.build_limits(2048, 3)

        assert flags & jobmod.JOB_OBJECT_LIMIT_PROCESS_MEMORY
        assert flags & jobmod.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        assert flags & jobmod.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        assert info.ProcessMemoryLimit == 2048 * 1024 * 1024
        assert info.BasicLimitInformation.ActiveProcessLimit == 3

    def test_default_process_limit_is_one(self):
        _flags, info = jobmod.build_limits(256)

        assert info.BasicLimitInformation.ActiveProcessLimit == 1


class TestOffsetsNotJustSizes:
    """A wrong offset does not raise anywhere — the kernel silently ignores the cap.

    Sizes alone are not enough: swapping two members of the same type keeps the
    struct 144 bytes while pointing ``ProcessMemoryLimit`` at the wrong place, so
    the offsets are pinned too. This is the detail whose failure mode is a limit
    that looks enforced and is not.

    Source: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
    """

    def test_extended_layout_offsets(self):
        extended = jobmod.JOBOBJECT_EXTENDED_LIMIT_INFORMATION

        assert extended.BasicLimitInformation.offset == 0
        assert extended.IoInfo.offset == 64
        # Top-level member, NOT inside BasicLimitInformation.
        assert extended.ProcessMemoryLimit.offset == 112
        assert extended.JobMemoryLimit.offset == 120
        assert extended.PeakJobMemoryUsed.offset == 136

    def test_active_process_limit_sits_inside_the_basic_block(self):
        assert jobmod.JOBOBJECT_BASIC_LIMIT_INFORMATION.ActiveProcessLimit.offset == 40

    def test_the_flag_mask_is_exactly_the_three_caps(self):
        # A membership check (`&`) would let an extra limit flag slip in unseen.
        flags, _info = jobmod.build_limits(512, 1)

        assert flags == (
            jobmod.JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | jobmod.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | jobmod.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
