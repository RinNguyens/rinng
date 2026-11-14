"""Các THÀNH PHẦN đo được của Wyckoff (docs/04-phuong-phap-phan-tich.md mục 4).

Không gắn nhãn cả sơ đồ (accumulation/distribution, phase A–E): theo docs/04 mục 4.7 nhãn đó
chỉ rõ khi nhìn lại. Module chỉ xuất các mảnh có định nghĩa cơ học để kiểm định riêng từng cái.

Đại lượng chung (tham số `window` = W, `atr_length` = A):
- ATR: Wilder, giá trị đầu tại nến A−1 = trung bình A true range đầu tiên.
- `volume_z`: z-score volume trên W nến gần nhất (gồm nến hiện tại), std mẫu.
- `spread_atr`: (high − low) / ATR của nến TRƯỚC, để biên độ nến hiện tại không tự nâng mẫu số.
- `spread_z`: z-score của spread_atr trên W nến.
- `effort_result_gap` = volume_z − spread_z: dương lớn = nhiều effort (volume) mà ít result
  (biên độ); âm lớn = biên độ lớn với volume thấp.
- `clv`: (close − low) / (high − low); 0 = đóng ở đáy, 1 = đóng ở đỉnh; null nếu high = low.

Sự kiện (Events):
- `selling_climax` / `buying_climax` (hàm `climaxes`): volume_z >= `volume_z_min` và
  spread_atr >= `spread_min`; chiều theo nến: close < open là selling, close > open là buying,
  nến doji bỏ qua. Không đòi xu hướng trước đó. known_at = lúc đóng nến climax.
- `trading_range` (hàm `trading_ranges`): khi không có range nào đang dựng hoặc còn hiệu lực,
  một nến climax c mở range. Biên = [min low, max high] của nến c..c+R (R = `reaction_bars`,
  tương ứng SC/BC và AR). Range được xác nhận khi `min_bars` = N nến liên tiếp sau đó đều có
  close nằm trong biên (tính cả biên); một close ra ngoài trước khi đủ N thì bỏ range.
  event_time = nến climax, known_at = lúc đóng nến thứ N.
- `spring` / `upthrust`: sau khi range được xác nhận, nến b có low < biên dưới (high > biên
  trên) mở một lần phá; nếu trong tối đa M = `reclaim_bars` nến tính cả b có một nến j đóng
  cửa trong biên thì có spring (upthrust). event_time = nến b, known_at = lúc đóng nến j.
  Không đóng lại trong M nến thì range bị phá: `invalidated_at` của trading_range = lúc đóng
  nến b+M−1. Mỗi phía theo dõi độc lập; range có thể có nhiều spring/upthrust.

Mọi ngưỡng là tự chọn (docs/04 mục 4.7) và càng nhiều ngưỡng càng dễ overfit. Bằng chứng học
thuật về lợi thế của Wyckoff sau chi phí: chưa xác minh. Range ở đây chỉ là một định nghĩa cơ
học, không khẳng định đó là tích lũy hay phân phối.
"""

from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.types import (
    bar_duration,
    check_ohlcv,
    events_frame,
    features_frame,
    params_hash,
)

MODULE = "wyckoff"


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    """ATR kiểu Wilder; NaN trước nến length−1."""
    if length < 1:
        raise ValueError("length phải >= 1")
    n = len(high)
    tr = np.empty(n)
    if n == 0:
        return tr
    tr[0] = high[0] - low[0]
    prev = close[:-1]
    tr[1:] = np.maximum.reduce(
        [high[1:] - low[1:], np.abs(high[1:] - prev), np.abs(low[1:] - prev)]
    )
    out = np.full(n, np.nan)
    if n >= length:
        out[length - 1] = tr[:length].mean()
        for i in range(length, n):
            out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


def rolling_zscore(values: np.ndarray, window: int) -> np.ndarray:
    """z-score trên `window` giá trị gần nhất (gồm hiện tại); NaN nếu chưa đủ hoặc std = 0."""
    if window < 2:
        raise ValueError("window phải >= 2")
    s = pl.Series(values, dtype=pl.Float64(), nan_to_null=True)
    mean = s.rolling_mean(window).to_numpy()
    std = s.rolling_std(window).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (np.asarray(values, dtype=float) - mean) / std
    return np.where(std > 0, z, np.nan)


def _measures(ohlcv: pl.DataFrame, window: int, atr_length: int) -> dict[str, np.ndarray]:
    high = ohlcv["high"].to_numpy()
    low = ohlcv["low"].to_numpy()
    close = ohlcv["close"].to_numpy()
    a = atr(high, low, close, atr_length)
    atr_prev = np.concatenate([[np.nan], a[:-1]])
    rng = high - low
    with np.errstate(divide="ignore", invalid="ignore"):
        spread_atr = np.where(atr_prev > 0, rng / atr_prev, np.nan)
        clv = np.where(rng > 0, (close - low) / rng, np.nan)
    volume_z = rolling_zscore(ohlcv["volume"].to_numpy(), window)
    spread_z = rolling_zscore(spread_atr, window)
    return {
        "atr_prev": atr_prev,
        "volume_z": volume_z,
        "spread_atr": spread_atr,
        "spread_z": spread_z,
        "effort_result_gap": volume_z - spread_z,
        "clv": clv,
    }


def _series(values: np.ndarray) -> pl.Series:
    return pl.Series(values, dtype=pl.Float64(), nan_to_null=True)


def effort_result(ohlcv: pl.DataFrame, *, window: int = 50, atr_length: int = 14) -> pl.DataFrame:
    """Features: volume_z, spread_atr, spread_z, effort_result_gap, clv."""
    check_ohlcv(ohlcv)
    m = _measures(ohlcv, window, atr_length)
    cols = ("volume_z", "spread_atr", "spread_z", "effort_result_gap", "clv")
    phash = params_hash(MODULE, {"kind": "effort_result", "window": window, "atr": atr_length})
    return features_frame(ohlcv, {c: _series(m[c]) for c in cols}, phash)


def _climax_flags(
    ohlcv: pl.DataFrame, m: dict[str, np.ndarray], volume_z_min: float, spread_min: float
) -> np.ndarray:
    """+1 buying climax, −1 selling climax, 0 không."""
    with np.errstate(invalid="ignore"):
        big = (m["volume_z"] >= volume_z_min) & (m["spread_atr"] >= spread_min)
    direction = np.sign(ohlcv["close"].to_numpy() - ohlcv["open"].to_numpy())
    return np.where(big, direction, 0).astype(int)


def _climax_params(window, atr_length, volume_z_min, spread_min) -> dict[str, Any]:
    return {
        "window": window,
        "atr": atr_length,
        "volume_z_min": volume_z_min,
        "spread_min": spread_min,
    }


def climaxes(
    ohlcv: pl.DataFrame,
    *,
    window: int = 50,
    atr_length: int = 14,
    volume_z_min: float = 2.5,
    spread_min: float = 1.8,
) -> pl.DataFrame:
    """Events kind = selling_climax | buying_climax; price_low/high = low/high của nến.

    attrs: {"index", "volume_z", "spread_atr", "clv"}
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {"kind": "climax", **_climax_params(window, atr_length, volume_z_min, spread_min)}
    m = _measures(ohlcv, window, atr_length)
    flags = _climax_flags(ohlcv, m, volume_z_min, spread_min)
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    high, low = ohlcv["high"].to_numpy(), ohlcv["low"].to_numpy()
    rows = []
    for i in np.flatnonzero(flags):
        rows.append(
            {
                "kind": "buying_climax" if flags[i] > 0 else "selling_climax",
                "event_time": times[i],
                "known_at": times[i] + duration,
                "price_low": float(low[i]),
                "price_high": float(high[i]),
                "attrs": {
                    "index": int(i),
                    "volume_z": float(m["volume_z"][i]),
                    "spread_atr": float(m["spread_atr"][i]),
                    "clv": None if np.isnan(m["clv"][i]) else float(m["clv"][i]),
                },
            }
        )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))


def trading_ranges(
    ohlcv: pl.DataFrame,
    *,
    window: int = 50,
    atr_length: int = 14,
    volume_z_min: float = 2.5,
    spread_min: float = 1.8,
    reaction_bars: int = 5,
    min_bars: int = 10,
    reclaim_bars: int = 3,
) -> pl.DataFrame:
    """Events kind = trading_range | spring | upthrust (định nghĩa ở docstring module).

    trading_range: price_low/high = biên; attrs {"climax", "origin_index", "confirm_index"}.
    spring/upthrust: price_low/high = cực trị của lần phá và biên bị phá;
    attrs {"break_index", "reclaim_index", "reclaim_bars", "penetration", "penetration_atr",
    "range_low", "range_high"}.
    """
    if reaction_bars < 0 or min_bars < 1 or reclaim_bars < 1:
        raise ValueError("cần reaction_bars >= 0, min_bars >= 1, reclaim_bars >= 1")
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {
        "kind": "trading_range",
        **_climax_params(window, atr_length, volume_z_min, spread_min),
        "reaction_bars": reaction_bars,
        "min_bars": min_bars,
        "reclaim_bars": reclaim_bars,
    }
    m = _measures(ohlcv, window, atr_length)
    flags = _climax_flags(ohlcv, m, volume_z_min, spread_min)
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    high = ohlcv["high"].to_numpy()
    low = ohlcv["low"].to_numpy()
    close = ohlcv["close"].to_numpy()

    rows: list[dict[str, Any]] = []
    state = "idle"
    origin = count = 0
    lo = hi = 0.0
    current: dict[str, Any] | None = None
    # lần phá đang chờ mỗi phía: (chỉ số nến phá, cực trị)
    pending: dict[str, tuple[int, float] | None] = {"spring": None, "upthrust": None}

    for i in range(len(close)):
        if state == "reaction":
            lo, hi = min(lo, low[i]), max(hi, high[i])
            if i == origin + reaction_bars:
                state, count = "confirm", 0
        elif state == "confirm":
            if lo <= close[i] <= hi:
                count += 1
                if count == min_bars:
                    current = {
                        "kind": "trading_range",
                        "event_time": times[origin],
                        "known_at": times[i] + duration,
                        "price_low": float(lo),
                        "price_high": float(hi),
                        "attrs": {
                            "climax": "buying" if flags[origin] > 0 else "selling",
                            "origin_index": origin,
                            "confirm_index": i,
                        },
                    }
                    rows.append(current)
                    pending = {"spring": None, "upthrust": None}
                    state = "active"
            else:
                state = "idle"
        elif state == "active":
            for kind in ("spring", "upthrust"):
                broke = low[i] < lo if kind == "spring" else high[i] > hi
                if pending[kind] is None and broke:
                    pending[kind] = (i, low[i] if kind == "spring" else high[i])
                if pending[kind] is None:
                    continue
                b, extreme = pending[kind]
                extreme = min(extreme, low[i]) if kind == "spring" else max(extreme, high[i])
                pending[kind] = (b, extreme)
                if lo <= close[i] <= hi:
                    edge = lo if kind == "spring" else hi
                    penetration = abs(edge - extreme)
                    a = m["atr_prev"][b]
                    rows.append(
                        {
                            "kind": kind,
                            "event_time": times[b],
                            "known_at": times[i] + duration,
                            "price_low": float(min(edge, extreme)),
                            "price_high": float(max(edge, extreme)),
                            "attrs": {
                                "break_index": b,
                                "reclaim_index": i,
                                "reclaim_bars": i - b + 1,
                                "penetration": float(penetration),
                                "penetration_atr": None
                                if np.isnan(a) or a <= 0
                                else float(penetration / a),
                                "range_low": float(lo),
                                "range_high": float(hi),
                            },
                        }
                    )
                    pending[kind] = None
                elif i - b + 1 >= reclaim_bars and current is not None:
                    current["invalidated_at"] = times[i] + duration
                    state = "idle"
                    break
        if state == "idle" and flags[i] != 0:
            origin, lo, hi = i, low[i], high[i]
            state, count = ("reaction", 0) if reaction_bars > 0 else ("confirm", 0)
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))
