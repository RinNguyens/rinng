"""5m trade signals, exits and chart analysis for MakeMoney.

Self-contained (numpy only). One strategy definition drives the chart, the backtest
(makemoney_backtest), the live auto-trader and the context sent to Haiku, so what is measured
is what trades. Every value at bar i uses bars <= i only; signals are taken on closed bars and
filled at the next bar's open.

Entry (trend pullback), all on the bar that just closed:
- Trend: close and EMA50 on the same side of EMA200; optionally the 1h close on the same side
  of the 1h EMA50 (`htf`), and ADX(14) >= `adx_min` so we only trade a market that is trending.
- Pullback: within the last 3 bars price came back to EMA21 (within 0.25 ATR).
- Trigger: the bar closes beyond the previous bar's high (long) / low (short), on the trend
  side of EMA21, in the trend direction, with RSI inside `rsi_long` / `rsi_short`, and (if
  `vol_mult` > 0) volume >= `vol_mult` x its 20-bar average.
- Cooldown: one signal per side every `cooldown` bars.

Exit plan, fixed at entry (R = distance from entry to the stop):
- Stop: beyond the 10-bar low/high plus 0.3 ATR, clamped to [`stop_atr_min`, `stop_atr_max`] ATR.
- TP1 at `tp1_r` R closes `tp1_frac` of the position and moves the stop to entry (break-even).
- TP2 at `tp2_r` R closes the rest.
- Time stop: whatever is still open after `max_bars` bars is closed at market.
- If one bar touches both a stop and a target, the stop is assumed to come first.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

SWING = 5  # pivot half-width for swing highs/lows


@dataclass(frozen=True)
class Strategy:
    htf: bool = False
    adx_min: float = 25.0
    vol_mult: float = 0.0
    rsi_long: tuple[float, float] = (45.0, 72.0)
    rsi_short: tuple[float, float] = (28.0, 55.0)
    stop_atr_min: float = 1.5
    stop_atr_max: float = 3.0
    tp1_r: float = 1.0
    tp1_frac: float = 0.5  # 0 = no partial take-profit
    tp2_r: float = 1.5
    max_bars: int = 288  # 24h
    cooldown: int = 6
    mode: str = "reversion"  # "pullback" (trend continuation) or "reversion" (fade a stretch)
    dev_atr: float = 1.5  # reversion: how far beyond EMA50 (in ATR) counts as stretched
    min_stop_pct: float = 0.75  # stop at least this % of price away
    tf: str = "1h"  # bar size the signals run on: 5m, 15m or 1h

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> Strategy:
        if not d:
            return cls()
        f = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        for k in ("rsi_long", "rsi_short"):
            if k in f:
                f[k] = tuple(f[k])
        return cls(**f)

    def describe(self) -> list[str]:
        if self.mode == "reversion":
            out = [
                "Mean reversion: trade back toward the trend after a stretch",
                (
                    "Long only when the 1h trend is up, short only when it is down"
                    if self.htf
                    else "Long above EMA200, short below it"
                ),
                f"Stretch: price reaches {self.dev_atr:g} ATR beyond EMA50",
                "Trigger: a reversal bar (closes back in the trend direction)",
            ]
        else:
            out = [
                "Trend: price and EMA50 on the same side of EMA200"
                + (", 1h trend agrees" if self.htf else ""),
            ]
            out.append(
                "Pullback to EMA21 within the last 3 bars, then a close beyond the prior bar"
            )
            out.append(
                f"RSI long {self.rsi_long[0]:g}–{self.rsi_long[1]:g}, "
                f"short {self.rsi_short[0]:g}–{self.rsi_short[1]:g}"
            )
        if self.adx_min:
            out.append(f"Trend strength: ADX(14) ≥ {self.adx_min:g}")
        if self.vol_mult:
            out.append(f"Volume ≥ {self.vol_mult:g}× its 20-bar average")
        out.append(
            f"Stop beyond the 10-bar swing, {self.stop_atr_min:g}–{self.stop_atr_max:g} ATR away"
            + (f", at least {self.min_stop_pct:g}% of price" if self.min_stop_pct else "")
        )
        if self.tp1_frac:
            out.append(
                f"TP1 at {self.tp1_r:g}R closes {self.tp1_frac:.0%}, stop moves to break-even"
            )
        out.append(f"TP2 at {self.tp2_r:g}R closes the rest")
        out.append(f"Time stop after {self.max_bars * 5 / 60:g}h")
        return out


DEFAULT = Strategy()


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


def adx(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    """Wilder ADX."""
    out = np.full(len(c), np.nan)
    if len(c) < 2 * n + 1:
        return out
    up = np.r_[0, h[1:] - h[:-1]]
    dn = np.r_[0, lo[:-1] - lo[1:]]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - lo, np.maximum(abs(h - pc), abs(lo - pc)))
    atr_, p_, n_ = tr[1 : n + 1].sum(), pdm[1 : n + 1].sum(), ndm[1 : n + 1].sum()
    dx = np.full(len(c), np.nan)
    for i in range(n, len(c)):
        if i > n:
            atr_ = atr_ - atr_ / n + tr[i]
            p_ = p_ - p_ / n + pdm[i]
            n_ = n_ - n_ / n + ndm[i]
        pdi, ndi = 100 * p_ / atr_, 100 * n_ / atr_
        dx[i] = 0 if pdi + ndi == 0 else 100 * abs(pdi - ndi) / (pdi + ndi)
    out[2 * n - 1] = np.nanmean(dx[n : 2 * n])
    for i in range(2 * n, len(c)):
        out[i] = (out[i - 1] * (n - 1) + dx[i]) / n
    return out


def indicators(bars: list[list[float]] | np.ndarray) -> dict:
    """Arrays for every bar. bars: [open_ms, o, h, l, c, v], oldest first."""
    a = np.asarray(bars, dtype=float)
    t = (a[:, 0] // 1000).astype(np.int64)
    o, h, lo, c, v = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    vavg = np.convolve(v, np.ones(20) / 20, mode="full")[: len(v)]
    vavg[:19] = np.nan
    return {
        "t": t,
        "o": o,
        "h": h,
        "l": lo,
        "c": c,
        "v": v,
        "e21": ema(c, 21),
        "e50": ema(c, 50),
        "e200": ema(c, 200),
        "rsi": rsi(c),
        "atr": atr(h, lo, c),
        "adx": adx(h, lo, c),
        "vavg": np.r_[np.nan, vavg[:-1]],  # average of the 20 bars *before* this one
        "h1": _h1_trend(t, c),
    }


def find_signals(ind: dict, p: Strategy, start: int = 210, end: int | None = None) -> list[dict]:
    """Signals on closed bars start..end-1 (end defaults to the last closed bar)."""
    t, o, h, lo, c, v = ind["t"], ind["o"], ind["h"], ind["l"], ind["c"], ind["v"]
    e21, e50, e200 = ind["e21"], ind["e50"], ind["e200"]
    r, at, ax, vavg, h1 = ind["rsi"], ind["atr"], ind["adx"], ind["vavg"], ind["h1"]
    end = len(c) - 1 if end is None else end
    out: list[dict] = []
    last = {"long": -(10**9), "short": -(10**9)}
    for i in range(max(start, 210), end):
        A = at[i]
        if np.isnan(e200[i]) or np.isnan(A) or np.isnan(r[i]):
            continue
        if p.adx_min and not (ax[i] >= p.adx_min):
            continue
        if p.vol_mult and not (v[i] >= p.vol_mult * vavg[i]):
            continue
        for side in ("long", "short"):
            if i - last[side] < p.cooldown:
                continue
            if p.mode == "reversion":
                # stretched away from EMA50 against a higher-timeframe trend, then a reversal bar
                if side == "long":
                    ok = (
                        (h1[i] > 0 if p.htf else c[i] > e200[i])
                        and lo[i] <= e50[i] - p.dev_atr * A
                        and c[i] > o[i]
                        and c[i] > c[i - 1]
                        and r[i] <= p.rsi_long[1]
                    )
                else:
                    ok = (
                        (h1[i] < 0 if p.htf else c[i] < e200[i])
                        and h[i] >= e50[i] + p.dev_atr * A
                        and c[i] < o[i]
                        and c[i] < c[i - 1]
                        and r[i] >= p.rsi_short[0]
                    )
            elif side == "long":
                ok = (
                    c[i] > e200[i]
                    and e50[i] > e200[i]
                    and (h1[i] > 0 or not p.htf)
                    and (lo[i - 3 : i + 1] <= e21[i - 3 : i + 1] + 0.25 * A).any()
                    and c[i] > h[i - 1]
                    and c[i] > e21[i]
                    and c[i] > o[i]
                    and p.rsi_long[0] <= r[i] <= p.rsi_long[1]
                )
            else:
                ok = (
                    c[i] < e200[i]
                    and e50[i] < e200[i]
                    and (h1[i] < 0 or not p.htf)
                    and (h[i - 3 : i + 1] >= e21[i - 3 : i + 1] - 0.25 * A).any()
                    and c[i] < lo[i - 1]
                    and c[i] < e21[i]
                    and c[i] < o[i]
                    and p.rsi_short[0] <= r[i] <= p.rsi_short[1]
                )
            if not ok:
                continue
            ref = c[i]
            if side == "long":
                raw = ref - (lo[i - 9 : i + 1].min() - 0.3 * A)
            else:
                raw = (h[i - 9 : i + 1].max() + 0.3 * A) - ref
            dist = min(max(raw, p.stop_atr_min * A), p.stop_atr_max * A)
            dist = max(dist, ref * p.min_stop_pct / 100)  # keep costs a small share of R
            sgn = 1 if side == "long" else -1
            out.append(
                {
                    "i": i,
                    "time": int(t[i]),
                    "side": side,
                    "entry": float(ref),
                    "risk": float(dist),
                    "stop": float(ref - sgn * dist),
                    "tp1": float(ref + sgn * p.tp1_r * dist) if p.tp1_frac else None,
                    "take": float(ref + sgn * p.tp2_r * dist),
                    "rsi": float(r[i]),
                    "adx": None if np.isnan(ax[i]) else float(ax[i]),
                    "atr": float(A),
                }
            )
            last[side] = i
    return out


def exit_step(
    st: dict, o: float, h: float, lo: float, c: float, held: int, p: Strategy, first: bool
) -> list[tuple[float, float, str]]:
    """One bar of the exit plan for an open trade. `st` holds side, entry, stop, tp1, take,
    left (fraction still open) and be (stop moved to break-even); it is updated in place.
    `held` counts bars including this one; `first` is the fill bar (entered at its open).
    Returns trigger-price fills [(price, fraction of the original size, reason)]; slippage
    and fees are added by the caller. Shared by the backtest, the chart and live trading."""
    long = st["side"] == "long"
    out: list[tuple[float, float, str]] = []
    if (lo <= st["stop"]) if long else (h >= st["stop"]):
        gap = ((o <= st["stop"]) if long else (o >= st["stop"])) and not first
        out.append((o if gap else st["stop"], st["left"], "breakeven" if st["be"] else "stop"))
        st["left"] = 0.0
        return out
    if (
        st.get("tp1") is not None
        and not st["be"]
        and ((h >= st["tp1"]) if long else (lo <= st["tp1"]))
    ):
        frac = min(p.tp1_frac, st["left"])
        out.append((st["tp1"], frac, "tp1"))
        st["left"] -= frac
        st["stop"], st["be"] = st["entry"], True
        # the same bar may also reach TP2; the moved stop is not checked again on this bar
    if (h >= st["take"]) if long else (lo <= st["take"]):
        gap = ((o >= st["take"]) if long else (o <= st["take"])) and not first
        out.append((o if gap else st["take"], st["left"], "tp2"))
        st["left"] = 0.0
        return out
    if held >= p.max_bars:
        out.append((c, st["left"], "time"))
        st["left"] = 0.0
    return out


def walk_exit(ind: dict, sig: dict, p: Strategy, entry: float, j0: int) -> dict:
    """Run exit_step from bar j0 (the fill bar) over the closed bars.
    Returns {"fills": [(bar, price, fraction, why)], "done": bool}."""
    h, lo, o, c = ind["h"], ind["l"], ind["o"], ind["c"]
    st = {
        "side": sig["side"],
        "entry": entry,
        "stop": sig["stop"],
        "tp1": sig["tp1"],
        "take": sig["take"],
        "left": 1.0,
        "be": False,
    }
    fills = []
    for j in range(j0, len(c) - 1):  # the forming bar is not used
        for px, frac, why in exit_step(st, o[j], h[j], lo[j], c[j], j - j0 + 1, p, j == j0):
            fills.append((j, px, frac, why))
        if st["left"] <= 1e-12:
            return {"fills": fills, "done": True}
    return {"fills": fills, "done": False}


def r_multiple(sig: dict, ex: dict, entry: float) -> float:
    sgn = 1 if sig["side"] == "long" else -1
    return sum(sgn * (px - entry) / sig["risk"] * frac for _, px, frac, _ in ex["fills"])


def analyse(bars: list[list[float]], p: Strategy = DEFAULT) -> dict:
    """bars: [open_ms, o, h, l, c, v] oldest first, the last one may still be forming."""
    ind = indicators(bars)
    t, o, h, lo, c, v = ind["t"], ind["o"], ind["h"], ind["l"], ind["c"], ind["v"]
    vw = daily_vwap(t, h, lo, c, v)
    piv = swings(h, lo)
    events = structure(c, piv)

    signals = find_signals(ind, p)
    for s in signals:
        j0 = s["i"] + 1
        entry = float(o[j0]) if j0 < len(c) else s["entry"]
        ex = walk_exit(ind, s, p, entry, j0)
        s["reasons"] = _reasons(s, p)
        if ex["done"]:
            rr = r_multiple(s, ex, entry)
            s["outcome"] = "win" if rr > 0.05 else ("loss" if rr < -0.05 else "flat")
            s["r"] = round(rr, 2)
            s["outcome_time"] = int(t[ex["fills"][-1][0]])
            s["exit_reason"] = ex["fills"][-1][3]
        else:
            s["outcome"], s["r"], s["outcome_time"], s["exit_reason"] = "open", None, None, None
        s["close_time"] = s["time"] + 300

    k = max(len(c) - 2, 0)  # last closed bar
    bias = "neutral"
    if not np.isnan(ind["e200"][k]):
        e50, e200, h1 = ind["e50"][k], ind["e200"][k], ind["h1"][k]
        if c[k] > e200 and e50 > e200:
            bias = "bullish" if h1 > 0 else "bullish (1h against)"
        elif c[k] < e200 and e50 < e200:
            bias = "bearish" if h1 < 0 else "bearish (1h against)"
    price = float(c[-1])
    highs = sorted({pp for _, kind, pp in piv[-40:] if kind == "H" and pp > price})
    lows = sorted({pp for _, kind, pp in piv[-40:] if kind == "L" and pp < price}, reverse=True)
    done = [s for s in signals if s["outcome"] != "open"]
    wins = sum(s["outcome"] == "win" for s in done)
    rs = [s["r"] for s in done]

    def ser(x: np.ndarray) -> list[dict]:
        return [
            {"time": int(t[i]), "value": round(float(x[i]), 8)}
            for i in range(len(x))
            if not np.isnan(x[i])
        ]

    def val(x) -> float | None:
        return None if np.isnan(x) else float(x)

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
        "ema21": ser(ind["e21"]),
        "ema50": ser(ind["e50"]),
        "ema200": ser(ind["e200"]),
        "vwap": ser(vw),
        "rsi": ser(ind["rsi"]),
        "swings": [{"time": int(t[i]), "kind": k2, "price": pp} for i, k2, pp in piv],
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
        "strategy": p.to_dict() | {"rules": p.describe()},
        "tf_sec": int(t[1] - t[0]) if len(t) > 1 else 300,
        "summary": {
            "price": price,
            "bias": bias,
            "rsi": val(ind["rsi"][k]),
            "adx": val(ind["adx"][k]),
            "atr": val(ind["atr"][k]),
            "atr_pct": None if np.isnan(ind["atr"][k]) else float(ind["atr"][k] / c[k] * 100),
            "ema21": float(ind["e21"][k]),
            "ema50": float(ind["e50"][k]),
            "ema200": val(ind["e200"][k]),
            "vwap": float(vw[k]),
            "h1_trend": int(ind["h1"][k]),
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
                "losses": sum(s["outcome"] == "loss" for s in done),
                "hit_rate": wins / len(done) * 100 if done else None,
                "avg_r": sum(rs) / len(rs) if rs else None,
                "total_r": sum(rs) if rs else None,
            },
        },
    }


def _reasons(s: dict, p: Strategy) -> list[str]:
    long = s["side"] == "long"
    out = [
        f"{'Up' if long else 'Down'}trend: price {'above' if long else 'below'} EMA200, "
        f"EMA50 {'>' if long else '<'} EMA200" + (", 1h agrees" if p.htf else ""),
        "Pullback to EMA21, close " + ("above previous high" if long else "below previous low"),
        f"RSI {s['rsi']:.0f}" + (f", ADX {s['adx']:.0f}" if s.get("adx") is not None else ""),
        f"Stop {s['risk'] / s['atr']:.1f} ATR"
        + (f", TP1 {p.tp1_r:g}R ({p.tp1_frac:.0%}) → BE" if p.tp1_frac else "")
        + f", TP2 {p.tp2_r:g}R",
    ]
    return out
