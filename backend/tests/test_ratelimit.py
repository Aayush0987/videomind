"""Tests for app.core.ratelimit (§8, §18.2). Always uses a fake clock --
never a real `asyncio.sleep`, so this suite runs instantly.
"""

import asyncio

import pytest
from app.core import ratelimit
from app.core.errors import DailyQuotaExhausted


class _FakeClock:
    """Injectable clock + sleep pair. `sleep` advances the fake clock
    instead of actually waiting, and yields once so concurrent tasks can
    interleave."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._now += seconds
        await asyncio.sleep(0)


async def test_calls_within_rpm_never_sleep() -> None:
    fake = _FakeClock()
    limiter = ratelimit.RateLimiter(rpm=3, clock=fake.time, sleep=fake.sleep)

    for _ in range(3):
        await limiter.acquire()

    assert fake.sleep_calls == []


async def test_nth_plus_one_call_blocks_until_window_slides() -> None:
    fake = _FakeClock()
    limiter = ratelimit.RateLimiter(rpm=2, clock=fake.time, sleep=fake.sleep)

    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()

    assert len(fake.sleep_calls) == 1
    assert fake.sleep_calls[0] == pytest.approx(60.0, abs=0.01)


async def test_daily_cap_raises_without_sleeping() -> None:
    fake = _FakeClock()
    limiter = ratelimit.RateLimiter(rpm=100, rpd=2, clock=fake.time, sleep=fake.sleep)

    await limiter.acquire()
    await limiter.acquire()
    with pytest.raises(DailyQuotaExhausted):
        await limiter.acquire()

    assert fake.sleep_calls == []


async def test_daily_window_slides_after_24_hours() -> None:
    fake = _FakeClock()
    limiter = ratelimit.RateLimiter(rpm=100, rpd=1, clock=fake.time, sleep=fake.sleep)

    await limiter.acquire()
    with pytest.raises(DailyQuotaExhausted):
        await limiter.acquire()

    fake.advance(86400.0 + 1.0)
    await limiter.acquire()  # succeeds again once the day window has slid


async def test_rpd_none_never_raises() -> None:
    fake = _FakeClock()
    limiter = ratelimit.RateLimiter(rpm=1000, rpd=None, clock=fake.time, sleep=fake.sleep)

    for _ in range(50):
        await limiter.acquire()


async def test_concurrent_acquires_serialize() -> None:
    fake = _FakeClock()
    limiter = ratelimit.RateLimiter(rpm=1, clock=fake.time, sleep=fake.sleep)
    results: list[float] = []

    async def worker() -> None:
        await limiter.acquire()
        results.append(fake.time())

    await asyncio.gather(*(worker() for _ in range(5)))

    assert len(results) == 5
    ordered = sorted(results)
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        assert later - earlier >= 60.0 - 1e-6
    assert len(fake.sleep_calls) == 4  # n-1 acquires had to wait


def test_get_rate_limiter_registry_keyed_by_provider_and_model() -> None:
    a = ratelimit.get_rate_limiter("gemini", "gemini-2.5-flash", rpm=10, rpd=1000)
    b = ratelimit.get_rate_limiter("gemini", "gemini-2.5-flash", rpm=10, rpd=1000)
    c = ratelimit.get_rate_limiter("openai", "gpt-4o", rpm=60)

    assert a is b
    assert a is not c


def test_reset_registry_clears_cached_instances() -> None:
    a = ratelimit.get_rate_limiter("gemini", "m", rpm=10)

    ratelimit.reset_registry()
    b = ratelimit.get_rate_limiter("gemini", "m", rpm=10)

    assert a is not b
