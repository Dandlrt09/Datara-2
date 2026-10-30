"""In-memory attempt limiter for the auth endpoints (S1-S3).

The server runs as a single process, so a dict is enough: no table, no
migration, and no personal data written to disk. Nothing here is persisted, so a
restart clears every counter -- acceptable for a brute-force brake, and it keeps
the app's promise of never storing an IP.

Sliding window: each key keeps the timestamps of its attempts inside the
window, and the sixth attempt is refused until the oldest one falls out.
"""

from __future__ import annotations

import time

# Five attempts inside fifteen minutes, then wait (S3).
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60

# Ceiling on distinct keys the map may track. The default is deliberately
# conservative: it is a memory bound, not a product knob, so it stays a module
# constant rather than configuration (F1).
MAX_TRACKED_KEYS = 10_000


class AttemptLimiter:
    """Count attempts per key inside a sliding window.

    ``clock`` is injectable so tests can move time without sleeping; production
    uses ``time.monotonic`` (immune to wall-clock jumps).
    """

    def __init__(
        self,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        window_seconds: int = WINDOW_SECONDS,
        max_tracked_keys: int = MAX_TRACKED_KEYS,
        clock=time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._max_tracked_keys = max_tracked_keys
        self._clock = clock
        self._events: dict[str, list[float]] = {}

    def _live_events(self, key: str, now: float) -> list[float]:
        """Drop the events that left the window and return what remains."""
        events = self._events.get(key)
        if not events:
            return []
        cutoff = now - self._window_seconds
        kept = [when for when in events if when > cutoff]
        if kept:
            self._events[key] = kept
        else:
            self._events.pop(key, None)
        return kept

    def _sweep(self, now: float) -> None:
        """Drop every key with no live events left (F1).

        Reuses ``_live_events`` so the window math has a single home: iterating
        a snapshot of the keys is what makes the in-loop deletion safe.
        """
        for key in list(self._events.keys()):
            self._live_events(key, now)

    def retry_after(self, key: str) -> int | None:
        """Seconds to wait before this key may try again, or None if it may now."""
        now = self._clock()
        events = self._live_events(key, now)
        if len(events) < self._max_attempts:
            return None
        remaining = self._window_seconds - (now - events[0])
        return max(1, int(remaining))

    def record(self, key: str) -> None:
        """Register one attempt for *key*."""
        now = self._clock()
        if key not in self._events and len(self._events) >= self._max_tracked_keys:
            self._sweep(now)
            if len(self._events) >= self._max_tracked_keys:
                # All live and at the cap: evict the single coldest key (oldest
                # most-recent event). Trade-off: a very active window can
                # forget another key's counter before it expires.
                coldest = min(self._events, key=lambda k: max(self._events[k]))
                self._events.pop(coldest, None)
        self._live_events(key, now)
        self._events.setdefault(key, []).append(now)

    def clear(self, key: str) -> None:
        """Forget every attempt for *key* (a successful authentication)."""
        self._events.pop(key, None)

    def reset(self) -> None:
        """Drop every counter. Used by tests; a restart has the same effect."""
        self._events.clear()


# One limiter for the process, shared by the login and register routes.
auth_attempt_limiter = AttemptLimiter()
