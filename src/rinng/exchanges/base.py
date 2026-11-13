"""Giao diện chung mà mọi sàn phải cài (docs/08-kien-truc.md mục 6).

Quy ước cho mọi phương thức:
- `symbol` là tên gốc trên sàn (lấy từ `Instrument.venue_symbol`).
- Khoảng thời gian là [start, end): gồm `start`, không gồm `end`.
- Kết quả trả về từng trang. Trong một trang các dòng tăng dần theo thời gian;
  thứ tự giữa các trang thì không đảm bảo (OKX trả từ mới về cũ).
- Thời gian là mili giây UTC kiểu int; giá và khối lượng kiểu float.
- Khối lượng tính bằng đồng base (BTC với BTCUSDT), không tính bằng số hợp đồng.
- Trường mà sàn không cung cấp có giá trị None.

Các trường của từng loại dòng:
- kline: open_time, open, high, low, close, volume, quote_volume, trades,
  taker_buy_volume, is_closed
- mark kline: open_time, open, high, low, close, is_closed
- funding: funding_time, rate, mark_price
- open interest: time, oi_base, oi_value
- long/short: time, ratio, long_pct, short_pct
- taker volume: time, buy_volume, sell_volume
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Protocol

Row = dict[str, Any]
Pages = Iterator[list[Row]]

_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}


def timeframe_ms(timeframe: str) -> int:
    """Độ dài một khung thời gian, ví dụ '15m', '4h', '1d', '1w'."""
    unit = timeframe[-1:]
    if unit not in _UNIT_MS or not timeframe[:-1].isdigit():
        raise ValueError(f"khung thời gian không hợp lệ: {timeframe!r}")
    return int(timeframe[:-1]) * _UNIT_MS[unit]


def to_ms(moment: datetime) -> int:
    """Đổi datetime sang mili giây UTC. Từ chối datetime không có múi giờ."""
    if moment.tzinfo is None:
        raise ValueError("datetime phải có múi giờ (dùng timezone UTC)")
    return int(moment.astimezone(UTC).timestamp() * 1000)


class Exchange(Protocol):
    name: str

    def klines(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> Pages: ...

    def mark_price_klines(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Pages: ...

    def funding(self, symbol: str, start: datetime, end: datetime) -> Pages: ...

    def open_interest(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages: ...

    def long_short(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages: ...

    def taker_volume(self, symbol: str, period: str, start: datetime, end: datetime) -> Pages: ...
