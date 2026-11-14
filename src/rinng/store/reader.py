"""Đọc dữ liệu curated theo instrument và khoảng thời gian."""

from datetime import datetime

import polars as pl

from rinng.store.paths import DataPaths
from rinng.store.schemas import Table
from rinng.store.writer import PART_FILE


def read_curated(
    paths: DataPaths,
    tbl: Table,
    *,
    exchange: str,
    symbol: str,
    timeframe: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pl.DataFrame:
    """Đọc bảng trong khoảng [start, end). Không có dữ liệu thì trả frame rỗng đúng schema."""
    if tbl.has_timeframe and timeframe is None:
        raise ValueError(f"bảng {tbl.name} cần timeframe")
    for moment in (start, end):
        if moment is not None and moment.tzinfo is None:
            raise ValueError("datetime phải có múi giờ (dùng timezone UTC)")

    base = paths.curated_dataset(tbl.name) / f"exchange={exchange}" / f"symbol={symbol}"
    if tbl.has_timeframe:
        base = base / f"timeframe={timeframe}"
    files = sorted(base.glob(f"year=*/{PART_FILE}"))
    if not files:
        return pl.DataFrame(schema=tbl.schema)

    query = pl.scan_parquet(files)
    when = pl.col(tbl.time_column)
    if start is not None:
        query = query.filter(when >= start)
    if end is not None:
        query = query.filter(when < end)
    return query.sort(list(tbl.key)).collect()
