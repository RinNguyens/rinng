"""In-sample/out-of-sample split, result saving, comparison table.

`save_result` is the only place in the backtest package that writes files. Each run saves:
- `trades.parquet`, `equity.parquet`: the Result frames.
- `summary.json`: metrics (NaN/infinity written as null).
- `config.json`: the caller's config, plus `params_hash` (if `strategy` and
  `params` are given), `costs`, `period`, `symbol`, `timeframe`, `initial_equity`, `leverage` from
  Result, and `git_commit` if `git rev-parse HEAD` succeeds (errors are ignored).
"""

import json
import math
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from rinng.analysis.types import params_hash
from rinng.backtest.engine import Result


def split_in_out(ohlcv: pl.DataFrame, split_time: datetime) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(in-sample: open_time < split_time, out-of-sample: open_time >= split_time).

    Note: strategies that need warm-up candles (EMA, regression window) lose the start of the
    out-of-sample set when run separately; for continuity generate signals on the full set, then
    filter.
    """
    return (
        ohlcv.filter(pl.col("open_time") < split_time),
        ohlcv.filter(pl.col("open_time") >= split_time),
    )


def git_commit(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd or Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip()
    return commit or None


def _clean(value: Any) -> Any:
    """Convert NaN/infinity to None for valid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def build_config(result: Result, config: dict[str, Any]) -> dict[str, Any]:
    out = dict(config)
    if "params_hash" not in out and "strategy" in out:
        out["params_hash"] = params_hash(str(out["strategy"]), out.get("params") or {})
    meta = result.meta
    out.setdefault("costs", meta.get("costs"))
    out.setdefault("period", {"start": meta.get("start"), "end": meta.get("end")})
    for key in ("symbol", "timeframe", "initial_equity", "leverage"):
        if key in meta:
            out.setdefault(key, meta[key])
    commit = git_commit()
    if commit:
        out["git_commit"] = commit
    return out


def save_result(result: Result, directory: str | Path, config: dict[str, Any]) -> Path:
    """Write 4 files to `directory` (created if missing); return the directory path."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    result.trades.write_parquet(path / "trades.parquet")
    result.equity.write_parquet(path / "equity.parquet")
    (path / "summary.json").write_text(
        json.dumps(_clean(result.summary), indent=2, ensure_ascii=False, default=str)
    )
    (path / "config.json").write_text(
        json.dumps(_clean(build_config(result, config)), indent=2, ensure_ascii=False, default=str)
    )
    return path


def compare(results: dict[str, Result]) -> pl.DataFrame:
    """One row per result: the `name` column, then the summary metrics."""
    rows = [{"name": name, **_clean(r.summary)} for name, r in results.items()]
    return pl.DataFrame(rows, infer_schema_length=None)
