"""Performance metrics (docs/05-quant-backtest-and-data.md section 3).

Conventions:
- Per-period returns come from mark-to-market equity at each candle close; the first period is vs
  initial capital.
- `periods_per_year` = candles per year for 24/7 crypto, 365 days (1h → 8 760, 1d → 365).
- Risk-free rate r_f = 0 and MAR = 0 for Sharpe/Sortino.
- Sharpe uses the sample standard deviation (ddof=1). Sortino: downside deviation over ALL periods.
- Years = candles / periods_per_year (same 365-day convention as the annualization factor).
- Max drawdown is negative (−0.2 = 20% drop) and includes the initial capital point.
- Undefined values (zero standard deviation, no losing trades, ...) return NaN.
"""

import math

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration

YEAR_DAYS = 365


def periods_per_year(timeframe: str) -> float:
    """Candles per year for a 24/7 market."""
    return YEAR_DAYS * 86_400_000 / (bar_duration(timeframe).total_seconds() * 1000)


def returns(equity: np.ndarray, initial: float) -> np.ndarray:
    values = np.concatenate([[initial], np.asarray(equity, dtype=float)])
    return values[1:] / values[:-1] - 1


def sharpe(rets: np.ndarray, periods: float) -> float:
    if len(rets) < 2:
        return math.nan
    sd = float(np.std(rets, ddof=1))
    return float(np.mean(rets)) / sd * math.sqrt(periods) if sd > 0 else math.nan


def sortino(rets: np.ndarray, periods: float) -> float:
    if len(rets) == 0:
        return math.nan
    dd = math.sqrt(float(np.mean(np.minimum(rets, 0.0) ** 2)))
    return float(np.mean(rets)) / dd * math.sqrt(periods) if dd > 0 else math.nan


def max_drawdown(equity: np.ndarray, initial: float | None = None) -> float:
    values = np.asarray(equity, dtype=float)
    if initial is not None:
        values = np.concatenate([[initial], values])
    if len(values) == 0:
        return math.nan
    peak = np.maximum.accumulate(values)
    return float(np.min(values / peak - 1))


def cagr(initial: float, final: float, years: float) -> float:
    if years <= 0 or initial <= 0 or final <= 0:
        return math.nan
    return (final / initial) ** (1 / years) - 1


def summarize(
    equity: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    initial_equity: float,
    periods: float,
) -> dict[str, float | int]:
    """Metric table from the engine's equity frame (equity, position columns) and trades frame."""
    eq = equity["equity"].to_numpy().astype(float)
    n = len(eq)
    final = float(eq[-1]) if n else initial_equity
    years = n / periods
    rets = returns(eq, initial_equity)
    mdd = max_drawdown(eq, initial_equity)
    growth = cagr(initial_equity, final, years)

    pnl = trades["pnl"].to_numpy().astype(float) if trades.height else np.array([])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_loss = float(-losses.sum())
    if trades.height:
        notional = (trades["qty"] * (trades["entry_price"] + trades["exit_price"])).sum()
    else:
        notional = 0.0
    mean_equity = float(np.mean(eq)) if n else initial_equity

    return {
        "bars": n,
        "years": years,
        "initial_equity": initial_equity,
        "final_equity": final,
        "total_return": final / initial_equity - 1,
        "cagr": growth,
        "sharpe": sharpe(rets, periods),
        "sortino": sortino(rets, periods),
        "max_drawdown": mdd,
        "calmar": growth / abs(mdd) if mdd < 0 and not math.isnan(growth) else math.nan,
        "trades": int(trades.height),
        "win_rate": len(wins) / len(pnl) if len(pnl) else math.nan,
        "profit_factor": float(wins.sum()) / gross_loss if gross_loss > 0 else math.nan,
        "expectancy": float(pnl.mean()) if len(pnl) else math.nan,
        "exposure": float((equity["position"] != 0).mean()) if n else math.nan,
        # Annual turnover by the Σ|Δw|/2 convention: total filled notional (entries + exits) / 2 /
        # mean
        # equity / years. One full-capital round trip = 1.
        "turnover": float(notional) / 2 / mean_equity / years if years > 0 else math.nan,
        "fees": float(trades["fees"].sum()) if trades.height else 0.0,
        "funding": float(trades["funding"].sum()) if trades.height else 0.0,
    }
