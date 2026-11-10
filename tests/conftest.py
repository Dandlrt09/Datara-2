"""Global test setup.

The routes now persist attempt counters in SQLite (S4), and every auth test
opens its own fresh ``:memory:`` database, so persisted state cannot leak
between tests. What still lives in the process is the pure in-memory
``AttemptLimiter`` -- the sliding-window algorithm and its direct-drive test
seam -- so it is reset here to keep that seam clean.
"""

import keyring
import pytest

from server.api import rate_limit
from tests.test_helpers import InMemoryKeyring


@pytest.fixture(autouse=True)
def _reset_auth_attempt_limiter():
    rate_limit.auth_attempt_limiter.reset()
    yield
    rate_limit.auth_attempt_limiter.reset()


@pytest.fixture(autouse=True)
def _hermetic_os_keyring():
    """Keep every test off the real OS keyring (F9/S11).

    ``SecretBox.for_store`` now consults the OS keyring for a file-backed store,
    so an unguarded suite run would read and write the developer's own secret
    store. Installing an in-process backend for every test keeps that side
    effect out of the run; a test that needs to inspect the backend asks for
    ``in_memory_keyring``.
    """
    original = keyring.get_keyring()
    keyring.set_keyring(InMemoryKeyring())
    try:
        yield
    finally:
        keyring.set_keyring(original)
