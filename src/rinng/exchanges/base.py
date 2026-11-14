"""Common interface every exchange must implement (docs/08-architecture.md section 6).

Conventions for all methods:
- `symbol` is the venue-native name (from `Instrument.venue_symbol`).
- Time ranges are [start, end): `start` inclusive, `end` exclusive.
- Results are returned page by page. Rows within a page ascend in time;
    order across pages is not guaranteed (OKX returns newest first).
- Times are int UTC milliseconds; prices and volumes are floats.
- Volume is in base currency (BTC for BTCUSDT), not in contracts.
- Fields the exchange does not provide are None.

Fields per row type:
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

from rinng.timeframes import timeframe_ms

__all__ = ["Exchange", "Pages", "Row", "timeframe_ms", "to_ms"]

Row = dict[str, Any]
Pages = Iterator[list[Row]]


def to_ms(moment: datetime) -> int:
    """Convert a datetime to UTC milliseconds. Rejects naive datetimes."""
    if moment.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (use UTC)")
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
