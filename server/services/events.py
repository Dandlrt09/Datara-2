"""Real-time session event bus: per-user bounded queues with drop-on-full.

Provides ``SessionEventType`` enum, ``SessionEvent`` dataclass, and a
singleton ``EventBus`` that fans out events to per-user subscribers via
bounded ``asyncio.Queue`` instances with a ``put_nowait`` drop policy.

Design: same-process, in-memory, no persistence. The bus is stateless
across server restarts — subscriptions and queued events are lost, which
is acceptable because the frontend reconnects and invalidates queries on
reconnect (see ``useSessionEvents``).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SessionEventType(str, Enum):
    """Canonical session event types (enum member name = SSE event name)."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    TITLED = "TITLED"
    DELETED = "DELETED"
    STREAMING_STARTED = "STREAMING_STARTED"
    STREAMING_ENDED = "STREAMING_ENDED"


@dataclass
class SessionEvent:
    """A single session-level event published through the bus.

    Attributes:
        type: The event type discriminator.
        session_id: Opaque session identifier (``ses_``-prefixed).
        timestamp: Epoch seconds (``time.time()``).
        payload: Event-specific data. For ``TITLED``: ``{"title": ...}``;
            for ``STREAMING_*``: ``{"is_streaming": true|false}``;
            for ``CREATED``/``UPDATED``: ``{"session": {...}}``;
            for ``DELETED``: ``{}``.
    """

    type: SessionEventType
    session_id: str
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Per-user event registry with bounded ``asyncio.Queue`` fan-out.

    Usage::

        bus = EventBus()
        q = await bus.subscribe(user_id=42)
        bus.publish(user_id=42, event)
        # ... read from q in SSE loop ...
        bus.unsubscribe(user_id=42, q)

    Thread-safety: all public methods are coroutine-safe. Internal dict
    mutations use the event loop's default lock (single-threaded asyncio).
    """

    QUEUE_MAX = 64

    def __init__(self) -> None:
        # user_id -> set of subscriber queues
        self._subscribers: dict[int, set[asyncio.Queue[SessionEvent]]] = (
            defaultdict(set)
        )
        # monotonic drop counter for observability
        self._drop_count: int = 0

    async def subscribe(self, user_id: int) -> asyncio.Queue[SessionEvent]:
        """Register a new subscriber for *user_id*.

        Returns a fresh ``asyncio.Queue`` (maxsize = ``QUEUE_MAX``). The
        caller **must** call ``unsubscribe()`` when done — the bus does
        not auto-cleanup orphan queues.
        """
        q: asyncio.Queue[SessionEvent] = asyncio.Queue(maxsize=self.QUEUE_MAX)
        self._subscribers[user_id].add(q)
        logger.debug("EventBus: subscribed user=%d (total subs=%d)", user_id, len(self._subscribers[user_id]))
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue[SessionEvent]) -> None:
        """Remove a subscriber queue for *user_id*.

        Safe to call multiple times: if *q* is not in the set, this is a
        no-op. Cleans up the user entry entirely when its last subscriber
        leaves.
        """
        subs = self._subscribers.get(user_id)
        if subs is None:
            return
        subs.discard(q)
        if not subs:
            del self._subscribers[user_id]
        logger.debug("EventBus: unsubscribed user=%d", user_id)

    def publish(self, user_id: int, event: SessionEvent) -> int:
        """Publish *event* to every subscriber of *user_id*.

        Uses ``Queue.put_nowait`` — queues that have reached ``maxsize``
        silently drop the event. Returns the number of queues that
        **successfully received** the event (i.e. delivered count).
        """
        subs = self._subscribers.get(user_id)
        if not subs:
            return 0

        delivered = 0
        for q in list(subs):
            try:
                q.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                self._drop_count += 1
        return delivered

    @property
    def drop_count(self) -> int:
        """How many events have been dropped due to full queues."""
        return self._drop_count

    @property
    def subscriber_count(self) -> int:
        """Total active subscriber queues across all users."""
        return sum(len(subs) for subs in self._subscribers.values())

    @property
    def user_count(self) -> int:
        """Number of distinct users with at least one subscriber."""
        return len(self._subscribers)