"""Gom bản ghi trong bộ nhớ rồi xả ra raw/ theo lô.

Mỗi lần xả tạo một file Parquet mới (bất biến) cho mỗi (bảng, sàn, symbol, ngày):
raw/{exchange}/{table}/{symbol}/date=YYYY-MM-DD/{first_ms}-{uuid}.parquet
Nội dung đã đúng schema curated; bước curate chỉ cần gộp và khử trùng.
"""

import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

import polars as pl

from rinng.ingest.collector.messages import Record
from rinng.store.paths import DataPaths
from rinng.store.schemas import rows_to_frame, table
from rinng.store.writer import write_raw_frame


class Sink:
    def __init__(
        self,
        paths: DataPaths,
        exchange: str,
        *,
        max_rows: int = 5000,
        max_age: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.paths = paths
        self.exchange = exchange
        self.max_rows = max_rows
        self.max_age = max_age
        self._clock = clock
        self._rows: dict[tuple[str, str, str | None], list[dict]] = defaultdict(list)
        self._count = 0
        self._since = clock()
        self.written_rows = 0

    def add(self, records: list[Record]) -> None:
        for r in records:
            self._rows[(r.table, r.symbol, r.timeframe)].append(r.row)
        self._count += len(records)
        if self._count >= self.max_rows or self._clock() - self._since >= self.max_age:
            self.flush()

    def flush(self) -> int:
        """Ghi mọi thứ đang giữ. Trả về số dòng đã ghi."""
        written = 0
        for (name, symbol, timeframe), rows in self._rows.items():
            if not rows:
                continue
            tbl = table(name)
            frame = rows_to_frame(
                tbl, rows, exchange=self.exchange, symbol=symbol, timeframe=timeframe
            )
            day_col = pl.col(tbl.time_column).dt.date().alias("_day")
            for (day,), part in frame.with_columns(day_col).group_by(["_day"]):
                part = part.drop("_day")
                first = part[tbl.time_column].min()
                first_ms = int(first.timestamp() * 1000)
                target = (
                    self.paths.raw_partition(
                        self.exchange,
                        name if timeframe is None else f"{name}_{timeframe}",
                        symbol,
                        day,
                    )
                    / f"{first_ms}-{uuid.uuid4().hex[:8]}.parquet"
                )
                write_raw_frame(target, part)
                written += part.height
        self._rows.clear()
        self._count = 0
        self._since = self._clock()
        self.written_rows += written
        return written


def utc_now() -> datetime:
    return datetime.now(UTC)
