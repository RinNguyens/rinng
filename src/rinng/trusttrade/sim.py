"""Long-only spot portfolio simulation, metrics and rule-based baselines.

Execution model (same for LLM variants and baselines): the decision for day D uses daily bars that
closed before D and fills at D's open; equity is marked at D's close. BUY p% spends p% of the free
cash, SELL p% sells p% of the held quantity, each fill pays `fee_bps` per side. This mirrors the
paper's partial allocation (25/50/75/100%); "full allocation" forces every BUY/SELL to 100%.

Baselines (paper: Experimental Details) use standard daily parameters and only past bars:
buy-and-hold, SMA(10/30) cross, MACD(12/26/9) line vs signal, KDJ+RSI (stochastic 14/3/3 with
RSI 14, oversold < 30 / overbought > 70), ZMR (z-score vs SMA20: enter below −1, exit at the
mean), and TrustTrade's own deterministic temporal recommendation ("temporal-rule").
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import polars as pl
import talib

from rinng.backtest.metrics import max_drawdown, returns, sharpe

BASELINES = ("buy_hold", "sma_cross", "macd", "kdj_rsi", "zmr")


@dataclass
class Portfolio:
    cash: float
    qty: float = 0.0
    fee: float = 0.001
    fees_paid: float = 0.0
    trades: int = 0

    def value(self, price: float) -> float:
        return self.cash + self.qty * price

    def execute(self, action: str, pct: int, price: float) -> float:
        """Apply a decision at `price`; return the signed quantity change."""
        frac = max(0, min(100, pct)) / 100
        if action == "BUY" and frac > 0 and self.cash > 1e-9:
            spend = self.cash * frac
            q = spend * (1 - self.fee) / price
            self.cash -= spend
            self.qty += q
            self.fees_paid += spend * self.fee
            self.trades += 1
            return q
        if action == "SELL" and frac > 0 and self.qty > 1e-12:
            q = self.qty * frac
            gross = q * price
            self.qty -= q
            self.cash += gross * (1 - self.fee)
            self.fees_paid += gross * self.fee
            self.trades += 1
            return -q
        return 0.0


def metrics(equity: list[float], initial: float, exposure: list[float] | None = None) -> dict:
    """CR, annualised return (365 days), Sharpe (daily, annualised √365), MDD — in percent."""
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return {"days": 0}
    rets = returns(eq, initial)
    cr = eq[-1] / initial - 1
    ar = (eq[-1] / initial) ** (365 / len(eq)) - 1 if eq[-1] > 0 else math.nan
    out = {
        "days": len(eq),
        "cr_pct": round(100 * cr, 3),
        "ar_pct": round(100 * ar, 3),
        "sharpe": round(sharpe(rets, 365), 3),
        "mdd_pct": round(abs(100 * max_drawdown(eq, initial)), 3),
    }
    if exposure is not None and len(exposure):
        out["avg_exposure_pct"] = round(100 * float(np.mean(exposure)), 1)
    return out


def rule_positions(d1: pl.DataFrame, name: str) -> np.ndarray:
    """Desired state (1 long, 0 flat) after each bar's close, using that bar and earlier ones.
    The decision for the next day reads the value at the previous row."""
    c = d1["close"].to_numpy().astype(float)
    h = d1["high"].to_numpy().astype(float)
    lo = d1["low"].to_numpy().astype(float)
    n = len(c)
    pos = np.zeros(n)
    if name == "buy_hold":
        return np.ones(n)
    if name == "sma_cross":
        f, s = talib.SMA(c, 10), talib.SMA(c, 30)
        return np.where(np.nan_to_num(f) > np.nan_to_num(s), 1.0, 0.0)
    if name == "macd":
        line, sig, _ = talib.MACD(c, 12, 26, 9)
        return np.where(np.nan_to_num(line) > np.nan_to_num(sig), 1.0, 0.0)
    if name == "kdj_rsi":
        k, d = talib.STOCH(h, lo, c, 14, 3, 0, 3, 0)
        rsi = talib.RSI(c, 14)
        state = 0.0
        for i in range(1, n):
            if np.isnan(k[i]) or np.isnan(d[i]) or np.isnan(rsi[i]):
                pos[i] = state
                continue
            cross_up = k[i - 1] <= d[i - 1] and k[i] > d[i]
            cross_dn = k[i - 1] >= d[i - 1] and k[i] < d[i]
            if (cross_up and k[i] < 30) or rsi[i] < 30:
                state = 1.0
            elif (cross_dn and k[i] > 70) or rsi[i] > 70:
                state = 0.0
            pos[i] = state
        return pos
    if name == "zmr":
        m, sd = talib.SMA(c, 20), talib.STDDEV(c, 20)
        state = 0.0
        for i in range(n):
            if np.isnan(m[i]) or not sd[i]:
                pos[i] = state
                continue
            z = (c[i] - m[i]) / sd[i]
            if z < -1:
                state = 1.0
            elif z >= 0:
                state = 0.0
            pos[i] = state
        return pos
    raise ValueError(f"unknown baseline {name}")


def to_action(want: float, holding: bool) -> tuple[str, int]:
    if want >= 0.5 and not holding:
        return "BUY", 100
    if want < 0.5 and holding:
        return "SELL", 100
    return "HOLD", 0
