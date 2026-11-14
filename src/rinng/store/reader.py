"""Read curated data by instrument and time range."""

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
    """Read a table over [start, end). With no data, return an empty frame with the right schema."""
    if tbl.has_timeframe and timeframe is None:
        raise ValueError(f"table {tbl.name} requires timeframe")
    for moment in (start, end):
        if moment is not None and moment.tzinfo is None:
            raise ValueError("datetime must be timezone-aware (use UTC)")

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
