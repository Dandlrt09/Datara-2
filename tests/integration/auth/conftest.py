"""Auth-suite test seam for outbound email.

The implementation lives in ``tests/test_helpers.py`` so the whole integration
suite shares one recorder; this module only re-exports it (the auth files still
import ``register_verified`` / ``RecordingMailer`` from here) and keeps a thin
autouse fixture that installs the recorder. The register -> verify -> login walk
itself is the shared ``register_verified`` / ``verify_email`` helper.
"""

from __future__ import annotations

import pytest

from tests.test_helpers import (
    RecordingMailer,
    install_recording_mailer,
    register_verified,
    verify_email,
)

__all__ = [
    "RecordingMailer",
    "register_verified",
    "verify_email",
]


@pytest.fixture(autouse=True)
def auth_recording_mailer(monkeypatch):
    """Install the shared mailer recorder for every auth test (S5/D4)."""
    return install_recording_mailer(monkeypatch)
