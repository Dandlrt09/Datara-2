"""Unit tests for ``server/services/events.py`` — EventBus.

Covers:
- EventBus lifecycle (subscribe, publish, unsubscribe, queue drain)
- Drop-on-full policy (maxsize=64 put_nowait on full queue)
- CancelledError while awaiting queue.get() -> unsubscribe + re-raise
- Per-user fan-out (N subscribers receive every event independently)
"""

from __future__ import annotations

import asyncio
import time

import pytest

from server.services.events import EventBus, SessionEvent, SessionEventType


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def sample_event():
    return SessionEvent(
        type=SessionEventType.CREATED,
        session_id="ses_test123",
        timestamp=time.time(),
        payload={"session": {"id": "ses_test123", "title": "Test"}},
    )


def _ev(type_: SessionEventType = SessionEventType.CREATED) -> SessionEvent:
    """Shorthand for creating an event with minimal boilerplate."""
    return SessionEvent(type=type_, session_id="s", timestamp=0)


class TestEventBusLifecycle:
    """Subscribe, publish, drain, unsubscribe — happy path."""

    async def test_subscribe_returns_queue(self, bus):
        q = await bus.subscribe(1)
        assert q is not None
        assert q.maxsize == EventBus.QUEUE_MAX

    async def test_subscribe_increments_subscriber_count(self, bus):
        await bus.subscribe(1)
        assert bus.subscriber_count == 1

    async def test_subscribe_multiple_times_same_user(self, bus):
        q1 = await bus.subscribe(1)
        q2 = await bus.subscribe(1)
        assert bus.subscriber_count == 2
        assert q1 is not q2

    async def test_publish_delivers_to_subscriber(self, bus, sample_event):
        q = await bus.subscribe(1)
        delivered = bus.publish(1, sample_event)
        assert delivered == 1
        received = await asyncio.wait_for(q.get(), timeout=1)
        assert received is sample_event  # same object reference

    async def test_publish_returns_zero_for_no_subscribers(self, bus, sample_event):
        delivered = bus.publish(1, sample_event)
        assert delivered == 0

    async def test_unsubscribe_removes_queue(self, bus):
        q = await bus.subscribe(1)
        bus.unsubscribe(1, q)
        assert bus.subscriber_count == 0
        # No more delivery after unsubscribe
        bus.publish(1, _ev())
        assert q.empty()

    async def test_unsubscribe_idempotent(self, bus):
        q = await bus.subscribe(1)
        bus.unsubscribe(1, q)
        bus.unsubscribe(1, q)  # second call — no-op
        assert bus.subscriber_count == 0

    async def test_unsubscribe_unknown_user(self, bus):
        q = asyncio.Queue()
        bus.unsubscribe(999, q)  # should not raise

    async def test_unsubscribe_unknown_queue(self, bus):
        q1 = await bus.subscribe(1)
        q2 = asyncio.Queue()
        bus.unsubscribe(1, q2)  # should not affect q1
        assert bus.subscriber_count == 1

    async def test_user_count_cleans_up_after_last_subscriber(self, bus):
        q = await bus.subscribe(1)
        assert bus.user_count == 1
        bus.unsubscribe(1, q)
        assert bus.user_count == 0

    async def test_drain_queue_after_publish(self, bus, sample_event):
        q = await bus.subscribe(1)
        bus.publish(1, sample_event)
        bus.publish(1, sample_event)
        received = []
        received.append(await asyncio.wait_for(q.get(), timeout=1))
        received.append(await asyncio.wait_for(q.get(), timeout=1))
        assert len(received) == 2
        assert q.empty()


class TestDropOnFull:
    """When a queue reaches maxsize, new events are silently dropped."""

    async def test_drop_when_queue_full(self, bus):
        q = await bus.subscribe(1)
        # Fill the queue to maxsize
        for _ in range(EventBus.QUEUE_MAX):
            q.put_nowait(_ev())
        # One more should drop
        ev = _ev(SessionEventType.CREATED)
        ev.session_id = "drop"
        delivered = bus.publish(1, ev)
        assert delivered == 0  # queue was full
        # Drop counter incremented
        assert bus.drop_count >= 1

    async def test_drop_counter_is_monotonic(self, bus):
        q = await bus.subscribe(1)
        # Fill to maxsize
        for _ in range(EventBus.QUEUE_MAX):
            q.put_nowait(_ev())
        # Drop a few
        for _ in range(3):
            bus.publish(1, _ev())
        assert bus.drop_count >= 3

    async def test_other_subscribers_not_affected_by_full_queue(self, bus):
        q1 = await bus.subscribe(1)
        q2 = await bus.subscribe(1)
        # Fill q1 but keep q2 empty
        for _ in range(EventBus.QUEUE_MAX):
            q1.put_nowait(_ev())
        ev = _ev(SessionEventType.CREATED)
        ev.session_id = "ok"
        delivered = bus.publish(1, ev)
        # One queue was full (q1), so delivery count only reflects q2
        assert delivered == 1
        assert q2.qsize() == 1

    async def test_drop_does_not_block(self, bus):
        """put_nowait raises QueueFull but is caught — publish never blocks."""
        q = await bus.subscribe(1)
        for _ in range(EventBus.QUEUE_MAX):
            q.put_nowait(_ev())
        # This should not raise
        bus.publish(1, _ev())


class TestCancelledErrorCleanup:
    """When an SSE loop is cancelled at await queue.get(),
    the subscriber must be unsubscribed before re-raising."""

    async def test_unsubscribe_on_cancelled_error(self, bus, sample_event):
        """Simulate the pattern used by the SSE endpoint:
        try:
            event = await queue.get()
        except CancelledError:
            bus.unsubscribe(user_id, q)
            raise
        """
        q = await bus.subscribe(1)

        async def _reader():
            try:
                # Do NOT put an event first — await on an empty queue
                # so we're guaranteed to be blocked when cancelled.
                return await q.get()
            except asyncio.CancelledError:
                bus.unsubscribe(1, q)
                raise

        reader_task = asyncio.create_task(_reader())
        # Give the task time to start and block on q.get()
        await asyncio.sleep(0.05)
        reader_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader_task

        # After cancellation, subscriber count should be back to 0
        assert bus.subscriber_count == 0
        assert bus.user_count == 0

    async def test_other_subscribers_survive_one_cancellation(self, bus, sample_event):
        """When one subscriber is cancelled, other subscribers for the same
        user should remain registered."""
        q1 = await bus.subscribe(1)
        q2 = await bus.subscribe(1)

        async def _reader():
            try:
                # Block on empty queue so cancellation catches us at await
                return await q1.get()
            except asyncio.CancelledError:
                bus.unsubscribe(1, q1)
                raise

        reader_task = asyncio.create_task(_reader())
        await asyncio.sleep(0.05)
        reader_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader_task

        # q2 should still be registered (user_count stays > 0)
        assert bus.subscriber_count == 1
        assert bus.user_count == 1


class TestPerUserFanOut:
    """Multiple subscribers receive independent copies of every event."""

    async def test_two_subscribers_receive_same_event(self, bus, sample_event):
        q1 = await bus.subscribe(1)
        q2 = await bus.subscribe(1)

        delivered = bus.publish(1, sample_event)
        assert delivered == 2

        received1 = await asyncio.wait_for(q1.get(), timeout=1)
        received2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert received1 is sample_event
        assert received2 is sample_event

    async def test_different_users_isolated(self, bus, sample_event):
        q_a = await bus.subscribe(1)
        q_b = await bus.subscribe(2)

        bus.publish(1, sample_event)
        assert q_a.qsize() == 1
        assert q_b.qsize() == 0

        bus.publish(2, sample_event)
        assert q_b.qsize() == 1

    async def test_events_delivered_in_order(self, bus):
        q = await bus.subscribe(1)
        events = [
            SessionEvent(type=SessionEventType.CREATED, session_id="s1", timestamp=1),
            SessionEvent(type=SessionEventType.UPDATED, session_id="s1", timestamp=2),
            SessionEvent(type=SessionEventType.TITLED, session_id="s1", timestamp=3),
        ]
        for ev in events:
            bus.publish(1, ev)
        received = []
        for _ in range(3):
            received.append(await asyncio.wait_for(q.get(), timeout=1))
        assert [e.type for e in received] == [
            SessionEventType.CREATED,
            SessionEventType.UPDATED,
            SessionEventType.TITLED,
        ]
        assert [e.timestamp for e in received] == [1, 2, 3]


class TestSessionEvent:
    """SessionEvent dataclass basics."""

    def test_event_creation(self):
        ev = SessionEvent(
            type=SessionEventType.TITLED,
            session_id="ses_abc",
            timestamp=123456.0,
            payload={"title": "My Session"},
        )
        assert ev.type == SessionEventType.TITLED
        assert ev.session_id == "ses_abc"
        assert ev.timestamp == 123456.0
        assert ev.payload["title"] == "My Session"

    def test_event_default_payload(self):
        ev = SessionEvent(
            type=SessionEventType.DELETED,
            session_id="ses_abc",
            timestamp=123456.0,
        )
        assert ev.payload == {}

    def test_event_type_enum_values(self):
        """Enum member values should match the SSE wire event names."""
        assert SessionEventType.CREATED.value == "CREATED"
        assert SessionEventType.UPDATED.value == "UPDATED"
        assert SessionEventType.TITLED.value == "TITLED"
        assert SessionEventType.DELETED.value == "DELETED"
        assert SessionEventType.STREAMING_STARTED.value == "STREAMING_STARTED"
        assert SessionEventType.STREAMING_ENDED.value == "STREAMING_ENDED"