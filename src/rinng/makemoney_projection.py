"""Projection for an open MakeMoney order.

Uses the analog forecast of rinng.analysis.forecast (past moments that looked like now, their
following paths in units of volatility) and replays each path against the order's own levels:
which comes first, the take-profit or the stop, within the time the order has left. The result
is a probability split, the expected value in $ and a quantile cone of where price may be.
Short-term crypto is close to random: the numbers are a distribution, not a promise.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from rinng.analysis import forecast as fc


def project(bars: list[list[float]], pos: dict | None, horizon: int, fee: float) -> dict | None:
    """bars: closed [open_ms, o, h, l, c, v] of the strategy timeframe, oldest first.
    pos: an open position dict (side, entry, stop, take, tp1, be, qty, mark).
    horizon: bars left before the time stop (capped by the caller)."""
    if len(bars) < fc.WARMUP + fc.MIN_POOL + horizon + 5:
        return None
    a = np.asarray(bars, dtype=float)
    df = pl.DataFrame({"high": a[:, 2], "low": a[:, 3], "close": a[:, 4], "volume": a[:, 5]})
    p = fc.prepare(df)
    origin = len(a) - 1
    pool = np.arange(fc.WARMUP, origin - horizon + 1)
    pool = pool[~np.isnan(p.features[pool]).any(axis=1)]
    if len(pool) < fc.MIN_POOL or np.isnan(p.features[origin]).any():
        return None
    k = int(np.clip(len(pool) // 15, 100, 600))
    w, near = fc.analog_weights(p, origin, pool, k, 0.7)
    z, up, down = fc._paths(p, pool, horizon)
    s, c = p.sigma[origin], p.close[origin]
    w = w / w.sum()
    t0 = int(a[-1, 0] // 1000)
    step = int((a[-1, 0] - a[-2, 0]) // 1000)

    def cone_of() -> dict:
        zq = fc._wquantile(z, w, fc.QUANTILES)
        cq = c * np.exp(zq * s)
        return {
            str(q_): [
                {"time": t0 + step * (j + 1), "value": round(float(cq[i, j]), 8)}
                for j in range(horizon)
            ]
            for i, q_ in enumerate(fc.QUANTILES)
        }

    if pos is None:  # no order: only where price may go
        return {
            "horizon_bars": horizon,
            "bar_sec": step,
            "price": float(c),
            "cone": cone_of(),
            "analogs": int(len(near)),
            "pool": int(len(pool)),
        }

    long = pos["side"] == "long"

    def zlev(x: float) -> float:
        return float(np.log(x / c) / s)

    z_tp, z_sl = zlev(pos["take"]), zlev(pos["stop"])
    if long:
        hit_tp = up >= z_tp
        hit_sl = down <= z_sl
    else:
        hit_tp = down <= z_tp
        hit_sl = up >= z_sl
    big = horizon + 1
    t_tp = np.where(hit_tp.any(axis=1), hit_tp.argmax(axis=1), big)
    t_sl = np.where(hit_sl.any(axis=1), hit_sl.argmax(axis=1), big)
    # same bar: assume the stop first, as the simulator does
    tp_first = t_tp < t_sl
    sl_first = (t_sl <= t_tp) & (t_sl < big)
    neither = ~tp_first & ~sl_first
    p_tp, p_sl, p_none = (float(np.sum(w * m)) for m in (tp_first, sl_first, neither))
    p_tp1 = None
    if pos.get("tp1") and not pos.get("be"):
        z1 = zlev(pos["tp1"])
        h1 = (up >= z1) if long else (down <= z1)
        t1 = np.where(h1.any(axis=1), h1.argmax(axis=1), big)
        p_tp1 = float(np.sum(w * (t1 < t_sl)))

    # $ outcome per path (exit fee included): TP, SL, or still open at the horizon
    sgn = 1 if long else -1
    q, entry = pos["qty"], pos["entry"]
    end_px = c * np.exp(z[:, -1] * s)
    pnl_tp = sgn * (pos["take"] - entry) * q - pos["take"] * q * fee
    pnl_sl = sgn * (pos["stop"] - entry) * q - pos["stop"] * q * fee
    pnl_end = sgn * (end_px - entry) * q - end_px * q * fee
    pnl = np.where(tp_first, pnl_tp, np.where(sl_first, pnl_sl, pnl_end))
    ev = float(np.sum(w * pnl))

    cone = cone_of()
    return {
        "horizon_bars": horizon,
        "bar_sec": step,
        "price": float(c),
        "p_tp_first": p_tp,
        "p_sl_first": p_sl,
        "p_neither": p_none,
        "p_tp1_before_sl": p_tp1,
        "ev_usd": ev,
        "pnl_if_tp": float(pnl_tp),
        "pnl_if_sl": float(pnl_sl),
        "median_end": cone["0.5"][-1]["value"],
        "cone": cone,
        "analogs": int(len(near)),
        "pool": int(len(pool)),
    }
