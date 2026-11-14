from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from rinng.store import catalog
from rinng.store.db import connect
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.schemas import FUNDING, LONG_SHORT, OHLCV, OPEN_INTEREST, conform, rows_to_frame
from rinng.store.writer import (
    PART_FILE,
    RawExistsError,
    merge_into,
    write_curated,
    write_raw_bytes,
    write_raw_frame,
)

H = 3_600_000
T0 = datetime(2026, 11, 1, tzinfo=UTC)
T0_MS = int(T0.timestamp() * 1000)


def kline_row(open_ms: int, close: float = 105.0) -> dict:
    """Candle rows exactly as the exchange adapter returns them."""
    return {
        "open_time": open_ms,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": close,
        "volume": 12.5,
        "quote_volume": 1300.0,
        "trades": 42,
        "taker_buy_volume": 7.0,
        "is_closed": True,
    }


def candles(n: int, start_ms: int = T0_MS, close: float = 105.0) -> pl.DataFrame:
    rows = [kline_row(start_ms + i * H, close) for i in range(n)]
    return rows_to_frame(OHLCV, rows, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "data")


# --- schemas ---


def test_rows_to_frame_converts_adapter_rows():
    frame = candles(2)
    assert frame.schema == pl.Schema(OHLCV.schema)
    assert frame["open_time"][0] == T0
    assert frame["symbol"].to_list() == ["BTC-USDT-PERP"] * 2


def test_rows_to_frame_fills_columns_adapter_does_not_send():
    rows = [{"time": T0_MS, "ratio": 2.5, "long_pct": None, "short_pct": None}]
    frame = rows_to_frame(
        LONG_SHORT,
        rows,
        exchange="okx",
        symbol="BTC-USDT-PERP",
        source="api",
        kind="global_account",
    )
    assert frame.row(0, named=True)["kind"] == "global_account"
    assert frame["long_pct"].null_count() == 1


def test_null_key_rejected():
    rows = [{"time": T0_MS, "oi_base": 1.0, "oi_value": 2.0}]  # missing source
    with pytest.raises(ValueError, match="key"):
        rows_to_frame(OPEN_INTEREST, rows, exchange="binance", symbol="BTC-USDT-PERP")


def test_missing_column_rejected():
    with pytest.raises(ValueError, match="missing column"):
        conform(pl.DataFrame({"exchange": ["x"]}), FUNDING)


def test_ohlcv_requires_timeframe():
    with pytest.raises(ValueError):
        rows_to_frame(OHLCV, [kline_row(T0_MS)], exchange="binance", symbol="BTC-USDT-PERP")


# --- writer + reader ---


def test_write_then_read_round_trip(paths):
    frame = candles(24)
    write_curated(paths, OHLCV, frame)
    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")
    assert got.equals(frame)


def test_writing_same_rows_twice_makes_no_duplicates(paths):
    write_curated(paths, OHLCV, candles(10))
    write_curated(paths, OHLCV, candles(10))
    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")
    assert got.height == 10


def test_newer_value_wins_on_same_key(paths):
    write_curated(paths, OHLCV, candles(3, close=105.0))
    write_curated(paths, OHLCV, candles(1, close=200.0))  # first candle revised by the exchange
    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")
    assert got["close"].to_list() == [200.0, 105.0, 105.0]


def test_overlapping_batches_merge_in_order(paths):
    write_curated(paths, OHLCV, candles(5, start_ms=T0_MS + 3 * H))
    write_curated(paths, OHLCV, candles(5))
    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")
    assert got["open_time"].to_list() == [T0 + timedelta(hours=i) for i in range(8)]


def test_rows_split_into_year_partitions(paths):
    new_year = int(datetime(2027, 1, 1, tzinfo=UTC).timestamp() * 1000)
    written = write_curated(paths, OHLCV, candles(4, start_ms=new_year - 2 * H))
    assert sorted(p.name for p in written) == ["year=2026", "year=2027"]
    assert sorted(written.values()) == [2, 2]
    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")
    assert got.height == 4


def test_read_filters_half_open_range(paths):
    write_curated(paths, OHLCV, candles(10))
    got = read_curated(
        paths,
        OHLCV,
        exchange="binance",
        symbol="BTC-USDT-PERP",
        timeframe="1h",
        start=T0 + timedelta(hours=2),
        end=T0 + timedelta(hours=5),
    )
    assert got["open_time"].to_list() == [T0 + timedelta(hours=h) for h in (2, 3, 4)]


def test_read_missing_data_returns_empty_frame_with_schema(paths):
    got = read_curated(paths, FUNDING, exchange="okx", symbol="BTC-USDT-PERP")
    assert got.is_empty()
    assert got.schema == pl.Schema(FUNDING.schema)


def test_read_rejects_naive_datetime(paths):
    with pytest.raises(ValueError):
        read_curated(paths, FUNDING, exchange="okx", symbol="X", start=datetime(2026, 1, 1))


def test_sources_are_kept_apart(paths):
    def oi(source: str, value: float) -> pl.DataFrame:
        rows = [{"time": T0_MS, "oi_base": value, "oi_value": value * 70_000}]
        return rows_to_frame(
            OPEN_INTEREST, rows, exchange="binance", symbol="BTC-USDT-PERP", source=source
        )

    write_curated(paths, OPEN_INTEREST, oi("api", 98690.01))
    write_curated(paths, OPEN_INTEREST, oi("dump", 98691.69))
    got = read_curated(paths, OPEN_INTEREST, exchange="binance", symbol="BTC-USDT-PERP")
    assert sorted(got["source"].to_list()) == ["api", "dump"]


# --- write safety ---


def test_raw_refuses_overwrite(paths, tmp_path):
    target = paths.raw / "binance" / "dumps" / "a.zip"
    write_raw_bytes(target, b"first")
    with pytest.raises(RawExistsError):
        write_raw_bytes(target, b"second")
    assert target.read_bytes() == b"first"


def test_raw_frame_refuses_overwrite(paths):
    target = paths.raw / "binance" / "klines" / "page.parquet"
    write_raw_frame(target, candles(1))
    with pytest.raises(RawExistsError):
        write_raw_frame(target, candles(2))
    assert pl.read_parquet(target).height == 1


def test_no_temp_files_left_after_writes(paths):
    write_curated(paths, OHLCV, candles(3))
    write_raw_bytes(paths.raw / "x.zip", b"z")
    leftovers = [p for p in paths.root.rglob("*") if p.name.endswith(".tmp")]
    assert leftovers == []


def test_crash_during_write_keeps_old_file(paths, monkeypatch):
    write_curated(paths, OHLCV, candles(3))

    def boom(self, path, *args, **kwargs):
        Path(path).write_bytes(b"half written")
        raise OSError("disk full")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", boom)
    with pytest.raises(OSError):
        write_curated(paths, OHLCV, candles(5))
    monkeypatch.undo()

    got = read_curated(paths, OHLCV, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")
    assert got.height == 3  # the committed file is intact
    parquet_files = [p.name for p in paths.root.rglob("*.parquet")]
    assert parquet_files == [PART_FILE]  # the partial file only has the .tmp suffix


def _merge_worker(partition: str, start_hour: int) -> None:
    rows = [kline_row(T0_MS + (start_hour + i) * H) for i in range(50)]
    frame = rows_to_frame(OHLCV, rows, exchange="binance", symbol="BTC-USDT-PERP", timeframe="1h")
    for _ in range(5):
        merge_into(Path(partition), frame, OHLCV)


def test_concurrent_merges_do_not_lose_rows(paths):
    # Child process via subprocess instead of multiprocessing: spawn re-runs the parent's
    # __main__ module, and the dashboard test (AppTest) may have replaced __main__.
    import subprocess
    import sys

    partition = paths.curated_partition("ohlcv", "binance", "BTC-USDT-PERP", 2026, timeframe="1h")
    code = (
        "import sys; from tests.test_store import _merge_worker; "
        "_merge_worker(sys.argv[1], int(sys.argv[2]))"
    )
    root = Path(__file__).resolve().parents[1]
    workers = [
        subprocess.Popen([sys.executable, "-c", code, str(partition), str(h)], cwd=root)
        for h in (0, 50, 100, 150)
    ]
    for w in workers:
        assert w.wait(timeout=120) == 0
    got = pl.read_parquet(partition / PART_FILE)
    assert got.height == 200
    assert got["open_time"].is_unique().all()


# --- catalog ---


def test_manifest_records_batches(paths):
    frame = candles(5)
    for batch in ("b1", "b2"):
        catalog.record_batch(
            paths,
            batch_id=batch,
            dataset="ohlcv",
            exchange="binance",
            symbol="BTC-USDT-PERP",
            timeframe="1h",
            source="api",
            start=T0,
            end=T0 + timedelta(hours=5),
            rows=frame.height,
            checksum=catalog.frame_checksum(frame),
        )
    manifest = catalog.read_meta(paths, "manifest")
    assert manifest["batch_id"].to_list() == ["b1", "b2"]
    assert manifest["checksum"][0] == catalog.frame_checksum(candles(5))


def test_checksum_changes_with_content():
    assert catalog.frame_checksum(candles(2)) != catalog.frame_checksum(candles(2, close=1.0))


def test_gaps_recorded_and_validated(paths):
    catalog.record_gap(
        paths,
        dataset="liquidations",
        exchange="binance",
        symbol="BTC-USDT-PERP",
        start=T0,
        end=T0 + timedelta(minutes=3),
        reason="websocket reconnect",
    )
    gaps = catalog.read_meta(paths, "gaps")
    assert gaps.height == 1
    assert gaps["reason"][0] == "websocket reconnect"
    with pytest.raises(ValueError):
        catalog.record_gap(
            paths, dataset="x", exchange="b", symbol="s", start=T0, end=T0, reason="r"
        )


# --- duckdb ---


def test_duckdb_views_count_written_rows(paths):
    write_curated(paths, OHLCV, candles(30))
    write_curated(paths, OHLCV, candles(20, start_ms=T0_MS + 30 * H))
    catalog.record_gap(
        paths,
        dataset="ohlcv",
        exchange="binance",
        symbol="BTC-USDT-PERP",
        start=T0,
        end=T0 + timedelta(hours=1),
        reason="test",
    )
    con = connect(paths)
    assert con.execute("SELECT count(*) FROM ohlcv").fetchone() == (50,)
    assert con.execute("SELECT count(*) FROM gaps").fetchone() == (1,)
    first = con.execute("SELECT min(open_time) FROM ohlcv").fetchone()[0]
    assert first == T0
    assert first.utcoffset() == timedelta(0)  # independent of the machine's timezone


def test_duckdb_without_data_has_no_views(paths):
    con = connect(paths)
    assert con.execute("SELECT count(*) FROM duckdb_views() WHERE NOT internal").fetchone() == (0,)


def test_funding_time_rounded_so_rest_and_dump_rows_merge(paths):
    def f(ms: int) -> pl.DataFrame:
        rows = [{"funding_time": ms, "rate": 0.0001, "mark_price": None}]
        return rows_to_frame(FUNDING, rows, exchange="binance", symbol="BTC-USDT-PERP")

    write_curated(paths, FUNDING, f(T0_MS + 2))  # REST
    write_curated(paths, FUNDING, f(T0_MS + 1))  # dump
    got = read_curated(paths, FUNDING, exchange="binance", symbol="BTC-USDT-PERP")
    assert got["funding_time"].to_list() == [T0]
