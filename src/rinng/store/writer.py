"""Safe writes when several processes run at once (docs/08-architecture.md section 3).

Three rules:
- Write to a temp file in the same directory, then rename. A process dying midway leaves only
  a `.tmp` file, never a partial Parquet file at the real path.
- The raw/ zone is immutable: overwriting an existing file is refused.
- The curated/ zone is merged: read the existing part, append the new part, dedupe by key
  (new wins),
  sort by key, then replace the file. A file lock (flock) keeps two processes from merging
  the same partition.
"""

import fcntl
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import polars as pl

from rinng.store.paths import DataPaths
from rinng.store.schemas import Table, conform

PART_FILE = "data.parquet"
TMP_SUFFIX = ".tmp"
LOCK_FILE = ".lock"


class RawExistsError(FileExistsError):
    """File in raw/ already exists; raw/ must not be overwritten."""


def _tmp_path(target: Path) -> Path:
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}{TMP_SUFFIX}")


def _commit(tmp: Path, target: Path, *, overwrite: bool) -> None:
    if overwrite:
        os.replace(tmp, target)
        return
    try:
        # link() fails if the target exists: creates a new file without overwriting, atomically.
        os.link(tmp, target)
    except FileExistsError:
        raise RawExistsError(f"refusing to overwrite raw data: {target}") from None
    finally:
        tmp.unlink(missing_ok=True)


def write_raw_bytes(target: Path, content: bytes) -> Path:
    """Write a raw file (e.g. a downloaded zip). Raises if the file exists."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RawExistsError(f"refusing to overwrite raw data: {target}")
    tmp = _tmp_path(target)
    tmp.write_bytes(content)
    _commit(tmp, target, overwrite=False)
    return target


def write_raw_frame(target: Path, frame: pl.DataFrame) -> Path:
    """Write a raw frame as Parquet. Raises if the file exists."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RawExistsError(f"refusing to overwrite raw data: {target}")
    tmp = _tmp_path(target)
    frame.write_parquet(tmp)
    _commit(tmp, target, overwrite=False)
    return target


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / LOCK_FILE, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def merge_into(partition: Path, frame: pl.DataFrame, tbl: Table) -> int:
    """Merge `frame` into one partition file. Returns the row count after merging."""
    frame = conform(frame, tbl)
    target = partition / PART_FILE
    with _locked(partition):
        if target.exists():
            frame = pl.concat([pl.read_parquet(target), frame], how="vertical")
        merged = frame.unique(subset=list(tbl.key), keep="last", maintain_order=True).sort(
            list(tbl.key)
        )
        tmp = _tmp_path(target)
        merged.write_parquet(tmp)
        _commit(tmp, target, overwrite=True)
    return merged.height


def write_curated(paths: DataPaths, tbl: Table, frame: pl.DataFrame) -> dict[Path, int]:
    """Split a frame by exchange, symbol, timeframe, year and merge into each partition.

    Returns the row count of each partition after merging.
    """
    frame = conform(frame, tbl)
    if frame.is_empty():
        return {}
    group_cols = ["exchange", "symbol"] + (["timeframe"] if tbl.has_timeframe else [])
    keyed = frame.with_columns(pl.col(tbl.time_column).dt.year().alias("_year"))
    result: dict[Path, int] = {}
    for keys, part in keyed.group_by(group_cols + ["_year"], maintain_order=True):
        values = dict(zip(group_cols + ["_year"], keys, strict=True))
        partition = paths.curated_partition(
            tbl.name,
            values["exchange"],
            values["symbol"],
            values["_year"],
            timeframe=values.get("timeframe"),
        )
        result[partition] = merge_into(partition, part.drop("_year"), tbl)
    return result
