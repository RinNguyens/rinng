"""Realistic portfolio backtest of the MakeMoney 5m strategy on a USDT-M account.

Accounting mirrors the live simulator (makemoney.MakeMoney):
- one shared account (default $1000) across all symbols, one position per symbol, at most
  `max_positions` open; signals are taken in time order while there is room;
- entry at the open of the bar after the signal, plus slippage, taker fee;
- size = equity x risk% / (stop distance + stop slippage + entry and exit fees), floored to the
  symbol's stepSize, capped by free margin at the chosen leverage, minQty / minNotional enforced;
- exits from makemoney_signals.exit_step (TP1 + break-even, TP2, stop, time stop), stops and
  time exits fill with slippage, every exit pays the taker fee;
- funding: real Binance funding-rate history, charged at each funding time on open size;
- equity is marked to each 5m close for the drawdown.
Known simplifications: no order-book depth, no liquidation (the stop must sit before the
liquidation price at entry, as live), and within one bar the stop is assumed to come first.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from rinng.makemoney_signals import Strategy, exit_step, find_signals, indicators

if TYPE_CHECKING:
    from rinng.makemoney import Binance

BAR_MS = 300_000
WARM_BARS = 2700  # 5m bars of warm-up (~9.4 days): enough for EMA200 on 1h bars
_IND: dict[tuple, dict] = {}  # indicators per (symbol, bar count, last bar)


@dataclass
class Account:
    balance: float = 1000.0
    risk_pct: float = 1.0
    leverage: int = 5
    max_positions: int = 2
    taker_fee: float = 0.0005
    slippage: float = 0.0002


# ---------------------------------------------------------------- data


async def history(bn: Binance, sym: str, days: int, cache: Path) -> dict:
    """5m bars and funding for the last `days`, cached on disk and topped up incrementally."""
    from rinng.makemoney import venue_symbol

    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{venue_symbol(sym)}_5m.json"
    data = json.loads(f.read_text()) if f.exists() else {"bars": [], "funding": []}
    now = int(time.time() * 1000)
    start = now - days * 86_400_000
    bars = [b for b in data["bars"] if b[0] >= start - (WARM_BARS + 50) * BAR_MS]
    have_from = bars[0][0] if bars else now
    if have_from > start - WARM_BARS * BAR_MS:  # need older history: refetch the whole window
        bars = []
    cursor = int(bars[-1][0]) + BAR_MS if bars else start - WARM_BARS * BAR_MS
    while cursor < now - BAR_MS:
        raw = await bn.get(
            "/fapi/v1/klines",
            symbol=venue_symbol(sym),
            interval="5m",
            startTime=cursor,
            limit=1500,
        )
        if not raw:
            break
        bars.extend([float(x) for x in b[:6]] for b in raw)
        cursor = int(raw[-1][0]) + BAR_MS
        await asyncio.sleep(0.15)  # stay well under the public rate limit
    # drop the still-forming bar
    bars = [b for b in bars if b[0] + BAR_MS <= now]
    fund = [x for x in data["funding"] if x[0] >= start]
    fcur = fund[-1][0] + 1 if fund else start
    while True:
        raw = await bn.get(
            "/fapi/v1/fundingRate", symbol=venue_symbol(sym), startTime=fcur, limit=1000
        )
        if not raw:
            break
        fund.extend([int(x["fundingTime"]), float(x["fundingRate"])] for x in raw)
        if len(raw) < 1000:
            break
        fcur = int(raw[-1]["fundingTime"]) + 1
    f.write_text(json.dumps({"bars": bars, "funding": fund}))
    return {"bars": bars, "funding": fund, "start_ms": start}


# ---------------------------------------------------------------- simulation


def resample(bars: list[list[float]], minutes: int) -> list[list[float]]:
    """5m [open_ms, o, h, l, c, v] -> `minutes` bars (only complete ones)."""
    if minutes == 5:
        return bars
    ms = minutes * 60_000
    need = minutes // 5
    out: list[list[float]] = []
    cur: list[float] | None = None
    n = 0
    for b in bars:
        k = b[0] - b[0] % ms
        if cur is None or k != cur[0]:
            if cur is not None and n == need:
                out.append(cur)
            cur, n = [k, b[1], b[2], b[3], b[4], b[5]], 1
        else:
            cur[2] = max(cur[2], b[2])
            cur[3] = min(cur[3], b[3])
            cur[4] = b[4]
            cur[5] += b[5]
            n += 1
    if cur is not None and n == need:
        out.append(cur)
    return out


TF_MIN = {"5m": 5, "15m": 15, "1h": 60}


def run(
    data: dict[str, dict],
    filters: dict[str, dict],
    p: Strategy,
    acct: Account,
    t_from: int | None = None,
    t_to: int | None = None,
) -> dict:
    """data: {symbol: {"bars", "funding"}}; filters: {symbol: {"step", "min_qty",
    "min_notional"}}. Only signals with t_from <= signal time < t_to (ms) are traded."""
    tfm = TF_MIN[p.tf]
    bar_ms = tfm * 60_000
    # time stop and cooldown are defined on 5m bars; keep the same hours on other frames
    p = replace(p, max_bars=max(1, math.ceil(p.max_bars * 5 / tfm)))
    per = {}
    for sym, d in data.items():
        key = (sym, p.tf, len(d["bars"]), d["bars"][-1][0] if d["bars"] else 0)
        ind = _IND.get(key)
        if ind is None:
            ind = _IND[key] = indicators(resample(d["bars"], tfm))
        t_ms = ind["t"] * 1000
        lo_i = int(np.searchsorted(t_ms, t_from)) if t_from else 0
        hi_i = int(np.searchsorted(t_ms, t_to)) if t_to else len(t_ms) - 1
        sigs = find_signals(ind, p, start=max(lo_i, 210), end=min(hi_i, len(t_ms) - 1))
        per[sym] = {
            "ind": ind,
            "t": t_ms,
            "by_fill": {int(t_ms[s["i"] + 1]): s for s in sigs if s["i"] + 1 < len(t_ms)},
            "fund": {int(ft - ft % bar_ms): r for ft, r in d["funding"]},
            "idx": {int(x): k for k, x in enumerate(t_ms)},
        }
    grid = sorted({int(x) for v in per.values() for x in v["t"]})
    if t_from:
        grid = [x for x in grid if x >= t_from]
    bal = acct.balance
    pos: dict[str, dict] = {}
    trades: list[dict] = []
    curve: list[tuple[int, float]] = []
    peak, max_dd = bal, 0.0
    fees_total = funding_total = 0.0
    skipped = {"max_positions": 0, "busy": 0, "too_small": 0}
    slip, fee = acct.slippage, acct.taker_fee

    def equity(marks: dict[str, float]) -> float:
        e = bal
        for s, q in pos.items():
            sgn = 1 if q["side"] == "long" else -1
            e += q["margin"] + sgn * (marks.get(s, q["entry"]) - q["entry"]) * q["qty"]
        return e

    for ts in grid:
        marks: dict[str, float] = {}
        for sym, v in per.items():
            k = v["idx"].get(ts)
            if k is None:
                continue
            ind = v["ind"]
            o, h, lo, c = ind["o"][k], ind["h"][k], ind["l"][k], ind["c"][k]
            marks[sym] = c
            # --- entry at this bar's open
            sig = v["by_fill"].get(ts)
            if sig is not None:
                if sym in pos:
                    skipped["busy"] += 1
                elif len(pos) >= acct.max_positions:
                    skipped["max_positions"] += 1
                else:
                    long = sig["side"] == "long"
                    fill = o * (1 + slip) if long else o * (1 - slip)
                    eq = equity(marks)
                    risk = eq * acct.risk_pct / 100
                    stop = sig["stop"]
                    per_unit = abs(fill - stop) + stop * slip + (fill + stop) * fee
                    ok_side = (stop < fill) if long else (stop > fill)
                    f = filters.get(sym, {"step": 0.0, "min_qty": 0.0, "min_notional": 5.0})
                    qty = risk / per_unit if ok_side else 0.0
                    qty = min(qty, bal / (fill / acct.leverage + fill * fee))
                    if f["step"]:
                        qty = math.floor(qty / f["step"] + 1e-9) * f["step"]
                    if qty <= 0 or qty < f["min_qty"] or qty * fill < f["min_notional"]:
                        skipped["too_small"] += 1
                    else:
                        margin = qty * fill / acct.leverage
                        ofee = qty * fill * fee
                        bal -= margin + ofee
                        fees_total += ofee
                        pos[sym] = {
                            "symbol": sym,
                            "side": sig["side"],
                            "qty": qty,
                            "qty0": qty,
                            "entry": fill,
                            "margin": margin,
                            "margin0": margin,
                            "opened": ts,
                            "fees": ofee,
                            "funding": 0.0,
                            "realized": 0.0,
                            "risk_usd": qty * abs(fill - stop),
                            "held": 0,
                            "st": {
                                "side": sig["side"],
                                "entry": fill,
                                "stop": stop,
                                "tp1": sig["tp1"],
                                "take": sig["take"],
                                "left": 1.0,
                                "be": False,
                            },
                            "exits": [],
                        }
            q = pos.get(sym)
            if q is None:
                continue
            # --- funding settled during this bar
            rate = v["fund"].get(ts)
            if rate is not None:
                sgn = 1 if q["side"] == "long" else -1
                amt = -sgn * q["qty"] * o * rate
                q["margin"] += amt
                q["funding"] += amt
                funding_total += amt
            # --- exits
            q["held"] += 1
            for px, frac, why in exit_step(q["st"], o, h, lo, c, q["held"], p, ts == q["opened"]):
                long = q["side"] == "long"
                # every exit is a market order (stop-market / take-profit-market): slippage
                px = px * (1 - slip) if long else px * (1 + slip)
                qx = q["qty0"] * frac
                sgn = 1 if long else -1
                pnl = sgn * (px - q["entry"]) * qx
                xfee = px * qx * fee
                mfree = q["margin"] * (qx / q["qty"]) if q["qty"] else 0.0
                bal += mfree + pnl - xfee
                q["margin"] -= mfree
                q["qty"] -= qx
                q["fees"] += xfee
                q["realized"] += pnl
                fees_total += xfee
                q["exits"].append({"t": ts, "price": px, "frac": frac, "why": why})
            if q["st"]["left"] <= 1e-12:
                bal += q["margin"]  # what is left of margin (funding adjustments)
                net = q["realized"] - q["fees"] + q["funding"]
                trades.append(
                    {
                        "symbol": sym,
                        "side": q["side"],
                        "opened": q["opened"] // 1000,
                        "closed": (ts + bar_ms) // 1000,
                        "entry": q["entry"],
                        "exit": q["exits"][-1]["price"],
                        "qty": q["qty0"],
                        "gross": q["realized"],
                        "fees": q["fees"],
                        "funding": q["funding"],
                        "pnl": net,
                        "r": net / q["risk_usd"] if q["risk_usd"] else 0.0,
                        "exit_reason": q["exits"][-1]["why"],
                        "tp1": any(e["why"] == "tp1" for e in q["exits"]),
                        "bars": q["held"],
                    }
                )
                del pos[sym]
        e = equity(marks)
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak * 100 if peak else 0)
        if not curve or ts - curve[-1][0] >= 3_600_000:
            curve.append((ts // 1000, round(e, 2)))
    end_eq = equity({s: per[s]["ind"]["c"][-1] for s in pos})
    if curve:
        curve.append((grid[-1] // 1000, round(end_eq, 2)))
    return metrics(
        trades,
        curve,
        acct,
        end_eq,
        max_dd,
        fees_total,
        funding_total,
        skipped,
        open_positions=len(pos),
    )


def metrics(trades, curve, acct, end_eq, max_dd, fees, funding, skipped, open_positions) -> dict:
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gw = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in losses)
    streak = worst = 0
    for t in trades:
        streak = streak + 1 if t["pnl"] <= 0 else 0
        worst = max(worst, streak)
    by = {}
    for key in ("symbol", "side", "exit_reason"):
        groups: dict[str, list] = {}
        for t in trades:
            groups.setdefault(t[key], []).append(t)
        by[key] = {
            k: {
                "trades": len(v),
                "win_rate": sum(x["pnl"] > 0 for x in v) / len(v) * 100,
                "pnl": sum(x["pnl"] for x in v),
            }
            for k, v in groups.items()
        }
    days = (curve[-1][0] - curve[0][0]) / 86400 if len(curve) > 1 else 0
    daily = []
    if len(curve) > 2:
        eq = np.array([c[1] for c in curve])
        step = 24
        d = eq[::step]
        if len(d) > 2:
            daily = np.diff(d) / d[:-1]
    sharpe = (
        float(np.mean(daily) / np.std(daily) * math.sqrt(365))
        if len(daily) > 2 and np.std(daily) > 0
        else None
    )
    return {
        "start_balance": acct.balance,
        "end_equity": end_eq,
        "net_pnl": end_eq - acct.balance,
        "return_pct": (end_eq / acct.balance - 1) * 100,
        "days": days,
        "trades": n,
        "win_rate": len(wins) / n * 100 if n else None,
        "tp1_rate": sum(t["tp1"] for t in trades) / n * 100 if n else None,
        "avg_win": gw / len(wins) if wins else None,
        "avg_loss": -gl / len(losses) if losses else None,
        "profit_factor": gw / gl if gl > 0 else None,
        "expectancy": (gw - gl) / n if n else None,
        "avg_r": sum(t["r"] for t in trades) / n if n else None,
        "max_drawdown_pct": max_dd,
        "worst_losing_streak": worst,
        "sharpe": sharpe,
        "fees": fees,
        "funding": funding,
        "skipped": skipped,
        "open_positions": open_positions,
        "by": by,
        "trades_list": trades[-300:],
        "equity_curve": curve,
    }


# ---------------------------------------------------------------- tuning


GRIDS = [
    {  # trend pullback
        "mode": ["pullback"],
        "htf": [True],
        "adx_min": [0.0, 25.0],
        "vol_mult": [0.0, 1.2],
        "min_stop_pct": [0.0, 0.5, 1.0],
        "stop_atr_min": [1.5, 3.0],
        "tp1_frac": [0.0, 0.5],
        "tp2_r": [1.5, 2.0, 3.0],
    },
    {  # mean reversion with the higher-timeframe trend
        "mode": ["reversion"],
        "htf": [True, False],
        "dev_atr": [1.5, 2.5, 3.5],
        "min_stop_pct": [0.0, 0.5, 1.0],
        "stop_atr_min": [1.5, 3.0],
        "tp1_frac": [0.0, 0.5],
        "tp2_r": [0.75, 1.0, 1.5],
    },
]
GRID_KEYS = sorted({k for g in GRIDS for k in g})


def candidates() -> list[Strategy]:
    out: list[dict] = []
    for g in GRIDS:
        rows = [{}]
        for k, vals in g.items():
            rows = [o | {k: v} for o in rows for v in vals]
        out += rows
    return [Strategy.from_dict(o) for o in out]


def score(m: dict) -> float:
    """Rank by risk-adjusted return; too few trades are not trusted."""
    if m["trades"] < 25:
        return -1e9
    return m["return_pct"] / max(m["max_drawdown_pct"], 2.0)


def optimise(data, filters, acct: Account, split: float = 0.67) -> dict:
    """Pick parameters on the first `split` of the period, then judge them on the rest."""
    t0 = min(int(d["start_ms"]) for d in data.values())
    t1 = int(time.time() * 1000)
    cut = int(t0 + (t1 - t0) * split)
    base = Strategy()
    rows = []
    for p in candidates():
        m = run(data, filters, p, acct, t0, cut)
        rows.append((score(m), p, m))
    rows.sort(key=lambda r: r[0], reverse=True)
    best = rows[0][1]
    test_best = run(data, filters, best, acct, cut, t1)
    test_base = run(data, filters, base, acct, cut, t1)
    full_best = run(data, filters, best, acct, t0, t1)
    full_base = run(data, filters, base, acct, t0, t1)
    slim = lambda m: {k: v for k, v in m.items() if k not in ("trades_list", "equity_curve")}  # noqa: E731
    return {
        "cut": cut // 1000,
        "from": t0 // 1000,
        "to": t1 // 1000,
        "tested": len(rows),
        "best": best.to_dict() | {"rules": best.describe()},
        "baseline": base.to_dict() | {"rules": base.describe()},
        "top": [{"params": p.to_dict(), "train": slim(m)} for _, p, m in rows[:8]],
        "train_best": slim(rows[0][2]),
        "test_best": test_best,
        "test_baseline": slim(test_base),
        "full_best": full_best,
        "full_baseline": slim(full_base),
    }


def report(data, filters, p: Strategy, acct: Account, windows: int = 3) -> dict:
    """Whole period plus equal sub-windows, to see whether a result is stable or luck."""
    t0 = min(int(d["start_ms"]) for d in data.values())
    t1 = int(time.time() * 1000)
    full = run(data, filters, p, acct, t0, t1)
    w = (t1 - t0) // windows
    parts = []
    for k in range(windows):
        m = run(data, filters, p, acct, t0 + k * w, t0 + (k + 1) * w if k < windows - 1 else t1)
        parts.append(
            {
                "from": (t0 + k * w) // 1000,
                "to": (t0 + (k + 1) * w) // 1000,
                **{
                    x: m[x]
                    for x in (
                        "trades",
                        "win_rate",
                        "return_pct",
                        "max_drawdown_pct",
                        "profit_factor",
                        "avg_r",
                    )
                },
            }
        )
    return full | {
        "from": t0 // 1000,
        "to": t1 // 1000,
        "windows": parts,
        "strategy": p.to_dict() | {"rules": p.describe()},
        "account": acct.__dict__,
    }


# ---------------------------------------------------------------- continuous training


def train_grid(tf: str) -> list[Strategy]:
    """A compact search space per timeframe (both families)."""
    rows: list[dict] = []
    for adx in (0.0, 25.0):
        for ms in (0.5, 1.0):
            for tp1 in (0.0, 0.5):
                for r in (2.0, 3.0):
                    rows.append(
                        dict(
                            tf=tf,
                            mode="pullback",
                            adx_min=adx,
                            min_stop_pct=ms,
                            tp1_frac=tp1,
                            tp2_r=r,
                            stop_atr_min=2.0,
                        )
                    )
        for htf in (True, False):
            for dev in (1.5, 2.5):
                for tp1 in (0.0, 0.5):
                    for r in (1.0, 1.5):
                        rows.append(
                            dict(
                                tf=tf,
                                mode="reversion",
                                adx_min=adx,
                                htf=htf,
                                dev_atr=dev,
                                min_stop_pct=0.75,
                                tp1_frac=tp1,
                                tp2_r=r,
                                stop_atr_min=1.5,
                            )
                        )
    return [Strategy.from_dict(x) for x in rows]


def train(
    data, filters, acct: Account, current: Strategy, tfs=("5m", "15m", "1h"), split: float = 0.67
) -> dict:
    """Pick the best setup on the first part, judge it on the rest, compare with `current`.
    Adopt only if it is profitable out of sample (PF >= 1.1, >= 8 trades) and beats the
    current setup there and over the whole period."""
    t0 = min(int(d["start_ms"]) for d in data.values())
    t1 = int(time.time() * 1000)
    cut = int(t0 + (t1 - t0) * split)
    started = time.time()
    rows = []
    for tf in tfs:
        for p in train_grid(tf):
            m = run(data, filters, p, acct, t0, cut)
            rows.append((score(m), p, m))
    rows.sort(key=lambda x: x[0], reverse=True)
    best = rows[0][1]
    keys = ("trades", "win_rate", "return_pct", "profit_factor", "max_drawdown_pct")

    def slim(m: dict) -> dict:
        return {k: m[k] for k in keys}

    res = {
        "t": time.time(),
        "seconds": time.time() - started,
        "tested": len(rows),
        "from": t0 // 1000,
        "cut": cut // 1000,
        "to": t1 // 1000,
        "candidate": best.to_dict(),
        "candidate_rules": best.describe(),
        "candidate_train": slim(rows[0][2]),
        "candidate_test": slim(run(data, filters, best, acct, cut, t1)),
        "candidate_full": slim(run(data, filters, best, acct, t0, t1)),
        "current": current.to_dict(),
        "current_test": slim(run(data, filters, current, acct, cut, t1)),
        "current_full": slim(run(data, filters, current, acct, t0, t1)),
    }
    ct, cf = res["candidate_test"], res["candidate_full"]
    checks = {
        "profitable out of sample": ct["return_pct"] > 0,
        "profit factor ≥ 1.1 out of sample": (ct["profit_factor"] or 0) >= 1.1,
        "≥ 8 trades out of sample": ct["trades"] >= 8,
        "beats current out of sample": ct["return_pct"] > res["current_test"]["return_pct"],
        "beats current over the whole period": cf["return_pct"] > res["current_full"]["return_pct"],
        "differs from current": best.to_dict() != current.to_dict(),
    }
    res["checks"] = {k: bool(v) for k, v in checks.items()}  # plain bools for JSON
    res["adopt"] = all(res["checks"].values())
    return res


# ---------------------------------------------------------------- take-profit study

TP_GRID = [round(0.5 + 0.25 * i, 2) for i in range(19)]  # 0.5R .. 5R


def excursions(data, p: Strategy, acct: Account, t_from: int, t_to: int) -> list[dict]:
    """For every signal of `p` in [t_from, t_to): entry at the next open (+slippage), then follow
    the bars with the stop fixed at its original level. Records the best move in our favour
    before the stop (MFE, in R), whether the stop was hit, the R at the time stop, and the cost
    of a round trip in R (two taker fees + two slippages)."""
    tfm = TF_MIN[p.tf]
    max_bars = max(1, math.ceil(p.max_bars * 5 / tfm))
    out = []
    for sym, d in data.items():
        key = (sym, p.tf, len(d["bars"]), d["bars"][-1][0] if d["bars"] else 0)
        ind = _IND.get(key)
        if ind is None:
            ind = _IND[key] = indicators(resample(d["bars"], tfm))
        t_ms = ind["t"] * 1000
        lo_i = int(np.searchsorted(t_ms, t_from))
        hi_i = int(np.searchsorted(t_ms, t_to))
        o, h, lo, c = ind["o"], ind["h"], ind["l"], ind["c"]
        for s in find_signals(ind, p, start=max(lo_i, 210), end=min(hi_i, len(c) - 1)):
            j0 = s["i"] + 1
            if j0 >= len(c) - 1:
                continue
            long = s["side"] == "long"
            entry = o[j0] * (1 + acct.slippage) if long else o[j0] * (1 - acct.slippage)
            risk = abs(entry - s["stop"])
            if risk <= 0 or (long and s["stop"] >= entry) or (not long and s["stop"] <= entry):
                continue
            mfe, stopped, end_r, bars = 0.0, False, 0.0, 0
            for j in range(j0, min(j0 + max_bars, len(c) - 1)):
                bars += 1
                if (lo[j] <= s["stop"]) if long else (h[j] >= s["stop"]):
                    stopped = True
                    break
                fav = (h[j] - entry) if long else (entry - lo[j])
                mfe = max(mfe, fav / risk)
                end_r = ((c[j] - entry) if long else (entry - c[j])) / risk
            cost_r = (2 * acct.taker_fee + 2 * acct.slippage) * entry / risk
            out.append(
                {
                    "symbol": sym,
                    "time": s["time"],
                    "side": s["side"],
                    "mfe": mfe,
                    "stopped": stopped,
                    "end_r": end_r,
                    "cost_r": cost_r,
                    "bars": bars,
                }
            )
    return out


def tp_curve(ex: list[dict], grid=TP_GRID) -> list[dict]:
    """Net expectancy (R per trade, costs included) and hit rate for each fixed TP.
    Same-bar ambiguity is resolved against us: the MFE only counts bars before the stop."""
    rows = []
    n = len(ex)
    for tp in grid:
        total, hits = 0.0, 0
        for e in ex:
            if e["mfe"] >= tp:
                total += tp - e["cost_r"]
                hits += 1
            elif e["stopped"]:
                total += -1 - e["cost_r"]
            else:
                total += e["end_r"] - e["cost_r"]
        rows.append(
            {
                "tp_r": tp,
                "expectancy_r": total / n if n else 0.0,
                "hit_rate": hits / n * 100 if n else 0.0,
                "trades": n,
            }
        )
    return rows


def tp_study(data, filters, acct: Account, p: Strategy, split: float = 0.67) -> dict:
    """Find the take-profit for strategy `p`: the excursion curve picks a TP on the first part,
    the last part (never seen) judges it, and the full simulator confirms the best few TP /
    TP1 combinations with real sizing, fees and funding."""
    t0 = min(int(d["start_ms"]) for d in data.values())
    t1 = int(time.time() * 1000)
    cut = int(t0 + (t1 - t0) * split)
    ex_tr = excursions(data, p, acct, t0, cut)
    ex_te = excursions(data, p, acct, cut, t1)
    tr, te = tp_curve(ex_tr), tp_curve(ex_te)
    best = max(tr, key=lambda r: r["expectancy_r"]) if tr else None
    mfes = sorted(e["mfe"] for e in ex_tr + ex_te)
    hist = [0] * 12  # 0-0.5R, 0.5-1R, ..., >=5.5R
    for m in mfes:
        hist[min(int(m / 0.5), 11)] += 1

    # confirm with the full simulator: current exits vs the best TPs, with and without TP1
    keys = ("trades", "win_rate", "return_pct", "profit_factor", "max_drawdown_pct", "avg_r")
    top = sorted(tr, key=lambda r: r["expectancy_r"], reverse=True)[:3]
    combos = [("current", p)]
    for r in top:
        combos.append((f"TP {r['tp_r']:g}R", replace(p, tp2_r=r["tp_r"], tp1_frac=0.0)))
        if r["tp_r"] >= 1.5:
            combos.append(
                (
                    f"TP1 1R 50% + TP {r['tp_r']:g}R",
                    replace(p, tp2_r=r["tp_r"], tp1_r=1.0, tp1_frac=0.5),
                )
            )
    confirm = []
    for name, q in combos:
        mt = run(data, filters, q, acct, cut, t1)
        mf = run(data, filters, q, acct, t0, t1)
        confirm.append(
            {
                "name": name,
                "tp2_r": q.tp2_r,
                "tp1_r": q.tp1_r,
                "tp1_frac": q.tp1_frac,
                "test": {k: mt[k] for k in keys},
                "full": {k: mf[k] for k in keys},
            }
        )
    cur = confirm[0]
    rivals = [x for x in confirm[1:]]
    pick = max(
        rivals, key=lambda x: (x["test"]["return_pct"], x["full"]["return_pct"]), default=None
    )
    checks = {}
    if pick:
        checks = {
            "more trades than 8 out of sample": pick["test"]["trades"] >= 8,
            "profitable out of sample": pick["test"]["return_pct"] > 0,
            "beats current exits out of sample": pick["test"]["return_pct"]
            > cur["test"]["return_pct"],
            "beats current exits over the whole period": pick["full"]["return_pct"]
            > cur["full"]["return_pct"],
            "differs from current exits": (pick["tp2_r"], pick["tp1_frac"])
            != (p.tp2_r, p.tp1_frac),
        }
    return {
        "t": time.time(),
        "from": t0 // 1000,
        "cut": cut // 1000,
        "to": t1 // 1000,
        "tf": p.tf,
        "mode": p.mode,
        "current_tp": {"tp2_r": p.tp2_r, "tp1_r": p.tp1_r, "tp1_frac": p.tp1_frac},
        "signals_train": len(ex_tr),
        "signals_test": len(ex_te),
        "curve_train": tr,
        "curve_test": te,
        "best_train": best,
        "best_on_test": next((r for r in te if best and r["tp_r"] == best["tp_r"]), None),
        "mfe_hist": hist,
        "mfe_median": float(np.median(mfes)) if mfes else None,
        "stop_rate": sum(e["stopped"] for e in ex_tr + ex_te) / max(len(mfes), 1) * 100,
        "confirm": confirm,
        "pick": pick,
        "checks": {k: bool(v) for k, v in checks.items()},
        "adopt": bool(pick) and all(checks.values()),
    }
