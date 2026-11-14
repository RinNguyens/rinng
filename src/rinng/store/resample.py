"""Aggregate 1-minute bars into larger timeframes, in UTC.

- Minute/hour/day timeframes align to the UTC epoch (4h bars open at 00, 04, 08... UTC).
- Weekly bars open Monday 00:00 UTC, like Binance and OKX `1Wutc`.
- An aggregated bar is closed (is_closed) when: every 1-minute bar inside is closed, the data
  starts no later than its open, and its close is no later than the close of the last
  1-minute bar. Partial first/last bars therefore have is_closed = False.
- trades, taker_buy_volume: null if any 1-minute bar inside is missing that value.
"""

import polars as pl

from rinng.store.schemas import OHLCV, conform
from rinng.timeframes import bar_duration


def resample_ohlcv(ohlcv_1m: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    if ohlcv_1m.is_empty():
        return pl.DataFrame(schema=OHLCV.schema)
    if set(ohlcv_1m["timeframe"].unique()) != {"1m"}:
        raise ValueError("input must be 1m bars")
    duration = bar_duration(timeframe)
    every = {"m": "m", "h": "h", "d": "d", "w": "w"}[timeframe[-1]]
    window = f"{timeframe[:-1]}{every}"
    first_open = ohlcv_1m["open_time"].min()
    last_close = ohlcv_1m["open_time"].max() + bar_duration("1m")

    def nullable_sum(col: str) -> pl.Expr:
        return (
            pl.when(pl.col(col).null_count() == 0)
            .then(pl.col(col).sum())
            .otherwise(None)
            .alias(col)
        )

    frames = []
    for (exchange, symbol), part in ohlcv_1m.sort("open_time").group_by(
        ["exchange", "symbol"], maintain_order=True
    ):
        grouped = part.group_by_dynamic(
            "open_time",
            every=window,
            closed="left",
            label="left",
            start_by="monday" if every == "w" else "window",
        ).agg(
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.col("quote_volume").sum(),
            nullable_sum("trades"),
            nullable_sum("taker_buy_volume"),
            pl.col("is_closed").all().alias("all_closed"),
        )
        frames.append(
            grouped.with_columns(
                pl.lit(exchange).alias("exchange"),
                pl.lit(symbol).alias("symbol"),
                pl.lit(timeframe).alias("timeframe"),
                (
                    pl.col("all_closed")
                    & (pl.col("open_time") >= first_open)
                    & (pl.col("open_time") + duration <= last_close)
                ).alias("is_closed"),
            )
        )
    return conform(pl.concat(frames), OHLCV)
