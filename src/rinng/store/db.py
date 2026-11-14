"""DuckDB holds only views pointing at Parquet; no copy of the data is stored.

Each curated table has a view of the same name; so do `manifest` and `gaps`. Partition columns
(exchange, symbol, timeframe) are already in the files, so hive partitioning is off.
"""

from pathlib import Path

import duckdb

from rinng.store.paths import DataPaths
from rinng.store.schemas import TABLES
from rinng.store.writer import PART_FILE


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def connect(paths: DataPaths, database: str = ":memory:") -> duckdb.DuckDBPyConnection:
    """Open a connection and create views for every table that has data.

    Views point at the file list at connect time; partitions created later need a new connection.
    """
    con = duckdb.connect(database)
    # DuckDB returns times in the machine time zone by default; the project uses UTC everywhere.
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
