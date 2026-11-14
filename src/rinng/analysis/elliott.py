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


def impulse_candidates(
    ohlcv: pl.DataFrame,
    *,
    threshold: float = 0.05,
    mode: str = "percent",
    atr_length: int = 14,
    log: bool = True,
) -> pl.DataFrame:
    """Events kind = impulse_candidate; price_low/high = min/max of the 6 pivots.

    attrs: {"direction": "up"|"down", "indices", "prices", "ratios"} with ratios computed on the
    same scale as the rules (`log`).
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {"kind": "impulse", **_zigzag_params(threshold, mode, atr_length), "log": log}
    piv = _pivots(ohlcv, threshold, mode, atr_length)
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    rows = []
    for k in range(len(piv) - 5):
        window = piv[k : k + 6]
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
                "id": window[0][0],
            }
        )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))
