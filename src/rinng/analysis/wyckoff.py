"""Measurable COMPONENTS of Wyckoff (docs/04-analysis-methods.md section 4).

Does not label the whole schematic (accumulation/distribution, phases A–E): per docs/04 section 4.7
that label is only clear in hindsight. The module only emits mechanically defined pieces, each
tested on its own.

Common quantities (parameters `window` = W, `atr_length` = A):
- ATR: Wilder, first value at candle A−1 = mean of the first A true ranges.
- `volume_z`: volume z-score over the last W candles (including the current one), sample std.
- `spread_atr`: (high − low) / ATR of the PREVIOUS candle, so the current range does not inflate the
  denominator.
- `spread_z`: z-score of spread_atr over W candles.
- `effort_result_gap` = volume_z − spread_z: large positive = much effort (volume) with little
  result (range); large negative = wide range on low volume.
- `clv`: (close − low) / (high − low); 0 = close at the low, 1 = close at the high; null if high =
  low.

Events:
- `selling_climax` / `buying_climax` (function `climaxes`): volume_z >= `volume_z_min` and
  spread_atr >= `spread_min`; direction by candle: close < open is selling, close > open is buying,
  doji candles are skipped. No prior trend required. known_at = close of the climax candle.
- `trading_range` (function `trading_ranges`): when no range is being built or still valid,
  a climax candle c opens a range. Bounds = [min low, max high] of candles c..c+R (R =
  `reaction_bars`, corresponding to SC/BC and AR). The range is confirmed when `min_bars` = N
  consecutive candles afterwards all close within the bounds (inclusive); a close outside before
  reaching N discards the range. event_time = climax candle, known_at = close of the N-th candle.
- `spring` / `upthrust`: after the range is confirmed, a candle b with low < lower bound (high >
  upper bound) opens a break; if within at most M = `reclaim_bars` candles including b some candle j
  closes inside the bounds, it is a spring (upthrust). event_time = candle b, known_at = close of
  candle j. If it does not close back within M candles the range is broken: `invalidated_at` of
  trading_range = close of candle b+M−1. Each side is tracked independently; a range may have
  several springs/upthrusts.

All thresholds are arbitrary (docs/04 section 4.7) and more thresholds overfit more easily. Academic
evidence of a Wyckoff edge after costs: unverified. A range here is just a mechanical
definition, not a claim of accumulation or distribution.
"""

from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.types import (
    bar_duration,
    check_ohlcv,
    events_frame,
    features_frame,
    params_hash,
)

MODULE = "wyckoff"


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    """Wilder-style ATR; NaN before candle length−1."""
    if length < 1:
        raise ValueError("length must be >= 1")
    n = len(high)
    tr = np.empty(n)
    if n == 0:
        return tr
    tr[0] = high[0] - low[0]
    prev = close[:-1]
    tr[1:] = np.maximum.reduce(
        [high[1:] - low[1:], np.abs(high[1:] - prev), np.abs(low[1:] - prev)]
    )
    out = np.full(n, np.nan)
    if n >= length:
        out[length - 1] = tr[:length].mean()
        for i in range(length, n):
            out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


def rolling_zscore(values: np.ndarray, window: int) -> np.ndarray:
    """z-score over the last `window` values (including the current); NaN if not enough data or std
    = 0."""
    if window < 2:
        raise ValueError("window must be >= 2")
    s = pl.Series(values, dtype=pl.Float64(), nan_to_null=True)
    mean = s.rolling_mean(window).to_numpy()
    std = s.rolling_std(window).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (np.asarray(values, dtype=float) - mean) / std
    return np.where(std > 0, z, np.nan)


def _measures(ohlcv: pl.DataFrame, window: int, atr_length: int) -> dict[str, np.ndarray]:
    high = ohlcv["high"].to_numpy()
    low = ohlcv["low"].to_numpy()
    close = ohlcv["close"].to_numpy()
    a = atr(high, low, close, atr_length)
    atr_prev = np.concatenate([[np.nan], a[:-1]])
    rng = high - low
    with np.errstate(divide="ignore", invalid="ignore"):
        spread_atr = np.where(atr_prev > 0, rng / atr_prev, np.nan)
        clv = np.where(rng > 0, (close - low) / rng, np.nan)
    volume_z = rolling_zscore(ohlcv["volume"].to_numpy(), window)
    spread_z = rolling_zscore(spread_atr, window)
    return {
        "atr_prev": atr_prev,
        "volume_z": volume_z,
        "spread_atr": spread_atr,
        "spread_z": spread_z,
        "effort_result_gap": volume_z - spread_z,
        "clv": clv,
    }


def _series(values: np.ndarray) -> pl.Series:
    return pl.Series(values, dtype=pl.Float64(), nan_to_null=True)


def effort_result(ohlcv: pl.DataFrame, *, window: int = 50, atr_length: int = 14) -> pl.DataFrame:
    """Features: volume_z, spread_atr, spread_z, effort_result_gap, clv."""
    check_ohlcv(ohlcv)
    m = _measures(ohlcv, window, atr_length)
    cols = ("volume_z", "spread_atr", "spread_z", "effort_result_gap", "clv")
    phash = params_hash(MODULE, {"kind": "effort_result", "window": window, "atr": atr_length})
    return features_frame(ohlcv, {c: _series(m[c]) for c in cols}, phash)


def _climax_flags(
    ohlcv: pl.DataFrame, m: dict[str, np.ndarray], volume_z_min: float, spread_min: float
) -> np.ndarray:
    """+1 buying climax, −1 selling climax, 0 none."""
    with np.errstate(invalid="ignore"):
        big = (m["volume_z"] >= volume_z_min) & (m["spread_atr"] >= spread_min)
    direction = np.sign(ohlcv["close"].to_numpy() - ohlcv["open"].to_numpy())
    return np.where(big, direction, 0).astype(int)


def _climax_params(window, atr_length, volume_z_min, spread_min) -> dict[str, Any]:
    return {
        "window": window,
        "atr": atr_length,
        "volume_z_min": volume_z_min,
        "spread_min": spread_min,
    }


def climaxes(
    ohlcv: pl.DataFrame,
    *,
    window: int = 50,
    atr_length: int = 14,
    volume_z_min: float = 2.5,
    spread_min: float = 1.8,
) -> pl.DataFrame:
    """Events kind = selling_climax | buying_climax; price_low/high = candle low/high.

    attrs: {"index", "volume_z", "spread_atr", "clv"}
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {"kind": "climax", **_climax_params(window, atr_length, volume_z_min, spread_min)}
    m = _measures(ohlcv, window, atr_length)
    flags = _climax_flags(ohlcv, m, volume_z_min, spread_min)
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    high, low = ohlcv["high"].to_numpy(), ohlcv["low"].to_numpy()
    rows = []
    for i in np.flatnonzero(flags):
        rows.append(
            {
                "kind": "buying_climax" if flags[i] > 0 else "selling_climax",
                "event_time": times[i],
                "known_at": times[i] + duration,
                "price_low": float(low[i]),
                "price_high": float(high[i]),
                "attrs": {
                    "index": int(i),
                    "volume_z": float(m["volume_z"][i]),
                    "spread_atr": float(m["spread_atr"][i]),
                    "clv": None if np.isnan(m["clv"][i]) else float(m["clv"][i]),
                },
            }
        )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))


def trading_ranges(
    ohlcv: pl.DataFrame,
    *,
    window: int = 50,
    atr_length: int = 14,
    volume_z_min: float = 2.5,
    spread_min: float = 1.8,
    reaction_bars: int = 5,
    min_bars: int = 10,
    reclaim_bars: int = 3,
) -> pl.DataFrame:
    """Events kind = trading_range | spring | upthrust (defined in the module docstring).

    trading_range: price_low/high = bounds; attrs {"climax", "origin_index", "confirm_index"}.
    spring/upthrust: price_low/high = extreme of the break and the broken bound;
    attrs {"break_index", "reclaim_index", "reclaim_bars", "penetration", "penetration_atr",
    "range_low", "range_high"}.
    """
    if reaction_bars < 0 or min_bars < 1 or reclaim_bars < 1:
        raise ValueError("requires reaction_bars >= 0, min_bars >= 1, reclaim_bars >= 1")
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {
        "kind": "trading_range",
        **_climax_params(window, atr_length, volume_z_min, spread_min),
        "reaction_bars": reaction_bars,
        "min_bars": min_bars,
        "reclaim_bars": reclaim_bars,
    }
    m = _measures(ohlcv, window, atr_length)
    flags = _climax_flags(ohlcv, m, volume_z_min, spread_min)
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    high = ohlcv["high"].to_numpy()
    low = ohlcv["low"].to_numpy()
    close = ohlcv["close"].to_numpy()

    rows: list[dict[str, Any]] = []
    state = "idle"
    origin = count = 0
    lo = hi = 0.0
    current: dict[str, Any] | None = None
    # pending break on each side: (break candle index, extreme)
    pending: dict[str, tuple[int, float] | None] = {"spring": None, "upthrust": None}

    for i in range(len(close)):
        if state == "reaction":
            lo, hi = min(lo, low[i]), max(hi, high[i])
            if i == origin + reaction_bars:
                state, count = "confirm", 0
        elif state == "confirm":
            if lo <= close[i] <= hi:
                count += 1
                if count == min_bars:
                    current = {
                        "kind": "trading_range",
                        "event_time": times[origin],
                        "known_at": times[i] + duration,
                        "price_low": float(lo),
                        "price_high": float(hi),
                        "attrs": {
                            "climax": "buying" if flags[origin] > 0 else "selling",
                            "origin_index": origin,
                            "confirm_index": i,
                        },
                    }
                    rows.append(current)
                    pending = {"spring": None, "upthrust": None}
                    state = "active"
            else:
                state = "idle"
        elif state == "active":
            for kind in ("spring", "upthrust"):
                broke = low[i] < lo if kind == "spring" else high[i] > hi
                if pending[kind] is None and broke:
                    pending[kind] = (i, low[i] if kind == "spring" else high[i])
                if pending[kind] is None:
                    continue
                b, extreme = pending[kind]
                extreme = min(extreme, low[i]) if kind == "spring" else max(extreme, high[i])
                pending[kind] = (b, extreme)
                if lo <= close[i] <= hi:
                    edge = lo if kind == "spring" else hi
                    penetration = abs(edge - extreme)
                    a = m["atr_prev"][b]
                    rows.append(
                        {
                            "kind": kind,
                            "event_time": times[b],
                            "known_at": times[i] + duration,
                            "price_low": float(min(edge, extreme)),
                            "price_high": float(max(edge, extreme)),
                            "attrs": {
                                "break_index": b,
                                "reclaim_index": i,
                                "reclaim_bars": i - b + 1,
                                "penetration": float(penetration),
                                "penetration_atr": None
                                if np.isnan(a) or a <= 0
                                else float(penetration / a),
                                "range_low": float(lo),
                                "range_high": float(hi),
                            },
                        }
                    )
                    pending[kind] = None
                elif i - b + 1 >= reclaim_bars and current is not None:
                    current["invalidated_at"] = times[i] + duration
                    state = "idle"
                    break
        if state == "idle" and flags[i] != 0:
            origin, lo, hi = i, low[i], high[i]
            state, count = ("reaction", 0) if reaction_bars > 0 else ("confirm", 0)
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))
