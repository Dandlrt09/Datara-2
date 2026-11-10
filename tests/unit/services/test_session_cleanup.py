"""F9/S4: hygiene sweep for the persistent auth attempt counters.

The limiter ignores events outside its window, so stale rows are pure waste.
The hourly sweep (and startup) must drop them using the same window the limiter
uses, or the table grows forever.
"""

from __future__ import annotations

import asyncio
import time

from server.api.rate_limit import WINDOW_SECONDS
from server.services.session_cleanup import sweep_expired_attempts


class _RecordingStore:
    def __init__(self) -> None:
        self.cutoff: float | None = None

    async def purge_auth_attempts(self, cutoff: float) -> int:
        self.cutoff = cutoff
        return 3


def test_sweep_purges_everything_older_than_the_rate_limit_window():
    store = _RecordingStore()
    before = time.time()
    deleted = asyncio.run(sweep_expired_attempts(store))
    after = time.time()

    assert deleted == 3
    assert store.cutoff is not None
    # The cutoff is "now - window", so a counter that has left the window is
    # dropped and one still inside it is kept.
    assert before - WINDOW_SECONDS <= store.cutoff <= after - WINDOW_SECONDS
