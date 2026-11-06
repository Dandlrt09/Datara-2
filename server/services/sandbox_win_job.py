"""Parent-side Windows Job Object limiter for the sandbox subprocess.

On Linux the sandbox child handicaps itself from inside with
``resource.setrlimit`` (RLIMIT_AS / RLIMIT_CPU / RLIMIT_NPROC /
RLIMIT_FSIZE). Windows has no equivalent in-process API, so the PARENT
creates a Job Object — a kernel-enforced container — and assigns the freshly
spawned child to it before the child is allowed to run. The child is spawned
suspended (``CREATE_SUSPENDED``) precisely so it cannot spawn a grandchild in
the window before it is inside the job; ``resume`` then releases it.

Only ``ctypes`` (stdlib) is used; no new dependency is added.

Two honest differences from the Linux path:

1. ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` caps *committed* memory, whereas
   ``RLIMIT_AS`` caps virtual address space. An over-limit Windows child
   therefore typically dies with ``MemoryError`` instead of being killed by
   the kernel. ``sandbox_local.run_code`` already normalizes a ``MemoryError``
   into the structured ``memory_limit_exceeded`` error, so the error taxonomy
   seen by callers does not change.
2. There is NO Windows equivalent of RLIMIT_FSIZE, so the file-write-size cap
   is simply absent on Windows. Only the Python-level ``open`` jail in
   ``sandbox_runner.py`` remains.

On non-Windows hosts this module still imports cleanly and every Windows-only
entry point degrades to a silent no-op, so callers can invoke it
unconditionally.
"""

from __future__ import annotations

import ctypes
import os

# ── Win32 constants ─────────────────────────────────────────────────────────
#
# Verified against the Microsoft Windows SDK documentation:
#   * Job object limit flags:
#     https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information
#   * SetInformationJobObject / JobObjectExtendedLimitInformation (= 9):
#     https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-setinformationjobobject
#   * Process access rights:
#     https://learn.microsoft.com/en-us/windows/win32/procthread/process-security-and-access-rights
#   * Process creation flags (CREATE_SUSPENDED):
#     https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags

#: Process creation flag: the primary thread starts suspended and does not
#: run until resumed. https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
CREATE_SUSPENDED: int = 0x00000004

#: Cap on committed memory (see note 1 in the module docstring).
JOB_OBJECT_LIMIT_PROCESS_MEMORY: int = 0x00000100
#: Cap on simultaneously active processes associated with the job.
JOB_OBJECT_LIMIT_ACTIVE_PROCESS: int = 0x00000008
#: Terminate every process in the job when the last job handle closes.
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: int = 0x00002000

#: JOBOBJECTINFOCLASS member passed to SetInformationJobObject.
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: int = 9

#: Process access rights needed to assign a process to a job.
PROCESS_SET_QUOTA: int = 0x0100
PROCESS_TERMINATE: int = 0x0001
#: Required by NtResumeProcess.
PROCESS_SUSPEND_RESUME: int = 0x0800


# ── Win32 structs ───────────────────────────────────────────────────────────
#
# DWORD is 32-bit and ULONG_PTR/SIZE_T are pointer-sized; mapping them to
# c_uint32 / c_size_t keeps the layout identical to the Windows x64 ABI (which
# is what the kernel parses) even though this file also imports on Linux.


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    """Win32 JOBOBJECT_BASIC_LIMIT_INFORMATION (x64 size 64).

    Source:
    https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information
    """

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class IO_COUNTERS(ctypes.Structure):
    """Win32 IO_COUNTERS (six ULONGLONG, x64 size 48).

    Source: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-io_counters
    """

    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    """Win32 JOBOBJECT_EXTENDED_LIMIT_INFORMATION (x64 size 144).

    Source:
    https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
    """

    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


# ── Lazily bound Win32 DLLs ─────────────────────────────────────────────────
#
# ctypes.WinDLL does not exist on non-Windows, so binding happens only behind
# a limits_supported() guard. Nothing here runs at import time.

_kernel32: ctypes.CDLL | None = None
_ntdll: ctypes.CDLL | None = None


def _load_apis() -> None:
    """Bind kernel32/ntdll entry points. Windows only; called after the gate."""
    global _kernel32, _ntdll
    if _kernel32 is not None:
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p

    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel32.SetInformationJobObject.restype = ctypes.c_int

    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p

    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int

    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    # NtResumeProcess is undocumented, but it is the same ntdll call psutil
    # uses for Process.resume(). It is needed because we spawn the child
    # suspended (CREATE_SUSPENDED), so it runs only once it is inside the job.
    # Signature: NTSTATUS NtResumeProcess(HANDLE ProcessHandle); 0 == success.
    ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
    ntdll.NtResumeProcess.restype = ctypes.c_int32

    _kernel32 = kernel32
    _ntdll = ntdll


# ── Public API ──────────────────────────────────────────────────────────────


def limits_supported() -> bool:
    """True only on Windows, where Job Objects are available."""
    return os.name == "nt"


def build_limits(
    memory_mb: int, max_processes: int = 1
) -> tuple[int, JOBOBJECT_EXTENDED_LIMIT_INFORMATION]:
    """Build the flag mask and extended-limit struct for a job.

    Pure and portable: no Win32 call, so it is unit-testable on any platform.
    ``ProcessMemoryLimit`` is a *commit* limit (bytes), not virtual address
    space. Note that it lives directly on the extended struct and NOT under
    ``BasicLimitInformation`` — that is how the Windows SDK defines it (see
    the struct source above).
    """
    flags = (
        JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = flags
    info.ProcessMemoryLimit = memory_mb * 1024 * 1024
    info.BasicLimitInformation.ActiveProcessLimit = max_processes
    return flags, info


def create_job(memory_mb: int, max_processes: int = 1) -> int | None:
    """Create a Job Object configured with the sandbox limits.

    Returns the job ``HANDLE`` as an int, or ``None`` on any failure / off
    Windows. Callers that close the returned handle also kill every process
    in the job: see ``close``.
    """
    if not limits_supported():
        return None

    _load_apis()
    assert _kernel32 is not None  # established by _load_apis

    _flags, info = build_limits(memory_mb, max_processes)
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    ok = _kernel32.SetInformationJobObject(
        job,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        _kernel32.CloseHandle(job)
        return None
    return int(job)


def assign(job: int | None, pid: int) -> bool:
    """Assign process *pid* to *job*. False off Windows or on any failure.

    Requests only PROCESS_SET_QUOTA | PROCESS_TERMINATE — the minimum needed
    to place a process in a job — and always closes the process handle.
    """
    if not limits_supported() or not job:
        return False

    _load_apis()
    assert _kernel32 is not None

    handle = _kernel32.OpenProcess(
        PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid
    )
    if not handle:
        return False
    try:
        return bool(_kernel32.AssignProcessToJobObject(job, handle))
    finally:
        _kernel32.CloseHandle(handle)


def resume(pid: int) -> bool:
    """Resume the process previously created with CREATE_SUSPENDED.

    Off Windows this is a silent no-op returning False. On Windows it opens a
    PROCESS_SUSPEND_RESUME handle and calls ``NtResumeProcess`` (see
    ``_load_apis`` for why that undocumented call is used).
    """
    if not limits_supported():
        return False

    _load_apis()
    assert _kernel32 is not None and _ntdll is not None

    handle = _kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not handle:
        return False
    try:
        status = _ntdll.NtResumeProcess(handle)
        return status == 0
    finally:
        _kernel32.CloseHandle(handle)


def close(job: int | None) -> None:
    """Close the job handle.

    Because the job was created with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, this
    is also the kill switch: when the Datara app exits and its handles close,
    the sandbox child (and anything it spawned) dies with it. That containment
    is a deliberate property — the reason for choosing KILL_ON_JOB_CLOSE —
    not a side effect.
    """
    if not limits_supported() or not job:
        return

    _load_apis()
    assert _kernel32 is not None
    _kernel32.CloseHandle(job)
