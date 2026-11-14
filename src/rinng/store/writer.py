"""Ghi dữ liệu an toàn khi nhiều tiến trình cùng chạy (docs/08-kien-truc.md mục 3).

Ba quy tắc:
- Ghi ra file tạm trong cùng thư mục rồi đổi tên. Tiến trình chết giữa chừng chỉ để lại
  file `.tmp`, không bao giờ để lại file Parquet dở ở đường dẫn chính thức.
- Vùng raw/ là bất biến: ghi đè một file đã có thì bị từ chối.
- Vùng curated/ được gộp: đọc phần đã có, nối phần mới, khử trùng theo khóa (bản mới thắng),
  sắp theo khóa, rồi thay file. Một khóa file (flock) giữ cho hai tiến trình không cùng gộp
  một phân vùng.
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
    """File trong raw/ đã tồn tại; raw/ không được ghi đè."""


def _tmp_path(target: Path) -> Path:
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}{TMP_SUFFIX}")


def _commit(tmp: Path, target: Path, *, overwrite: bool) -> None:
    if overwrite:
        os.replace(tmp, target)
        return
    try:
        # link() thất bại nếu đích đã tồn tại: tạo file mới mà không ghi đè, nguyên tử.
        os.link(tmp, target)
    except FileExistsError:
        raise RawExistsError(f"không ghi đè dữ liệu thô: {target}") from None
    finally:
        tmp.unlink(missing_ok=True)


def write_raw_bytes(target: Path, content: bytes) -> Path:
    """Ghi một file thô (ví dụ file zip tải về). Báo lỗi nếu file đã có."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RawExistsError(f"không ghi đè dữ liệu thô: {target}")
    tmp = _tmp_path(target)
    tmp.write_bytes(content)
    _commit(tmp, target, overwrite=False)
    return target


def write_raw_frame(target: Path, frame: pl.DataFrame) -> Path:
    """Ghi một frame thô thành Parquet. Báo lỗi nếu file đã có."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RawExistsError(f"không ghi đè dữ liệu thô: {target}")
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
    """Gộp `frame` vào file của một phân vùng. Trả về số dòng sau khi gộp."""
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
    """Chia frame theo exchange, symbol, timeframe, năm rồi gộp vào từng phân vùng.

    Trả về số dòng của mỗi phân vùng sau khi gộp.
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
