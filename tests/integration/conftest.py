"""Integration-suite mail seam (T7).

Registration is the first step of almost every integration test, and the hard
gate (S3/D4) means the test must walk register -> verify -> login through the
mail that registration sends. Swapping the mailer factory is what keeps that
walk honest without any test touching a real mailbox.

The fixture is autouse so no test has to opt in: the recorder is installed for
every integration test, and tests that assert on the mail request it by name
(``recorder``).
"""

import pytest

from tests.test_helpers import install_recording_mailer


@pytest.fixture(autouse=True)
def recorder(monkeypatch):
    """Install the in-memory mailer for every integration test (S5/D4)."""
    return install_recording_mailer(monkeypatch)
