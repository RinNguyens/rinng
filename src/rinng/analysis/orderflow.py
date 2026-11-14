"""Order flow: delta, CVD, footprint, imbalance chéo, stacked imbalance, absorption.

Quy ước phía taker: `taker_buy_volume` của nến là volume taker MUA; ở trades,
`is_buyer_maker=True` nghĩa là người mua là maker, tức taker BÁN (docs/04 mục 2.2).

Từ nến (`delta_features`, Features, known_at = đóng nến):
- `delta` = taker buy − taker sell = 2 * taker_buy_volume − volume.
- `cvd` = tổng cộng dồn của delta từ đầu dữ liệu (`cvd_reset=None`), hoặc khởi động lại
  mỗi ngày UTC (`"day"`) / mỗi tuần từ thứ Hai 00:00 UTC (`"week"`). Mức tuyệt đối của CVD
  phụ thuộc điểm bắt đầu cộng dồn, chỉ nên dùng thay đổi hoặc độ dốc.
- `delta_pct` = delta / volume (null khi volume = 0), trong [-1, 1].

Từ trades:
- `trade_bars`: gộp trades theo `open_time` của khung (trade thuộc nến chứa `time` của nó):
  volume, buy_volume, sell_volume, delta, n_trades.
- `footprint`: bảng (open_time, price_bin, buy_volume, sell_volume, delta), chỉ gồm mức có
  giao dịch; price_bin = cạnh dưới bin, lưới neo tại 0 với `bin_size` tuyệt đối.
- `diagonal_imbalances`: imbalance chéo. Tại mức p của một nến, buy imbalance khi
  ask(p) >= ratio * bid(p − 1 bin); sell imbalance khi bid(p) >= ratio * ask(p + 1 bin).
  ask = volume taker mua, bid = volume taker bán. Ngưỡng mặc định ratio = 3.0 (300%), là quy
  ước của các nền tảng footprint, không có cơ sở thống kê. Mức đối diện không có giao dịch
  được tính là 0 (nên mọi volume > 0 đều vượt ngưỡng), NHƯNG chỉ so khi mức đối diện nằm
  trong biên giá có giao dịch của nến: mức thấp nhất không có buy imbalance, mức cao nhất
  không có sell imbalance. Phía chủ động còn phải >= `min_volume` và > 0.
- `stacked_imbalances` (Events kind `stacked_imbalance`): >= `min_stack` (mặc định 3) mức
  liền nhau trong cùng một nến cùng loại imbalance. price_low/high = cạnh dưới mức thấp
  nhất / cạnh trên mức cao nhất của chuỗi; attrs: side ("buy"/"sell"), levels.
  event_time = mở nến, known_at = đóng nến.

Absorption (`absorption`, Events kind `absorption`): nến i là absorption khi
- volume[i] >= `volume_mult` * trung bình volume của `window` nến TRƯỚC i, và
- high[i] − low[i] <= `range_frac` * ATR của `window` nến TRƯỚC i (ATR = trung bình đơn giản
  của true range), tức volume rất lớn mà giá gần như không đi.
attrs.side theo dấu delta của nến: "buy" = taker mua mạnh bị lệnh bán thụ động hấp thụ,
"sell" ngược lại, "flat" khi delta = 0. Delta lấy từ `trades` nếu truyền vào, không thì từ
`taker_buy_volume`. known_at = đóng nến (chỉ dùng nến đã đóng tới i).
"""

import polars as pl

from rinng.analysis.types import (
    bar_duration,
    check_ohlcv,
    events_frame,
    features_frame,
    params_hash,
)

MODULE = "orderflow"

_RESETS = {"day": "1d", "week": "1w"}


def _bar_open(time: pl.Expr, timeframe: str) -> pl.Expr:
    """open_time của nến chứa `time`. Khung m/h/d neo theo epoch (UTC), khung w neo thứ Hai."""
    bar_duration(timeframe)  # kiểm định dạng khung
    return time.dt.truncate(timeframe).dt.cast_time_unit("ms")


def _taker_buy() -> pl.Expr:
    return pl.when(pl.col("is_buyer_maker")).then(0.0).otherwise(pl.col("qty"))


# ---------------------------------------------------------------- từ nến


def delta_features(ohlcv: pl.DataFrame, *, cvd_reset: str | None = None) -> pl.DataFrame:
    """Features: delta, cvd, delta_pct (xem docstring module)."""
    check_ohlcv(ohlcv)
    if cvd_reset is not None and cvd_reset not in _RESETS:
        raise ValueError(f"cvd_reset phải là None hoặc một trong {list(_RESETS)}")
    phash = params_hash(f"{MODULE}.delta", {"cvd_reset": cvd_reset})
    delta = 2 * pl.col("taker_buy_volume") - pl.col("volume")
    cvd = delta.cum_sum()
    if cvd_reset is not None:
        cvd = cvd.over(pl.col("open_time").dt.truncate(_RESETS[cvd_reset]))
    pct = pl.when(pl.col("volume") > 0).then(delta / pl.col("volume")).otherwise(None)
    return features_frame(ohlcv, {"delta": delta, "cvd": cvd, "delta_pct": pct}, phash)


# ---------------------------------------------------------------- từ trades


def trade_bars(trades: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Gộp trades theo nến: open_time, volume, buy_volume, sell_volume, delta, n_trades."""
    buy = _taker_buy()
    return (
        trades.group_by(_bar_open(pl.col("time"), timeframe).alias("open_time"))
        .agg(
            pl.col("qty").sum().alias("volume"),
            buy.sum().alias("buy_volume"),
            (pl.col("qty") - buy).sum().alias("sell_volume"),
            pl.len().cast(pl.Int64).alias("n_trades"),
        )
        .with_columns((pl.col("buy_volume") - pl.col("sell_volume")).alias("delta"))
        .select("open_time", "volume", "buy_volume", "sell_volume", "delta", "n_trades")
        .sort("open_time")
    )


def _level(price: pl.Expr, bin_size: float) -> pl.Expr:
    return (price / bin_size + 1e-7).floor().cast(pl.Int64)


def footprint(trades: pl.DataFrame, timeframe: str, bin_size: float) -> pl.DataFrame:
    """Footprint: open_time, price_bin, buy_volume, sell_volume, delta (mức có giao dịch)."""
    if not bin_size > 0:
        raise ValueError("bin_size phải > 0")
    buy = _taker_buy()
    return (
        trades.group_by(
            _bar_open(pl.col("time"), timeframe).alias("open_time"),
            _level(pl.col("price"), bin_size).alias("level"),
        )
        .agg(buy.sum().alias("buy_volume"), (pl.col("qty") - buy).sum().alias("sell_volume"))
        .sort("open_time", "level")
        .select(
            "open_time",
            (pl.col("level").cast(pl.Float64) * bin_size).alias("price_bin"),
            "buy_volume",
            "sell_volume",
            (pl.col("buy_volume") - pl.col("sell_volume")).alias("delta"),
        )
    )


def diagonal_imbalances(
    fp: pl.DataFrame, bin_size: float, *, ratio: float = 3.0, min_volume: float = 0.0
) -> pl.DataFrame:
    """Thêm cột buy_imbalance, sell_imbalance (bool) vào footprint (xem docstring module)."""
    keyed = fp.with_columns(_level(pl.col("price_bin") + bin_size / 2, bin_size).alias("_k"))
    below = keyed.select(
        "open_time", (pl.col("_k") + 1).alias("_k"), pl.col("sell_volume").alias("_bid_below")
    )
    above = keyed.select(
        "open_time", (pl.col("_k") - 1).alias("_k"), pl.col("buy_volume").alias("_ask_above")
    )
    ask, bid = pl.col("buy_volume"), pl.col("sell_volume")
    k_min = pl.col("_k").min().over("open_time")
    k_max = pl.col("_k").max().over("open_time")
    return (
        keyed.join(below, on=["open_time", "_k"], how="left")
        .join(above, on=["open_time", "_k"], how="left")
        .with_columns(pl.col("_bid_below", "_ask_above").fill_null(0.0))
        .with_columns(
            (
                (pl.col("_k") > k_min)
                & (ask > 0)
                & (ask >= min_volume)
                & (ask >= ratio * pl.col("_bid_below"))
            ).alias("buy_imbalance"),
            (
                (pl.col("_k") < k_max)
                & (bid > 0)
                & (bid >= min_volume)
                & (bid >= ratio * pl.col("_ask_above"))
            ).alias("sell_imbalance"),
        )
        .sort("open_time", "_k")
        .drop("_k", "_bid_below", "_ask_above")
    )


def _symbol(frame: pl.DataFrame) -> str:
    if frame.is_empty() or frame["symbol"].n_unique() != 1:
        raise ValueError("frame phải không rỗng và chỉ có một symbol")
    return frame["symbol"][0]


def stacked_imbalances(
    trades: pl.DataFrame,
    timeframe: str,
    bin_size: float,
    *,
    ratio: float = 3.0,
    min_volume: float = 0.0,
    min_stack: int = 3,
) -> pl.DataFrame:
    """Events kind `stacked_imbalance` (xem docstring module)."""
    symbol = _symbol(trades)
    if min_stack < 1:
        raise ValueError("min_stack phải >= 1")
    phash = params_hash(
        f"{MODULE}.stacked",
        {"bin_size": bin_size, "ratio": ratio, "min_volume": min_volume, "min_stack": min_stack},
    )
    duration = bar_duration(timeframe)
    flagged = diagonal_imbalances(
        footprint(trades, timeframe, bin_size), bin_size, ratio=ratio, min_volume=min_volume
    ).with_columns(_level(pl.col("price_bin") + bin_size / 2, bin_size).alias("k"))
    rows = []
    for side in ("buy", "sell"):
        hits = flagged.filter(pl.col(f"{side}_imbalance")).sort("open_time", "k")
        # mức liên tiếp: k − thứ tự trong nến không đổi trong một chuỗi
        runs = (
            hits.with_columns((pl.col("k") - pl.int_range(pl.len()).over("open_time")).alias("run"))
            .group_by("open_time", "run")
            .agg(pl.col("k").min().alias("k_lo"), pl.col("k").max().alias("k_hi"), pl.len())
            .filter(pl.col("len") >= min_stack)
        )
        for r in runs.iter_rows(named=True):
            rows.append(
                {
                    "kind": "stacked_imbalance",
                    "event_time": r["open_time"],
                    "known_at": r["open_time"] + duration,
                    "price_low": r["k_lo"] * bin_size,
                    "price_high": (r["k_hi"] + 1) * bin_size,
                    "id": f"{side}|{r['k_lo']}",
                    "attrs": {"side": side, "levels": int(r["len"])},
                }
            )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=phash)


# ---------------------------------------------------------------- absorption


def absorption(
    ohlcv: pl.DataFrame,
    *,
    window: int = 20,
    volume_mult: float = 2.0,
    range_frac: float = 0.5,
    trades: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Events kind `absorption` (xem docstring module). attrs: side, delta, volume_ratio,
    range_atr."""
    symbol, timeframe = check_ohlcv(ohlcv)
    if window < 1:
        raise ValueError("window phải >= 1")
    phash = params_hash(
        f"{MODULE}.absorption",
        {
            "window": window,
            "volume_mult": volume_mult,
            "range_frac": range_frac,
            "source": "trades" if trades is not None else "candles",
        },
    )
    duration = bar_duration(timeframe)
    frame = ohlcv.select("open_time", "high", "low", "close", "volume", "taker_buy_volume")
    if trades is not None:
        frame = frame.join(
            trade_bars(trades, timeframe).select("open_time", "delta"), on="open_time", how="left"
        ).with_columns(pl.col("delta").fill_null(0.0))
    else:
        frame = frame.with_columns(
            (2 * pl.col("taker_buy_volume") - pl.col("volume")).alias("delta")
        )
    prev_close = pl.col("close").shift(1)
    tr = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    flagged = (
        frame.with_columns(tr.alias("tr"))
        .with_columns(
            pl.col("volume").shift(1).rolling_mean(window).alias("vol_mean"),
            pl.col("tr").shift(1).rolling_mean(window).alias("atr"),
        )
        .with_columns(
            (pl.col("volume") / pl.col("vol_mean")).alias("volume_ratio"),
            ((pl.col("high") - pl.col("low")) / pl.col("atr")).alias("range_atr"),
        )
        .filter(
            (pl.col("vol_mean") > 0)
            & (pl.col("atr") > 0)
            & (pl.col("volume_ratio") >= volume_mult)
            & (pl.col("range_atr") <= range_frac)
        )
    )
    rows = []
    for r in flagged.iter_rows(named=True):
        d = float(r["delta"])
        rows.append(
            {
                "kind": "absorption",
                "event_time": r["open_time"],
                "known_at": r["open_time"] + duration,
                "price_low": r["low"],
                "price_high": r["high"],
                "attrs": {
                    "side": "buy" if d > 0 else "sell" if d < 0 else "flat",
                    "delta": d,
                    "volume_ratio": float(r["volume_ratio"]),
                    "range_atr": float(r["range_atr"]),
                },
            }
        )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=phash)
