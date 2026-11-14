"""Order flow: delta, CVD, footprint, diagonal imbalance, stacked imbalance, absorption.

Taker side convention: a candle's `taker_buy_volume` is taker BUY volume; in trades,
`is_buyer_maker=True` means the buyer is the maker, i.e. the taker SOLD (docs/04 section 2.2).

From candles (`delta_features`, Features, known_at = candle close):
- `delta` = taker buy − taker sell = 2 * taker_buy_volume − volume.
- `cvd` = cumulative sum of delta from the start of the data (`cvd_reset=None`), or restarted
  every UTC day (`"day"`) / every week from Monday 00:00 UTC (`"week"`). The absolute CVD level
  depends on where accumulation starts; only use changes or slope.
- `delta_pct` = delta / volume (null khi volume = 0), trong [-1, 1].

From trades:
- `trade_bars`: group trades by the timeframe's `open_time` (a trade belongs to the candle
  containing its `time`): volume, buy_volume, sell_volume, delta, n_trades.
- `footprint`: table (open_time, price_bin, buy_volume, sell_volume, delta), only levels with
  trades; price_bin = lower bin edge, grid anchored at 0 with absolute `bin_size`.
- `diagonal_imbalances`: diagonal imbalance. At level p of a candle, buy imbalance when
  ask(p) >= ratio * bid(p − 1 bin); sell imbalance khi bid(p) >= ratio * ask(p + 1 bin).
  ask = taker buy volume, bid = taker sell volume. Default ratio threshold = 3.0 (300%), a
  convention of footprint platforms with no statistical basis. An opposite level with no trades
  counts as 0 (so any volume > 0 passes the threshold), BUT only compared when the opposite level
  lies within the candle's traded price range: the lowest level has no buy imbalance, the highest
  level has no sell imbalance. The aggressive side must also be >= `min_volume` and > 0.
- `stacked_imbalances` (Events kind `stacked_imbalance`): >= `min_stack` (default 3) adjacent
  levels in the same candle with the same imbalance type. price_low/high = lower edge of the lowest
  level / upper edge of the highest level of the run; attrs: side ("buy"/"sell"), levels.
  event_time = candle open, known_at = candle close.

Absorption (`absorption`, Events kind `absorption`): candle i is absorption when
- volume[i] >= `volume_mult` * mean volume of the `window` candles BEFORE i, and
- high[i] − low[i] <= `range_frac` * ATR of the `window` candles BEFORE i (ATR = simple mean
  of true range), i.e. very large volume while price barely moves.
attrs.side by the sign of the candle's delta: "buy" = aggressive taker buying absorbed by passive
sell orders, "sell" the opposite, "flat" when delta = 0. Delta comes from `trades` if given,
otherwise from `taker_buy_volume`. known_at = candle close (only uses candles closed up to i).
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
    """open_time of the candle containing `time`. m/h/d timeframes anchor to the epoch (UTC), w
    anchors to Monday."""
    bar_duration(timeframe)  # validate the timeframe format
    return time.dt.truncate(timeframe).dt.cast_time_unit("ms")


def _taker_buy() -> pl.Expr:
    return pl.when(pl.col("is_buyer_maker")).then(0.0).otherwise(pl.col("qty"))


# ---------------------------------------------------------------- from candles


def delta_features(ohlcv: pl.DataFrame, *, cvd_reset: str | None = None) -> pl.DataFrame:
    """Features: delta, cvd, delta_pct (xem docstring module)."""
    check_ohlcv(ohlcv)
    if cvd_reset is not None and cvd_reset not in _RESETS:
        raise ValueError(f"cvd_reset must be None or one of {list(_RESETS)}")
    phash = params_hash(f"{MODULE}.delta", {"cvd_reset": cvd_reset})
    delta = 2 * pl.col("taker_buy_volume") - pl.col("volume")
    cvd = delta.cum_sum()
    if cvd_reset is not None:
        cvd = cvd.over(pl.col("open_time").dt.truncate(_RESETS[cvd_reset]))
    pct = pl.when(pl.col("volume") > 0).then(delta / pl.col("volume")).otherwise(None)
    return features_frame(ohlcv, {"delta": delta, "cvd": cvd, "delta_pct": pct}, phash)


# ---------------------------------------------------------------- from trades


def trade_bars(trades: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Group trades by candle: open_time, volume, buy_volume, sell_volume, delta, n_trades."""
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
    """Footprint: open_time, price_bin, buy_volume, sell_volume, delta (levels with trades)."""
    if not bin_size > 0:
        raise ValueError("bin_size must be > 0")
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
    """Add buy_imbalance, sell_imbalance (bool) columns to the footprint (see module docstring)."""
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
        raise ValueError("frame must be non-empty and contain a single symbol")
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
        raise ValueError("min_stack must be >= 1")
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
        # consecutive levels: k − position within the candle is constant along a run
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
        raise ValueError("window must be >= 1")
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
