"""Gộp nến 1 phút lên khung lớn hơn, theo UTC.

- Khung theo phút/giờ/ngày căn theo mốc epoch UTC (nến 4h mở lúc 00, 04, 08... UTC).
- Khung tuần mở thứ Hai 00:00 UTC, giống Binance và OKX `1Wutc`.
- Nến gộp được coi là đã đóng (is_closed) khi: mọi nến 1 phút bên trong đã đóng, dữ liệu
  bắt đầu không muộn hơn lúc mở của nó, và lúc đóng của nó không muộn hơn lúc đóng của nến
  1 phút cuối cùng. Nến đầu/cuối chỉ có một phần dữ liệu vì thế có is_closed = False.
- trades, taker_buy_volume: null nếu bất kỳ nến 1 phút nào bên trong thiếu giá trị đó.
"""

import polars as pl

from rinng.store.schemas import OHLCV, conform
from rinng.timeframes import bar_duration


def resample_ohlcv(ohlcv_1m: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    if ohlcv_1m.is_empty():
        return pl.DataFrame(schema=OHLCV.schema)
    if set(ohlcv_1m["timeframe"].unique()) != {"1m"}:
        raise ValueError("đầu vào phải là nến 1m")
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
