"""Memory bank with retrospective metrics (paper: Methods eq. 3-7, Fig. 7c).

Every decision day t stores a record R_t = {a_t, p_t, q_t, P_t, V_t, {R_t,h, v_t,h^R},
{SR_t,h, v_t,h^SR}}. Outcome fields start empty and are back-filled only once day t+h has been
reached, so nothing about the future is visible at decision time:

    R_t,h (%) = 100 · (P_{t+h} − P_t) · d_t · q_t / V_t        (trade PnL over h days)
    SR_t,h    = √365 · mean / std of the portfolio's daily returns over (t, t+h]   (h ≥ 7)
    v_t,h     = linear slope of the last `w` available R_·,h (or SR_·,h) values

√365 instead of the paper's √252 because crypto trades every day. Positive slopes mean the strategy
is improving at that horizon. `prompt_table` renders the bank for the reflection agents; short-term
reflection reads H_short = {1, 7, 14}, long-term H_long = {28, 90, 180, 360}.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

SHORT = (1, 7, 14)
LONG = (28, 90, 180, 360)
HORIZONS = SHORT + LONG
SLOPE_WINDOW = 5


@dataclass
class Record:
    day: int  # index into the run's day list
    date: str
    action: str
    pct: int
    qty_change: float  # signed: + bought, − sold
    price: float  # execution price
    value: float  # portfolio value before the trade (V_t)
    returns: dict[int, float | None] = field(default_factory=dict)
    sharpe: dict[int, float | None] = field(default_factory=dict)
    slope_r: dict[int, float | None] = field(default_factory=dict)
    slope_sr: dict[int, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    x = np.arange(len(values), dtype=float)
    return float(np.polyfit(x, np.asarray(values, dtype=float), 1)[0])


class MemoryBank:
    def __init__(self, window: int = SLOPE_WINDOW):
        self.records: list[Record] = []
        self.window = window
        self.reflections: list[dict] = []  # {"day", "short", "long"}

    def add(self, rec: Record) -> None:
        rec.returns = {h: None for h in HORIZONS}
        rec.sharpe = {h: None for h in HORIZONS if h >= 7}
        rec.slope_r = {h: None for h in HORIZONS}
        rec.slope_sr = {h: None for h in HORIZONS if h >= 7}
        self.records.append(rec)

    def backfill(self, today: int, prices: list[float], equity: list[float]) -> None:
        """`today`: current day index t. `prices[k]`: execution price of day k (known for
        k ≤ t). `equity[k]`: end-of-day portfolio value of day k (known for k ≤ t − 1)."""
        for r in self.records:
            for h in HORIZONS:
                if r.returns[h] is None and r.day + h <= today and r.day + h < len(prices):
                    pnl = (prices[r.day + h] - r.price) * r.qty_change
                    r.returns[h] = 100 * pnl / r.value if r.value > 0 else 0.0
                if h >= 7 and r.sharpe[h] is None and r.day + h <= today - 1:
                    seg = np.asarray(equity[r.day : r.day + h + 1], dtype=float)
                    if len(seg) == h + 1:
                        dr = seg[1:] / seg[:-1] - 1
                        sd = float(np.std(dr, ddof=1))
                        r.sharpe[h] = float(np.mean(dr) / sd * math.sqrt(365)) if sd > 0 else 0.0
        for i, r in enumerate(self.records):
            past = self.records[max(0, i - self.window + 1) : i + 1]
            for h in HORIZONS:
                vals = [p.returns[h] for p in past if p.returns[h] is not None]
                r.slope_r[h] = slope(vals) if len(vals) >= 2 else None
                if h >= 7:
                    svals = [p.sharpe[h] for p in past if p.sharpe[h] is not None]
                    r.slope_sr[h] = slope(svals) if len(svals) >= 2 else None

    def latest_slopes(self, horizons: tuple[int, ...]) -> dict:
        """Most recent available slope per horizon."""
        out = {}
        for h in horizons:
            r = next(
                (r.slope_r[h] for r in reversed(self.records) if r.slope_r[h] is not None), None
            )
            s = next(
                (
                    r.slope_sr[h]
                    for r in reversed(self.records)
                    if h in r.slope_sr and r.slope_sr[h] is not None
                ),
                None,
            )
            out[h] = {"return_slope": r, "sharpe_slope": s}
        return out

    def prompt_table(self, horizons: tuple[int, ...], last: int = 20) -> str:
        if not self.records:
            return "(no past decisions yet)"
        head = ["date", "action", "price"] + [f"R{h}d%" for h in horizons]
        head += [f"SR{h}d" for h in horizons if h >= 7]
        rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for r in self.records[-last:]:
            cells = [r.date, f"{r.action} {r.pct}%", f"{r.price:.6g}"]
            cells += ["" if r.returns[h] is None else f"{r.returns[h]:+.2f}" for h in horizons]
            cells += [
                "" if r.sharpe.get(h) is None else f"{r.sharpe[h]:+.2f}" for h in horizons if h >= 7
            ]
            rows.append("| " + " | ".join(cells) + " |")
        slopes = self.latest_slopes(horizons)
        lines = [
            f"- {h}d: return slope {_f(v['return_slope'])}, Sharpe slope {_f(v['sharpe_slope'])}"
            for h, v in slopes.items()
        ]
        return (
            "\n".join(rows)
            + f"\nTrend of performance (slope over the last {self.window} decisions; "
            "> 0 improving):\n" + "\n".join(lines)
        )

    def last_reflection(self) -> dict | None:
        return self.reflections[-1] if self.reflections else None


def _f(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.3f}"
