"""DuckDB chỉ chứa view trỏ vào Parquet; không lưu bản sao dữ liệu.

Mỗi bảng curated có một view cùng tên; `manifest` và `gaps` cũng vậy. Các cột phân vùng
(exchange, symbol, timeframe) đã có sẵn trong file nên không bật hive partitioning.
"""

from pathlib import Path

import duckdb

from rinng.store.paths import DataPaths
from rinng.store.schemas import TABLES
from rinng.store.writer import PART_FILE


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def connect(paths: DataPaths, database: str = ":memory:") -> duckdb.DuckDBPyConnection:
    """Mở kết nối và tạo view cho mọi bảng đã có dữ liệu.

    View trỏ vào danh sách file lúc mở kết nối; phân vùng tạo sau đó cần mở kết nối mới.
    """
    con = duckdb.connect(database)
    # Mặc định DuckDB trả thời gian theo múi giờ của máy; dự án dùng UTC ở mọi nơi.
    con.execute("SET TimeZone = 'UTC'")
    for name in TABLES:
        files = sorted(paths.curated_dataset(name).rglob(PART_FILE))
        if files:
            sources = ", ".join(_quote(f) for f in files)
            con.execute(
                f'CREATE OR REPLACE VIEW "{name}" AS SELECT * FROM read_parquet([{sources}])'
            )
    for name in ("manifest", "gaps"):
        target = paths.meta / name / PART_FILE
        if target.exists():
            con.execute(
                f'CREATE OR REPLACE VIEW "{name}" AS SELECT * FROM read_parquet({_quote(target)})'
            )
    return con
