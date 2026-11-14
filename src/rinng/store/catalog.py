"""Sổ sách dữ liệu ở data/meta/: manifest (đã tải gì) và gaps (thiếu gì).

- manifest: mỗi lần ghi một lô dữ liệu thì thêm một dòng: nguồn, khoảng thời gian, số dòng,
  checksum của nội dung, thời điểm tải. Dùng để biết một backtest chạy trên dữ liệu nào.
- gaps: mỗi khoảng thời gian biết là thiếu dữ liệu (mất kết nối, sàn bảo trì...).
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from rinng.store.paths import DataPaths
from rinng.store.schemas import TIME, Table, _table
from rinng.store.writer import PART_FILE, merge_into

MANIFEST = Table(
    "manifest",
    {
        "batch_id": pl.String(),
        "dataset": pl.String(),
        "exchange": pl.String(),
        "symbol": pl.String(),
        "timeframe": pl.String(),
        "source": pl.String(),
        "start": TIME,
        "end": TIME,
        "rows": pl.Int64(),
        "checksum": pl.String(),
        "fetched_at": TIME,
    },
    key=("batch_id",),
    time_column="fetched_at",
)

GAPS = _table(
    "gaps",
    "start",
    {
        "dataset": pl.String(),
        "start": TIME,
        "end": TIME,
        "reason": pl.String(),
        "recorded_at": TIME,
    },
    extra_key=("dataset",),
)


def frame_checksum(frame: pl.DataFrame) -> str:
    """SHA-256 của nội dung frame dạng CSV, không phụ thuộc cách nén file hay phiên bản polars."""
    return hashlib.sha256(frame.write_csv().encode()).hexdigest()


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _meta_partition(paths: DataPaths, name: str) -> Path:
    return paths.meta / name


def record_batch(
    paths: DataPaths,
    *,
    batch_id: str,
    dataset: str,
    exchange: str,
    symbol: str,
    source: str,
    start: datetime,
    end: datetime,
    rows: int,
    checksum: str,
    timeframe: str | None = None,
    fetched_at: datetime | None = None,
) -> None:
    row = {
        "batch_id": batch_id,
        "dataset": dataset,
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
        "start": start,
        "end": end,
        "rows": rows,
        "checksum": checksum,
        "fetched_at": fetched_at or datetime.now(UTC),
    }
    merge_into(_meta_partition(paths, "manifest"), pl.DataFrame([row]), MANIFEST)


def record_gap(
    paths: DataPaths,
    *,
    dataset: str,
    exchange: str,
    symbol: str,
    start: datetime,
    end: datetime,
    reason: str,
) -> None:
    if end <= start:
        raise ValueError("khoảng trống phải có end > start")
    row = {
        "exchange": exchange,
        "symbol": symbol,
        "dataset": dataset,
        "start": start,
        "end": end,
        "reason": reason,
        "recorded_at": datetime.now(UTC),
    }
    merge_into(_meta_partition(paths, "gaps"), pl.DataFrame([row]), GAPS)


def read_meta(paths: DataPaths, name: str) -> pl.DataFrame:
    tbl = {"manifest": MANIFEST, "gaps": GAPS}[name]
    target = _meta_partition(paths, name) / PART_FILE
    if not target.exists():
        return pl.DataFrame(schema=tbl.schema)
    return pl.read_parquet(target)
