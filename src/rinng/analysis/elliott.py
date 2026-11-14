"""Thành phần đo được của Elliott Wave (docs/04-phuong-phap-phan-tich.md mục 5).

Không tự chọn một cách đếm sóng duy nhất: module chỉ dựng pivot, kiểm quy tắc cứng và liệt kê
mọi ứng viên thỏa quy tắc để kiểm định như một feature mô tả.

Zigzag (tham số `threshold`, `mode`):
- mode "percent": đảo chiều xuống từ đỉnh ứng viên H khi low[i] <= H * (1 − threshold); đảo
  chiều lên từ đáy ứng viên L khi high[i] >= L * (1 + threshold).
- mode "atr": như trên nhưng khoảng cách là threshold * ATR(atr_length) của nến i (Wilder,
  `rinng.analysis.wyckoff.atr`); chưa có ATR thì chưa xác nhận được pivot.
- Đỉnh ứng viên là high lớn nhất kể từ pivot trước (bằng nhau thì lấy nến đầu tiên); đáy đối
  xứng. Pivot phải nằm ở nến TRƯỚC nến xác nhận: nến vừa lập cực trị mới thì chưa đảo chiều
  được trong chính nến đó (không biết high hay low đến trước).
- Lúc đầu chưa có hướng: pivot đầu tiên là cực trị nào bị vượt ngưỡng đảo chiều trước; nếu
  cùng một nến thì lấy cực trị xảy ra sớm hơn.
- known_at = lúc đóng nến i mà ngưỡng đảo chiều bị vượt. Pivot cuối (đang chạy) không xuất.

Quy tắc cứng cho impulse 6 pivot P0..P5 (đổi dấu khi sóng 1 đi xuống, `log=True` dùng log giá):
1. `wave2_within_wave1`: P2 không vượt gốc sóng 1, tức P2 > P0 (chạm bằng là sai).
2. `wave3_not_shortest`: |sóng 3| >= min(|sóng 1|, |sóng 5|).
3. `wave4_no_overlap`: P4 > P1 (sóng 4 không vào vùng giá sóng 1; không xét diagonal).
Quy tắc 1 và 3 không đổi theo thang giá; quy tắc 2 phụ thuộc thang log hay tuyến tính.

Tỷ lệ Fibonacci (độ dài sóng tuyệt đối): wave2/wave1, wave3/wave1, wave4/wave3, wave5/wave1,
wave5/(P0→P3). Chỉ để mô tả, không chấm điểm.

`impulse_candidates`: mọi cửa sổ 6 pivot zigzag liên tiếp thỏa cả ba quy tắc, cả tăng và
giảm, thành Events `impulse_candidate`; event_time = nến P5, known_at = known_at của P5 (lúc
P5 được zigzag xác nhận). Các cửa sổ chồng nhau đều được giữ.

Giới hạn (docs/04 mục 5.7, 5.8): bằng chứng thực nghiệm về khả năng dự báo yếu; kết quả rất
nhạy với ngưỡng zigzag và thang giá; ba quy tắc cứng lọc rất ít nên gần như chuỗi nào cũng có
ứng viên. Không kiểm cấu trúc con (5-3-5-3-5) hay mẫu điều chỉnh.
"""

from collections.abc import Sequence
from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration, check_ohlcv, events_frame, params_hash
from rinng.analysis.wyckoff import atr

MODULE = "elliott"

RULES = ("wave2_within_wave1", "wave3_not_shortest", "wave4_no_overlap")


def zigzag_pivots(
    high: np.ndarray, low: np.ndarray, distance: np.ndarray | None = None, *, pct: float = 0.0
) -> list[tuple[int, str, float, int]]:
    """Pivot xen kẽ (index, "H"|"L", giá, index xác nhận).

    `distance` (mảng cùng độ dài, NaN = chưa xác nhận được) cho ngưỡng tuyệt đối theo nến;
    nếu None thì dùng ngưỡng tương đối `pct`.
    """
    n = len(high)

    def down(peak: float, i: int) -> bool:
        if distance is None:
            return low[i] <= peak * (1 - pct)
        d = distance[i]
        return not np.isnan(d) and peak - low[i] >= d

    def up(trough: float, i: int) -> bool:
        if distance is None:
            return high[i] >= trough * (1 + pct)
        d = distance[i]
        return not np.isnan(d) and high[i] - trough >= d

    out: list[tuple[int, str, float, int]] = []
    direction = 0  # 1: pivot cuối là đáy, đang tìm đỉnh; -1: ngược lại
    hi_i = lo_i = 0
    for i in range(n):
        if direction >= 0 and high[i] > high[hi_i]:
            hi_i = i
        if direction <= 0 and low[i] < low[lo_i]:
            lo_i = i
        while True:
            go_up = direction <= 0 and lo_i < i and up(low[lo_i], i)
            go_down = direction >= 0 and hi_i < i and down(high[hi_i], i)
            if direction == 0 and go_up and go_down:
                go_up = lo_i <= hi_i
                go_down = not go_up
            if go_up:
                out.append((lo_i, "L", float(low[lo_i]), i))
                direction = 1
                hi_i = lo_i + 1 + int(np.argmax(high[lo_i + 1 : i + 1]))
            elif go_down:
                out.append((hi_i, "H", float(high[hi_i]), i))
                direction = -1
                lo_i = hi_i + 1 + int(np.argmin(low[hi_i + 1 : i + 1]))
            else:
                break
    return out


def _zigzag_params(threshold: float, mode: str, atr_length: int) -> dict[str, Any]:
    if mode not in ("percent", "atr"):
        raise ValueError("mode phải là percent hoặc atr")
    if threshold <= 0 or (mode == "percent" and threshold >= 1):
        raise ValueError("threshold không hợp lệ")
    return {"threshold": threshold, "mode": mode, "atr": atr_length if mode == "atr" else None}


def _pivots(ohlcv: pl.DataFrame, threshold: float, mode: str, atr_length: int):
    high = ohlcv["high"].to_numpy()
    low = ohlcv["low"].to_numpy()
    if mode == "percent":
        return zigzag_pivots(high, low, pct=threshold)
    a = atr(high, low, ohlcv["close"].to_numpy(), atr_length)
    return zigzag_pivots(high, low, threshold * a)


def zigzag(
    ohlcv: pl.DataFrame, *, threshold: float = 0.05, mode: str = "percent", atr_length: int = 14
) -> pl.DataFrame:
    """Events kind = zigzag_high | zigzag_low; price_low = price_high = giá pivot.

    attrs: {"index", "confirm_index"}
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {"kind": "zigzag", **_zigzag_params(threshold, mode, atr_length)}
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    rows = [
        {
            "kind": "zigzag_high" if kind == "H" else "zigzag_low",
            "event_time": times[i],
            "known_at": times[c] + duration,
            "price_low": price,
            "price_high": price,
            "attrs": {"index": i, "confirm_index": c},
        }
        for i, kind, price, c in _pivots(ohlcv, threshold, mode, atr_length)
    ]
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))


def zigzag_table(events: pl.DataFrame) -> pl.DataFrame:
    """Tiện ích: bảng pivot gọn (kind, event_time, known_at, price, index) theo thứ tự thời gian."""
    piv = events.filter(pl.col("kind").is_in(["zigzag_high", "zigzag_low"]))
    decoded = piv["attrs"].str.json_decode(pl.Struct({"index": pl.Int64()}))
    return (
        piv.select("kind", "event_time", "known_at", pl.col("price_high").alias("price"))
        .with_columns(decoded.struct.field("index").alias("index"))
        .sort("event_time")
    )


def _signed(prices: Sequence[float], log: bool) -> np.ndarray:
    p = np.asarray(prices, dtype=float)
    if p.shape != (6,):
        raise ValueError("cần đúng 6 pivot P0..P5")
    if log:
        if (p <= 0).any():
            raise ValueError("log cần giá dương")
        p = np.log(p)
    q = p if p[1] > p[0] else -p
    legs = np.diff(q)
    if not ((legs[0::2] > 0).all() and (legs[1::2] < 0).all()):
        raise ValueError("6 pivot phải xen kẽ đỉnh/đáy")
    return q


def impulse_rules(prices: Sequence[float], *, log: bool = True) -> dict[str, bool]:
    """Ba quy tắc cứng của impulse cho P0..P5; mỗi quy tắc đúng/sai riêng."""
    q = _signed(prices, log)
    w1, w3, w5 = q[1] - q[0], q[3] - q[2], q[5] - q[4]
    return {
        "wave2_within_wave1": bool(q[2] > q[0]),
        "wave3_not_shortest": bool(w3 >= min(w1, w5)),
        "wave4_no_overlap": bool(q[4] > q[1]),
    }


def impulse_ratios(prices: Sequence[float], *, log: bool = False) -> dict[str, float]:
    """Tỷ lệ giữa độ dài các sóng (giá trị tuyệt đối)."""
    q = _signed(prices, log)
    w = np.abs(np.diff(q))
    return {
        "wave2_wave1": float(w[1] / w[0]),
        "wave3_wave1": float(w[2] / w[0]),
        "wave4_wave3": float(w[3] / w[2]),
        "wave5_wave1": float(w[4] / w[0]),
        "wave5_wave1to3": float(w[4] / abs(q[3] - q[0])),
    }


def impulse_candidates(
    ohlcv: pl.DataFrame,
    *,
    threshold: float = 0.05,
    mode: str = "percent",
    atr_length: int = 14,
    log: bool = True,
) -> pl.DataFrame:
    """Events kind = impulse_candidate; price_low/high = min/max của 6 pivot.

    attrs: {"direction": "up"|"down", "indices", "prices", "ratios"} với ratios tính cùng thang
    với quy tắc (`log`).
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    params = {"kind": "impulse", **_zigzag_params(threshold, mode, atr_length), "log": log}
    piv = _pivots(ohlcv, threshold, mode, atr_length)
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    rows = []
    for k in range(len(piv) - 5):
        window = piv[k : k + 6]
        prices = [p[2] for p in window]
        if not all(impulse_rules(prices, log=log).values()):
            continue
        last = window[-1]
        rows.append(
            {
                "kind": "impulse_candidate",
                "event_time": times[last[0]],
                "known_at": times[last[3]] + duration,
                "price_low": min(prices),
                "price_high": max(prices),
                "attrs": {
                    "direction": "up" if prices[1] > prices[0] else "down",
                    "indices": [p[0] for p in window],
                    "prices": prices,
                    "ratios": impulse_ratios(prices, log=log),
                },
                "id": window[0][0],
            }
        )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=params_hash(MODULE, params))
