import io
import zipfile
from datetime import UTC, date, datetime, timedelta

import httpx
import polars as pl
import pytest

from rinng.config import Instrument, Settings
from rinng.ingest import dumps
from rinng.ingest.dumps import Downloader, DumpFile, plan
from rinng.pipeline.curate import curate
from rinng.pipeline.validate import check_candles, compare_frames, cross_exchange
from rinng.store import catalog
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.resample import resample_ohlcv
from rinng.store.schemas import FUNDING, LONG_SHORT, OHLCV, OPEN_INTEREST
from tests.analysis.helpers import make_ohlcv

D = date


def zipped(text: str, name: str = "x.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text)
    return buf.getvalue()


# --- plan ---


def test_plan_prefers_months_then_days():
    files = plan("klines_1m", "BTCUSDT", D(2026, 9, 15), D(2026, 11, 13), today=D(2026, 11, 13))
    periods = [f.period for f in files]
    assert periods[:16] == [f"2026-09-{d:02d}" for d in range(15, 31)]
    assert "2026-10" in periods
    assert periods[-1] == "2026-11-12"  # hôm nay chưa có file
    assert len(periods) == 16 + 1 + 12


def test_plan_monthly_only_dataset_stops_at_current_month():
    files = plan("funding", "BTCUSDT", D(2026, 9, 1), D(2026, 11, 13), today=D(2026, 11, 13))
    assert [f.period for f in files] == ["2026-09", "2026-10"]
    assert dumps.covered_until(files, D(2026, 9, 1)) == D(2026, 11, 1)


def test_plan_partial_first_month_for_monthly_only_uses_month_file():
    files = plan("funding", "BTCUSDT", D(2026, 9, 10), D(2026, 10, 1), today=D(2026, 11, 13))
    assert [f.period for f in files] == ["2026-09"]


def test_plan_daily_only_dataset():
    files = plan("metrics", "BTCUSDT", D(2026, 11, 10), D(2026, 11, 20), today=D(2026, 11, 13))
    assert [f.period for f in files] == ["2026-11-10", "2026-11-11", "2026-11-12"]


def test_dump_url():
    f = DumpFile("klines_1m", "BTCUSDT", "2026-10", D(2026, 10, 1), D(2026, 11, 1))
    assert f.url == (
        "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2026-10.zip"
    )


# --- downloader ---


def test_downloader_verifies_checksum_and_skips_404(tmp_path):
    import hashlib

    paths = DataPaths(tmp_path)
    good = zipped("1,2")
    files = {
        "/a.zip": httpx.Response(200, content=good),
        "/a.zip.CHECKSUM": httpx.Response(200, text=hashlib.sha256(good).hexdigest() + "  a.zip"),
        "/b.zip": httpx.Response(200, content=good),
        "/b.zip.CHECKSUM": httpx.Response(200, text="deadbeef  b.zip"),
    }

    def handler(request):
        return files.get(request.url.path, httpx.Response(404))

    dl = Downloader(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)

    class F:
        def __init__(self, name):
            self.url = f"https://h.test/{name}"
            self.filename = name

        def raw_path(self, p):
            return p.raw / self.filename

    assert dl.fetch(F("a.zip"), paths).read_bytes() == good
    with pytest.raises(ValueError, match="checksum"):
        dl.fetch(F("b.zip"), paths)
    assert dl.fetch(F("c.zip"), paths) is None


# --- parse: mẫu dòng lấy từ file thật ---

KLINES_NEW = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
    "taker_buy_quote_volume,ignore\n"
    "1790812800000,83576.80,83612.60,83536.50,83536.50,165.529,1790812859999,13835811.75180,"
    "4471,73.888,6175639.62280,0\n"
)
KLINES_OLD = "1577836800000,7189.43,7190.52,7177,7182.44,246.092,1577836859999,1767430.16,336,46.630,334813.19,0\n"  # noqa: E501


def test_parse_klines_with_and_without_header():
    new = dumps.parse_klines(zipped(KLINES_NEW), "BTC-USDT-PERP")
    old = dumps.parse_klines(zipped(KLINES_OLD), "BTC-USDT-PERP")
    assert new.schema == pl.Schema(OHLCV.schema)
    assert new.row(0, named=True)["taker_buy_volume"] == 73.888
    assert old["open_time"][0] == datetime(2020, 1, 1, tzinfo=UTC)
    assert old["trades"][0] == 336


def test_parse_microsecond_timestamps():
    us = KLINES_OLD.replace("1577836800000", "1577836800000000", 1)
    assert dumps.parse_klines(zipped(us), "X")["open_time"][0] == datetime(2020, 1, 1, tzinfo=UTC)


def test_parse_funding_rounds_time():
    f = dumps.parse_funding(
        zipped("calc_time,funding_interval_hours,last_funding_rate\n1790812800001,8,0.00007981\n"),
        "X",
    )
    assert f.schema == pl.Schema(FUNDING.schema)
    assert f["funding_time"][0] == datetime(2026, 10, 1, tzinfo=UTC)


def test_parse_metrics_maps_ratios():
    text = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
        "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
        "2026-11-10 05:40:00,BTCUSDT,98691.693,7389698420.08,3.15166337,2.34416100,2.80764210,1.575607\n"  # noqa: E501
    )
    oi, ls = dumps.parse_metrics(zipped(text), "BTC-USDT-PERP")
    assert oi.schema == pl.Schema(OPEN_INTEREST.schema)
    assert oi["oi_base"][0] == 98691.693
    assert oi["source"][0] == "dump"
    kinds = dict(zip(ls["kind"], ls["ratio"], strict=True))
    assert kinds == {
        "top_account": 3.15166337,
        "top_position": 2.344161,
        "global_account": 2.8076421,
    }
    assert ls.schema == pl.Schema(LONG_SHORT.schema)


def test_parse_agg_trades_and_book_depth():
    t = dumps.parse_agg_trades(zipped("1,68000.5,0.1,10,12,1790812800000,true\n"), "X")
    assert t.row(0, named=True)["is_buyer_maker"] is True
    b = dumps.parse_book_depth(
        zipped(
            "timestamp,percentage,depth,notional\n2026-11-10 00:00:01,-5.00,8864.4,654377433.3\n"
        ),
        "X",
    )
    assert b["percentage"][0] == -5.0


# --- curate ---


SETTINGS = Settings(
    data_dir="data",
    base_timeframe="1m",
    timeframes=["1h"],
    instruments=[
        Instrument(id="BTC-USDT-PERP", kind="perp", binance="BTCUSDT", okx="BTC-USDT-SWAP")
    ],
)


def test_curate_dump_and_parquet_once(tmp_path):
    from rinng.ingest.collector.messages import Record
    from rinng.ingest.collector.sink import Sink

    paths = DataPaths(tmp_path)
    f = DumpFile("klines_1m", "BTCUSDT", "2026-10", D(2026, 10, 1), D(2026, 11, 1))
    target = f.raw_path(paths)
    target.parent.mkdir(parents=True)
    target.write_bytes(zipped(KLINES_NEW))
    sink = Sink(paths, "binance")
    row = {
        "open_time": 1790812860000,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
        "quote_volume": 1.0,
        "trades": 1,
        "taker_buy_volume": 0.5,
        "is_closed": True,
    }
    sink.add([Record("ohlcv", "BTC-USDT-PERP", row, "1m")])
    sink.flush()

    assert curate(paths, SETTINGS) == {"ohlcv": 2}
    assert curate(paths, SETTINGS) == {}  # lần hai không làm gì
    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1m")
    assert got.height == 2
    assert catalog.read_meta(paths, "manifest").height == 2


# --- resample ---


def test_resample_hourly_and_weekly_alignment():
    m1 = make_ohlcv(
        [float(i) for i in range(1, 181)],
        timeframe="1m",
        start=datetime(2026, 1, 4, 23, 0, tzinfo=UTC),
    )  # Chủ nhật 23:00
    h1 = resample_ohlcv(m1, "1h")
    assert h1["open_time"].to_list() == [
        datetime(2026, 1, 4, 23 + i, 0, tzinfo=UTC)
        if i == 0
        else datetime(2026, 1, 5, i - 1, tzinfo=UTC)
        for i in range(3)
    ]
    first = h1.row(0, named=True)
    assert (first["open"], first["close"], first["high"], first["low"]) == (1.0, 60.0, 60.0, 1.0)
    assert first["volume"] == 600.0
    assert h1["is_closed"].to_list() == [True, True, True]
    w = resample_ohlcv(m1, "1w")
    assert w["open_time"].to_list() == [
        datetime(2025, 12, 29, tzinfo=UTC),
        datetime(2026, 1, 5, tzinfo=UTC),
    ]
    assert w["is_closed"].to_list() == [False, False]


def test_resample_partial_last_bucket_not_closed_and_null_propagates():
    m1 = make_ohlcv([1.0] * 90, timeframe="1m")
    m1 = m1.with_columns(
        pl.when(pl.int_range(pl.len()) == 5).then(None).otherwise(pl.col("trades")).alias("trades")
    )
    h1 = resample_ohlcv(m1, "1h")
    assert h1["is_closed"].to_list() == [True, False]
    assert h1["trades"].to_list()[0] is None


def test_resample_matches_direct_hourly_on_random_data():
    from tests.analysis.helpers import random_walk

    m1 = random_walk(600, timeframe="1m")
    h1 = resample_ohlcv(m1, "1h")
    first = m1.head(60)
    row = h1.row(0, named=True)
    assert row["high"] == first["high"].max()
    assert row["close"] == first["close"][-1]
    assert abs(row["taker_buy_volume"] - first["taker_buy_volume"].sum()) < 1e-9


# --- validate ---


def test_check_candles_finds_gaps_and_bad_rows():
    m1 = make_ohlcv([1.0] * 10, timeframe="1m")
    holed = pl.concat([m1.head(3), m1.slice(6)])
    bad = holed.with_columns(
        pl.when(pl.int_range(pl.len()) == 0).then(5.0).otherwise(pl.col("low")).alias("low")
    )
    r = check_candles(bad)
    assert r.missing == 3
    assert r.gaps == [(m1["open_time"][3], m1["open_time"][6])]
    assert r.invalid_ohlc == 1
    assert not r.ok


def test_compare_frames_and_cross_exchange():
    a = make_ohlcv([1.0, 2.0, 3.0])
    b = a.with_columns(
        pl.when(pl.int_range(pl.len()) == 1).then(2.5).otherwise(pl.col("close")).alias("close")
    )
    res = compare_frames(a, b)
    assert (res["common"], res["mismatched"]) == (3, 1)
    x = cross_exchange(a, b)
    assert x["common"] == 3
    assert x["max_rel_diff"] == pytest.approx(0.2)


def test_hourly_window_helper():
    assert timedelta(hours=1) == timedelta(minutes=60)


def test_parse_metrics_tolerates_empty_cells():
    text = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
        "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
        "2021-12-01 00:00:00,BTCUSDT,100.0,5000000.0,,,1.5,\n"
        "2021-12-01 00:05:00,BTCUSDT,,,,,,\n"
    )
    oi, ls = dumps.parse_metrics(zipped(text), "BTC-USDT-PERP")
    assert oi.height == 1
    assert ls["kind"].to_list() == ["global_account"]
