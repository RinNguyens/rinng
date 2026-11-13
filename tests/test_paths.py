from datetime import date
from pathlib import Path

import pytest

from rinng.store.paths import DataPaths

P = DataPaths(Path("data"))


def test_raw_partition():
    got = P.raw_partition("binance", "klines_1m", "BTCUSDT", date(2026, 11, 10))
    assert got == Path("data/raw/binance/klines_1m/BTCUSDT/date=2026-11-10")


def test_curated_partition():
    got = P.curated_partition("ohlcv", "binance", "BTC-USDT-PERP", "1h", 2026)
    assert got == Path(
        "data/curated/ohlcv/exchange=binance/symbol=BTC-USDT-PERP/timeframe=1h/year=2026"
    )


def test_derived():
    got = P.derived("events", "smc", 1, "BTC-USDT-PERP", "4h")
    assert got == Path("data/events/smc/v1/symbol=BTC-USDT-PERP/timeframe=4h")


def test_derived_rejects_unknown_zone():
    with pytest.raises(ValueError):
        P.derived("raw", "smc", 1, "BTC-USDT-PERP", "4h")
