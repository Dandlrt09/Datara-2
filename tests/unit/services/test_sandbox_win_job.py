"""Tests for the Windows Job Object sandbox limiter.

The module under test must import cleanly on non-Windows hosts and degrade
every Windows-only entry point to a silent no-op. The pure ``build_limits``
builder and the ``ctypes`` struct layouts are portable, so they are asserted
here: a silently wrong layout is the riskiest failure mode because the
Windows kernel ignores a struct it cannot parse.
"""

from __future__ import annotations

import ctypes
import logging

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


class TestWinErrorHelpers:
    """The Win32 diagnostics are portable to test from Linux by faking ctypes."""

    def test_error_code_is_none_when_get_last_error_is_missing(self, monkeypatch):
        monkeypatch.delattr(ctypes, "get_last_error", raising=False)

        assert jobmod._win_error_code() is None

    def test_error_code_is_none_when_get_last_error_raises(self, monkeypatch):
        def boom():
            raise OSError("unreadable")

        monkeypatch.setattr(ctypes, "get_last_error", boom, raising=False)

        assert jobmod._win_error_code() is None

    def test_error_code_returns_the_value_when_available(self, monkeypatch):
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)

        assert jobmod._win_error_code() == 5

    def test_error_text_returns_format_error_text(self, monkeypatch):
        monkeypatch.setattr(
            ctypes, "FormatError", lambda code: "Access is denied.", raising=False
        )

        assert jobmod._win_error_text(5) == "Access is denied."

    def test_error_text_is_empty_when_format_error_is_missing(self, monkeypatch):
        monkeypatch.delattr(ctypes, "FormatError", raising=False)

        assert jobmod._win_error_text(5) == ""

    def test_error_text_is_empty_when_format_error_raises(self, monkeypatch):
        def boom(code):
            raise OSError("unreadable")

        monkeypatch.setattr(ctypes, "FormatError", boom, raising=False)

        assert jobmod._win_error_text(5) == ""


class TestLogWinFailure:
    def test_logs_step_code_and_text(self, caplog, monkeypatch):
        monkeypatch.setattr(
            ctypes, "FormatError", lambda code: "Access is denied.", raising=False
        )

        with caplog.at_level(logging.ERROR, logger=jobmod.__name__):
            jobmod._log_win_failure("create", 5)

        records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(records) == 1
        message = records[0].getMessage()
        assert "create" in message
        assert "5" in message
        assert "Access is denied." in message

    def test_logs_missing_code_without_inventing_a_number(self, caplog):
        with caplog.at_level(logging.ERROR, logger=jobmod.__name__):
            jobmod._log_win_failure("assign", None)

        records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(records) == 1
        message = records[0].getMessage()
        assert "no win32 error code" in message.lower()
        # The requirement's own wording names "Win32"; strip that literal so
        # this only rejects an invented error-code number.
        assert not any(ch.isdigit() for ch in message.replace("Win32", ""))

    def test_logs_zero_code_as_no_code(self, caplog):
        # D5: get_last_error() == 0 means no system error, so it is never
        # printed as if it were an error code.
        with caplog.at_level(logging.ERROR, logger=jobmod.__name__):
            jobmod._log_win_failure("resume", 0)

        records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(records) == 1
        message = records[0].getMessage()
        assert "no win32 error code" in message.lower()
        assert not any(ch.isdigit() for ch in message.replace("Win32", ""))


class TestNonWindowsStaysSilent:
    def test_entry_points_do_not_log_when_the_platform_cannot(
        self, caplog, monkeypatch
    ):
        """The module's contract: off Windows every entry point is a silent no-op.

        The new diagnostics must not leak there either, so the failure sites stay
        behind the ``limits_supported()`` gate. Patching the gate (instead of
        relying on the host OS) makes this hold on any platform.
        """
        monkeypatch.setattr(jobmod, "limits_supported", lambda: False)

        with caplog.at_level(logging.ERROR, logger=jobmod.__name__):
            assert jobmod.create_job(256) is None
            assert jobmod.assign(123, 4242) is False
            assert jobmod.resume(4242) is False
            jobmod.close(123)

        assert [r for r in caplog.records if r.levelno == logging.ERROR] == []
