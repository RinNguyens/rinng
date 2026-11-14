"""The two output shapes of the analysis layer (docs/08-architecture.md section 5.3).

Common input of every module: a candle frame in the curated `ohlcv` schema for ONE symbol and ONE
timeframe, sorted ascending by `open_time`, without duplicates.

- Features: one row per candle. Key columns `symbol, timeframe, open_time, known_at, params_hash`
  followed by the value columns. `known_at` = candle close time.
- Events: one row per event, fixed schema `EVENT_SCHEMA`.
  `event_time` is the candle the event attaches to; `known_at` is when the event is confirmed
  (always >= the close time of the `event_time` candle). `invalidated_at` is when the zone is
  broken/filled. `attrs` is a JSON string holding kind-specific attributes.

No-lookahead rule: results with `known_at <= T` must not change when data after T
is appended. `rinng.analysis.testing.assert_no_lookahead` checks this.
"""

import hashlib
import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import polars as pl

from rinng.exchanges.base import timeframe_ms
from rinng.store.schemas import TIME

FEATURE_KEYS = ("symbol", "timeframe", "open_time", "known_at", "params_hash")

EVENT_SCHEMA: dict[str, pl.DataType] = {
    "event_id": pl.String(),
    "symbol": pl.String(),
    "timeframe": pl.String(),
    "kind": pl.String(),
    "event_time": TIME,
    "known_at": TIME,
    "price_low": pl.Float64(),
    "price_high": pl.Float64(),
    "invalidated_at": TIME,
    "attrs": pl.String(),
    "params_hash": pl.String(),
}


def params_hash(module: str, params: Mapping[str, Any]) -> str:
    """Stable hash of (module, params)."""
    payload = json.dumps({"module": module, "params": dict(params)}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def bar_duration(timeframe: str) -> timedelta:
    return timedelta(milliseconds=timeframe_ms(timeframe))


def check_ohlcv(ohlcv: pl.DataFrame) -> tuple[str, str]:
    """Validate the input and return (symbol, timeframe)."""
    if ohlcv.is_empty():
        raise ValueError("empty candle frame")
    for col in ("symbol", "timeframe"):
        if ohlcv[col].n_unique() != 1:
            raise ValueError(f"candle frame must have a single {col} value")
    times = ohlcv["open_time"]
    if not times.is_sorted() or times.n_unique() != len(times):
        raise ValueError("open_time must be strictly increasing without duplicates")
    return ohlcv["symbol"][0], ohlcv["timeframe"][0]


def features_frame(
    ohlcv: pl.DataFrame, values: Mapping[str, pl.Series | pl.Expr], phash: str
) -> pl.DataFrame:
    """Build a Features frame from candles and value columns of the same length."""
    _, timeframe = check_ohlcv(ohlcv)
    duration = bar_duration(timeframe)
    return ohlcv.select(
        "symbol",
        "timeframe",
        "open_time",
        (pl.col("open_time") + duration).alias("known_at"),
        pl.lit(phash).alias("params_hash"),
        *[(v if isinstance(v, pl.Expr) else pl.lit(v)).alias(k) for k, v in values.items()],
    )


def events_frame(
    rows: list[dict[str, Any]], *, symbol: str, timeframe: str, phash: str
) -> pl.DataFrame:
    """Build an Events frame. Each dict needs: kind, event_time, known_at; optional: price_low,
    price_high, invalidated_at, attrs (dict). `event_id` is derived stably from the content."""
    out = []
    for r in rows:
        attrs = r.get("attrs") or {}
        record = {
            "symbol": symbol,
            "timeframe": timeframe,
            "kind": r["kind"],
            "event_time": r["event_time"],
            "known_at": r["known_at"],
            "price_low": r.get("price_low"),
            "price_high": r.get("price_high"),
            "invalidated_at": r.get("invalidated_at"),
            "attrs": json.dumps(attrs, sort_keys=True, default=str),
            "params_hash": phash,
        }
        if record["known_at"] < record["event_time"]:
            raise ValueError(f"known_at before event_time in event {r['kind']}")
        ident = f"{symbol}|{timeframe}|{r['kind']}|{r['event_time']}|{phash}|{r.get('id', '')}"
        record["event_id"] = hashlib.sha1(ident.encode()).hexdigest()[:16]
        out.append(record)
    if not out:
        return empty_events()
    frame = pl.DataFrame(out, schema_overrides=EVENT_SCHEMA).select(list(EVENT_SCHEMA))
    return frame.sort(["event_time", "kind", "event_id"])


def empty_events() -> pl.DataFrame:
    return pl.DataFrame(schema=EVENT_SCHEMA)
