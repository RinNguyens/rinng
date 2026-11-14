"""Schemas of the curated-zone tables (docs/08-architecture.md section 5.2).

Every table has `exchange` and `symbol` (the project canonical name, e.g. BTC-USDT-PERP).
Times are stored as millisecond Datetime, UTC.

Some tables have a `source` column because the same series comes from two
sources with slightly different numbers.
E.g. open interest at 2026-11-10 05:40 UTC: the API returns 98690.01, the `metrics` file from
data.binance.vision records 98691.69. Both sources are kept side by side, never mixed.
"""

from dataclasses import dataclass, replace

import polars as pl

TIME = pl.Datetime("ms", "UTC")


@dataclass(frozen=True)
class Table:
    name: str
    schema: dict[str, pl.DataType]
    key: tuple[str, ...]
    time_column: str
    has_timeframe: bool = False
    # Round time columns when normalizing. Binance funding is a few ms off the round mark
    # and differs between REST (…400002) and dumps (…800001); without rounding the same
    # funding event becomes two rows.
    round_time: str | None = None

    @property
    def columns(self) -> list[str]:
        return list(self.schema)


def _table(name, time_column, columns, extra_key=(), has_timeframe=False) -> Table:
    schema = {"exchange": pl.String(), "symbol": pl.String()}
    if has_timeframe:
        schema["timeframe"] = pl.String()
    schema.update(columns)
    key = ("exchange", "symbol") + (("timeframe",) if has_timeframe else ()) + tuple(extra_key)
    return Table(name, schema, key + (time_column,), time_column, has_timeframe)


F64 = pl.Float64()

OHLCV = _table(
    "ohlcv",
    "open_time",
    {
        "open_time": TIME,
        "open": F64,
        "high": F64,
        "low": F64,
        "close": F64,
        "volume": F64,
        "quote_volume": F64,
        "trades": pl.Int64(),
        "taker_buy_volume": F64,
        "is_closed": pl.Boolean(),
    },
    has_timeframe=True,
)

MARK_OHLCV = _table(
    "mark_ohlcv",
    "open_time",
    {
        "open_time": TIME,
        "open": F64,
        "high": F64,
        "low": F64,
        "close": F64,
        "is_closed": pl.Boolean(),
    },
    has_timeframe=True,
)

FUNDING = replace(
    _table("funding", "funding_time", {"funding_time": TIME, "rate": F64, "mark_price": F64}),
    round_time="1s",
)

OPEN_INTEREST = _table(
    "open_interest",
    "time",
    {"source": pl.String(), "time": TIME, "oi_base": F64, "oi_value": F64},
    extra_key=("source",),
)

# kind: global_account | top_account | top_position
LONG_SHORT = _table(
    "long_short",
    "time",
    {
        "source": pl.String(),
        "kind": pl.String(),
        "time": TIME,
        "ratio": F64,
        "long_pct": F64,
        "short_pct": F64,
    },
    extra_key=("source", "kind"),
)

TAKER_VOLUME = _table(
    "taker_volume",
    "time",
    {
        "source": pl.String(),
        "time": TIME,
        "buy_volume": F64,
        "sell_volume": F64,
        "buy_sell_ratio": F64,
    },
    extra_key=("source",),
)

# Mark price per tick from WebSocket (Binance every 1 second, OKX on change).
MARK_PRICE = _table(
    "mark_price",
    "time",
    {"time": TIME, "mark_price": F64, "index_price": F64, "funding_rate": F64},
)

TRADES = _table(
    "trades",
    "time",
    {
        "trade_id": pl.Int64(),
        "time": TIME,
        "price": F64,
        "qty": F64,
        "is_buyer_maker": pl.Boolean(),
    },
    extra_key=("trade_id",),
)

# No exchange id; the whole record is the key.
LIQUIDATIONS = _table(
    "liquidations",
    "time",
    {"time": TIME, "side": pl.String(), "price": F64, "qty": F64},
    extra_key=("side", "price", "qty"),
)

# Cumulative order book depth within ±percentage % of price (bookDepth files, every 30 seconds).
BOOK_DEPTH = _table(
    "book_depth",
    "time",
    {"time": TIME, "percentage": F64, "depth": F64, "notional": F64},
    extra_key=("percentage",),
)

TABLES: dict[str, Table] = {
    t.name: t
    for t in (
        OHLCV,
        MARK_OHLCV,
        FUNDING,
        OPEN_INTEREST,
        LONG_SHORT,
        TAKER_VOLUME,
        MARK_PRICE,
        TRADES,
        LIQUIDATIONS,
        BOOK_DEPTH,
    )
}


def table(name: str) -> Table:
    try:
        return TABLES[name]
    except KeyError:
        raise KeyError(f"no table {name!r}; tables: {list(TABLES)}") from None


def conform(frame: pl.DataFrame, tbl: Table) -> pl.DataFrame:
    """Coerce a frame to the table columns, order and types. Raises on missing cols/null keys."""
    missing = [c for c in tbl.columns if c not in frame.columns]
    if missing:
        raise ValueError(f"table {tbl.name} is missing columns {missing}")
    casts = []
    for name, dtype in tbl.schema.items():
        col = pl.col(name)
        if dtype == TIME and frame.schema[name].is_integer():
            col = pl.from_epoch(col, time_unit="ms").dt.replace_time_zone("UTC")
        casts.append(col.cast(dtype, strict=True).alias(name))
    out = frame.select(casts)
    if tbl.round_time is not None:
        out = out.with_columns(pl.col(tbl.time_column).dt.round(tbl.round_time))
    null_keys = [k for k in tbl.key if out[k].null_count()]
    if null_keys:
        raise ValueError(f"table {tbl.name} has nulls in key columns {null_keys}")
    return out


def rows_to_frame(
    tbl: Table,
    rows: list[dict],
    *,
    exchange: str,
    symbol: str,
    timeframe: str | None = None,
    **constants: str,
) -> pl.DataFrame:
    """Turn rows returned by an exchange adapter into a frame with the right schema.

    `constants` fills fixed columns the adapter does not return, e.g. source="api".
    """
    if tbl.has_timeframe and timeframe is None:
        raise ValueError(f"table {tbl.name} requires timeframe")
    fixed = {"exchange": exchange, "symbol": symbol, **constants}
    if tbl.has_timeframe:
        fixed["timeframe"] = timeframe
    data = [{**{c: None for c in tbl.columns}, **row, **fixed} for row in rows]
    frame = pl.DataFrame(data, schema_overrides=_int_time_schema(tbl), strict=False)
    return conform(frame, tbl)


def _int_time_schema(tbl: Table) -> dict[str, pl.DataType]:
    """Schema for building a frame from dicts: time columns stay int ms, converted in `conform`."""
    return {name: (pl.Int64() if dtype == TIME else dtype) for name, dtype in tbl.schema.items()}
