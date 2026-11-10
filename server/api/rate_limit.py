"""Attempt limiter for the auth endpoints (S1-S4).

Two limiters share the same window (five attempts inside fifteen minutes):

- ``AttemptLimiter`` is the pure in-memory sliding window. It is the tested
  algorithm and the test seam, but a restart clears every counter -- acceptable
  only for a best-effort brake.
- ``PersistentAttemptLimiter`` stores the counters in SQLite keyed by a SHA-256
  hash of the limiter key (S4). A restart no longer resets the brake, and no IP
  or email is ever written in clear: only the hash reaches disk.

Both keep the app's promise of never storing an IP or an email. Only the
persisted limiter uses wall-clock time, because its window must survive the
process (``time.monotonic`` resets with it).

Sliding window: each key keeps the timestamps of its attempts inside the
window, and the sixth attempt is refused until the oldest one falls out.
"""

from __future__ import annotations

import hashlib
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
#
# It is the in-memory seam only: the routes themselves go through
# ``PersistentAttemptLimiter`` so the counters survive a restart (S4). Kept for
# tests that drive the sliding-window algorithm directly and for conftest's
# per-test reset.
auth_attempt_limiter = AttemptLimiter()


def hash_attempt_key(key: str) -> str:
    """SHA-256 hex of a limiter key, the only form written to disk (S4).

    ``hash_token`` in ``auth_service`` would be an import cycle and is about
    session/token secrets, not limiter keys; ``hashlib`` directly keeps this
    boundary independent. Hashing is what lets a leaked database yield no IP and
    no email while the counter still works.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class PersistentAttemptLimiter:
    """Store-backed sliding-window limiter that survives a restart (S4).

    Uses the same ``MAX_ATTEMPTS`` / ``WINDOW_SECONDS`` constants as
    ``AttemptLimiter``; the only difference is where the timestamps live. The
    window math mirrors the in-memory limiter (strict ``>`` cutoff, refuse at
    ``>= max``) so the two stay behaviourally identical.

    ``clock`` defaults to ``time.time`` (wall clock) because a monotonic clock
    would restart with the process and defeat the point of persisting.
    """

    def __init__(
        self,
        store,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        window_seconds: int = WINDOW_SECONDS,
        clock=time.time,
    ) -> None:
        self._store = store
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._clock = clock

    async def retry_after(self, key: str) -> int | None:
        """Seconds to wait before *key* may try again, or None if it may now."""
        now = self._clock()
        events = await self._store.list_auth_attempts(
            hash_attempt_key(key), now - self._window_seconds
        )
        if len(events) < self._max_attempts:
            return None
        remaining = self._window_seconds - (now - events[0])
        return max(1, int(remaining))

    async def record(self, key: str) -> None:
        """Register one attempt for *key*."""
        await self._store.record_auth_attempt(hash_attempt_key(key), self._clock())

    async def clear(self, key: str) -> None:
        """Forget every attempt for *key* (a successful authentication)."""
        await self._store.clear_auth_attempts(hash_attempt_key(key))
