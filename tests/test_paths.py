from datetime import date
from pathlib import Path

import pytest

from rinng.store.paths import DataPaths

P = DataPaths(Path("data"))


def test_raw_partition():
    got = P.raw_partition("binance", "klines_1m", "BTCUSDT", date(2026, 11, 10))
    assert got == Path("data/raw/binance/klines_1m/BTCUSDT/date=2026-11-10")


def test_curated_partition():
    got = P.curated_partition("ohlcv", "binance", "BTC-USDT-PERP", 2026, timeframe="1h")
    assert got == Path(
        "data/curated/ohlcv/exchange=binance/symbol=BTC-USDT-PERP/timeframe=1h/year=2026"
    )


def test_curated_partition_without_timeframe():
    got = P.curated_partition("funding", "okx", "BTC-USDT-PERP", 2025)
    assert got == Path("data/curated/funding/exchange=okx/symbol=BTC-USDT-PERP/year=2025")


def test_derived():
    got = P.derived("events", "smc", 1, "BTC-USDT-PERP", "4h")
    assert got == Path("data/events/smc/v1/symbol=BTC-USDT-PERP/timeframe=4h")


def test_derived_rejects_unknown_zone():
    with pytest.raises(ValueError):
        P.derived("raw", "smc", 1, "BTC-USDT-PERP", "4h")
