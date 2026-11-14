"""Strategy interface (docs/08-architecture.md section 6).

A strategy takes candles, Features and Events (rinng.analysis.types) and returns a signal frame:

| Column | Type | Meaning |
|---|---|---|
| `time` | Datetime ms UTC | When the signal is known (known_at), always a candle close |
| `side` | String | "long" \\| "short" \\| "flat" |
| `stop` | Float64, nullable | Stop-loss price |
| `take_profit` | Float64, nullable | Take-profit price |
| `size` | Float64 | Capital fraction 0..1, default 1 |
| `reason` | String | Reason, for later reading |

Conventions:
- A new signal replaces the current position: long→short = close long then open short; "flat" =
  close.
- The engine ignores a signal in the same direction as the open position (no resize, no stop/TP
  change).
  So a strategy should only emit a signal when the desired state changes.
- A signal computed from the candle closing at T fills at the earliest at the open of the candle
  starting at T
  (see rinng.backtest.engine).
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
        """Return a frame matching `SIGNAL_SCHEMA`, sorted ascending by `time`."""
        ...


def empty_signals() -> pl.DataFrame:
    return pl.DataFrame(schema=SIGNAL_SCHEMA)


def signals_frame(rows: list[Mapping[str, Any]]) -> pl.DataFrame:
    """Build a signal frame from dicts; missing stop/take_profit are null, missing size is 1."""
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
    """Validate and normalize a signal frame; return a frame matching `SIGNAL_SCHEMA`.

    Adds missing columns (stop, take_profit null; size = 1; reason = ""). Raises when:
    `time`/`side` is missing, side is unknown, size is outside [0, 1], time is null or not
    ascending, stop/TP on the wrong side
    of each other (long needs stop < take_profit, short the reverse).
    If `ohlcv` is given, also checks that each `time` matches a candle close.
    """
    for col in ("time", "side"):
        if col not in signals.columns:
            raise ValueError(f"signal frame is missing column {col!r}")
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
        raise ValueError("time column has null values")
    if not frame["time"].is_sorted():
        raise ValueError("signals must be sorted ascending by time")
    bad = frame.filter(~pl.col("side").is_in(SIDES) | pl.col("side").is_null())
    if bad.height:
        raise ValueError(f"invalid side: {bad['side'].unique().to_list()}; allowed {SIDES}")
    if frame.filter((pl.col("size") < 0) | (pl.col("size") > 1)).height:
        raise ValueError("size must be within [0, 1]")
    wrong = frame.filter(
        pl.col("stop").is_not_null()
        & pl.col("take_profit").is_not_null()
        & (
            ((pl.col("side") == "long") & (pl.col("stop") >= pl.col("take_profit")))
            | ((pl.col("side") == "short") & (pl.col("stop") <= pl.col("take_profit")))
        )
    )
    if wrong.height:
        raise ValueError(f"stop/take_profit on the wrong side in {wrong.height} signals")

    if ohlcv is not None and frame.height:
        duration = bar_duration(ohlcv["timeframe"][0])
        closes = ohlcv["open_time"] + duration
        off = frame.filter(~pl.col("time").is_in(closes.implode()))
        if off.height:
            raise ValueError(f"{off.height} signals have a time that matches no candle close")
    return frame


def dedupe_sides(times: list, sides: list[str], reasons: list[str]) -> pl.DataFrame:
    """Keep signals whose side differs from the previous one (emit only on state change)."""
    rows = []
    last = None
    for t, s, r in zip(times, sides, reasons, strict=True):
        if s != last:
            rows.append({"time": t, "side": s, "reason": r})
            last = s
    return signals_frame(rows)
