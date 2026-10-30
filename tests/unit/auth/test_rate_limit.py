"""Unit tests for the in-memory attempt limiter (S1-S3)."""

from server.api.rate_limit import AttemptLimiter


def _clock_starting_at(start: float = 0.0):
    now = [start]
    return now, lambda: now[0]


class TestAttemptLimiter:
    def test_allows_up_to_the_limit_then_blocks(self):
        _now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock)

        for _ in range(5):
            assert limiter.retry_after("ip:1") is None
            limiter.record("ip:1")

        assert limiter.retry_after("ip:1") is not None

    def test_a_successful_clear_frees_the_key(self):
        _now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock)
        for _ in range(5):
            limiter.record("ip:1")
        assert limiter.retry_after("ip:1") is not None

        limiter.clear("ip:1")

        assert limiter.retry_after("ip:1") is None

    def test_attempts_expire_after_the_window(self):
        now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock)
        for _ in range(5):
            limiter.record("ip:1")
        assert limiter.retry_after("ip:1") is not None

        now[0] = 15 * 60 + 1

        assert limiter.retry_after("ip:1") is None

    def test_retry_after_is_positive_seconds(self):
        now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock)
        for _ in range(5):
            limiter.record("ip:1")

        retry = limiter.retry_after("ip:1")
        assert retry == 15 * 60

        now[0] = 15 * 60 - 30
        assert 0 < limiter.retry_after("ip:1") <= 30

    def test_keys_are_independent(self):
        _now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock)
        for _ in range(5):
            limiter.record("ip:1")

        assert limiter.retry_after("ip:1") is not None
        assert limiter.retry_after("ip:2") is None


class TestTrackedKeyCap:
    """The map is bounded so distinct keys cannot grow memory forever."""

    def test_map_stays_at_the_cap_when_new_keys_arrive(self):
        _now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock, max_tracked_keys=2)

        limiter.record("k1")
        limiter.record("k2")
        limiter.record("k3")

        assert len(limiter._events) == 2

    def test_expired_keys_are_swept_instead_of_evicting_live_ones(self):
        now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock, max_tracked_keys=2)

        limiter.record("old")
        now[0] = 15 * 60 + 1  # "old" left the window
        limiter.record("live1")
        limiter.record("live2")

        assert "old" not in limiter._events
        assert "live1" in limiter._events
        assert "live2" in limiter._events
        assert len(limiter._events) == 2

    def test_oldest_live_key_is_evicted_when_all_are_live(self):
        now, clock = _clock_starting_at()
        limiter = AttemptLimiter(clock=clock, max_tracked_keys=2)

        limiter.record("first")
        now[0] = 1
        limiter.record("second")
        now[0] = 2
        limiter.record("third")

        assert "first" not in limiter._events
        assert "second" in limiter._events
        assert "third" in limiter._events
        assert len(limiter._events) == 2
