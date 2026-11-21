"""5m trade signals and chart analysis for MakeMoney.

Self-contained (numpy only) so the same logic drives the chart, the auto-trader and the
context sent to Haiku. Every value at bar i uses bars <= i only; signals are only taken on
closed bars.

Signal (trend pullback):
- Trend: 5m close and EMA50 on the same side of EMA200, and 1h close on the same side of the
  1h EMA50 (1h bars resampled from the 5m ones).
- Pullback: within the last 3 bars price traded back to EMA21 (within 0.25 ATR).
- Trigger: the closed bar resumes the trend: closes beyond the previous bar's high (long) or
  low (short) and on the trend side of EMA21, with RSI between 45 and 72 (long) or between 28
  and 55 (short), so we neither buy exhaustion nor chase it.
- Stop: beyond the lowest low / highest high of the last 10 bars plus 0.3 ATR, kept between
  1 and 3 ATR from entry. Take-profit at 2R.
- Cooldown: at most one signal per side every 6 bars.
"""

from __future__ import annotations

import numpy as np

RR = 2.0
SWING = 5  # pivot half-width for swing highs/lows


def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    a = 2 / (n + 1)
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def rsi(x: np.ndarray, n: int = 14) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    d = np.diff(x)
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    au, ad = up[:n].mean(), dn[:n].mean()
    for i in range(n, len(x)):
        if i > n:
            au = (au * (n - 1) + up[i - 1]) / n
            ad = (ad * (n - 1) + dn[i - 1]) / n
        out[i] = 100 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


def atr(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    tr = np.maximum(h - lo, np.maximum(abs(h - np.r_[c[0], c[:-1]]), abs(lo - np.r_[c[0], c[:-1]])))
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return out
    out[n] = tr[1 : n + 1].mean()
    for i in range(n + 1, len(c)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def daily_vwap(t: np.ndarray, h, lo, c, v) -> np.ndarray:
    tp = (h + lo + c) / 3
    day = t // 86400
    out = np.empty(len(c))
    pv = vv = 0.0
    for i in range(len(c)):
        if i and day[i] != day[i - 1]:
            pv = vv = 0.0
        pv += tp[i] * v[i]
        vv += v[i]
        out[i] = pv / vv if vv else c[i]
    return out


def _h1_trend(t: np.ndarray, c: np.ndarray) -> np.ndarray:
    """+1/-1/0 per 5m bar: last *closed* 1h close vs the 1h EMA50."""
    hour = t // 3600
    idx = np.flatnonzero(np.r_[hour[1:] != hour[:-1], True])  # last 5m bar of each hour
    h_close = c[idx]
    h_ema = ema(h_close, 50)
    sign = np.sign(h_close - h_ema)
    out = np.zeros(len(c))
    j = -1
    for i in range(len(c)):
        while j + 1 < len(idx) and idx[j + 1] < i:  # hour fully closed before bar i
            j += 1
        if j >= 0 and not np.isnan(h_ema[j]):
            out[i] = sign[j]
    return out


def swings(h: np.ndarray, lo: np.ndarray, n: int = SWING) -> list[tuple[int, str, float]]:
    """Confirmed pivots as (bar index, "H"/"L", price); a pivot is known n bars later."""
    out = []
    for i in range(n, len(h) - n):
        if h[i] == h[i - n : i + n + 1].max():
            out.append((i, "H", float(h[i])))
        if lo[i] == lo[i - n : i + n + 1].min():
            out.append((i, "L", float(lo[i])))
    return out


def structure(c: np.ndarray, piv: list[tuple[int, str, float]]) -> list[dict]:
    """BOS (break with the trend) / CHoCH (first break against it) on closes."""
    events: list[dict] = []
    trend = 0
    last_h = last_l = None
    p = 0
    for i in range(len(c)):
        while p < len(piv) and piv[p][0] + SWING <= i:  # pivot confirmed
            if piv[p][1] == "H":
                last_h = piv[p]
            else:
                last_l = piv[p]
            p += 1
        if last_h and c[i] > last_h[2]:
            events.append(
                {
                    "i": i,
                    "from": last_h[0],
                    "price": last_h[2],
                    "dir": "up",
                    "kind": "BOS" if trend >= 0 else "CHoCH",
                }
            )
            trend, last_h = 1, None
        elif last_l and c[i] < last_l[2]:
            events.append(
                {
                    "i": i,
                    "from": last_l[0],
                    "price": last_l[2],
                    "dir": "down",
                    "kind": "BOS" if trend <= 0 else "CHoCH",
                }
            )
            trend, last_l = -1, None
    return events


def analyse(bars: list[list[float]]) -> dict:
    """bars: [open_ms, o, h, l, c, v] oldest first, the last one may still be forming."""
    a = np.asarray(bars, dtype=float)
    t = (a[:, 0] // 1000).astype(np.int64)
    o, h, lo, c, v = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    e21, e50, e200 = ema(c, 21), ema(c, 50), ema(c, 200)
    r = rsi(c)
    at = atr(h, lo, c)
    vw = daily_vwap(t, h, lo, c, v)
    h1 = _h1_trend(t, c)
    piv = swings(h, lo)
    events = structure(c, piv)

    closed = len(c) - 1  # the last bar is still forming
    signals: list[dict] = []
    last_sig = {"long": -99, "short": -99}
    for i in range(210, closed):
        if np.isnan(e200[i]) or np.isnan(at[i]) or np.isnan(r[i]):
            continue
        A = at[i]
        for side in ("long", "short"):
            if i - last_sig[side] < 6:
                continue
            if side == "long":
                trend = c[i] > e200[i] and e50[i] > e200[i] and h1[i] > 0
                pull = (lo[i - 3 : i + 1] <= e21[i - 3 : i + 1] + 0.25 * A).any()
                trig = c[i] > h[i - 1] and c[i] > e21[i] and c[i] > o[i] and 45 <= r[i] <= 72
            else:
                trend = c[i] < e200[i] and e50[i] < e200[i] and h1[i] < 0
                pull = (h[i - 3 : i + 1] >= e21[i - 3 : i + 1] - 0.25 * A).any()
                trig = c[i] < lo[i - 1] and c[i] < e21[i] and c[i] < o[i] and 28 <= r[i] <= 55
            if not (trend and pull and trig):
                continue
            entry = c[i]
            if side == "long":
                stop = lo[i - 9 : i + 1].min() - 0.3 * A
                dist = min(max(entry - stop, A), 3 * A)
                stop, take = entry - dist, entry + RR * dist
            else:
                stop = h[i - 9 : i + 1].max() + 0.3 * A
                dist = min(max(stop - entry, A), 3 * A)
                stop, take = entry + dist, entry - RR * dist
            reasons = [
                f"{'Up' if side == 'long' else 'Down'}trend: price "
                f"{'above' if side == 'long' else 'below'} EMA200, EMA50 "
                f"{'>' if side == 'long' else '<'} EMA200, 1h trend agrees",
                "Pullback to EMA21",
                "Trigger: close "
                + ("above previous high" if side == "long" else "below previous low"),
                f"RSI {r[i]:.0f}",
                f"Stop {dist / A:.1f} ATR, target {RR:.0f}R",
            ]
            # outcome on the bars after the signal (stop wins if a bar touches both)
            outcome, out_i = "open", None
            for j in range(i + 1, closed + 1):
                hit_s = lo[j] <= stop if side == "long" else h[j] >= stop
                hit_t = h[j] >= take if side == "long" else lo[j] <= take
                if hit_s or hit_t:
                    outcome, out_i = ("loss" if hit_s else "win"), j
                    break
            signals.append(
                {
                    "time": int(t[i]),
                    "close_time": int(t[i]) + 300,
                    "side": side,
                    "entry": float(entry),
                    "stop": float(stop),
                    "take": float(take),
                    "rsi": float(r[i]),
                    "atr": float(A),
                    "reasons": reasons,
                    "outcome": outcome,
                    "outcome_time": int(t[out_i]) if out_i is not None else None,
                }
            )
            last_sig[side] = i

    # current read of the market
    k = closed - 1 if closed > 0 else 0
    bias = "neutral"
    if not np.isnan(e200[k]):
        if c[k] > e200[k] and e50[k] > e200[k]:
            bias = "bullish" if h1[k] > 0 else "bullish (1h against)"
        elif c[k] < e200[k] and e50[k] < e200[k]:
            bias = "bearish" if h1[k] < 0 else "bearish (1h against)"
    price = float(c[-1])
    highs = sorted({p for _, kind, p in piv[-40:] if kind == "H" and p > price})
    lows = sorted({p for _, kind, p in piv[-40:] if kind == "L" and p < price}, reverse=True)
    done = [s for s in signals if s["outcome"] != "open"]
    wins = sum(s["outcome"] == "win" for s in done)

    def ser(x: np.ndarray) -> list[dict]:
        return [
            {"time": int(t[i]), "value": round(float(x[i]), 8)}
            for i in range(len(x))
            if not np.isnan(x[i])
        ]

    return {
        "candles": [
            {
                "time": int(t[i]),
                "open": o[i],
                "high": h[i],
                "low": lo[i],
                "close": c[i],
                "volume": v[i],
            }
            for i in range(len(c))
        ],
        "ema21": ser(e21),
        "ema50": ser(e50),
        "ema200": ser(e200),
        "vwap": ser(vw),
        "rsi": ser(r),
        "swings": [{"time": int(t[i]), "kind": k2, "price": p} for i, k2, p in piv],
        "structure": [
            {
                "time": int(t[e["i"]]),
                "from": int(t[e["from"]]),
                "price": e["price"],
                "dir": e["dir"],
                "kind": e["kind"],
            }
            for e in events
        ],
        "resistance": highs[:3],
        "support": lows[:3],
        "signals": signals,
        "summary": {
            "price": price,
            "bias": bias,
            "rsi": float(r[k]) if not np.isnan(r[k]) else None,
            "atr": float(at[k]) if not np.isnan(at[k]) else None,
            "atr_pct": float(at[k] / c[k] * 100) if not np.isnan(at[k]) else None,
            "ema21": float(e21[k]),
            "ema50": float(e50[k]),
            "ema200": float(e200[k]) if not np.isnan(e200[k]) else None,
            "vwap": float(vw[k]),
            "h1_trend": int(h1[k]),
            "last_structure": (
                {
                    "kind": events[-1]["kind"],
                    "dir": events[-1]["dir"],
                    "price": events[-1]["price"],
                    "time": int(t[events[-1]["i"]]),
                }
                if events
                else None
            ),
            "last_signal": signals[-1] if signals else None,
            "signal_stats": {
                "count": len(signals),
                "wins": wins,
                "losses": len(done) - wins,
                "hit_rate": wins / len(done) * 100 if done else None,
            },
        },
    }
