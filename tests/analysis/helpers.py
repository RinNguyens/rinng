"""Synthetic candles for analysis tests."""

from datetime import UTC, datetime, timedelta

import polars as pl

from rinng.store.schemas import OHLCV, conform

T0 = datetime(2026, 1, 5, tzinfo=UTC)  # Monday


def make_ohlcv(
    closes: list[float] | None = None,
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    opens: list[float] | None = None,
    volumes: list[float] | None = None,
    taker_buy: list[float] | None = None,
    timeframe: str = "1h",
    symbol: str = "BTC-USDT-PERP",
    start: datetime = T0,
) -> pl.DataFrame:
    """Candles from a price list. Missing high/low default to max/min of open, close."""
    if closes is None:
        raise ValueError("closes required")
    n = len(closes)
    opens = opens or [closes[0]] + closes[:-1]
    highs = highs or [max(o, c) for o, c in zip(opens, closes, strict=True)]
    lows = lows or [min(o, c) for o, c in zip(opens, closes, strict=True)]
    volumes = volumes or [10.0] * n
    taker_buy = taker_buy or [v / 2 for v in volumes]
    step = {"m": timedelta(minutes=1), "h": timedelta(hours=1), "d": timedelta(days=1)}
    unit = step[timeframe[-1]] * int(timeframe[:-1])
    frame = pl.DataFrame(
        {
            "exchange": ["binance"] * n,
            "symbol": [symbol] * n,
            "timeframe": [timeframe] * n,
            "open_time": [start + i * unit for i in range(n)],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "quote_volume": [v * c for v, c in zip(volumes, closes, strict=True)],
            "trades": [1] * n,
            "taker_buy_volume": taker_buy,
            "is_closed": [True] * n,
        }
    )
    return conform(frame, OHLCV)


def random_walk(
    n: int = 500, seed: int = 7, start: float = 100.0, timeframe: str = "1h"
) -> pl.DataFrame:
    import numpy as np

    rng = np.random.default_rng(seed)
    closes = start * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    opens = np.concatenate([[start], closes[:-1]])
    spread = np.abs(rng.normal(0, 0.004, n)) * closes
    highs = np.maximum(opens, closes) + spread
    lows = np.minimum(opens, closes) - spread
    volumes = rng.uniform(5, 50, n)
    return make_ohlcv(
        closes.tolist(),
        opens=opens.tolist(),
        highs=highs.tolist(),
        lows=lows.tolist(),
        volumes=volumes.tolist(),
        taker_buy=(volumes * rng.uniform(0.2, 0.8, n)).tolist(),
        timeframe=timeframe,
    )
