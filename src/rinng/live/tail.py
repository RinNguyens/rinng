"""Cập nhật curated tăng dần khi có nến 1m mới đóng, thay cho curate + resample toàn bộ.

`curate_tail` gộp nến 1m mới vào curated rồi resample lại chỉ phần đuôi của mỗi khung: bắt đầu
từ mốc mở của nến *trước* nến đang chạy, để nến vừa đóng cũng được ghi lại với is_closed đúng.
Vì đầu vào luôn bắt đầu đúng mốc mở của một nến, kết quả trùng với resample toàn bộ (có test).
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
    """Mốc mở của nến liền trước nến `timeframe` chứa `last_open`."""
    ms = int(last_open.timestamp() * 1000)
    start = bucket_start_ms(ms, timeframe) - timeframe_ms(timeframe)
    return datetime.fromtimestamp(start / 1000, UTC)


def latest_1m_open(paths: DataPaths, exchange: str, symbol: str) -> datetime | None:
    """Mốc mở của nến 1m cuối cùng trong curated (đọc 10 ngày gần nhất trước cho nhanh)."""
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
    """Resample lại từ nến chứa `since` (mặc định: nến 1m cuối) tới hết, ghi đè và trả về.

    `since` là nến 1m sớm nhất vừa thay đổi; bắt đầu từ nến liền trước nến chứa nó để nến vừa
    đóng cũng được ghi lại với is_closed đúng.
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
    """Ghi nến 1m đã đóng (dòng dạng collector, open_time tính bằng ms) rồi resample đuôi."""
    since = None
    if bars_1m:
        frame = rows_to_frame(OHLCV, bars_1m, exchange=exchange, symbol=symbol, timeframe="1m")
        frame = frame.filter(pl.col("is_closed"))
        if not frame.is_empty():
            write_curated(paths, OHLCV, frame)
            since = frame["open_time"].min()
    return {tf: resample_tail(paths, exchange, symbol, tf, since) for tf in timeframes}
