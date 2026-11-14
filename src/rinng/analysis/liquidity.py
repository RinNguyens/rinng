"""Liquidity as Events (docs/03-pine-script-and-smc.md section B6).

Notation as in `smc`: swings from `structure.swings(length=L)`; a swing at candle s is known when
candle s+L closes (known_index = s+L); `close_time(i)` = open_time[i] + candle duration. All
sweeps/comparisons only consider candles AFTER the level's known_index, so a level is only used once
known.

Liquidity levels (`liquidity_levels`, `swing_length`=5):
- Each swing high is a buy-side liquidity level (kind liquidity_bsl): the zone above an old high
  where buy stops sit; each swing low is sell-side (liquidity_ssl). price_low = price_high = level.
- event_time = swing candle, known_at = the swing's known_at.
- invalidated_at = close_time of the first candle after known_index with high > level (BSL) or
  low < level (SSL), i.e. liquidity taken by a wick.

Equal highs / lows (`equal_levels`, `tolerance_atr`=0.1, `atr_length`=14, `max_lookback`=100):
- When swing high k becomes known, collect earlier swing highs p (same kind) satisfying:
  index_k - index_p <= max_lookback; |price_p - price_k| <= tolerance_atr × ATR[known_index_k];
  and no candle between p and k has high > max(price_p, price_k) (level not yet taken). At least
  one p is required, i.e. a cluster of >= 2 swings. Equal lows are symmetric on low.
- kind eqh/eql, event_time = swing candle k, known_at = known_at of swing k, zone =
  [min, max] of the swing prices in the cluster.
- invalidated_at = close_time of the first candle after known_index_k with high > zone top (eqh)
  or low < zone bottom (eql).

Liquidity sweep (`sweeps`, `max_bars`=1):
- For each swing level (BSL/SSL), the first candle i after known_index whose wick pierces the level
  (high > level for BSL, low < level for SSL) is the piercing candle. If within max_bars candles
  from i (i .. i+max_bars-1) some candle r closes back inside (close <= level for BSL, close >=
  level for SSL) it is a sweep; otherwise it is a breakout and no event is emitted. Only the first
  pierce of each level is considered.
- kind sweep_bsl/sweep_ssl, event_time = piercing candle i, known_at = close_time(r). Zone spans
  from the level to the extreme of candles i..r. Sweeps of equal high/low clusters are covered via
  the highest/lowest swing in the cluster.
"""

from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.indicators import atr
from rinng.analysis.smc import _Bars, known_swings
from rinng.analysis.types import params_hash

MODULE = "liquidity"

_SIDE = {"swing_high": ("bsl", 1), "swing_low": ("ssl", -1)}


def _taken(bars: _Bars, start: int, level: float, side: int) -> int | None:
    """First candle >= start whose wick crosses the level (side=1 above, -1 below)."""
    for i in range(start, bars.n):
        if (side == 1 and bars.h[i] > level) or (side == -1 and bars.l[i] < level):
            return i
    return None


def liquidity_levels(ohlcv: pl.DataFrame, swing_length: int = 5) -> pl.DataFrame:
    """Events liquidity_bsl / liquidity_ssl. attrs: {"swing_index"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "levels", "swing_length": swing_length})
    rows = []
    for kind, idx, price, known in known_swings(ohlcv, swing_length):
        name, side = _SIDE[kind]
        hit = _taken(bars, known + 1, price, side)
        rows.append(
            {
                "kind": f"liquidity_{name}",
                "event_time": bars.times[idx],
                "known_at": bars.close_time(known),
                "price_low": price,
                "price_high": price,
                "invalidated_at": bars.close_time(hit) if hit is not None else None,
                "attrs": {"swing_index": idx},
            }
        )
    return bars.frame(rows, phash)


def equal_levels(
    ohlcv: pl.DataFrame,
    swing_length: int = 5,
    tolerance_atr: float = 0.1,
    atr_length: int = 14,
    max_lookback: int = 100,
) -> pl.DataFrame:
    """Events eqh / eql. attrs: {"count", "swing_indices", "tolerance"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE,
        {
            "fn": "equal",
            "swing_length": swing_length,
            "tolerance_atr": tolerance_atr,
            "atr_length": atr_length,
            "max_lookback": max_lookback,
        },
    )
    a = atr(ohlcv, atr_length)
    rows: list[dict[str, Any]] = []
    seen: dict[str, list[tuple[int, float]]] = {"swing_high": [], "swing_low": []}
    for kind, idx, price, known in known_swings(ohlcv, swing_length):
        _, side = _SIDE[kind]
        prior = seen[kind]
        tol = tolerance_atr * a[known]
        members = [(idx, price)]
        if not np.isnan(tol):
            for p_idx, p_price in prior:
                if idx - p_idx > max_lookback or abs(p_price - price) > tol:
                    continue
                between = slice(p_idx + 1, idx)
                if side == 1:
                    ok = bars.h[between].size == 0 or bars.h[between].max() <= max(p_price, price)
                else:
                    ok = bars.l[between].size == 0 or bars.l[between].min() >= min(p_price, price)
                if ok:
                    members.append((p_idx, p_price))
        prior.append((idx, price))
        if len(members) < 2:
            continue
        members.sort()
        low = min(m[1] for m in members)
        high = max(m[1] for m in members)
        hit = _taken(bars, known + 1, high if side == 1 else low, side)
        rows.append(
            {
                "kind": "eqh" if side == 1 else "eql",
                "event_time": bars.times[idx],
                "known_at": bars.close_time(known),
                "price_low": low,
                "price_high": high,
                "invalidated_at": bars.close_time(hit) if hit is not None else None,
                "attrs": {
                    "count": len(members),
                    "swing_indices": [m[0] for m in members],
                    "tolerance": float(tol),
                },
            }
        )
    return bars.frame(rows, phash)


def sweeps(ohlcv: pl.DataFrame, swing_length: int = 5, max_bars: int = 1) -> pl.DataFrame:
    """Events sweep_bsl / sweep_ssl.

    attrs: {"level", "level_index", "level_time", "bars", "penetration"}.
    """
    if max_bars < 1:
        raise ValueError("max_bars must be >= 1")
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE, {"fn": "sweeps", "swing_length": swing_length, "max_bars": max_bars}
    )
    rows = []
    for kind, idx, level, known in known_swings(ohlcv, swing_length):
        name, side = _SIDE[kind]
        i = _taken(bars, known + 1, level, side)
        if i is None:
            continue
        back = None
        for r in range(i, min(i + max_bars, bars.n)):
            if (side == 1 and bars.c[r] <= level) or (side == -1 and bars.c[r] >= level):
                back = r
                break
        if back is None:
            continue  # breakout: closed outside the level for all max_bars candles
        if side == 1:
            extreme = float(bars.h[i : back + 1].max())
            low, high, pen = level, extreme, extreme - level
        else:
            extreme = float(bars.l[i : back + 1].min())
            low, high, pen = extreme, level, level - extreme
        rows.append(
            {
                "kind": f"sweep_{name}",
                "id": idx,
                "event_time": bars.times[i],
                "known_at": bars.close_time(back),
                "price_low": low,
                "price_high": high,
                "attrs": {
                    "level": level,
                    "level_index": idx,
                    "level_time": bars.times[idx],
                    "bars": back - i + 1,
                    "penetration": pen,
                },
            }
        )
    return bars.frame(rows, phash)
