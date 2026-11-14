"""Giao diện chiến lược (docs/08-kien-truc.md mục 6).

Một chiến lược nhận nến, Features và Events (rinng.analysis.types) rồi trả frame tín hiệu:

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `time` | Datetime ms UTC | Lúc tín hiệu được biết (known_at), luôn là lúc đóng một nến |
| `side` | String | "long" \\| "short" \\| "flat" |
| `stop` | Float64, có thể rỗng | Giá stop-loss |
| `take_profit` | Float64, có thể rỗng | Giá take-profit |
| `size` | Float64 | Tỷ lệ vốn 0..1, mặc định 1 |
| `reason` | String | Lý do, để đọc lại |

Quy ước:
- Một tín hiệu mới thay thế vị thế hiện tại: long→short = đóng long rồi mở short; "flat" = đóng.
- Tín hiệu cùng chiều với vị thế đang mở bị engine bỏ qua (không đổi cỡ, không đổi stop/TP).
  Vì vậy chiến lược nên chỉ phát tín hiệu khi trạng thái mong muốn đổi.
- Tín hiệu tính từ nến đóng lúc T chỉ được khớp sớm nhất ở giá mở của nến bắt đầu lúc T
  (xem rinng.backtest.engine).
"""

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

import polars as pl

from rinng.analysis.types import bar_duration
from rinng.store.schemas import TIME

SIDES = ("long", "short", "flat")

SIGNAL_SCHEMA: dict[str, pl.DataType] = {
    "time": TIME,
    "side": pl.String(),
    "stop": pl.Float64(),
    "take_profit": pl.Float64(),
    "size": pl.Float64(),
    "reason": pl.String(),
}


@runtime_checkable
class Strategy(Protocol):
    name: str
    params: dict[str, Any]

    def signals(
        self, ohlcv: pl.DataFrame, features: pl.DataFrame | None, events: pl.DataFrame | None
    ) -> pl.DataFrame:
        """Trả frame theo `SIGNAL_SCHEMA`, sắp tăng dần theo `time`."""
        ...


def empty_signals() -> pl.DataFrame:
    return pl.DataFrame(schema=SIGNAL_SCHEMA)


def signals_frame(rows: list[Mapping[str, Any]]) -> pl.DataFrame:
    """Dựng frame tín hiệu từ các dict; thiếu stop/take_profit thì rỗng, thiếu size thì 1."""
    if not rows:
        return empty_signals()
    data = [
        {
            "time": r["time"],
            "side": r["side"],
            "stop": r.get("stop"),
            "take_profit": r.get("take_profit"),
            "size": 1.0 if r.get("size") is None else float(r["size"]),
            "reason": r.get("reason", ""),
        }
        for r in rows
    ]
    return validate_signals(pl.DataFrame(data, schema_overrides=SIGNAL_SCHEMA))


def validate_signals(signals: pl.DataFrame, ohlcv: pl.DataFrame | None = None) -> pl.DataFrame:
    """Kiểm và chuẩn hóa frame tín hiệu; trả frame đúng `SIGNAL_SCHEMA`.

    Thêm cột thiếu (stop, take_profit rỗng; size = 1; reason = ""). Báo lỗi khi: thiếu
    `time`/`side`, side lạ, size ngoài [0, 1], time rỗng hoặc không tăng dần, stop/TP sai phía
    so với nhau (long cần stop < take_profit, short ngược lại).
    Nếu có `ohlcv`, kiểm thêm mỗi `time` trùng một thời điểm đóng nến.
    """
    for col in ("time", "side"):
        if col not in signals.columns:
            raise ValueError(f"frame tín hiệu thiếu cột {col!r}")
    frame = signals.with_columns(
        *[
            pl.lit(None, dtype=dtype).alias(name)
            for name, dtype in SIGNAL_SCHEMA.items()
            if name not in signals.columns and name not in ("size", "reason")
        ],
        *([pl.lit(1.0).alias("size")] if "size" not in signals.columns else []),
        *([pl.lit("").alias("reason")] if "reason" not in signals.columns else []),
    )
    frame = frame.select(
        [pl.col(n).cast(t, strict=True).alias(n) for n, t in SIGNAL_SCHEMA.items()]
    ).with_columns(pl.col("size").fill_null(1.0), pl.col("reason").fill_null(""))

    if frame["time"].null_count():
        raise ValueError("cột time có giá trị rỗng")
    if not frame["time"].is_sorted():
        raise ValueError("tín hiệu phải sắp tăng dần theo time")
    bad = frame.filter(~pl.col("side").is_in(SIDES) | pl.col("side").is_null())
    if bad.height:
        raise ValueError(f"side không hợp lệ: {bad['side'].unique().to_list()}; cho phép {SIDES}")
    if frame.filter((pl.col("size") < 0) | (pl.col("size") > 1)).height:
        raise ValueError("size phải nằm trong [0, 1]")
    wrong = frame.filter(
        pl.col("stop").is_not_null()
        & pl.col("take_profit").is_not_null()
        & (
            ((pl.col("side") == "long") & (pl.col("stop") >= pl.col("take_profit")))
            | ((pl.col("side") == "short") & (pl.col("stop") <= pl.col("take_profit")))
        )
    )
    if wrong.height:
        raise ValueError(f"stop/take_profit sai phía ở {wrong.height} tín hiệu")

    if ohlcv is not None and frame.height:
        duration = bar_duration(ohlcv["timeframe"][0])
        closes = ohlcv["open_time"] + duration
        off = frame.filter(~pl.col("time").is_in(closes.implode()))
        if off.height:
            raise ValueError(f"{off.height} tín hiệu có time không trùng lúc đóng nến nào")
    return frame


def dedupe_sides(times: list, sides: list[str], reasons: list[str]) -> pl.DataFrame:
    """Giữ các tín hiệu mà side khác side liền trước (chỉ phát khi trạng thái đổi)."""
    rows = []
    last = None
    for t, s, r in zip(times, sides, reasons, strict=True):
        if s != last:
            rows.append({"time": t, "side": s, "reason": r})
            last = s
    return signals_frame(rows)
