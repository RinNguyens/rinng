"""Binance USDⓈ-M Futures: dữ liệu thị trường công khai, không cần API key.

Định dạng phản hồi đã đối chiếu với lời gọi thật ngày 2026-11-13.
Nhóm /futures/data/* chỉ giữ khoảng 30 ngày; hỏi xa hơn sàn trả lỗi -1130.
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx

from rinng.exchanges.base import Pages, Row, timeframe_ms, to_ms
from rinng.exchanges.ratelimit import (
    ExchangeError,
    IpBanned,
    RateLimited,
    WeightLimiter,
    WindowLimiter,
)

BASE_URL = "https://fapi.binance.com"
KLINES_LIMIT = 1500
FUNDING_LIMIT = 1000
STATS_LIMIT = 500
PERIODS = ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d")


class Binance:
    name = "binance"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        weight_limit: int = 2400,
        max_retries: int = 3,
        now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=20.0)
        self._max_retries = max_retries
        self._now_ms = now_ms
        self._sleep = sleep
        self._weight = WeightLimiter(weight_limit, sleep=sleep)
        # Hai nhóm endpoint này có giới hạn riêng và không trả header weight.
        self._funding_limiter = WindowLimiter(500, 300, sleep=sleep)
        self._stats_limiter = WindowLimiter(1000, 300, sleep=sleep)

    def sync_limits(self) -> None:
        """Đọc giới hạn weight hiện hành từ sàn thay cho giá trị mặc định."""
        info = self._get("/fapi/v1/exchangeInfo", {}, self._weight)
        for limit in info.get("rateLimits", []):
            if limit.get("rateLimitType") == "REQUEST_WEIGHT" and limit.get("interval") == "MINUTE":
                per_minute = limit["limit"] / limit.get("intervalNum", 1)
                self._weight.budget = per_minute * 0.5

    # --- phương thức của giao diện Exchange ---

    def klines(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> Pages:
        timeframe_ms(timeframe)
        params = {"symbol": symbol, "interval": timeframe}
        for page in self._pages("/fapi/v1/klines", params, self._weight, start, end, KLINES_LIMIT):
            yield [self._kline(x) for x in page]

    def mark_price_klines(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Pages:
        timeframe_ms(timeframe)
        params = {"symbol": symbol, "interval": timeframe}
        path = "/fapi/v1/markPriceKlines"
        for page in self._pages(path, params, self._weight, start, end, KLINES_LIMIT):
            yield [self._mark_kline(x) for x in page]

    def funding(self, symbol: str, start: datetime, end: datetime) -> Pages:
        pages = self._pages(
            "/fapi/v1/fundingRate",
            {"symbol": symbol},
            self._funding_limiter,
            start,
            end,
            FUNDING_LIMIT,
            time_key="fundingTime",
        )
        for page in pages:
            yield [
                {
                    "funding_time": int(x["fundingTime"]),
                    "rate": float(x["fundingRate"]),
                    "mark_price": float(x["markPrice"]) if x.get("markPrice") else None,
                }
                for x in page
            ]

    def open_interest(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages:
        for page in self._stats("openInterestHist", symbol, period, start, end):
            yield [
                {
                    "time": int(x["timestamp"]),
                    "oi_base": float(x["sumOpenInterest"]),
                    "oi_value": float(x["sumOpenInterestValue"]),
                }
                for x in page
            ]

    def long_short(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages:
        for page in self._stats("globalLongShortAccountRatio", symbol, period, start, end):
            yield [
                {
                    "time": int(x["timestamp"]),
                    "ratio": float(x["longShortRatio"]),
                    "long_pct": float(x["longAccount"]),
                    "short_pct": float(x["shortAccount"]),
                }
                for x in page
            ]

    def taker_volume(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages:
        for page in self._stats("takerlongshortRatio", symbol, period, start, end):
            yield [
                {
                    "time": int(x["timestamp"]),
                    "buy_volume": float(x["buyVol"]),
                    "sell_volume": float(x["sellVol"]),
                }
                for x in page
            ]

    # --- nội bộ ---

    def _stats(self, endpoint: str, symbol: str, period: str, start: datetime, end: datetime):
        """Phân trang lùi theo thời gian.

        Khác klines và funding: khi khoảng hỏi có nhiều hơn `limit` điểm, nhóm /futures/data/*
        trả `limit` điểm MỚI NHẤT trong khoảng (vẫn xếp tăng dần), không phải cũ nhất.
        Đã kiểm trên sàn thật ngày 2026-11-13. Vì vậy lùi `endTime` về trước điểm cũ nhất.
        """
        if period not in PERIODS:
            raise ValueError(f"period không hợp lệ: {period!r}; dùng một trong {PERIODS}")
        path = f"/futures/data/{endpoint}"
        start_ms, cursor = to_ms(start), to_ms(end)
        while cursor > start_ms:
            query = {
                "symbol": symbol,
                "period": period,
                "startTime": start_ms,
                "endTime": cursor - 1,
                "limit": STATS_LIMIT,
            }
            raw = self._get(path, query, self._stats_limiter)
            page = [x for x in raw if start_ms <= int(x["timestamp"]) < cursor]
            if not page:
                return
            yield page
            if len(raw) < STATS_LIMIT:
                return
            cursor = int(page[0]["timestamp"])

    def _pages(
        self,
        path: str,
        params: dict[str, Any],
        limiter: WeightLimiter | WindowLimiter,
        start: datetime,
        end: datetime,
        limit: int,
        time_key: str | int = 0,
    ):
        """Phân trang tiến theo thời gian: sàn trả từ cũ đến mới kể từ `startTime`."""
        cursor, end_ms = to_ms(start), to_ms(end)
        while cursor < end_ms:
            query = {**params, "startTime": cursor, "endTime": end_ms - 1, "limit": limit}
            raw = self._get(path, query, limiter)
            page = [x for x in raw if cursor <= int(x[time_key]) < end_ms]
            if not page:
                return
            yield page
            if len(raw) < limit:
                return
            cursor = int(page[-1][time_key]) + 1

    def _get(self, path: str, params: dict[str, Any], limiter: WeightLimiter | WindowLimiter):
        for attempt in range(self._max_retries + 1):
            limiter.acquire()
            try:
                response = self._client.get(path, params=params)
            except httpx.TransportError:
                # Lỗi mạng thoáng qua (connection reset, timeout): chờ rồi thử lại.
                if attempt == self._max_retries:
                    raise
                self._sleep(2.0 * (attempt + 1))
                continue
            used = response.headers.get("x-mbx-used-weight-1m")
            if used is not None:
                self._weight.update(int(used))
            if response.status_code == 418:
                retry_after = _retry_after(response)
                raise IpBanned(
                    f"Binance đã ban IP này (HTTP 418), hết ban sau {retry_after} giây",
                    retry_after=retry_after,
                )
            if response.status_code == 429:
                if attempt == self._max_retries:
                    raise RateLimited("Binance vẫn trả 429 sau khi đã chờ", status=429)
                self._sleep(_retry_after(response) or 60.0)
                continue
            if response.status_code >= 400:
                raise _error(response)
            return response.json()
        raise AssertionError("không tới được đây")

    def _kline(self, x: list) -> Row:
        return {
            "open_time": int(x[0]),
            "open": float(x[1]),
            "high": float(x[2]),
            "low": float(x[3]),
            "close": float(x[4]),
            "volume": float(x[5]),
            "quote_volume": float(x[7]),
            "trades": int(x[8]),
            "taker_buy_volume": float(x[9]),
            "is_closed": int(x[6]) < self._now_ms(),
        }

    def _mark_kline(self, x: list) -> Row:
        return {
            "open_time": int(x[0]),
            "open": float(x[1]),
            "high": float(x[2]),
            "low": float(x[3]),
            "close": float(x[4]),
            "is_closed": int(x[6]) < self._now_ms(),
        }


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _error(response: httpx.Response) -> ExchangeError:
    try:
        body = response.json()
        code, message = str(body.get("code")), body.get("msg", "")
    except ValueError:
        code, message = None, response.text[:200]
    return ExchangeError(
        f"Binance HTTP {response.status_code} code={code}: {message}",
        status=response.status_code,
        code=code,
    )
