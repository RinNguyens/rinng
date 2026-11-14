"""Schema các bảng ở vùng curated (docs/08-kien-truc.md mục 5.2).

Mọi bảng có `exchange` và `symbol` (tên chuẩn của dự án, ví dụ BTC-USDT-PERP).
Thời gian lưu dạng Datetime mili giây, múi giờ UTC.

Một số bảng có cột `source` vì cùng một chuỗi đến từ hai nguồn cho số hơi khác nhau.
Ví dụ open interest lúc 2026-11-10 05:40 UTC: API trả 98690.01, file `metrics` của
data.binance.vision ghi 98691.69. Hai nguồn được giữ song song, không trộn.
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
    # Làm tròn cột thời gian khi chuẩn hóa. Funding của Binance lệch vài mili giây so với mốc
    # tròn và lệch khác nhau giữa REST (…400002) và dump (…800001); không làm tròn thì cùng
    # một lần funding thành hai dòng.
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

# Mark price theo tick từ WebSocket (Binance mỗi 1 giây, OKX khi thay đổi).
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

# Không có id từ sàn; coi cả bản ghi là khóa.
LIQUIDATIONS = _table(
    "liquidations",
    "time",
    {"time": TIME, "side": pl.String(), "price": F64, "qty": F64},
    extra_key=("side", "price", "qty"),
)

# Độ sâu sổ lệnh lũy kế trong ±percentage % quanh giá (file bookDepth, mỗi 30 giây).
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
        raise KeyError(f"không có bảng {name!r}; các bảng: {list(TABLES)}") from None


def conform(frame: pl.DataFrame, tbl: Table) -> pl.DataFrame:
    """Ép frame về đúng cột, thứ tự và kiểu của bảng. Thiếu cột hoặc khóa rỗng thì báo lỗi."""
    missing = [c for c in tbl.columns if c not in frame.columns]
    if missing:
        raise ValueError(f"bảng {tbl.name} thiếu cột {missing}")
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
        raise ValueError(f"bảng {tbl.name} có giá trị rỗng ở cột khóa {null_keys}")
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
    """Đổi các dòng mà bộ chuyển đổi sàn trả về thành frame đúng schema.

    `constants` điền các cột cố định mà bộ chuyển đổi không trả, ví dụ source="api".
    """
    if tbl.has_timeframe and timeframe is None:
        raise ValueError(f"bảng {tbl.name} cần timeframe")
    fixed = {"exchange": exchange, "symbol": symbol, **constants}
    if tbl.has_timeframe:
        fixed["timeframe"] = timeframe
    data = [{**{c: None for c in tbl.columns}, **row, **fixed} for row in rows]
    frame = pl.DataFrame(data, schema_overrides=_int_time_schema(tbl), strict=False)
    return conform(frame, tbl)


def _int_time_schema(tbl: Table) -> dict[str, pl.DataType]:
    """Schema để dựng frame từ dict: cột thời gian vẫn là int ms, sẽ đổi trong `conform`."""
    return {name: (pl.Int64() if dtype == TIME else dtype) for name, dtype in tbl.schema.items()}
