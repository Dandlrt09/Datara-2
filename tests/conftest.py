"""Global test setup.

The routes now persist attempt counters in SQLite (S4), and every auth test
opens its own fresh ``:memory:`` database, so persisted state cannot leak
between tests. What still lives in the process is the pure in-memory
``AttemptLimiter`` -- the sliding-window algorithm and its direct-drive test
seam -- so it is reset here to keep that seam clean.
"""

import pytest

from server.api import rate_limit


@pytest.fixture(autouse=True)
def _reset_auth_attempt_limiter():
    rate_limit.auth_attempt_limiter.reset()
    yield
    rate_limit.auth_attempt_limiter.reset()
