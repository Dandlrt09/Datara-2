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
