"""Download and read data.binance.vision dump files (USDⓈ-M Futures).

Checked on 2026-11-13:
- klines 1m: monthly and daily files; newer files have a header row, old ones (2020) do not.
- fundingRate: monthly files only (daily return 404). Columns: calc_time, funding_interval_hours,
  last_funding_rate.
- metrics: daily files only. Columns: see docs/09-phase-roadmap.md Phase 0.
- aggTrades, bookDepth: daily files (aggTrades also has monthly files).
- Daily files appear the next day; monthly files at the start of the next month.
- Each .zip file comes with a .CHECKSUM (sha256) file.

Downloaded files are stored unchanged at raw/binance/dumps/{dataset}/{SYMBOL}/{file name}.
"""

import calendar
import hashlib
import io
import logging
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import polars as pl

from rinng.store.paths import DataPaths
from rinng.store.schemas import (
    BOOK_DEPTH,
    FUNDING,
    LONG_SHORT,
    OHLCV,
    OPEN_INTEREST,
    TRADES,
    conform,
)
from rinng.store.writer import write_raw_bytes

log = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision/data/futures/um"


@dataclass(frozen=True)
class DumpKind:
    dataset: str  # directory name on data.binance.vision
    path: str  # sub-path, {s} is the symbol
    stem: str  # middle part of the file name, {s} is the symbol
    monthly: bool
    daily: bool


DUMPS = {
    "klines_1m": DumpKind("klines", "klines/{s}/1m", "{s}-1m", monthly=True, daily=True),
    "funding": DumpKind("fundingRate", "fundingRate/{s}", "{s}-fundingRate", True, False),
    "metrics": DumpKind("metrics", "metrics/{s}", "{s}-metrics", monthly=False, daily=True),
    "agg_trades": DumpKind("aggTrades", "aggTrades/{s}", "{s}-aggTrades", True, True),
    "book_depth": DumpKind("bookDepth", "bookDepth/{s}", "{s}-bookDepth", False, True),
}


@dataclass(frozen=True)
class DumpFile:
    name: str  # key in DUMPS
    symbol: str  # venue symbol
    period: str  # "2026-10" or "2026-11-12"
    start: date
    end: date  # exclusive

    @property
    def filename(self) -> str:
        return f"{DUMPS[self.name].stem.format(s=self.symbol)}-{self.period}.zip"

    @property
    def url(self) -> str:
        kind = DUMPS[self.name]
        granularity = "monthly" if len(self.period) == 7 else "daily"
        return f"{BASE_URL}/{granularity}/{kind.path.format(s=self.symbol)}/{self.filename}"

    def raw_path(self, paths: DataPaths) -> Path:
        return paths.raw / "binance" / "dumps" / self.name / self.symbol / self.filename


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1]) + timedelta(days=1)


def plan(
    name: str, symbol: str, start: date, end: date, today: date | None = None
) -> list[DumpFile]:
    """Files needed to cover [start, end), preferring monthly files.

    Only files already published: finished months, days before today (UTC).
    Whatever cannot be covered (current month for monthly-only datasets) must come from REST.
    """
    kind = DUMPS[name]
    today = today or datetime.now(UTC).date()
    end = min(end, today)
    files: list[DumpFile] = []
    day = start
    while day < end:
        month_start = day.replace(day=1)
        month_end = _month_end(day)
        whole_month = day == month_start and month_end <= end and month_end <= today
        if kind.monthly and (whole_month or not kind.daily) and month_end <= today:
            files.append(DumpFile(name, symbol, f"{day:%Y-%m}", month_start, month_end))
            day = month_end
        elif kind.daily:
            files.append(DumpFile(name, symbol, day.isoformat(), day, day + timedelta(days=1)))
            day += timedelta(days=1)
        else:
            break  # monthly-only dataset and this month has not finished
    return files


def covered_until(files: list[DumpFile], start: date) -> date:
    return max((f.end for f in files), default=start)


class Downloader:
    def __init__(self, client: httpx.Client | None = None, *, retries: int = 4, sleep=time.sleep):
        self._client = client or httpx.Client(timeout=60.0, follow_redirects=True)
        self._retries = retries
        self._sleep = sleep

    def _get(self, url: str) -> httpx.Response:
        for attempt in range(self._retries + 1):
            try:
                response = self._client.get(url)
            except httpx.TransportError:
                if attempt == self._retries:
                    raise
                self._sleep(2.0 * (attempt + 1))
                continue
            if response.status_code >= 500 and attempt < self._retries:
                self._sleep(2.0 * (attempt + 1))
                continue
            return response
        raise AssertionError("unreachable")

    def fetch(self, dump: DumpFile, paths: DataPaths) -> Path | None:
        """Download one file if missing. Returns None if the exchange has no such file (404)."""
        target = dump.raw_path(paths)
        if target.exists():
            return target
        response = self._get(dump.url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        checksum = self._get(dump.url + ".CHECKSUM")
        checksum.raise_for_status()
        expected = checksum.text.split()[0]
        actual = hashlib.sha256(response.content).hexdigest()
        if actual != expected:
            raise ValueError(f"checksum sai cho {dump.filename}: {actual} != {expected}")
        write_raw_bytes(target, response.content)
        return target


# --- read zip files into frames with the right schema ---


def _read_csv(content: bytes, columns: list[str]) -> pl.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        data = z.read(z.namelist()[0])
    first = data.split(b"\n", 1)[0]
    has_header = not first[:1].isdigit()
    frame = pl.read_csv(data, has_header=has_header, new_columns=columns, infer_schema_length=0)
    return frame


def _epoch(col: str) -> pl.Expr:
    """Milliseconds or microseconds (Spot since 2025) → UTC Datetime."""
    v = pl.col(col).cast(pl.Int64)
    ms = pl.when(v > 10**14).then(v // 1000).otherwise(v)
    return pl.from_epoch(ms, time_unit="ms").dt.replace_time_zone("UTC")


def _const(exchange: str, symbol: str) -> list[pl.Expr]:
    return [pl.lit(exchange).alias("exchange"), pl.lit(symbol).alias("symbol")]


KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
    "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]  # fmt: skip


def parse_klines(content: bytes, symbol: str) -> pl.DataFrame:
    f = _read_csv(content, KLINE_COLUMNS)
    out = f.select(
        *_const("binance", symbol),
        pl.lit("1m").alias("timeframe"),
        _epoch("open_time").alias("open_time"),
        *[pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close", "volume")],
        pl.col("quote_volume").cast(pl.Float64),
        pl.col("count").cast(pl.Int64).alias("trades"),
        pl.col("taker_buy_volume").cast(pl.Float64),
        pl.lit(True).alias("is_closed"),
    )
    return conform(out, OHLCV)


def parse_funding(content: bytes, symbol: str) -> pl.DataFrame:
    f = _read_csv(content, ["calc_time", "funding_interval_hours", "last_funding_rate"])
    out = f.select(
        *_const("binance", symbol),
        _epoch("calc_time").alias("funding_time"),
        pl.col("last_funding_rate").cast(pl.Float64).alias("rate"),
        pl.lit(None, pl.Float64).alias("mark_price"),
    )
    return conform(out, FUNDING)


METRICS_COLUMNS = [
    "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]  # fmt: skip

# Mapping checked against the API on 2026-11-13 (values close, not identical).
METRICS_RATIOS = {
    "count_toptrader_long_short_ratio": "top_account",
    "sum_toptrader_long_short_ratio": "top_position",
    "count_long_short_ratio": "global_account",
}


def _num(col: str) -> pl.Expr:
    """Float; empty cells (old metrics files have many) become null."""
    return pl.col(col).replace("", None).cast(pl.Float64)


def parse_metrics(content: bytes, symbol: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (open_interest, long_short), both with source="dump". Taker columns are dropped: not
    yet verified which API values they correspond to."""
    f = _read_csv(content, METRICS_COLUMNS)
    when = pl.col("create_time").str.to_datetime("%Y-%m-%d %H:%M:%S", time_zone="UTC")
    when = when.dt.cast_time_unit("ms").alias("time")
    oi = f.select(
        *_const("binance", symbol),
        pl.lit("dump").alias("source"),
        when,
        _num("sum_open_interest").alias("oi_base"),
        _num("sum_open_interest_value").alias("oi_value"),
    ).drop_nulls("oi_base")
    ratios = [
        f.select(
            *_const("binance", symbol),
            pl.lit("dump").alias("source"),
            pl.lit(kind).alias("kind"),
            when,
            _num(col).alias("ratio"),
            pl.lit(None, pl.Float64).alias("long_pct"),
            pl.lit(None, pl.Float64).alias("short_pct"),
        )
        for col, kind in METRICS_RATIOS.items()
    ]
    ratios = [r.drop_nulls("ratio") for r in ratios]
    return conform(oi, OPEN_INTEREST), conform(pl.concat(ratios), LONG_SHORT)


AGG_COLUMNS = ["agg_id", "price", "qty", "first_id", "last_id", "time", "is_buyer_maker"]


def parse_agg_trades(content: bytes, symbol: str) -> pl.DataFrame:
    f = _read_csv(content, AGG_COLUMNS)
    out = f.select(
        *_const("binance", symbol),
        pl.col("agg_id").cast(pl.Int64).alias("trade_id"),
        _epoch("time").alias("time"),
        pl.col("price").cast(pl.Float64),
        pl.col("qty").cast(pl.Float64),
        (pl.col("is_buyer_maker").str.to_lowercase() == "true").alias("is_buyer_maker"),
    )
    return conform(out, TRADES)


def parse_book_depth(content: bytes, symbol: str) -> pl.DataFrame:
    f = _read_csv(content, ["timestamp", "percentage", "depth", "notional"])
    out = f.select(
        *_const("binance", symbol),
        pl.col("timestamp")
        .str.to_datetime("%Y-%m-%d %H:%M:%S", time_zone="UTC")
        .dt.cast_time_unit("ms")
        .alias("time"),
        *[pl.col(c).cast(pl.Float64) for c in ("percentage", "depth", "notional")],
    )
    return conform(out, BOOK_DEPTH)


def parse(name: str, content: bytes, symbol: str) -> dict[str, pl.DataFrame]:
    """Read one dump file; return {curated table name: frame}. `symbol` is the canonical name."""
    if name == "klines_1m":
        return {"ohlcv": parse_klines(content, symbol)}
    if name == "funding":
        return {"funding": parse_funding(content, symbol)}
    if name == "metrics":
        oi, ls = parse_metrics(content, symbol)
        return {"open_interest": oi, "long_short": ls}
    if name == "agg_trades":
        return {"trades": parse_agg_trades(content, symbol)}
    if name == "book_depth":
        return {"book_depth": parse_book_depth(content, symbol)}
    raise KeyError(name)
