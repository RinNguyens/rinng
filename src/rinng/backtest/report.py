"""Tách in-sample/out-of-sample, lưu kết quả, bảng so sánh.

`save_result` là chỗ duy nhất của gói backtest ghi file. Mỗi lần chạy lưu:
- `trades.parquet`, `equity.parquet`: frame của Result.
- `summary.json`: metric (NaN/vô cực ghi thành null).
- `config.json`: cấu hình người gọi đưa vào, thêm `params_hash` (nếu có `strategy` và
  `params`), `costs`, `period`, `symbol`, `timeframe`, `initial_equity`, `leverage` lấy từ
  Result, và `git_commit` nếu `git rev-parse HEAD` chạy được (lỗi thì bỏ qua).
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

    Lưu ý: chiến lược cần nến khởi động (EMA, cửa sổ hồi quy) sẽ mất phần đầu của tập
    out-of-sample nếu chạy riêng; muốn liền mạch thì sinh tín hiệu trên toàn bộ rồi lọc.
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
    """Đổi NaN/vô cực thành None để JSON hợp lệ."""
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
    """Ghi 4 file vào `directory` (tạo nếu chưa có); trả đường dẫn thư mục."""
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
    """Một dòng mỗi kết quả, cột `name` rồi các metric trong summary."""
    rows = [{"name": name, **_clean(r.summary)} for name, r in results.items()]
    return pl.DataFrame(rows, infer_schema_length=None)
