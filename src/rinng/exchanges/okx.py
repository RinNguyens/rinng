"""OKX: dữ liệu thị trường công khai của hợp đồng SWAP, không cần API key.

Khác Binance ở ba điểm mà mã dưới đây phải xử lý:
- Dữ liệu trả từ mới về cũ, phân trang lùi bằng `after` (hoặc `end`).
- Lỗi vẫn đi kèm HTTP 200; phải đọc `code` trong body.
- Nến từ 6 giờ trở lên mặc định mở theo UTC+8; phải dùng biến thể `utc`.

Định dạng phản hồi đã đối chiếu với lời gọi thật ngày 2026-11-13.
Nhóm thống kê `rubik` chỉ giữ 1440 bản ghi mới nhất; funding qua REST chỉ 3 tháng.
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx

from rinng.exchanges.base import Pages, Row, timeframe_ms, to_ms
from rinng.exchanges.ratelimit import ExchangeError, RateLimited, WindowLimiter

BASE_URL = "https://openapi.okx.com"
CANDLES_LIMIT = 300
MARK_CANDLES_LIMIT = 100
FUNDING_LIMIT = 400
STATS_LIMIT = 100
RATE_LIMIT_CODE = "50011"

_BARS = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6Hutc",
    "12h": "12Hutc",
    "1d": "1Dutc",
    "1w": "1Wutc",
}

CANDLES = "/api/v5/market/history-candles"
MARK_CANDLES = "/api/v5/market/history-mark-price-candles"
FUNDING = "/api/v5/public/funding-rate-history"
OPEN_INTEREST = "/api/v5/rubik/stat/contracts/open-interest-history"
LONG_SHORT = "/api/v5/rubik/stat/contracts/long-short-account-ratio-contract"
TAKER_VOLUME = "/api/v5/rubik/stat/taker-volume-contract"

# Số request mỗi 2 giây theo tài liệu của sàn.
_LIMITS = {
    CANDLES: 20,
    MARK_CANDLES: 20,
    FUNDING: 10,
    OPEN_INTEREST: 10,
    LONG_SHORT: 5,
    TAKER_VOLUME: 5,
}


def okx_bar(timeframe: str) -> str:
    try:
        return _BARS[timeframe]
    except KeyError:
        raise ValueError(
            f"OKX không hỗ trợ khung {timeframe!r}; dùng một trong {list(_BARS)}"
        ) from None


class Okx:
    name = "okx"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=20.0)
        self._max_retries = max_retries
        self._sleep = sleep
        self._limiters = {path: WindowLimiter(n, 2.0, sleep=sleep) for path, n in _LIMITS.items()}

    # --- phương thức của giao diện Exchange ---

    def klines(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> Pages:
        params = {"instId": symbol, "bar": okx_bar(timeframe)}
        for page in self._pages_after(CANDLES, params, start, end, CANDLES_LIMIT):
            yield [
                {
                    "open_time": int(x[0]),
                    "open": float(x[1]),
                    "high": float(x[2]),
                    "low": float(x[3]),
                    "close": float(x[4]),
                    # x[5] là số hợp đồng; x[6] mới là khối lượng tính bằng đồng base.
                    "volume": float(x[6]),
                    "quote_volume": float(x[7]),
                    "trades": None,
                    "taker_buy_volume": None,
                    "is_closed": x[8] == "1",
                }
                for x in page
            ]

    def mark_price_klines(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Pages:
        params = {"instId": symbol, "bar": okx_bar(timeframe)}
        for page in self._pages_after(MARK_CANDLES, params, start, end, MARK_CANDLES_LIMIT):
            yield [
                {
                    "open_time": int(x[0]),
                    "open": float(x[1]),
                    "high": float(x[2]),
                    "low": float(x[3]),
                    "close": float(x[4]),
                    "is_closed": x[5] == "1",
                }
                for x in page
            ]

    def funding(self, symbol: str, start: datetime, end: datetime) -> Pages:
        pages = self._pages_after(
            FUNDING, {"instId": symbol}, start, end, FUNDING_LIMIT, time_key="fundingTime"
        )
        for page in pages:
            yield [
                {
                    "funding_time": int(x["fundingTime"]),
                    "rate": float(x["realizedRate"] or x["fundingRate"]),
                    "mark_price": None,
                }
                for x in page
            ]

    def open_interest(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages:
        for page in self._pages_stats(OPEN_INTEREST, symbol, period, start, end):
            yield [
                {"time": int(x[0]), "oi_base": float(x[2]), "oi_value": float(x[3])} for x in page
            ]

    def long_short(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages:
        for page in self._pages_stats(LONG_SHORT, symbol, period, start, end):
            yield [
                {"time": int(x[0]), "ratio": float(x[1]), "long_pct": None, "short_pct": None}
                for x in page
            ]

    def taker_volume(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages:
        # unit=0: khối lượng tính bằng đồng base. Thứ tự cột là [ts, bán, mua].
        extra = {"unit": "0"}
        for page in self._pages_stats(TAKER_VOLUME, symbol, period, start, end, extra):
            yield [
                {"time": int(x[0]), "buy_volume": float(x[2]), "sell_volume": float(x[1])}
                for x in page
            ]

    # --- nội bộ ---

    def _pages_after(
        self,
        path: str,
        params: dict[str, Any],
        start: datetime,
        end: datetime,
        limit: int,
        time_key: str | int = 0,
    ):
        """Phân trang lùi: `after=T` trả các bản ghi cũ hơn T, mới nhất trước."""
        start_ms, cursor = to_ms(start), to_ms(end)
        while cursor > start_ms:
            raw = self._get(path, {**params, "after": cursor, "limit": limit})
            if not raw:
                return
            page = [x for x in raw if start_ms <= int(x[time_key]) < cursor]
            page.reverse()
            if page:
                yield page
            oldest = int(raw[-1][time_key])
            if len(raw) < limit or oldest >= cursor:
                return
            cursor = oldest

    def _pages_stats(
        self,
        path: str,
        symbol: str,
        period: str,
        start: datetime,
        end: datetime,
        extra: dict[str, Any] | None = None,
    ):
        """Phân trang lùi cho nhóm `rubik`, dùng `begin`/`end` thay cho `after`."""
        timeframe_ms(period)
        params = {"instId": symbol, "period": okx_bar(period), **(extra or {})}
        start_ms, cursor = to_ms(start), to_ms(end)
        while cursor > start_ms:
            query = {**params, "begin": start_ms, "end": cursor - 1, "limit": STATS_LIMIT}
            raw = self._get(path, query)
            if not raw:
                return
            page = [x for x in raw if start_ms <= int(x[0]) < cursor]
            page.reverse()
            if page:
                yield page
            oldest = int(raw[-1][0])
            if len(raw) < STATS_LIMIT or oldest >= cursor:
                return
            cursor = oldest

    def _get(self, path: str, params: dict[str, Any]) -> list[Row] | list[list[str]]:
        limiter = self._limiters[path]
        for attempt in range(self._max_retries + 1):
            limiter.acquire()
            response = self._client.get(path, params=params)
            try:
                body = response.json()
            except ValueError:
                body = {}
            code = str(body.get("code", ""))
            if code == RATE_LIMIT_CODE or response.status_code == 429:
                if attempt == self._max_retries:
                    raise RateLimited(
                        "OKX vẫn báo giới hạn tốc độ sau khi đã chờ",
                        status=response.status_code,
                        code=code or None,
                    )
                self._sleep(2.0 * (attempt + 1))
                continue
            if response.status_code >= 400 or code != "0":
                raise ExchangeError(
                    f"OKX HTTP {response.status_code} code={code}: {body.get('msg', '')}",
                    status=response.status_code,
                    code=code or None,
                )
            return body["data"]
        raise AssertionError("không tới được đây")
