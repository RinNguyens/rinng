"""Smart Money Concepts as Events/Features (docs/03-pine-script-and-smc.md part B).

SMC has no standard definition; this module picks the definitions below. Notation: candle i,
`close_time(i)` = open_time[i] + candle duration. Swings come from `structure.swings(length=L)`; a
swing at candle s is known when candle s+L closes.

Swing usage rule: when evaluating candle i for a decision (structure break), only use swings with
known_at <= open_time[i], i.e. known before candle i opens. Premium/discount Features at row i
(known_at = close_time(i)) use swings with known_at <= close_time(i).

BOS / CHoCH (`structure_breaks`, parameters `swing_length`, `break_on` = "close" | "wick"):
- Upper level = the most recent known, unbroken swing high; lower level likewise with swing low. A
  newly known swing replaces the old level of the same kind.
- Break up at candle i: close[i] > upper level (`break_on="close"`) or high[i] > upper level
  ("wick"). Break down is symmetric. Each level is broken only once.
- Label by the trend before candle i: opposite direction → CHoCH, same direction or no trend yet →
  BOS. Afterwards trend = break direction. If one candle breaks both levels (only possible with
  "wick"), both events are recorded, each labelled by the trend before the candle; the trend after =
  candle body direction (close >= open is up).
- kind: bos_bull, bos_bear, choch_bull, choch_bear. event_time = breaking candle, known_at =
  close_time(breaking candle), price_low = price_high = broken level.

Displacement (`displacement`, `k`=1.5, `atr_length`=14):
- Candle i is a displacement if |close - open| > k × ATR[i-1] (ATR of the previous candle, so the
  body does not raise its own threshold). Direction by body. kind displacement_bull/bear, known_at =
  close_time(i), zone = candle body.

FVG (`fair_value_gaps`, `min_size_atr`=0, `atr_length`=14), 3-candle pattern t-2, t-1, t:
- Bull: low[t] > high[t-2], zone [high[t-2], low[t]]. Bear: high[t] < low[t-2], zone
  [high[t], low[t-2]]. Zone size must be >= min_size_atr × ATR[t].
- event_time = middle candle t-1, known_at = close_time(t).
- FULL FILL: the first candle j > t with low[j] <= zone bottom (bull) or high[j] >= zone top
  (bear), i.e. a wick through the whole zone. invalidated_at = close_time(j).
- FIRST TOUCH: the first candle j > t with low[j] <= zone top (bull) or high[j] >= zone bottom
  (bear), recorded as a separate event fvg_bull_mitigated/fvg_bear_mitigated at candle j
  (attrs {"fvg_time", "depth"}: depth = fraction of the zone the wick reached, clipped to [0, 1]).

Order block (`order_blocks`):
- For each upward BOS/CHoCH at candle b: the last down candle (close < open) j in
  [b - max_lookback, b-1]. If `require_displacement`, at least one bullish displacement is required
  in (j, b]; otherwise no OB is emitted. Break down is symmetric (last up candle). Each candle
  becomes an OB at most once per direction.
- Zone = the whole candle j [low, high]. kind ob_bull/ob_bear, event_time = candle j, known_at =
  close_time(b) (an OB only matters after structure breaks).
- Tracked from candle b+1. Mitigation (touch): the first candle with low <= zone top (bull) or
  high >= zone bottom (bear), including the invalidating candle; recorded as a separate event
  ob_bull_mitigated/ob_bear_mitigated at that candle (not stored in the OB's attrs, since attrs must
  not contain future information).
- Invalidation: close (or wick if `invalidate_on="wick"`) through the far edge: bull when
  < zone bottom, bear when > zone top. invalidated_at = close_time(that candle).
- Breaker = an invalidated OB with flipped role: a broken ob_bull yields breaker_bear (and vice
  versa) at the invalidating candle, same zone. A breaker is invalidated when price closes (or
  wicks) back through the other edge: breaker_bear when > zone top, breaker_bull when < zone bottom.

Premium / discount (`premium_discount`, Features): range [L, H] = the most recent known swing low
and swing high. pd_position = (close - L) / (H - L), clipped to [0, 1]; equilibrium = (H + L) / 2
(position 0.5). pd_zone = "equilibrium" when |pd_position - 0.5| <= `equilibrium_band` (default 0,
plus a float tolerance of 1e-9), otherwise "premium" (> 0.5) or "discount" (< 0.5). Null when
there are not yet two swings or H <= L. The range is not extended by new extremes (unlike LuxAlgo
"trailing").

Previous period high/low (`previous_levels`, `period` = polars duration such as "1d", "1w", "4h"):
- Candles are bucketed by `open_time.dt.truncate(period)` (UTC; "1w" starts Monday). A period is
  emitted only when complete: its first candle opens at the bucket start and the data reaches the
  bucket end. Periods cut off at the start of the data are skipped (their high/low would be wrong).
- kind prev_high / prev_low, event_time = first candle of the period, known_at = period end (the
  close of its last candle), price_low = price_high = level. attrs {"period", "period_start"}.
- invalidated_at = close_time of the first candle at/after the period end with high > level
  (prev_high) or low < level (prev_low), i.e. taken by a wick.

Sessions (`sessions`, Features): session_active (bool), session_high, session_low. A candle is in
the session when its open_time (UTC, minute of day m) satisfies start <= m < end, or for windows
crossing midnight m >= start or m < end (end exclusive). High/low run within one session instance
and reset at the next one; null outside. Times are fixed UTC (no DST shift); pass custom
start/end for DST-aware use.

Retracements (`retracements`, Features): at row i, take the latest swing known by close_time(i) (by
swing index). After a swing low the leg is up: origin = swing low, extreme = max high from the swing
to i; after a swing high it is symmetric. retrace_pct = 100 x (extreme - close) / (extreme -
origin) for an up leg (mirror for down), may exceed 100 when price passes the origin. deepest_pct =
the largest retrace_pct since the extreme last moved. leg_dir = +1 / -1. Null before any swing.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.indicators import atr
from rinng.analysis.structure import swing_table, swings
from rinng.analysis.types import (
    bar_duration,
    check_ohlcv,
    empty_events,
    events_frame,
    features_frame,
    params_hash,
)

MODULE = "smc"
BREAK_SOURCES = ("close", "wick")


def known_swings(ohlcv: pl.DataFrame, length: int) -> list[tuple[str, int, float, int]]:
    """List of (kind, index, price, known_index) sorted by known_index then index.

    known_index = index + length: the swing is known when candle known_index closes.
    """
    table = swing_table(swings(ohlcv, length))
    out = [
        (kind, int(idx), float(price), int(idx) + length)
        for kind, idx, price in zip(table["kind"], table["index"], table["price"], strict=True)
    ]
    return sorted(out, key=lambda r: (r[3], r[1]))


class _Bars:
    """Numpy arrays and times of the candle frame."""

    def __init__(self, ohlcv: pl.DataFrame):
        self.symbol, self.timeframe = check_ohlcv(ohlcv)
        self.n = ohlcv.height
        self.times: list[datetime] = ohlcv["open_time"].to_list()
        self.duration = bar_duration(self.timeframe)
        self.o, self.h, self.l, self.c = (
            ohlcv[col].cast(pl.Float64).to_numpy() for col in ("open", "high", "low", "close")
        )

    def close_time(self, i: int) -> datetime:
        return self.times[i] + self.duration

    def frame(self, rows: list[dict[str, Any]], phash: str) -> pl.DataFrame:
        return events_frame(rows, symbol=self.symbol, timeframe=self.timeframe, phash=phash)


def _check_source(name: str, value: str) -> None:
    if value not in BREAK_SOURCES:
        raise ValueError(f"{name} must be one of {BREAK_SOURCES}")


def _breaks(bars: _Bars, ohlcv: pl.DataFrame, swing_length: int, break_on: str) -> list[dict]:
    """Structure breaks as internal dicts: i, side, kind, level, swing_index."""
    _check_source("break_on", break_on)
    up_src = bars.c if break_on == "close" else bars.h
    dn_src = bars.c if break_on == "close" else bars.l
    pending = known_swings(ohlcv, swing_length)
    ptr = 0
    hi: tuple[float, int] | None = None
    lo: tuple[float, int] | None = None
    trend = 0
    out = []
    for i in range(bars.n):
        # Only load swings known before candle i opens (known_index < i).
        while ptr < len(pending) and pending[ptr][3] < i:
            kind, idx, price, _ = pending[ptr]
            if kind == "swing_high":
                hi = (price, idx)
            else:
                lo = (price, idx)
            ptr += 1
        before = trend
        hits = []
        if hi is not None and up_src[i] > hi[0]:
            hits.append((1, hi))
            hi = None
        if lo is not None and dn_src[i] < lo[0]:
            hits.append((-1, lo))
            lo = None
        for side, (level, idx) in hits:
            label = "choch" if before == -side else "bos"
            direction = "bull" if side == 1 else "bear"
            out.append(
                {"i": i, "side": side, "kind": f"{label}_{direction}", "level": level, "swing": idx}
            )
        if len(hits) == 1:
            trend = hits[0][0]
        elif len(hits) == 2:
            trend = 1 if bars.c[i] >= bars.o[i] else -1
    return out


def structure_breaks(
    ohlcv: pl.DataFrame, swing_length: int = 5, break_on: str = "close"
) -> pl.DataFrame:
    """Events BOS/CHoCH. attrs: {"swing_index", "swing_time", "break_index"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "breaks", "swing_length": swing_length, "on": break_on})
    rows = [
        {
            "kind": b["kind"],
            "event_time": bars.times[b["i"]],
            "known_at": bars.close_time(b["i"]),
            "price_low": b["level"],
            "price_high": b["level"],
            "attrs": {
                "swing_index": b["swing"],
                "swing_time": bars.times[b["swing"]],
                "break_index": b["i"],
            },
        }
        for b in _breaks(bars, ohlcv, swing_length, break_on)
    ]
    return bars.frame(rows, phash)


def _displacement_flags(bars: _Bars, ohlcv: pl.DataFrame, k: float, atr_length: int):
    """(+1/-1/0 per candle, ATR of the previous candle)."""
    a = atr(ohlcv, atr_length)
    prev = np.concatenate([[np.nan], a[:-1]])
    body = bars.c - bars.o
    with np.errstate(invalid="ignore"):
        big = np.abs(body) > k * prev
    flags = np.where(big & ~np.isnan(prev), np.sign(body), 0).astype(np.int64)
    return flags, prev


def displacement(ohlcv: pl.DataFrame, k: float = 1.5, atr_length: int = 14) -> pl.DataFrame:
    """Events displacement_bull/bear. attrs: {"body", "atr", "ratio"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "displacement", "k": k, "atr_length": atr_length})
    flags, prev = _displacement_flags(bars, ohlcv, k, atr_length)
    rows = []
    for i in np.flatnonzero(flags):
        i = int(i)
        body = abs(bars.c[i] - bars.o[i])
        rows.append(
            {
                "kind": "displacement_bull" if flags[i] > 0 else "displacement_bear",
                "event_time": bars.times[i],
                "known_at": bars.close_time(i),
                "price_low": float(min(bars.o[i], bars.c[i])),
                "price_high": float(max(bars.o[i], bars.c[i])),
                "attrs": {"body": body, "atr": float(prev[i]), "ratio": body / float(prev[i])},
            }
        )
    return bars.frame(rows, phash)


def fair_value_gaps(
    ohlcv: pl.DataFrame, min_size_atr: float = 0.0, atr_length: int = 14
) -> pl.DataFrame:
    """Events fvg_bull/fvg_bear, invalidated_at = when fully filled. attrs: {"size"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "fvg", "min_size_atr": min_size_atr, "atr": atr_length})
    a = atr(ohlcv, atr_length) if min_size_atr > 0 else None
    h, lo = bars.h, bars.l
    rows = []
    for t in range(2, bars.n):
        for side in (1, -1):
            if side == 1:
                bottom, top = h[t - 2], lo[t]
            else:
                bottom, top = h[t], lo[t - 2]
            size = top - bottom
            if size <= 0:
                continue
            if a is not None and not (size >= min_size_atr * a[t]):  # ATR NaN → skip
                continue
            filled = touched = None
            for j in range(t + 1, bars.n):
                if touched is None and (
                    (side == 1 and lo[j] <= top) or (side == -1 and h[j] >= bottom)
                ):
                    touched = j
                if (side == 1 and lo[j] <= bottom) or (side == -1 and h[j] >= top):
                    filled = bars.close_time(j)
                    break
            name = "bull" if side == 1 else "bear"
            if touched is not None:
                reach = (top - lo[touched]) if side == 1 else (h[touched] - bottom)
                rows.append(
                    {
                        "kind": f"fvg_{name}_mitigated",
                        "id": t,
                        "event_time": bars.times[touched],
                        "known_at": bars.close_time(touched),
                        "price_low": float(bottom),
                        "price_high": float(top),
                        "attrs": {
                            "fvg_time": bars.times[t - 1],
                            "depth": float(min(max(reach / size, 0.0), 1.0)),
                        },
                    }
                )
            rows.append(
                {
                    "kind": f"fvg_{name}",
                    "event_time": bars.times[t - 1],
                    "known_at": bars.close_time(t),
                    "price_low": float(bottom),
                    "price_high": float(top),
                    "invalidated_at": filled,
                    "attrs": {"size": float(size), "fill": "full"},
                }
            )
    return bars.frame(rows, phash)


def order_blocks(
    ohlcv: pl.DataFrame,
    swing_length: int = 5,
    break_on: str = "close",
    invalidate_on: str = "close",
    require_displacement: bool = True,
    displacement_k: float = 1.5,
    atr_length: int = 14,
    max_lookback: int = 50,
) -> pl.DataFrame:
    """Events ob_*, ob_*_mitigated, breaker_*.

    ob attrs: {"break_index", "break_kind", "ob_index"}; mitigated/breaker attrs:
    {"ob_index", "ob_time"}.
    """
    _check_source("invalidate_on", invalidate_on)
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE,
        {
            "fn": "order_blocks",
            "swing_length": swing_length,
            "break_on": break_on,
            "invalidate_on": invalidate_on,
            "require_displacement": require_displacement,
            "displacement_k": displacement_k,
            "atr_length": atr_length,
            "max_lookback": max_lookback,
        },
    )
    flags, _ = _displacement_flags(bars, ohlcv, displacement_k, atr_length)
    o, h, lo, c = bars.o, bars.h, bars.l, bars.c
    low_src = c if invalidate_on == "close" else lo
    high_src = c if invalidate_on == "close" else h
    used: set[tuple[int, int]] = set()
    rows: list[dict[str, Any]] = []
    for brk in _breaks(bars, ohlcv, swing_length, break_on):
        b, side = brk["i"], brk["side"]
        j = None
        for k in range(b - 1, max(-1, b - 1 - max_lookback), -1):
            if (side == 1 and c[k] < o[k]) or (side == -1 and c[k] > o[k]):
                j = k
                break
        if j is None or (side, j) in used:
            continue
        if require_displacement and not np.any(flags[j + 1 : b + 1] == side):
            continue
        used.add((side, j))
        bottom, top = float(lo[j]), float(h[j])
        name = "bull" if side == 1 else "bear"
        opposite = "bear" if side == 1 else "bull"
        mitigated = invalid = None
        for m in range(b + 1, bars.n):
            if mitigated is None and (
                (side == 1 and lo[m] <= top) or (side == -1 and h[m] >= bottom)
            ):
                mitigated = m
            if (side == 1 and low_src[m] < bottom) or (side == -1 and high_src[m] > top):
                invalid = m
                break
        zone = {"price_low": bottom, "price_high": top}
        ref = {"ob_index": j, "ob_time": bars.times[j]}
        rows.append(
            {
                "kind": f"ob_{name}",
                "id": j,
                "event_time": bars.times[j],
                "known_at": bars.close_time(b),
                "invalidated_at": bars.close_time(invalid) if invalid is not None else None,
                "attrs": {"break_index": b, "break_kind": brk["kind"], "ob_index": j},
                **zone,
            }
        )
        if mitigated is not None:
            rows.append(
                {
                    "kind": f"ob_{name}_mitigated",
                    "id": j,
                    "event_time": bars.times[mitigated],
                    "known_at": bars.close_time(mitigated),
                    "attrs": ref,
                    **zone,
                }
            )
        if invalid is not None:
            # Breaker: a broken bull OB becomes resistance, invalidated when price crosses back
            # above the top.
            ended = None
            for w in range(invalid + 1, bars.n):
                if (side == 1 and high_src[w] > top) or (side == -1 and low_src[w] < bottom):
                    ended = bars.close_time(w)
                    break
            rows.append(
                {
                    "kind": f"breaker_{opposite}",
                    "id": j,
                    "event_time": bars.times[invalid],
                    "known_at": bars.close_time(invalid),
                    "invalidated_at": ended,
                    "attrs": ref,
                    **zone,
                }
            )
    return bars.frame(rows, phash)


def premium_discount(
    ohlcv: pl.DataFrame, swing_length: int = 5, equilibrium_band: float = 0.0
) -> pl.DataFrame:
    """Features pd_range_high, pd_range_low, pd_equilibrium, pd_position, pd_zone."""
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE,
        {"fn": "premium_discount", "swing_length": swing_length, "band": equilibrium_band},
    )
    hi = np.full(bars.n, np.nan)
    lo = np.full(bars.n, np.nan)
    for kind, _, price, known in known_swings(ohlcv, swing_length):
        # A swing known at the close of candle `known` → usable from row `known` onward.
        target = hi if kind == "swing_high" else lo
        target[known:] = price
    valid = hi > lo
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = np.where(valid, np.clip((bars.c - lo) / (hi - lo), 0.0, 1.0), np.nan)
    eq = np.where(valid, (hi + lo) / 2, np.nan)
    band = equilibrium_band + 1e-9
    zone = [
        None
        if np.isnan(p)
        else "equilibrium"
        if abs(p - 0.5) <= band
        else "premium"
        if p > 0.5
        else "discount"
        for p in pos
    ]
    return features_frame(
        ohlcv,
        {
            "pd_range_high": pl.Series(np.where(valid, hi, np.nan)).fill_nan(None),
            "pd_range_low": pl.Series(np.where(valid, lo, np.nan)).fill_nan(None),
            "pd_equilibrium": pl.Series(eq).fill_nan(None),
            "pd_position": pl.Series(pos).fill_nan(None),
            "pd_zone": pl.Series(zone, dtype=pl.String()),
        },
        phash,
    )


def previous_levels(ohlcv: pl.DataFrame, period: str = "1d") -> pl.DataFrame:
    """Events prev_high/prev_low of each complete `period`. attrs: {"period", "period_start"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "previous_levels", "period": period})
    t = ohlcv["open_time"]
    buckets = t.dt.truncate(period).to_list()
    ends = t.dt.truncate(period).dt.offset_by(period).to_list()
    data_end = bars.close_time(bars.n - 1)
    rows: list[dict[str, Any]] = []
    start = 0
    while start < bars.n:
        bucket, end = buckets[start], ends[start]
        stop = start
        while stop + 1 < bars.n and buckets[stop + 1] == bucket:
            stop += 1
        if bars.times[start] == bucket and end <= data_end:
            after = start
            while after < bars.n and bars.times[after] < end:
                after += 1
            for kind, level, src, side in (
                ("prev_high", float(bars.h[start : stop + 1].max()), bars.h, 1),
                ("prev_low", float(bars.l[start : stop + 1].min()), bars.l, -1),
            ):
                tail = src[after:]
                hit = np.flatnonzero(tail > level if side == 1 else tail < level)
                taken = bars.close_time(after + int(hit[0])) if hit.size else None
                rows.append(
                    {
                        "kind": kind,
                        "event_time": bars.times[start],
                        "known_at": end,
                        "price_low": level,
                        "price_high": level,
                        "invalidated_at": taken,
                        "attrs": {"period": period, "period_start": bucket},
                    }
                )
        start = stop + 1
    return bars.frame(rows, phash)


SESSIONS: dict[str, tuple[str, str]] = {
    "sydney": ("21:00", "06:00"),
    "tokyo": ("00:00", "09:00"),
    "london": ("07:00", "16:00"),
    "new_york": ("13:00", "22:00"),
    "asia_killzone": ("00:00", "04:00"),
    "london_killzone": ("06:00", "09:00"),
    "new_york_killzone": ("11:00", "14:00"),
    "london_close_killzone": ("14:00", "16:00"),
}


def _minutes(hhmm: str) -> int:
    hh, mm = (int(x) for x in hhmm.split(":"))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        raise ValueError(f"bad time {hhmm!r}, expected HH:MM")
    return hh * 60 + mm


def sessions(
    ohlcv: pl.DataFrame, session: str = "london", start: str | None = None, end: str | None = None
) -> pl.DataFrame:
    """Features session_active, session_high, session_low (UTC; custom start/end override)."""
    check_ohlcv(ohlcv)
    if start is None or end is None:
        if session not in SESSIONS:
            raise ValueError(f"session must be one of {sorted(SESSIONS)} or pass start/end")
        start, end = SESSIONS[session]
    s_min, e_min = _minutes(start), _minutes(end)
    if s_min == e_min:
        raise ValueError("session start and end must differ")
    phash = params_hash(MODULE, {"fn": "sessions", "start": start, "end": end})
    m = pl.col("open_time").dt.hour().cast(pl.Int32) * 60 + pl.col("open_time").dt.minute()
    active = (m >= s_min) & (m < e_min) if s_min < e_min else (m >= s_min) | (m < e_min)
    # Instance key = UTC date of (open_time - start): a midnight-crossing session is one group.
    key = (pl.col("open_time") - pl.duration(minutes=s_min)).dt.date()
    frame = ohlcv.select(
        active.alias("a"),
        key.alias("k"),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
    ).with_columns(
        pl.when("a").then(pl.col("high").cum_max().over("k", "a")).alias("sh"),
        pl.when("a").then(pl.col("low").cum_min().over("k", "a")).alias("sl"),
    )
    return features_frame(
        ohlcv,
        {"session_active": frame["a"], "session_high": frame["sh"], "session_low": frame["sl"]},
        phash,
    )


def retracements(ohlcv: pl.DataFrame, swing_length: int = 5) -> pl.DataFrame:
    """Features leg_dir, retrace_pct, deepest_pct from the latest known swing."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "retracements", "swing_length": swing_length})
    pending = known_swings(ohlcv, swing_length)
    ptr = 0
    latest: tuple[str, int, float] | None = None
    leg = np.full(bars.n, np.nan)
    cur = np.full(bars.n, np.nan)
    deep = np.full(bars.n, np.nan)
    extreme = deepest = np.nan
    for i in range(bars.n):
        changed = False
        # Swings known at the close of candle i (known_index <= i) are usable at row i.
        while ptr < len(pending) and pending[ptr][3] <= i:
            kind, idx, price, _ = pending[ptr]
            if latest is None or idx > latest[1]:
                latest = (kind, idx, price)
                changed = True
            ptr += 1
        if latest is None:
            continue
        kind, idx, origin = latest
        up = kind == "swing_low"
        if changed:
            seg = bars.h[idx : i + 1] if up else bars.l[idx : i + 1]
            extreme = float(seg.max() if up else seg.min())
            deepest = np.nan
        elif (bars.h[i] > extreme) if up else (bars.l[i] < extreme):
            extreme = float(bars.h[i] if up else bars.l[i])
            deepest = np.nan
        span = (extreme - origin) if up else (origin - extreme)
        if span <= 0:
            continue
        pct = 100.0 * ((extreme - bars.c[i]) if up else (bars.c[i] - extreme)) / span
        deepest = pct if np.isnan(deepest) else max(deepest, pct)
        leg[i], cur[i], deep[i] = (1 if up else -1), pct, deepest
    return features_frame(
        ohlcv,
        {
            "leg_dir": pl.Series(leg).fill_nan(None).cast(pl.Int8),
            "retrace_pct": pl.Series(cur).fill_nan(None),
            "deepest_pct": pl.Series(deep).fill_nan(None),
        },
        phash,
    )


def events(ohlcv: pl.DataFrame, params: Mapping[str, Any] | None = None) -> pl.DataFrame:
    """Combine all SMC Events. `params` = {"breaks": {...}, "displacement": {...}, "fvg": {...},
    "order_blocks": {...}, "previous_levels": {...}}, each entry is kwargs for the corresponding
    function."""
    p = dict(params or {})
    parts = [
        structure_breaks(ohlcv, **p.get("breaks", {})),
        displacement(ohlcv, **p.get("displacement", {})),
        fair_value_gaps(ohlcv, **p.get("fvg", {})),
        order_blocks(ohlcv, **p.get("order_blocks", {})),
        previous_levels(ohlcv, **p.get("previous_levels", {})),
    ]
    out = pl.concat([x for x in parts if not x.is_empty()] or [empty_events()])
    return out.sort(["event_time", "kind", "event_id"])
