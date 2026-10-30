"""Global test setup.

The auth attempt limiter lives in the process, not the database, so without a
reset the counters would leak from one test to the next (every TestClient shares
the same source address). Each test starts from a clean limiter.
"""

import pytest

from server.api import rate_limit


@pytest.fixture(autouse=True)
def _reset_auth_attempt_limiter():
    rate_limit.auth_attempt_limiter.reset()
    yield
    rate_limit.auth_attempt_limiter.reset()
