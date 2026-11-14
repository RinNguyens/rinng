"""Incremental curated update when a new 1m candle closes, instead of a full curate + resample.

`curate_tail` merges new 1m candles into curated and resamples only the tail of each timeframe,
starting at the open of the candle *before* the running one, so the just-closed candle is
rewritten with correct is_closed.
Since the input always starts on a candle open, the result matches a full resample (tested).
"""

from datetime import UTC, datetime, timedelta

import polars as pl

from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.resample import resample_ohlcv
from rinng.store.schemas import OHLCV, rows_to_frame
from rinng.store.writer import write_curated
from rinng.timeframes import bucket_start_ms, timeframe_ms


def tail_start(last_open: datetime, timeframe: str) -> datetime:
    """Open time of the candle just before the `timeframe` candle containing `last_open`."""
    ms = int(last_open.timestamp() * 1000)
    start = bucket_start_ms(ms, timeframe) - timeframe_ms(timeframe)
    return datetime.fromtimestamp(start / 1000, UTC)


def latest_1m_open(paths: DataPaths, exchange: str, symbol: str) -> datetime | None:
    """Open time of the last 1m candle in curated (reads the last 10 days first for speed)."""
    for start in (datetime.now(UTC) - timedelta(days=10), None):
        f = read_curated(
            paths, OHLCV, exchange=exchange, symbol=symbol, timeframe="1m", start=start
        )
        if not f.is_empty():
            return f["open_time"].max()
    return None


def resample_tail(
    paths: DataPaths,
    exchange: str,
    symbol: str,
    timeframe: str,
    since: datetime | None = None,
) -> pl.DataFrame:
    """Resample from the candle containing `since` (default: last 1m) to the end; overwrite, return.

    `since` is the earliest changed 1m candle; start from the candle before the one containing
    it so the just-closed candle is rewritten with correct is_closed.
    """
    since = since or latest_1m_open(paths, exchange, symbol)
    if since is None:
        return pl.DataFrame(schema=OHLCV.schema)
    base = read_curated(
        paths,
        OHLCV,
        exchange=exchange,
        symbol=symbol,
        timeframe="1m",
        start=tail_start(since, timeframe),
    )
    out = resample_ohlcv(base, timeframe)
    write_curated(paths, OHLCV, out)
    return out


def curate_tail(
    paths: DataPaths,
    exchange: str,
    symbol: str,
    bars_1m: list[dict],
    timeframes: list[str],
) -> dict[str, pl.DataFrame]:
    """Write closed 1m candles (collector-style rows, open_time in ms) then resample the tail."""
    since = None
    if bars_1m:
        frame = rows_to_frame(OHLCV, bars_1m, exchange=exchange, symbol=symbol, timeframe="1m")
        frame = frame.filter(pl.col("is_closed"))
        if not frame.is_empty():
            write_curated(paths, OHLCV, frame)
            since = frame["open_time"].min()
    return {tf: resample_tail(paths, exchange, symbol, tf, since) for tf in timeframes}
