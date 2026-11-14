"""Swing high/low và nhãn cấu trúc HH/HL/LH/LL.

Định nghĩa (tham số `length` = L):
- Nến i là swing high nếu high[i] > mọi high trong L nến bên trái và high[i] >= mọi high
  trong L nến bên phải. Trái nghiêm ngặt, phải không nghiêm ngặt: khi có đỉnh bằng nhau
  liên tiếp, đỉnh đầu tiên được chọn. Swing low đối xứng với low.
- Swing chỉ được biết sau khi nến i+L đóng: known_at = open_time[i+L] + độ dài nến.
- Nhãn: so với swing cùng loại liền trước. Đỉnh cao hơn → HH, thấp hơn hoặc bằng → LH;
  đáy cao hơn hoặc bằng → HL, thấp hơn → LL. Swing đầu tiên mỗi loại không có nhãn.
"""

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration, check_ohlcv, events_frame, params_hash

MODULE = "structure"


def pivots(values: np.ndarray, length: int, *, high: bool) -> np.ndarray:
    """Chỉ số các pivot. `high=True` tìm đỉnh, False tìm đáy."""
    if length < 1:
        raise ValueError("length phải >= 1")
    v = values if high else -values
    n = len(v)
    out = []
    for i in range(length, n - length):
        left = v[i - length : i]
        right = v[i + 1 : i + length + 1]
        if v[i] > left.max() and v[i] >= right.max():
            out.append(i)
    return np.asarray(out, dtype=np.int64)


def swings(ohlcv: pl.DataFrame, length: int = 5) -> pl.DataFrame:
    """Events kind = swing_high | swing_low; price_low = price_high = giá swing.

    attrs: {"label": "HH"|"LH"|"HL"|"LL"|null, "index": i}
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    phash = params_hash(MODULE, {"length": length})
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"].to_list()
    rows = []
    for kind, col, is_high in (("swing_high", "high", True), ("swing_low", "low", False)):
        prices = ohlcv[col].to_numpy()
        previous = None
        for i in pivots(prices, length, high=is_high):
            price = float(prices[i])
            label = None
            if previous is not None:
                if is_high:
                    label = "HH" if price > previous else "LH"
                else:
                    label = "HL" if price >= previous else "LL"
            previous = price
            rows.append(
                {
                    "kind": kind,
                    "event_time": times[i],
                    "known_at": times[i + length] + duration,
                    "price_low": price,
                    "price_high": price,
                    "attrs": {"label": label, "index": int(i)},
                }
            )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=phash)


def swing_table(events: pl.DataFrame) -> pl.DataFrame:
    """Tiện ích: bảng swing gọn (kind, event_time, known_at, price, label, index)."""
    swing = events.filter(pl.col("kind").is_in(["swing_high", "swing_low"]))
    decoded = swing["attrs"].str.json_decode(pl.Struct({"label": pl.String(), "index": pl.Int64()}))
    return swing.select(
        "kind", "event_time", "known_at", pl.col("price_high").alias("price")
    ).with_columns(
        decoded.struct.field("label").alias("label"), decoded.struct.field("index").alias("index")
    )
