"""Upload and storage limits, read from the environment at call time.

Keeping the read at call time (rather than import time) lets tests
monkeypatch the ``DATARA_MAX_*`` variables per-test and lets an operator
change a limit without re-importing the module.

The per-file byte cap is the hard bound on RAM/disk growth. The session and
user quotas are best-effort soft caps: two concurrent uploads can race past
them because the check happens before the bytes are written.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Defaults approved for the Files F1 hardening work order.
DEFAULT_MAX_UPLOAD_BYTES = 104_857_600  # 100 MB per file
DEFAULT_MAX_EXPANDED_BYTES = 524_288_000  # 500 MB uncompressed/footprint
DEFAULT_MAX_SESSION_BYTES = 1_073_741_824  # 1 GB per chat session
DEFAULT_MAX_USER_BYTES = 5_368_709_120  # 5 GB per user


@dataclass(frozen=True)
class UploadLimits:
    """Resolved upload/storage limits for one request."""

    max_upload_bytes: int
    max_expanded_bytes: int
    max_session_bytes: int
    max_user_bytes: int


def _read_int(env_var: str, default: int) -> int:
    """Read a non-negative integer from the environment, else the default."""
    raw = os.environ.get(env_var)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def get_limits() -> UploadLimits:
    """Resolve limits from the current environment on every call."""
    return UploadLimits(
        max_upload_bytes=_read_int(
            "DATARA_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES
        ),
        max_expanded_bytes=_read_int(
            "DATARA_MAX_EXPANDED_BYTES", DEFAULT_MAX_EXPANDED_BYTES
        ),
        max_session_bytes=_read_int(
            "DATARA_MAX_SESSION_BYTES", DEFAULT_MAX_SESSION_BYTES
        ),
        max_user_bytes=_read_int("DATARA_MAX_USER_BYTES", DEFAULT_MAX_USER_BYTES),
    )