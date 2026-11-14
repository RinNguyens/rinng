"""Feature từ dữ liệu phái sinh, căn theo nến (docs/04-phuong-phap-phan-tich.md mục 3).

Mọi hàm nhận frame nến (một symbol, một khung bất kỳ) cùng frame dữ liệu phái sinh theo schema
curated (`funding`, `open_interest`, `long_short`, `mark_price`, `liquidations`) và trả Features
một dòng mỗi nến, riêng `liquidation_clusters` trả Events.

Căn thời gian (chống nhìn trước):
- Dữ liệu dạng điểm (funding, OI, long/short, mark price) được join asof backward theo lúc ĐÓNG
  nến: nến [open, close) nhận điểm mới nhất có thời gian <= close. Điểm đúng bằng close được
  dùng, điểm sau close thì không. known_at = close như mọi Features.
- Liquidation là dòng sự kiện: được cộng vào nến chứa nó, tức open <= time < close.
- Frame phái sinh được lọc theo `exchange`, `symbol` của nến. Bảng có nhiều `source` (hoặc
  `kind` với long/short) phải chỉ rõ bằng tham số, không trộn.

Định nghĩa:
- funding: `funding_rate` = mức gần nhất; `funding_z` = z-score của mức đó so với `z_window` kỳ
  funding gần nhất (tính trên chuỗi kỳ funding, không phải chuỗi nến); `funding_sum` = tổng
  `sum_periods` kỳ funding gần nhất.
- OI: `oi` = mức (mặc định `oi_base`, tính bằng coin, vì OI theo USD tăng theo giá dù số hợp
  đồng không đổi); `oi_change_pct` và `price_change_pct` = % thay đổi qua `n` nến;
  `price_oi_state` = long_build (giá lên, OI lên) | short_cover (giá lên, OI xuống) |
  short_build (giá xuống, OI lên) | long_liquidation (giá xuống, OI xuống); null nếu một trong
  hai thay đổi bằng 0 hoặc thiếu.
- long/short: `ls_ratio` = ratio gần nhất của `kind`; `ls_ratio_z` = z-score trượt `z_window` nến.
- basis: `premium` = (mark − index) / index từ tick mark price gần nhất; null nếu thiếu index.
- liquidation: side "sell" = vị thế long bị thanh lý, "buy" = short bị thanh lý. Tổng qty và
  notional (price * qty) mỗi phía trong nến; nến không có lệnh nào = 0.
- `liquidation_clusters`: Events `liquidation_cluster` khi tổng notional của nến vượt ngưỡng
  tính từ `window` nến TRƯỚC đó (không gồm nến hiện tại, để một cú đột biến không tự nâng
  ngưỡng): z-score >= `z_min`, hoặc > phân vị `quantile` nếu tham số này được đặt.
  event_time = nến đó, known_at = lúc đóng nến.

z-score: (x − mean) / std với std mẫu (ddof=1) trên cửa sổ đủ `window` giá trị khác null; std
quá nhỏ (<= 1e-9 * |mean|, ví dụ funding đứng yên ở 0,01%) cho null thay vì số khổng lồ.

Khoảng trống (`gaps`, frame meta/gaps: exchange, symbol, dataset, start, end): nến [open, close)
giao với khoảng (start, end) của dataset tương ứng thì feature của dataset đó là null. Cửa sổ
trượt (z-score, % thay đổi, ngưỡng cluster) chứa một nến null cũng cho null, nên feature chỉ
được tính trên đoạn liền không có khoảng trống. `recorded_at` của gap không được xét: gap mô
tả dữ liệu vốn đã thiếu, không phải thông tin mới.

Giới hạn (docs/04 mục 3.7): bảng giá + OI là suy diễn, OI không có hướng; tín hiệu funding cực
đoan chưa có bằng chứng bình duyệt; liquidation từ stream forceOrder chỉ là cận dưới (mỗi giây
một lệnh), và nến trước khi bắt đầu thu thập sẽ là 0 nếu không khai báo gap. Join asof không
giới hạn độ cũ: nguồn ngừng cập nhật mà không có gap thì giá trị cũ bị kéo dài.
"""

from collections.abc import Mapping
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

MODULE = "derivatives"

PRICE_OI_STATES = {
    (1, 1): "long_build",
    (1, -1): "short_cover",
    (-1, 1): "short_build",
    (-1, -1): "long_liquidation",
}


# ---------------------------------------------------------------- tiện ích nội bộ


def _scope(ohlcv: pl.DataFrame, data: pl.DataFrame, **filters: str | None) -> pl.DataFrame:
    """Lọc frame phái sinh theo exchange/symbol của nến và các cột phân biệt (source, kind)."""
    symbol, _ = check_ohlcv(ohlcv)
    out = data
    if "symbol" in out.columns:
        out = out.filter(pl.col("symbol") == symbol)
    if "exchange" in out.columns and "exchange" in ohlcv.columns:
        out = out.filter(pl.col("exchange") == ohlcv["exchange"][0])
    for col, value in filters.items():
        if col not in out.columns:
            continue
        if value is not None:
            out = out.filter(pl.col(col) == value)
        elif out[col].n_unique() > 1:
            raise ValueError(f"có nhiều {col} {sorted(out[col].unique().to_list())}; chọn một")
    return out


def _asof(ohlcv: pl.DataFrame, data: pl.DataFrame, time_col: str, cols: list[str]) -> pl.DataFrame:
    """Giá trị mới nhất có thời gian <= lúc đóng nến, một dòng mỗi nến theo đúng thứ tự nến."""
    _, timeframe = check_ohlcv(ohlcv)
    left = ohlcv.select((pl.col("open_time") + bar_duration(timeframe)).alias("_close"))
    right = data.select(pl.col(time_col).alias("_t"), *cols).sort("_t")
    joined = left.join_asof(right, left_on="_close", right_on="_t", strategy="backward")
    return joined.select(cols)


def gap_mask(ohlcv: pl.DataFrame, gaps: pl.DataFrame | None, dataset: str) -> np.ndarray:
    """True ở nến [open, close) giao với một khoảng (start, end) của `dataset` trong `gaps`."""
    symbol, timeframe = check_ohlcv(ohlcv)
    mask = np.zeros(ohlcv.height, dtype=bool)
    if gaps is None or gaps.is_empty():
        return mask
    g = gaps.filter((pl.col("dataset") == dataset) & (pl.col("symbol") == symbol))
    if "exchange" in g.columns and "exchange" in ohlcv.columns:
        g = g.filter(pl.col("exchange") == ohlcv["exchange"][0])
    opens = ohlcv["open_time"].dt.epoch("ms").to_numpy()
    closes = opens + int(bar_duration(timeframe).total_seconds() * 1000)
    starts = g["start"].dt.epoch("ms").to_numpy()
    ends = g["end"].dt.epoch("ms").to_numpy()
    for start, end in zip(starts, ends, strict=True):
        mask |= (opens < end) & (closes > start)
    return mask


def _null_where(s: pl.Series, mask: np.ndarray) -> pl.Series:
    if not mask.any():
        return s
    return pl.select(pl.when(pl.Series(mask)).then(None).otherwise(s).alias(s.name)).to_series()


def _zscore(x: pl.Expr, window: int) -> pl.Expr:
    mean = x.rolling_mean(window)
    std = x.rolling_std(window)
    return pl.when((std > 0) & (std > 1e-9 * mean.abs())).then((x - mean) / std)


def _check_window(**windows: int) -> None:
    for name, value in windows.items():
        if value < 1:
            raise ValueError(f"{name} phải >= 1")


def _features(
    ohlcv: pl.DataFrame, values: dict[str, pl.Series], params: Mapping[str, Any]
) -> pl.DataFrame:
    return features_frame(ohlcv, values, params_hash(MODULE, params))


# ---------------------------------------------------------------- funding


def funding_features(
    ohlcv: pl.DataFrame,
    funding: pl.DataFrame,
    *,
    z_window: int = 30,
    sum_periods: int = 21,
    gaps: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Features: funding_rate, funding_z, funding_sum (xem docstring module)."""
    _check_window(z_window=z_window, sum_periods=sum_periods)
    data = (
        _scope(ohlcv, funding)
        .sort("funding_time")
        .with_columns(
            _zscore(pl.col("rate"), z_window).alias("funding_z"),
            pl.col("rate").rolling_sum(sum_periods).alias("funding_sum"),
        )
    )
    aligned = _asof(ohlcv, data, "funding_time", ["rate", "funding_z", "funding_sum"])
    mask = gap_mask(ohlcv, gaps, "funding")
    values = {
        "funding_rate": _null_where(aligned["rate"], mask),
        "funding_z": _null_where(aligned["funding_z"], mask),
        "funding_sum": _null_where(aligned["funding_sum"], mask),
    }
    params = {"kind": "funding", "z_window": z_window, "sum_periods": sum_periods}
    return _features(ohlcv, values, params)


# ---------------------------------------------------------------- open interest


def open_interest_features(
    ohlcv: pl.DataFrame,
    open_interest: pl.DataFrame,
    *,
    n: int = 24,
    value: str = "oi_base",
    source: str | None = None,
    gaps: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Features: oi, oi_change_pct, price_change_pct, price_oi_state (xem docstring module)."""
    _check_window(n=n)
    if value not in ("oi_base", "oi_value"):
        raise ValueError("value phải là oi_base hoặc oi_value")
    data = _scope(ohlcv, open_interest, source=source)
    mask = gap_mask(ohlcv, gaps, "open_interest")
    oi = _null_where(_asof(ohlcv, data, "time", [value])[value].alias("oi"), mask)
    # % thay đổi null nếu bất kỳ nến nào trong n+1 nến của cửa sổ rơi vào khoảng trống.
    window_gap = pl.Series(mask).cast(pl.Int8).rolling_max(n + 1, min_samples=1).cast(pl.Boolean)
    frame = pl.DataFrame({"oi": oi, "close": ohlcv["close"], "_gap": window_gap}).with_columns(
        pl.when(~pl.col("_gap")).then(pl.col("oi") / pl.col("oi").shift(n) - 1).alias("oi_chg"),
        (pl.col("close") / pl.col("close").shift(n) - 1).alias("px_chg"),
    )
    p, o = pl.col("px_chg").sign(), pl.col("oi_chg").sign()
    expr = pl.lit(None, dtype=pl.String())
    for (dp, doi), label in PRICE_OI_STATES.items():
        expr = pl.when((p == dp) & (o == doi)).then(pl.lit(label)).otherwise(expr)
    state = frame.select(expr.alias("price_oi_state")).to_series()
    values = {
        "oi": frame["oi"],
        "oi_change_pct": frame["oi_chg"],
        "price_change_pct": frame["px_chg"],
        "price_oi_state": state,
    }
    params = {"kind": "open_interest", "n": n, "value": value, "source": source}
    return _features(ohlcv, values, params)


# ---------------------------------------------------------------- long/short


def long_short_features(
    ohlcv: pl.DataFrame,
    long_short: pl.DataFrame,
    *,
    kind: str = "global_account",
    source: str | None = None,
    z_window: int = 48,
    gaps: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Features: ls_ratio, ls_ratio_z (z-score trượt theo nến)."""
    _check_window(z_window=z_window)
    data = _scope(ohlcv, long_short, source=source, kind=kind)
    mask = gap_mask(ohlcv, gaps, "long_short")
    ratio = _null_where(_asof(ohlcv, data, "time", ["ratio"])["ratio"], mask)
    z = pl.DataFrame({"r": ratio}).select(_zscore(pl.col("r"), z_window)).to_series()
    values = {"ls_ratio": ratio, "ls_ratio_z": z}
    params = {"kind": "long_short", "ls_kind": kind, "source": source, "z_window": z_window}
    return _features(ohlcv, values, params)


# ---------------------------------------------------------------- basis / premium


def basis_features(
    ohlcv: pl.DataFrame, mark_price: pl.DataFrame, *, gaps: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Features: mark_price, index_price, premium = (mark − index) / index."""
    data = _scope(ohlcv, mark_price)
    mask = gap_mask(ohlcv, gaps, "mark_price")
    aligned = _asof(ohlcv, data, "time", ["mark_price", "index_price"])
    mark = _null_where(aligned["mark_price"], mask)
    index = _null_where(aligned["index_price"], mask)
    premium = pl.DataFrame({"m": mark, "i": index}).select(
        pl.when(pl.col("i") > 0).then((pl.col("m") - pl.col("i")) / pl.col("i"))
    )
    values = {"mark_price": mark, "index_price": index, "premium": premium.to_series()}
    return _features(ohlcv, values, {"kind": "basis"})


# ---------------------------------------------------------------- liquidation


def _liquidations_by_bar(ohlcv: pl.DataFrame, liquidations: pl.DataFrame) -> pl.DataFrame:
    """Tổng theo nến (open <= time < close), một dòng mỗi nến; nến không có lệnh = 0."""
    _, timeframe = check_ohlcv(ohlcv)
    duration = bar_duration(timeframe)
    bars = ohlcv.select("open_time")
    data = (
        _scope(ohlcv, liquidations)
        .select("time", pl.col("side").str.to_lowercase(), "price", "qty")
        .sort("time")
        .join_asof(bars, left_on="time", right_on="open_time", strategy="backward")
        .filter(pl.col("time") < pl.col("open_time") + duration)
        .with_columns((pl.col("price") * pl.col("qty")).alias("notional"))
    )
    is_long = pl.col("side") == "sell"
    is_short = pl.col("side") == "buy"
    agg = data.group_by("open_time").agg(
        pl.col("qty").filter(is_long).sum().alias("liq_long_qty"),
        pl.col("qty").filter(is_short).sum().alias("liq_short_qty"),
        pl.col("notional").filter(is_long).sum().alias("liq_long_notional"),
        pl.col("notional").filter(is_short).sum().alias("liq_short_notional"),
        pl.col("price").min().alias("price_min"),
        pl.col("price").max().alias("price_max"),
    )
    sums = ["liq_long_qty", "liq_short_qty", "liq_long_notional", "liq_short_notional"]
    return (
        bars.join(agg, on="open_time", how="left", maintain_order="left")
        .with_columns(pl.col(sums).fill_null(0.0))
        .with_columns(
            (pl.col("liq_long_notional") + pl.col("liq_short_notional")).alias("liq_notional")
        )
    )


LIQ_COLUMNS = (
    "liq_long_qty",
    "liq_short_qty",
    "liq_long_notional",
    "liq_short_notional",
    "liq_notional",
)


def liquidation_features(
    ohlcv: pl.DataFrame, liquidations: pl.DataFrame, *, gaps: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Features: các cột trong `LIQ_COLUMNS` (qty/notional long, short và tổng notional)."""
    per_bar = _liquidations_by_bar(ohlcv, liquidations)
    mask = gap_mask(ohlcv, gaps, "liquidations")
    values = {c: _null_where(per_bar[c], mask) for c in LIQ_COLUMNS}
    return _features(ohlcv, values, {"kind": "liquidation"})


def liquidation_clusters(
    ohlcv: pl.DataFrame,
    liquidations: pl.DataFrame,
    *,
    window: int = 48,
    z_min: float = 3.0,
    quantile: float | None = None,
    min_notional: float = 0.0,
    gaps: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Events kind = liquidation_cluster.

    Điều kiện: liq_notional > min_notional và (quantile None) z-score so với `window` nến
    trước >= z_min, hoặc (quantile đặt) liq_notional > phân vị `quantile` của `window` nến
    trước. price_low/high = giá thanh lý thấp/cao nhất trong nến.
    attrs: {"notional", "long_notional", "short_notional", "score", "method"}; score là z-score
    hoặc ngưỡng phân vị.
    """
    _check_window(window=window)
    if quantile is not None and not 0 < quantile < 1:
        raise ValueError("quantile phải trong (0, 1)")
    symbol, timeframe = check_ohlcv(ohlcv)
    method = "z" if quantile is None else "quantile"
    params = {
        "kind": "liquidation_cluster",
        "window": window,
        "z_min": z_min if quantile is None else None,
        "quantile": quantile,
        "min_notional": min_notional,
    }
    phash = params_hash(MODULE, params)
    per_bar = _liquidations_by_bar(ohlcv, liquidations)
    mask = gap_mask(ohlcv, gaps, "liquidations")
    x = _null_where(per_bar["liq_notional"], mask)
    prev = pl.col("x").shift(1)
    if quantile is None:
        mean, std = prev.rolling_mean(window), prev.rolling_std(window)
        score = pl.when(std > 0).then((pl.col("x") - mean) / std)
        hit = score >= z_min
    else:
        score = prev.rolling_quantile(quantile, "linear", window)
        hit = pl.col("x") > score
    scored = pl.DataFrame({"x": x}).with_columns(
        score.alias("score"), (hit & (pl.col("x") > min_notional)).fill_null(False).alias("hit")
    )
    duration = bar_duration(timeframe)
    rows = []
    for i in np.flatnonzero(scored["hit"].to_numpy()):
        bar = per_bar.row(int(i), named=True)
        rows.append(
            {
                "kind": "liquidation_cluster",
                "event_time": bar["open_time"],
                "known_at": bar["open_time"] + duration,
                "price_low": bar["price_min"],
                "price_high": bar["price_max"],
                "attrs": {
                    "notional": bar["liq_notional"],
                    "long_notional": bar["liq_long_notional"],
                    "short_notional": bar["liq_short_notional"],
                    "score": scored["score"][int(i)],
                    "method": method,
                },
            }
        )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=phash)
