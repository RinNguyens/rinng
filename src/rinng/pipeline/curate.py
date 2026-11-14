"""raw/ → curated/. Safe to rerun any number of times.

Two kinds of raw files:
- Zip dump files: raw/binance/dumps/{dump}/{exchange SYMBOL}/{name}.zip
- Parquet files written by collector/backfill, already in schema:
  raw/{exchange}/{table}[_{timeframe}]/{canonical symbol}/date=YYYY-MM-DD/*.parquet

Each processed file is recorded in the manifest with batch_id = "raw:<relative path>" and
skipped next time. Parquet files are grouped by day directory to write curated less often.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from rinng.config import Settings
from rinng.ingest import dumps
from rinng.store import catalog
from rinng.store.paths import DataPaths
from rinng.store.schemas import TABLES, table
from rinng.store.writer import TMP_SUFFIX, write_curated

log = logging.getLogger(__name__)


def _table_name(directory: str) -> str:
    if directory in TABLES:
        return directory
    base = directory.rsplit("_", 1)[0]
    if base in TABLES:
        return base
    raise KeyError(f"cannot infer table from raw directory {directory!r}")


def _record(paths: DataPaths, file: Path, tbl_name: str, frame: pl.DataFrame, source: str) -> None:
    tbl = table(tbl_name)
    times = frame[tbl.time_column]
    first = frame.row(0, named=True) if frame.height else {}
    catalog.record_batch(
        paths,
        batch_id=f"raw:{file.relative_to(paths.raw)}",
        dataset=tbl_name,
        exchange=first.get("exchange", ""),
        symbol=first.get("symbol", ""),
        timeframe=first.get("timeframe"),
        source=source,
        start=times.min() if frame.height else datetime.now(UTC),
        end=times.max() if frame.height else datetime.now(UTC),
        rows=frame.height,
        checksum=catalog.file_checksum(file),
    )


def curate(paths: DataPaths, settings: Settings, *, only: set[str] | None = None) -> dict[str, int]:
    """Process every raw file not yet in the manifest. Returns merged row counts per table.

    `only`: process only Parquet files of these tables and skip dumps (used in live mode).
    """
    done = set(catalog.read_meta(paths, "manifest")["batch_id"].to_list())
    venue_to_id = {i.binance: i.id for i in settings.instruments if i.binance}
    totals: dict[str, int] = defaultdict(int)

    dump_root = paths.raw / "binance" / "dumps"
    for file in [] if only is not None else sorted(dump_root.glob("*/*/*.zip")):
        if f"raw:{file.relative_to(paths.raw)}" in done:
            continue
        name, venue_symbol = file.parent.parent.name, file.parent.name
        symbol = venue_to_id.get(venue_symbol)
        if symbol is None:
            log.warning("skipping %s: %s not in config", file.name, venue_symbol)
            continue
        frames = dumps.parse(name, file.read_bytes(), symbol)
        for tbl_name, frame in frames.items():
            write_curated(paths, table(tbl_name), frame)
            totals[tbl_name] += frame.height
        main_name, main = next(iter(frames.items()))
        _record(paths, file, main_name, main, "dump")

    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for file in paths.raw.glob("*/*/*/date=*/*.parquet"):
        if file.name.endswith(TMP_SUFFIX) or file.is_relative_to(dump_root):
            continue
        if only is not None and _table_name(file.parent.parent.parent.name) not in only:
            continue
        if f"raw:{file.relative_to(paths.raw)}" not in done:
            by_dir[file.parent].append(file)
    for directory, files in sorted(by_dir.items()):
        tbl_name = _table_name(directory.parent.parent.name)
        frame = pl.concat([pl.read_parquet(f) for f in sorted(files)], how="vertical")
        write_curated(paths, table(tbl_name), frame)
        totals[tbl_name] += frame.height
        for f in files:
            _record(paths, f, tbl_name, pl.read_parquet(f), "api")
    return dict(totals)
