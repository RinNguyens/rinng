"""Baseline strategies for comparison (docs/09-phase-roadmap.md Phase 9).

- BuyAndHold: long from the first candle close to the end of data.
- LinearRegression: baseline trong paper QuantHarness (docs/01-quantharness-paper.md):
  OLS of close on candle index over the last `window` closed candles; slope > 0 → long, otherwise
  (including slope = 0) → short. Evaluated every candle, emits only when direction changes.
- EmaCross: fast EMA > slow EMA → long, < → short. EMA via polars
  `ewm_mean(span=..., adjust=False)`. Evaluated only from candle `slow` on (skipping warm-up),
  skips candles where the EMAs are equal, emits only when direction changes.

Every signal has `time` = close of the candle it was computed from (open_time + candle length).
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration, check_ohlcv
from rinng.strategy.base import dedupe_sides, signals_frame


def _close_times(ohlcv: pl.DataFrame) -> pl.Series:
    _, timeframe = check_ohlcv(ohlcv)
    return ohlcv["open_time"] + bar_duration(timeframe)


@dataclass
class BuyAndHold:
    name: str = "buy_and_hold"
    params: dict[str, Any] = field(default_factory=dict)

    def signals(self, ohlcv, features=None, events=None) -> pl.DataFrame:
        times = _close_times(ohlcv)
        return signals_frame([{"time": times[0], "side": "long", "reason": "buy_and_hold"}])


@dataclass
class LinearRegression:
    window: int = 40
    name: str = "linear_regression"

    def __post_init__(self) -> None:
        if self.window < 2:
            raise ValueError("window must be >= 2")

    @property
    def params(self) -> dict[str, Any]:
        return {"window": self.window}

    def slopes(self, ohlcv: pl.DataFrame) -> np.ndarray:
        """OLS slope (price/candle) at each candle; NaN until `window` candles are available."""
        close = ohlcv["close"].to_numpy().astype(float)
        out = np.full(len(close), np.nan)
        if len(close) < self.window:
            return out
        x = np.arange(self.window, dtype=float)
        xc = x - x.mean()
        windows = np.lib.stride_tricks.sliding_window_view(close, self.window)
        out[self.window - 1 :] = (windows - windows.mean(axis=1, keepdims=True)) @ xc / (xc @ xc)
        return out

    def signals(self, ohlcv, features=None, events=None) -> pl.DataFrame:
        times = _close_times(ohlcv)
        slope = self.slopes(ohlcv)
        idx = np.flatnonzero(~np.isnan(slope))
        sides = ["long" if slope[i] > 0 else "short" for i in idx]
        reasons = [f"lr_slope={slope[i]:.6g}" for i in idx]
        return dedupe_sides([times[int(i)] for i in idx], sides, reasons)


@dataclass
class EmaCross:
    fast: int = 12
    slow: int = 26
    name: str = "ema_cross"

    def __post_init__(self) -> None:
        if not 1 <= self.fast < self.slow:
            raise ValueError("requires 1 <= fast < slow")

    @property
    def params(self) -> dict[str, Any]:
        return {"fast": self.fast, "slow": self.slow}

    def emas(self, ohlcv: pl.DataFrame) -> pl.DataFrame:
        return ohlcv.select(
            pl.col("close").ewm_mean(span=self.fast, adjust=False).alias("ema_fast"),
            pl.col("close").ewm_mean(span=self.slow, adjust=False).alias("ema_slow"),
        )

    def signals(self, ohlcv, features=None, events=None) -> pl.DataFrame:
        times = _close_times(ohlcv)
        ema = self.emas(ohlcv)
        diff = (ema["ema_fast"] - ema["ema_slow"]).to_numpy()
        keep = [i for i in range(self.slow - 1, len(diff)) if diff[i] != 0]
        sides = ["long" if diff[i] > 0 else "short" for i in keep]
        reasons = [f"ema{self.fast}{'>' if diff[i] > 0 else '<'}ema{self.slow}" for i in keep]
        return dedupe_sides([times[i] for i in keep], sides, reasons)
