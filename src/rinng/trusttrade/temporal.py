"""Deterministic temporal signals (paper: "Deterministic temporal signal analytical pipeline").

Price-only, no LLM, fully reproducible. Input: closed daily candles up to the decision time.
Outputs, as in the paper's Fig. 3d / Fig. 7b:

- price history per horizon H = {1, 7, 14, 28, 90, 180, 360} days: cumulative return, realized
  volatility, high/low, average volume and a five-level trend label;
- a rule-scored next-day forecast (up / down / uncertain) with a bounded magnitude;
- a 0-100 confidence score and a BUY/SELL/HOLD recommendation with a position size;
- a summary table for the trader prompt.

Trend label: a quadratic is fitted to closes over the horizon (normalised to the first close); the
fitted start-to-end change and the terminal slope are averaged into one score, which is divided by
the horizon's expected move (daily volatility × √h) so thresholds mean the same thing for BTC and
for a small cap. |z| > 1 strong, > 0.25 trend, else sideways.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
import polars as pl

HORIZONS = (1, 7, 14, 28, 90, 180, 360)
TREND_LABELS = ("strong downtrend", "downtrend", "sideways", "uptrend", "strong uptrend")
SIZES = (0, 25, 50, 75, 100)


@dataclass
class Horizon:
    days: int
    ret: float
    vol: float | None  # daily realized volatility (std of log returns)
    high: float
    low: float
    avg_volume: float
    trend: str | None
    trend_z: float | None


@dataclass
class TemporalSignals:
    as_of: str
    close: float
    horizons: list[Horizon]
    direction: str  # up | down | uncertain
    magnitude: float  # expected next-day move, fraction (bounded)
    forecast_confidence: int  # 0-100
    support: float
    resistance: float
    alignment: int  # 0-100, share of horizons whose trend agrees with the forecast
    score: int  # 0-100 recommendation confidence
    action: str  # BUY | SELL | HOLD
    pct: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def table(self, label_dates: bool = True) -> str:
        """Markdown summary table for prompts."""
        rows = [
            "| Temporal signal | Value | Notes |",
            "|---|---|---|",
        ]
        if label_dates:
            rows.append(f"| Last close time | {self.as_of} | decision uses bars up to here |")
        rows.append(f"| Current price | {_px(self.close)} | last daily close |")
        for h in self.horizons:
            name = _hname(h.days)
            note = h.trend or ("one-day move" if h.days == 1 else "")
            rows.append(f"| {name} return | {h.ret * 100:+.2f}% | {note} |")
        for h in self.horizons:
            if h.vol is not None and h.days in (7, 28, 90, 180):
                rows.append(f"| {_hname(h.days)} volatility (daily) | {h.vol * 100:.2f}% | |")
        rows += [
            f"| Next-day prediction | {self.direction.upper()} {self.magnitude * 100:.2f}% | "
            f"confidence {self.forecast_confidence}/100 |",
            f"| Key support (14d low) | {_px(self.support)} | "
            f"{(self.support / self.close - 1) * 100:+.1f}% from price |",
            f"| Key resistance (14d high) | {_px(self.resistance)} | "
            f"{(self.resistance / self.close - 1) * 100:+.1f}% from price |",
            f"| Trend alignment score | {self.alignment}/100 | horizons agreeing with forecast |",
            f"| Rule-based proposal | {self.action} {self.pct}% | score {self.score}/100 |",
        ]
        return "\n".join(rows)


def _px(v: float) -> str:
    return f"{v:,.2f}" if v >= 1 else f"{v:.6g}"


def _hname(d: int) -> str:
    return {1: "1-day", 7: "1-week", 14: "2-week", 28: "4-week", 90: "3-month"}.get(d, f"{d}-day")


def trend_z(closes: np.ndarray, daily_vol: float) -> float:
    """Volatility-normalised trend score of a close series (see module docstring)."""
    y = closes / closes[0]
    x = np.linspace(0.0, 1.0, len(y))
    c = np.polyfit(x, y, 2)
    fit = np.polyval(c, [0.0, 1.0])
    slope_end = 2 * c[0] + c[1]  # derivative at x = 1, per window
    score = 0.5 * (fit[1] - fit[0]) + 0.5 * slope_end
    scale = max(daily_vol, 1e-4) * math.sqrt(len(y) - 1)
    return float(score / scale)


def trend_label(z: float) -> str:
    if z > 1:
        return TREND_LABELS[4]
    if z > 0.25:
        return TREND_LABELS[3]
    if z >= -0.25:
        return TREND_LABELS[2]
    if z >= -1:
        return TREND_LABELS[1]
    return TREND_LABELS[0]


def _size(score: int) -> int:
    if score >= 90:
        return 100
    if score >= 80:
        return 75
    if score >= 70:
        return 50
    return 25


def compute(d1: pl.DataFrame, *, holding: bool = False, as_of: str = "") -> TemporalSignals:
    """`d1`: closed daily candles (open_time, open, high, low, close, volume), oldest first,
    at least 30 rows. `holding`: whether a position is open (a SELL needs something to sell)."""
    if d1.height < 30:
        raise ValueError("temporal signals need at least 30 daily candles")
    close = d1["close"].to_numpy().astype(float)
    high = d1["high"].to_numpy().astype(float)
    low = d1["low"].to_numpy().astype(float)
    vol = d1["volume"].to_numpy().astype(float)
    logret = np.diff(np.log(close))
    last = float(close[-1])

    horizons: list[Horizon] = []
    for h in HORIZONS:
        if len(close) <= h:
            continue
        seg = slice(len(close) - h - 1, len(close))
        r = logret[-h:]
        dvol = float(np.std(r, ddof=1)) if h >= 2 else None
        z = trend_z(close[seg], dvol) if dvol is not None and h >= 7 else None
        horizons.append(
            Horizon(
                days=h,
                ret=float(close[-1] / close[-1 - h] - 1),
                vol=dvol,
                high=float(high[-h:].max()),
                low=float(low[-h:].min()),
                avg_volume=float(vol[-h:].mean()),
                trend=trend_label(z) if z is not None else None,
                trend_z=None if z is None else round(z, 3),
            )
        )
    by = {h.days: h for h in horizons}

    # --- rule-scored next-day forecast
    ma = {n: float(close[-n:].mean()) for n in (5, 10, 20)}
    bull = bear = 0
    reasons: list[str] = []
    if last > max(ma.values()):
        bull += 2
        reasons.append("price above MA5/MA10/MA20 (+2 bull)")
    elif last < min(ma.values()):
        bear += 2
        reasons.append("price below MA5/MA10/MA20 (+2 bear)")
    if ma[5] > ma[10] > ma[20]:
        bull += 1
        reasons.append("MA5 > MA10 > MA20 (+1 bull)")
    elif ma[5] < ma[10] < ma[20]:
        bear += 1
        reasons.append("MA5 < MA10 < MA20 (+1 bear)")
    roc5 = last / float(close[-6]) - 1
    if roc5 > 0:
        bull += 1
        reasons.append(f"5-day rate of change {roc5 * 100:+.1f}% (+1 bull)")
    elif roc5 < 0:
        bear += 1
        reasons.append(f"5-day rate of change {roc5 * 100:+.1f}% (+1 bear)")
    for d in (7, 28):
        t = by.get(d)
        if t and t.trend and "up" in t.trend:
            bull += 1
            reasons.append(f"{_hname(d)} {t.trend} (+1 bull)")
        elif t and t.trend and "down" in t.trend:
            bear += 1
            reasons.append(f"{_hname(d)} {t.trend} (+1 bear)")
    max_pts = 6
    net = bull - bear
    direction = "up" if net >= 2 else "down" if net <= -2 else "uncertain"
    fc_conf = round(100 * abs(net) / max_pts)
    dvol14 = by[14].vol if 14 in by and by[14].vol else float(np.std(logret[-14:], ddof=1))
    cap = 1.5 * dvol14  # bounded magnitude: never extrapolate more than 1.5 daily sigmas
    magnitude = float(np.clip(net / max_pts * dvol14, -cap, cap))

    # --- recommendation score
    sign = 1 if direction == "up" else -1 if direction == "down" else 0
    trended = [h for h in horizons if h.trend_z is not None]
    if sign and trended:
        agree = sum(1 for h in trended if np.sign(h.trend_z) == sign and h.trend != "sideways")
        alignment = round(100 * agree / len(trended))
    else:
        alignment = 0
    r7 = by[7].ret if 7 in by else 0.0
    strength = float(np.clip(50 + 50 * sign * r7 / max(dvol14 * math.sqrt(7), 1e-4), 0, 100))
    mag_score = float(np.clip(100 * abs(magnitude) / max(cap, 1e-9), 0, 100))
    score = round(0.35 * alignment + 0.35 * fc_conf + 0.15 * strength + 0.15 * mag_score)
    if not sign:
        score = min(score, 50)

    action, pct = "HOLD", 0
    if score >= 60 and direction == "up":
        action, pct = "BUY", _size(score)
    elif score >= 60 and direction == "down" and holding:
        action, pct = "SELL", _size(score)

    return TemporalSignals(
        as_of=as_of,
        close=last,
        horizons=horizons,
        direction=direction,
        magnitude=magnitude,
        forecast_confidence=fc_conf,
        support=float(low[-14:].min()),
        resistance=float(high[-14:].max()),
        alignment=alignment,
        score=score,
        action=action,
        pct=pct,
        reasons=reasons,
    )
