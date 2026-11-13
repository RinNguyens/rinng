"""Điều tiết tốc độ gọi API và các lỗi chung của lớp sàn.

Hai sàn giới hạn theo hai cách khác nhau:
- Binance tính theo weight mỗi phút và báo lượng đã dùng qua header.
- OKX tính số request trong một cửa sổ thời gian cho từng endpoint, không báo gì.

Cả hai bộ điều tiết mặc định chỉ dùng một nửa mức sàn cho phép.
"""

import time
from collections import deque
from collections.abc import Callable


class ExchangeError(Exception):
    """Sàn trả lỗi. `code` là mã lỗi của sàn nếu có."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class RateLimited(ExchangeError):
    """Vẫn bị giới hạn tốc độ sau khi đã chờ và thử lại hết số lần cho phép."""


class IpBanned(ExchangeError):
    """Binance trả HTTP 418: IP đã bị ban. Không được thử lại."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message, status=418)
        self.retry_after = retry_after


class WeightLimiter:
    """Giữ lượng weight đã dùng trong phút dưới `fraction` của `limit`.

    Lượng đã dùng lấy từ header của sàn qua `update`, không tự cộng.
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
            # Bộ đếm của sàn về 0 ở đầu mỗi phút.
            self._sleep(60 - self._clock() % 60 + 0.5)
            self.used = 0

    def update(self, used: int) -> None:
        self.used = used


class WindowLimiter:
    """Không quá `max_requests * fraction` request trong mỗi `window` giây (cửa sổ trượt)."""

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
