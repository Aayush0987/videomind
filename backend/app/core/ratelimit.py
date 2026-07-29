"""Deterministic token-bucket rate-limit guard, keyed per provider/purpose (§8).

A sliding-window limiter that gates calls *before* they're made, not a
reactive try/except. One `RateLimiter` instance per (provider, model) key,
held in a module-level registry because `acquire()` runs on every LLM call.
"""

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from app.config import settings
from app.core.errors import DailyQuotaExhausted

_MINUTE_SECONDS = 60.0
_HOUR_SECONDS = 3600.0
_DAY_SECONDS = 86400.0


class RateLimiter:
    """Sliding-window limiter, one instance per (provider, model) key.
    Module-level registry because it is called on every LLM invocation."""

    def __init__(
        self,
        rpm: int,
        rpd: int | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._rpm = rpm
        self._rpd = rpd
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._minute_calls: deque[float] = deque()
        self._day_calls: deque[float] = deque()

    async def acquire(self) -> None:
        """Blocks until a slot is free. Raises DailyQuotaExhausted if rpd is hit."""
        async with self._lock:
            now = self._clock()
            self._evict(self._day_calls, now, _DAY_SECONDS)
            self._check_daily_quota()
            self._evict(self._minute_calls, now, _MINUTE_SECONDS)
            while len(self._minute_calls) >= self._rpm:
                wait_for = self._minute_calls[0] + _MINUTE_SECONDS - now
                await self._sleep(max(wait_for, 0.0))
                now = self._clock()
                self._evict(self._day_calls, now, _DAY_SECONDS)
                self._check_daily_quota()
                self._evict(self._minute_calls, now, _MINUTE_SECONDS)
            self._minute_calls.append(now)
            self._day_calls.append(now)

    def _check_daily_quota(self) -> None:
        if self._rpd is not None and len(self._day_calls) >= self._rpd:
            raise DailyQuotaExhausted(f"Daily quota of {self._rpd} requests exhausted.")

    @staticmethod
    def _evict(window: deque[float], now: float, span: float) -> None:
        while window and now - window[0] >= span:
            window.popleft()


class IPRateLimiter:
    """Simple per-IP sliding-window cap on `POST /api/videos` (§14.3) — the
    public demo must not be a free Whisper farm. Synchronous: it gates the
    request handler, it does not block on a slot."""

    def __init__(self, limit: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, ip: str) -> bool:
        now = self._clock()
        window = self._hits[ip]
        while window and now - window[0] >= _HOUR_SECONDS:
            window.popleft()
        if len(window) >= self._limit:
            return False
        window.append(now)
        return True


_REGISTRY: dict[tuple[str, str], RateLimiter] = {}
_ip_limiter: IPRateLimiter | None = None


def get_rate_limiter(provider: str, model: str, *, rpm: int, rpd: int | None = None) -> RateLimiter:
    key = (provider, model)
    if key not in _REGISTRY:
        _REGISTRY[key] = RateLimiter(rpm=rpm, rpd=rpd)
    return _REGISTRY[key]


def get_ip_limiter() -> IPRateLimiter:
    global _ip_limiter  # noqa: PLW0603
    if _ip_limiter is None:
        _ip_limiter = IPRateLimiter(settings.ANALYZE_RATE_PER_HOUR)
    return _ip_limiter


def reset_registry() -> None:
    """Test-only escape hatch: clears cached limiters so tests don't leak
    accumulated call timestamps across the module-level registry."""
    global _ip_limiter  # noqa: PLW0603
    _REGISTRY.clear()
    _ip_limiter = None
