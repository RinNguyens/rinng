"""Indicator kỹ thuật dạng Features (một dòng mỗi nến).

Phần lớn bọc TA-Lib; VWAP và anchored VWAP tự viết bằng polars.

Định nghĩa và tham số mặc định (khóa trong `params` của `compute`):
- RSI(`rsi`=14): Wilder, như TA-Lib (trung bình đầu = SMA của n thay đổi đầu tiên).
- MACD(`macd_fast`=12, `macd_slow`=26, `macd_signal`=9): line = EMA nhanh - EMA chậm,
  signal = EMA của line, hist = line - signal. Cách seed EMA theo TA-Lib nên vài chục giá trị
  đầu có thể lệch nhẹ so với TradingView; về sau hội tụ.
- ROC(`roc`=10): 100 × (close / close[n] - 1).
- Stochastic(`stoch_k`=14, `stoch_k_smooth`=3, `stoch_d`=3): %K = SMA(raw %K, k_smooth),
  %D = SMA(%K, d). Raw %K = 100 × (close - LL) / (HH - LL) trên `stoch_k` nến. Như TA-Lib,
  %K chỉ có giá trị từ nến đầu tiên %D có giá trị.
- Williams %R(`willr`=14): -100 × (HH - close) / (HH - LL).
- ATR(`atr`=14): Wilder, seed = SMA của n true range đầu tiên (true range bắt đầu từ nến 1).
- Bollinger(`bb_length`=20, `bb_std`=2.0): mid = SMA, upper/lower = mid ± k × độ lệch chuẩn
  tổng thể (ddof=0).
- EMA(`ema`=[9, 21, 50, 200]) và SMA(`sma`=[20, 50, 200]): mỗi chu kỳ một cột `ema_<n>`,
  `sma_<n>`. EMA seed bằng SMA của n giá đầu (TA-Lib).
- ADX(`adx`=14): Wilder, như TA-Lib.
- OBV: cộng dồn volume có dấu theo chiều close; giá trị đầu = volume[0] (như TA-Lib).
- VWAP ngày (`vwap`=True): Σ(typical × volume) / Σ volume, reset lúc 00:00 UTC mỗi ngày;
  typical = (high + low + close) / 3. Ngày có tổng volume = 0 cho null.
- Anchored VWAP (`avwap_anchor`=None): như trên nhưng cộng dồn từ nến đầu tiên có
  `open_time >= anchor`, không reset; trước mốc là null.

Giá trị khởi động (TA-Lib trả NaN) giữ là null. Mọi giá trị ở nến i chỉ dùng nến <= i nên
known_at = thời điểm đóng nến (do `features_frame` gán).
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import numpy as np
import polars as pl
import talib

from rinng.analysis.types import check_ohlcv, features_frame, params_hash

MODULE = "indicators"

DEFAULTS: dict[str, Any] = {
    "rsi": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "roc": 10,
    "stoch_k": 14,
    "stoch_k_smooth": 3,
    "stoch_d": 3,
    "willr": 14,
    "atr": 14,
    "bb_length": 20,
    "bb_std": 2.0,
    "ema": [9, 21, 50, 200],
    "sma": [20, 50, 200],
    "adx": 14,
    "vwap": True,
    "avwap_anchor": None,
}


def _series(values: np.ndarray) -> pl.Series:
    """numpy → polars Float64, NaN thành null."""
    return pl.Series(np.asarray(values, dtype=np.float64)).fill_nan(None)


def _arrays(ohlcv: pl.DataFrame) -> tuple[np.ndarray, ...]:
    return tuple(
        ohlcv[c].cast(pl.Float64).to_numpy().astype(np.float64)
        for c in ("open", "high", "low", "close", "volume")
    )


def atr(ohlcv: pl.DataFrame, length: int = 14) -> np.ndarray:
    """ATR Wilder (TA-Lib) dạng numpy, NaN ở giai đoạn khởi động. Dùng chung cho smc/liquidity."""
    _, high, low, close, _ = _arrays(ohlcv)
    return talib.ATR(high, low, close, timeperiod=length)


def _vwap(ohlcv: pl.DataFrame, group: pl.Expr | None, mask: pl.Expr | None) -> pl.Series:
    typical = (pl.col("high") + pl.col("low") + pl.col("close")) / 3
    pv = typical * pl.col("volume")
    vol = pl.col("volume")
    if mask is not None:
        pv = pl.when(mask).then(pv).otherwise(None)
        vol = pl.when(mask).then(vol).otherwise(None)
    cum_pv = pv.cum_sum()
    cum_v = vol.cum_sum()
    if group is not None:
        cum_pv = cum_pv.over(group)
        cum_v = cum_v.over(group)
    out = pl.when(cum_v > 0).then(cum_pv / cum_v).otherwise(None)
    return ohlcv.select(out.cast(pl.Float64).alias("v"))["v"]


def vwap_daily(ohlcv: pl.DataFrame) -> pl.Series:
    """VWAP reset theo ngày UTC."""
    return _vwap(ohlcv, pl.col("open_time").dt.convert_time_zone("UTC").dt.date(), None)


def anchored_vwap(ohlcv: pl.DataFrame, anchor: datetime) -> pl.Series:
    """VWAP cộng dồn từ nến đầu tiên có open_time >= anchor; trước mốc là null."""
    dtype = ohlcv.schema["open_time"]
    return _vwap(ohlcv, None, pl.col("open_time") >= pl.lit(anchor).cast(dtype))


def compute(ohlcv: pl.DataFrame, params: Mapping[str, Any] | None = None) -> pl.DataFrame:
    """Features gồm mọi indicator ở docstring module. `params` ghi đè `DEFAULTS`."""
    check_ohlcv(ohlcv)
    unknown = set(params or {}) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"tham số không biết: {sorted(unknown)}")
    p = {**DEFAULTS, **(params or {})}
    _, high, low, close, volume = _arrays(ohlcv)

    values: dict[str, pl.Series] = {}
    values["rsi"] = _series(talib.RSI(close, timeperiod=p["rsi"]))
    line, signal, hist = talib.MACD(
        close,
        fastperiod=p["macd_fast"],
        slowperiod=p["macd_slow"],
        signalperiod=p["macd_signal"],
    )
    values["macd"] = _series(line)
    values["macd_signal"] = _series(signal)
    values["macd_hist"] = _series(hist)
    values["roc"] = _series(talib.ROC(close, timeperiod=p["roc"]))
    k, d = talib.STOCH(
        high,
        low,
        close,
        fastk_period=p["stoch_k"],
        slowk_period=p["stoch_k_smooth"],
        slowk_matype=0,
        slowd_period=p["stoch_d"],
        slowd_matype=0,
    )
    values["stoch_k"] = _series(k)
    values["stoch_d"] = _series(d)
    values["willr"] = _series(talib.WILLR(high, low, close, timeperiod=p["willr"]))
    values["atr"] = _series(talib.ATR(high, low, close, timeperiod=p["atr"]))
    upper, mid, lower = talib.BBANDS(
        close,
        timeperiod=p["bb_length"],
        nbdevup=float(p["bb_std"]),
        nbdevdn=float(p["bb_std"]),
        matype=0,
    )
    values["bb_upper"] = _series(upper)
    values["bb_mid"] = _series(mid)
    values["bb_lower"] = _series(lower)
    for n in p["ema"]:
        values[f"ema_{n}"] = _series(talib.EMA(close, timeperiod=int(n)))
    for n in p["sma"]:
        values[f"sma_{n}"] = _series(talib.SMA(close, timeperiod=int(n)))
    values["adx"] = _series(talib.ADX(high, low, close, timeperiod=p["adx"]))
    values["obv"] = _series(talib.OBV(close, volume))
    if p["vwap"]:
        values["vwap"] = vwap_daily(ohlcv)
    if p["avwap_anchor"] is not None:
        values["avwap"] = anchored_vwap(ohlcv, p["avwap_anchor"])

    return features_frame(ohlcv, values, params_hash(MODULE, p))
