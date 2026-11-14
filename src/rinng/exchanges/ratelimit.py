"""API rate throttling and common errors of the exchange layer.

The two exchanges limit differently:
- Binance counts weight per minute and reports usage via headers.
- OKX counts requests per time window per endpoint, and reports nothing.

Both throttlers default to using half of the allowed limit.
"""

import time
from collections import deque
from collections.abc import Callable


class ExchangeError(Exception):
    """Exchange returned an error. `code` is the exchange error code, if any."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class RateLimited(ExchangeError):
    """Still rate limited after waiting and exhausting the allowed retries."""


class IpBanned(ExchangeError):
    """Binance returned HTTP 418: the IP is banned. Do not retry."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message, status=418)
        self.retry_after = retry_after


class WeightLimiter:
    """Keep the weight used this minute below `fraction` of `limit`.

    Usage comes from the exchange headers via `update`, not counted locally.
    """

    def __init__(
        self,
        limit: int,
        fraction: float = 0.5,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.budget = limit * fraction
        self.used = 0
        self._clock = clock
        self._sleep = sleep

    def acquire(self) -> None:
        if self.used >= self.budget:
            # The exchange counter resets at the start of each minute.
            self._sleep(60 - self._clock() % 60 + 0.5)
            self.used = 0

    def update(self, used: int) -> None:
        self.used = used


class WindowLimiter:
    """At most `max_requests * fraction` requests per `window` seconds (sliding window)."""

    def __init__(
        self,
        max_requests: int,
        window: float,
        fraction: float = 0.5,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.capacity = max(1, int(max_requests * fraction))
        self.window = window
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[float] = deque()

    def acquire(self) -> None:
        now = self._clock()
        self._drop_expired(now)
        if len(self._sent) >= self.capacity:
            self._sleep(self._sent[0] + self.window - now)
            now = self._clock()
            self._drop_expired(now)
        self._sent.append(now)

    def _drop_expired(self, now: float) -> None:
        while self._sent and now - self._sent[0] >= self.window:
            self._sent.popleft()
