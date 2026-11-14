"""curate_tail lặp nhiều lần phải cho đúng kết quả của curate + resample toàn bộ."""

from datetime import UTC, datetime

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from rinng.live.tail import curate_tail, tail_start
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.resample import resample_ohlcv
from rinng.store.schemas import OHLCV
from rinng.store.writer import write_curated
from rinng.timeframes import bucket_start_ms
from tests.analysis.helpers import make_ohlcv

TFS = ["15m", "1h", "4h", "1d", "1w"]


def _rows(frame: pl.DataFrame) -> list[dict]:
    out = []
    for r in frame.to_dicts():
        r = {k: v for k, v in r.items() if k not in ("exchange", "symbol", "timeframe")}
        r["open_time"] = int(r["open_time"].timestamp() * 1000)
        out.append(r)
    return out


@pytest.mark.parametrize("split", [17, 600, 2000])
def test_incremental_equals_full_resample(tmp_path, split):
    # Thứ Sáu 2026-01-09 tới thứ Hai: đi qua mốc ngày và mốc tuần.
    import numpy as np

    n = 4 * 1440
    closes = list(100 + np.cumsum(np.random.default_rng(3).normal(0, 0.1, n)))
    bars = make_ohlcv(closes, timeframe="1m", start=datetime(2026, 1, 9, tzinfo=UTC))
    paths = DataPaths(tmp_path)

    first = bars.head(split)
    write_curated(paths, OHLCV, first)
    for tf in TFS:
        write_curated(paths, OHLCV, resample_ohlcv(first, tf))
    rest = _rows(bars.slice(split))
    for i in range(0, len(rest), 97):  # từng lô nhỏ như khi chạy live
        curate_tail(paths, "binance", "BTC-USDT-PERP", rest[i : i + 97], TFS)

    for tf in TFS:
        got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe=tf)
        assert_frame_equal(got, resample_ohlcv(bars, tf).sort("open_time"), check_exact=False)


def test_forming_bars_are_not_written(tmp_path):
    paths = DataPaths(tmp_path)
    bars = make_ohlcv([1.0, 2.0, 3.0], timeframe="1m", start=datetime(2026, 1, 5, tzinfo=UTC))
    rows = _rows(bars)
    rows[-1]["is_closed"] = False
    curate_tail(paths, "binance", "BTC-USDT-PERP", rows, ["15m"])
    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1m")
    assert got.height == 2


def test_bucket_and_tail_start_alignment():
    monday = datetime(2026, 1, 12, tzinfo=UTC)
    wed = int(datetime(2026, 1, 14, 13, 7, tzinfo=UTC).timestamp() * 1000)
    assert bucket_start_ms(wed, "1w") == int(monday.timestamp() * 1000)
    assert bucket_start_ms(wed, "4h") == int(
        datetime(2026, 1, 14, 12, tzinfo=UTC).timestamp() * 1000
    )
    assert tail_start(datetime(2026, 1, 14, 13, 7, tzinfo=UTC), "1d") == datetime(
        2026, 1, 13, tzinfo=UTC
    )
