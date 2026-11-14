"""Chiến lược baseline để so sánh (docs/09-lo-trinh-phase.md Phase 9).

- BuyAndHold: long từ lúc đóng nến đầu tiên tới hết dữ liệu.
- LinearRegression: baseline trong paper QuantHarness (docs/01-quantharness-paper.md):
  OLS của close theo chỉ số nến trên `window` nến đóng gần nhất; dốc > 0 → long, ngược lại
  (kể cả dốc = 0) → short. Đánh giá ở mỗi nến, chỉ phát tín hiệu khi chiều đổi.
- EmaCross: EMA nhanh > EMA chậm → long, < → short. EMA bằng polars
  `ewm_mean(span=..., adjust=False)`. Chỉ đánh giá từ nến thứ `slow` (bỏ giai đoạn khởi động),
  bỏ qua nến hai EMA bằng nhau, chỉ phát tín hiệu khi chiều đổi.

Mọi tín hiệu có `time` = lúc đóng nến dùng để tính (open_time + độ dài nến).
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
            raise ValueError("window phải >= 2")

    @property
    def params(self) -> dict[str, Any]:
        return {"window": self.window}

    def slopes(self, ohlcv: pl.DataFrame) -> np.ndarray:
        """Dốc OLS (giá/nến) tại mỗi nến; NaN khi chưa đủ `window` nến."""
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
            raise ValueError("cần 1 <= fast < slow")

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
