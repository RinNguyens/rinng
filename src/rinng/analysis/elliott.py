"""Measurable components of Elliott Wave (docs/04-analysis-methods.md section 5).

Does not pick a single wave count: the module only builds pivots, checks the hard rules and lists
every candidate that satisfies them, to be tested as a descriptive feature.

Zigzag (parameters `threshold`, `mode`):
- mode "percent": reverse down from candidate high H when low[i] <= H * (1 − threshold); reverse
  up from candidate low L when high[i] >= L * (1 + threshold).
- mode "atr": as above but the distance is threshold * ATR(atr_length) of candle i (Wilder,
  `rinng.analysis.wyckoff.atr`); no pivot can be confirmed before ATR exists.
- The candidate high is the largest high since the previous pivot (ties take the first candle); lows
  are symmetric. The pivot must lie on a candle BEFORE the confirming candle: a candle that just set
  a new extreme cannot reverse within itself (we do not know whether the high or the low came
  first).
- Initially there is no direction: the first pivot is whichever extreme gets its reversal threshold
  crossed first; if on the same candle, the earlier extreme wins.
- known_at = close of candle i where the reversal threshold is crossed. The last (running) pivot is
  not emitted.

Hard rules for a 6-pivot impulse P0..P5 (signs flipped when wave 1 goes down, `log=True` uses log
price):
1. `wave2_within_wave1`: P2 does not pass the origin of wave 1, i.e. P2 > P0 (touching fails).
2. `wave3_not_shortest`: |wave 3| >= min(|wave 1|, |wave 5|).
3. `wave4_no_overlap`: P4 > P1 (wave 4 does not enter wave 1's price range; diagonals not
   considered).
Rules 1 and 3 are scale-invariant; rule 2 depends on log vs linear scale.

Fibonacci ratios (absolute wave lengths): wave2/wave1, wave3/wave1, wave4/wave3, wave5/wave1,
wave5/(P0→P3). Descriptive only, not scored.

`impulse_candidates`: every window of 6 consecutive zigzag pivots satisfying all three rules, both
up and down, as `impulse_candidate` Events; event_time = candle P5, known_at = known_at of P5 (when
P5 is confirmed by the zigzag). Overlapping windows are all kept.

Limits (docs/04 sections 5.7, 5.8): empirical evidence of predictive power is weak; results are very
sensitive to the zigzag threshold and price scale; the three hard rules filter very little, so
almost any series has candidates. Sub-structure (5-3-5-3-5) and corrective patterns are not checked.
"""

import json
from collections.abc import Sequence
from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration, check_ohlcv, events_frame, params_hash
from rinng.analysis.wyckoff import atr

MODULE = "elliott"

RULES = ("wave2_within_wave1", "wave3_not_shortest", "wave4_no_overlap")


def zigzag_pivots(
    high: np.ndarray, low: np.ndarray, distance: np.ndarray | None = None, *, pct: float = 0.0
) -> list[tuple[int, str, float, int]]:
    """Alternating pivots (index, "H"|"L", price, confirm index).

    `distance` (array of the same length, NaN = cannot confirm yet) gives an absolute per-candle
    threshold; if None the relative threshold `pct` is used.
    """
    n = len(high)

    def down(peak: float, i: int) -> bool:
        if distance is None:
            return low[i] <= peak * (1 - pct)
        d = distance[i]
        return not np.isnan(d) and peak - low[i] >= d

    def up(trough: float, i: int) -> bool:
        if distance is None:
            return high[i] >= trough * (1 + pct)
        d = distance[i]
        return not np.isnan(d) and high[i] - trough >= d

    out: list[tuple[int, str, float, int]] = []
    direction = 0  # 1: last pivot is a low, looking for a high; -1: the opposite
    hi_i = lo_i = 0
    for i in range(n):
        if direction >= 0 and high[i] > high[hi_i]:
            hi_i = i
        if direction <= 0 and low[i] < low[lo_i]:
            lo_i = i
        while True:
            go_up = direction <= 0 and lo_i < i and up(low[lo_i], i)
            go_down = direction >= 0 and hi_i < i and down(high[hi_i], i)
            if direction == 0 and go_up and go_down:
                go_up = lo_i <= hi_i
                go_down = not go_up
            if go_up:
                out.append((lo_i, "L", float(low[lo_i]), i))
                direction = 1
                hi_i = lo_i + 1 + int(np.argmax(high[lo_i + 1 : i + 1]))
            elif go_down:
                out.append((hi_i, "H", float(high[hi_i]), i))
                direction = -1
                lo_i = hi_i + 1 + int(np.argmin(low[hi_i + 1 : i + 1]))
            else:
                break
    return out


def _zigzag_params(threshold: float, mode: str, atr_length: int) -> dict[str, Any]:
    if mode not in ("percent", "atr"):
        raise ValueError("mode must be percent or atr")
    if threshold <= 0 or (mode == "percent" and threshold >= 1):
        raise ValueError("invalid threshold")
    return {"threshold": threshold, "mode": mode, "atr": atr_length if mode == "atr" else None}


def _pivots(ohlcv: pl.DataFrame, threshold: float, mode: str, atr_length: int):
    high = ohlcv["high"].to_numpy()
    low = ohlcv["low"].to_numpy()
    if mode == "percent":
        return zigzag_pivots(high, low, pct=threshold)
    a = atr(high, low, ohlcv["close"].to_numpy(), atr_length)
    return zigzag_pivots(high, low, threshold * a)


def zigzag(
    ohlcv: pl.DataFrame, *, threshold: float = 0.05, mode: str = "percent", atr_length: int = 14
) -> pl.DataFrame:
    """Events kind = zigzag_high | zigzag_low; price_low = price_high = pivot price.

    attrs: {"index", "confirm_index"}
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {"kind": "zigzag", **_zigzag_params(threshold, mode, atr_length)}
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    rows = [
        {
            "kind": "zigzag_high" if kind == "H" else "zigzag_low",
            "event_time": times[i],
            "known_at": times[c] + duration,
            "price_low": price,
            "price_high": price,
            "attrs": {"index": i, "confirm_index": c},
        }
        for i, kind, price, c in _pivots(ohlcv, threshold, mode, atr_length)
    ]
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))


def zigzag_table(events: pl.DataFrame) -> pl.DataFrame:
    """Helper: compact pivot table (kind, event_time, known_at, price, index) in time order."""
    piv = events.filter(pl.col("kind").is_in(["zigzag_high", "zigzag_low"]))
    decoded = piv["attrs"].str.json_decode(pl.Struct({"index": pl.Int64()}))
    return (
        piv.select("kind", "event_time", "known_at", pl.col("price_high").alias("price"))
        .with_columns(decoded.struct.field("index").alias("index"))
        .sort("event_time")
    )


def _signed(prices: Sequence[float], log: bool) -> np.ndarray:
    p = np.asarray(prices, dtype=float)
    if p.shape != (6,):
        raise ValueError("exactly 6 pivots P0..P5 required")
    if log:
        if (p <= 0).any():
            raise ValueError("log requires positive prices")
        p = np.log(p)
    q = p if p[1] > p[0] else -p
    legs = np.diff(q)
    if not ((legs[0::2] > 0).all() and (legs[1::2] < 0).all()):
        raise ValueError("the 6 pivots must alternate high/low")
    return q


def impulse_rules(prices: Sequence[float], *, log: bool = True) -> dict[str, bool]:
    """The three hard impulse rules for P0..P5; each rule true/false separately."""
    q = _signed(prices, log)
    w1, w3, w5 = q[1] - q[0], q[3] - q[2], q[5] - q[4]
    return {
        "wave2_within_wave1": bool(q[2] > q[0]),
        "wave3_not_shortest": bool(w3 >= min(w1, w5)),
        "wave4_no_overlap": bool(q[4] > q[1]),
    }


def impulse_ratios(prices: Sequence[float], *, log: bool = False) -> dict[str, float]:
    """Ratios between wave lengths (absolute values)."""
    q = _signed(prices, log)
    w = np.abs(np.diff(q))
    return {
        "wave2_wave1": float(w[1] / w[0]),
        "wave3_wave1": float(w[2] / w[0]),
        "wave4_wave3": float(w[3] / w[2]),
        "wave5_wave1": float(w[4] / w[0]),
        "wave5_wave1to3": float(w[4] / abs(q[3] - q[0])),
    }


def _wave_ends(piv: Sequence[tuple], i: int, max_legs: int) -> list[int]:
    """Pivot positions j > i that can end one wave starting at pivot i.

    A wave from a low (high) ends at a high (low) that is the extreme of every pivot in i..j, while
    no pivot between them goes beyond the start; at most `max_legs` zigzag legs per wave.
    """
    s = 1.0 if piv[i][1] == "L" else -1.0
    out, best = [], -np.inf
    for j in range(i + 1, min(len(piv), i + 1 + max_legs)):
        v = s * piv[j][2]
        if s * (piv[j][2] - piv[i][2]) <= 0:
            break  # went beyond the start: no longer one wave
        if piv[j][1] != piv[i][1] and v > best:
            out.append(j)
        best = max(best, v) if piv[j][1] != piv[i][1] else best
    return out


def nested_windows(piv: Sequence[tuple], *, max_legs: int = 5) -> list[list[tuple]]:
    """All P0..P5 pivot sequences where each wave is one clean move (see `_wave_ends`).

    Includes every consecutive 6-pivot window (one leg per wave); a wave may span up to `max_legs`
    zigzag legs, so wave 3 can contain its own 1-2-3-4-5 sub-swings.
    """
    out: list[list[tuple]] = []

    def walk(path: list[int]) -> None:
        if len(path) == 6:
            out.append([piv[k] for k in path])
            return
        for j in _wave_ends(piv, path[-1], max_legs):
            walk([*path, j])

    for i in range(len(piv)):
        walk([i])
    return out


def impulse_candidates(
    ohlcv: pl.DataFrame,
    *,
    threshold: float = 0.05,
    mode: str = "percent",
    atr_length: int = 14,
    log: bool = True,
    nested: bool = False,
) -> pl.DataFrame:
    """Events kind = impulse_candidate; price_low/high = min/max of the 6 pivots.

    nested=False: windows of 6 consecutive zigzag pivots. nested=True: also lets each wave span
    smaller sub-swings (see `nested_windows`), e.g. a wave 3 made of 3 zigzag legs.

    attrs: {"direction": "up"|"down", "indices", "prices", "ratios"} with ratios computed on the
    same scale as the rules (`log`).
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {"kind": "impulse", **_zigzag_params(threshold, mode, atr_length), "log": log}
    piv = _pivots(ohlcv, threshold, mode, atr_length)
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    rows = []
    windows = nested_windows(piv) if nested else [piv[k : k + 6] for k in range(len(piv) - 5)]
    for window in windows:
        prices = [p[2] for p in window]
        if not all(impulse_rules(prices, log=log).values()):
            continue
        last = window[-1]
        rows.append(
            {
                "kind": "impulse_candidate",
                "event_time": times[last[0]],
                "known_at": times[last[3]] + duration,
                "price_low": min(prices),
                "price_high": max(prices),
                "attrs": {
                    "direction": "up" if prices[1] > prices[0] else "down",
                    "indices": [p[0] for p in window],
                    "prices": prices,
                    "ratios": impulse_ratios(prices, log=log),
                },
                "id": "-".join(str(p[0]) for p in window) if nested else window[0][0],
            }
        )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))


# Fibonacci guideline targets per wave ratio (linear price, absolute wave lengths). A ratio scores
# by its log distance to the nearest target: exp(-(ln(r/t) / FIB_TOLERANCE)^2), so a ratio exactly
# on a target scores 1 and one ~25% away scores ~0.37. The impulse score is the mean of the four.
FIB_TARGETS: dict[str, tuple[float, ...]] = {
    "wave2_wave1": (0.5, 0.618, 0.786),
    "wave3_wave1": (1.618, 2.618),
    "wave4_wave3": (0.236, 0.382, 0.5),
    "wave5_wave1": (0.618, 1.0, 1.618),
}
FIB_TOLERANCE = 0.25


def _closeness(r: float, targets: Sequence[float]) -> float:
    """exp(-(ln(r/t) / FIB_TOLERANCE)^2) for the nearest target t; 0 when r <= 0."""
    if r <= 0:
        return 0.0
    d = min(abs(np.log(r / t)) for t in targets)
    return float(np.exp(-((d / FIB_TOLERANCE) ** 2)))


def fib_score(prices: Sequence[float]) -> dict[str, float]:
    """Per-ratio closeness to the Fibonacci guidelines (0..1) plus their mean under "score".

    Guidelines, not rules: a low score does not invalidate a count, it only ranks candidates.
    """
    ratios = impulse_ratios(prices, log=False)
    out = {name: _closeness(ratios[name], targets) for name, targets in FIB_TARGETS.items()}
    out["score"] = float(np.mean([out[k] for k in FIB_TARGETS]))
    return out


def best_impulses(candidates: pl.DataFrame, *, min_score: float = 0.35) -> list[dict[str, Any]]:
    """Pick non-overlapping impulse candidates, highest Fibonacci score first.

    Each kept candidate is the dict of its row with decoded attrs plus "fib" (from `fib_score`).
    Two candidates overlap when their P0..P5 index spans intersect (sharing one end pivot is
    allowed). Result is in time order. Uses only each candidate's own pivots, so it adds no
    lookahead beyond the candidates themselves; but which candidate wins a span can change when a
    later, better-scoring one appears.
    """
    scored = []
    for row in candidates.filter(pl.col("kind") == "impulse_candidate").to_dicts():
        attrs = json.loads(row["attrs"]) if isinstance(row["attrs"], str) else row["attrs"]
        fib = fib_score(attrs["prices"])
        if fib["score"] >= min_score:
            scored.append({**row, "attrs": attrs, "fib": fib})
    scored.sort(key=lambda c: -c["fib"]["score"])
    kept: list[dict[str, Any]] = []
    for c in scored:
        a, b = c["attrs"]["indices"][0], c["attrs"]["indices"][-1]
        if all(b <= k["attrs"]["indices"][0] or a >= k["attrs"]["indices"][-1] for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: c["attrs"]["indices"][0])


def pivots(
    ohlcv: pl.DataFrame,
    *,
    threshold: float = 0.05,
    mode: str = "percent",
    atr_length: int = 14,
    running: bool = False,
) -> list[tuple[int, str, float, int | None]]:
    """Zigzag pivots (index, "H"|"L", price, confirm index).

    running=True appends the still-unconfirmed extreme after the last pivot with confirm index
    None (it can still move: display only, never use it as a known event).
    """
    _zigzag_params(threshold, mode, atr_length)
    out: list[tuple[int, str, float, int | None]] = list(
        _pivots(ohlcv, threshold, mode, atr_length)
    )
    if running and out:
        last_i, last_kind = out[-1][0], out[-1][1]
        high = ohlcv["high"].to_numpy()
        low = ohlcv["low"].to_numpy()
        if last_i + 1 < len(high):
            if last_kind == "H":
                j = last_i + 1 + int(np.argmin(low[last_i + 1 :]))
                out.append((j, "L", float(low[j]), None))
            else:
                j = last_i + 1 + int(np.argmax(high[last_i + 1 :]))
                out.append((j, "H", float(high[j]), None))
    return out


# Corrective A-B-C after an impulse (linear price). b = B retrace of A, c = C length vs A.
ABC_TARGETS: dict[str, dict[str, tuple[float, ...]]] = {
    "zigzag": {"b_a": (0.5, 0.618, 0.786), "c_a": (1.0, 1.618)},
    "flat": {"b_a": (0.9, 1.0), "c_a": (1.0, 1.236)},
    "expanded_flat": {"b_a": (1.236, 1.382), "c_a": (1.618, 2.618)},
}


def correction_after(
    impulse_indices: Sequence[int], pivot_list: Sequence[tuple[int, str, float, int | None]]
) -> dict[str, Any] | None:
    """The A-B-C following an impulse's P5, or None.

    Works across sub-swings of the zigzag (s = +1 after an up impulse, -1 after a down one):
    - A = first pivot after P5; it must not retrace past the impulse origin P0.
    - B = most extreme counter-pivot (s * price largest) after A, scanned until a pivot passes A's
      end (that is where wave C has broken out).
    - C = most extreme pivot in the move direction after B, scanned until a pivot passes B (the
      correction is then over). Needs at least one pivot after B.
    With fewer than 2 pivots after A the correction is still forming: shape and score are None,
    indices/prices hold A (and B if present), tentative is True.
    Shape by B's retrace of A (b_a): < 0.9 zigzag, 0.9..1.05 flat, 1.05..1.618 expanded flat;
    beyond that it is not a correction of this impulse. C is "tentative" when it is the running
    pivot or has not yet passed A's end. Score = mean Fibonacci closeness of b_a and c_a.
    """
    pos = {p[0]: k for k, p in enumerate(pivot_list)}
    k5 = pos.get(impulse_indices[-1])
    k0 = pos.get(impulse_indices[0])
    if k5 is None or k0 is None or k5 + 1 >= len(pivot_list):
        return None
    p0, p5 = pivot_list[k0][2], pivot_list[k5][2]
    s = 1.0 if p5 > p0 else -1.0
    a_ = pivot_list[k5 + 1]
    a_len = s * (p5 - a_[2])
    if a_len <= 0 or s * (a_[2] - p0) <= 0:
        return None
    rest = pivot_list[k5 + 2 :]
    if len(rest) < 2:
        # Correction still forming: only A (and maybe a B) so far, no shape yet.
        legs = [a_, *rest]
        return {
            "shape": None,
            "direction": "down" if s > 0 else "up",
            "indices": [p[0] for p in legs],
            "prices": [p[2] for p in legs],
            "ratios": {},
            "score": None,
            "tentative": True,
        }
    kb = 0
    for k, p in enumerate(rest):
        if s * (p[2] - a_[2]) < 0:  # passed A's end: wave C under way
            break
        if s * p[2] > s * rest[kb][2]:
            kb = k
    b_ = rest[kb]
    after_b = rest[kb + 1 :]
    if not after_b:
        return None
    c_ = after_b[0]
    for p in after_b:
        if s * p[2] > s * b_[2]:  # passed B: correction over
            break
        if s * p[2] < s * c_[2]:
            c_ = p
    b_a = s * (b_[2] - a_[2]) / a_len
    c_a = s * (b_[2] - c_[2]) / a_len
    if b_a < 0.9:
        shape = "zigzag"
    elif b_a <= 1.05:
        shape = "flat"
    elif b_a <= 1.618:
        shape = "expanded_flat"
    else:
        return None
    t = ABC_TARGETS[shape]
    score = float(np.mean([_closeness(b_a, t["b_a"]), _closeness(c_a, t["c_a"])]))
    return {
        "shape": shape,
        "direction": "down" if s > 0 else "up",
        "indices": [a_[0], b_[0], c_[0]],
        "prices": [a_[2], b_[2], c_[2]],
        "ratios": {"b_a": float(b_a), "c_a": float(c_a)},
        "score": score,
        "tentative": c_[3] is None or s * (c_[2] - a_[2]) > 0,
    }
