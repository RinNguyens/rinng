"""Point-in-time market data and the per-domain inputs the analysts read.

The paper's four domains (fundamentals, market, news, sentiment) map to crypto as:

- `market`: daily candles and technical indicators (rinng.analysis.indicators);
- `derivatives`: funding, open interest and the global long/short account ratio, i.e. crowd
  positioning, the crypto stand-in for both "fundamentals" and "sentiment";
- `news`: headlines from rinng.news. Only available in the live protocol: the feed is not stored
  historically, so backtests run without it rather than with headlines fetched after the fact.

Everything is sliced *as of* the decision time t (00:00 UTC of the decision day): daily bars that
closed by t, derivative points stamped before t.

Blind mode (anti-leakage, not in the paper): the model sees "ASSET" instead of the ticker, day
offsets instead of calendar dates, and prices rebased so the close on the day before the run
starts is 100. Ratios (returns, RSI, funding, OI changes) are unchanged, so the information is the
same but a model cannot look the period up in its training data.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from rinng.analysis import indicators
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.schemas import FUNDING, LONG_SHORT, OHLCV, OPEN_INTEREST

log = logging.getLogger(__name__)

DAY = timedelta(days=1)
PRICE_COLS = ("open", "high", "low", "close")
DOMAINS_BACKTEST = ("market", "derivatives")
DOMAINS_LIVE = ("market", "derivatives", "news")


@dataclass
class SymbolData:
    symbol: str
    d1: pl.DataFrame  # closed daily candles
    funding: pl.DataFrame  # time, rate
    oi: pl.DataFrame  # time (day), oi_value (last of day)
    ls: pl.DataFrame  # time (day), ratio, long_pct (last of day)
    price_factor: float = 1.0  # blind mode: multiply prices by this
    label: str = ""
    news: list[dict] = field(default_factory=list)
    now: datetime | None = None  # live: the real decision moment (news up to here)

    def asof(self, t: datetime) -> SymbolData:
        """Only what is known at time t (bars closed by t; in live, news up to `now`)."""
        cut = max(t, self.now) if self.now else t
        return SymbolData(
            symbol=self.symbol,
            d1=self.d1.filter(pl.col("open_time") + DAY <= t),
            funding=self.funding.filter(pl.col("time") < t),
            oi=self.oi.filter(pl.col("time") + DAY <= t),
            ls=self.ls.filter(pl.col("time") + DAY <= t),
            price_factor=self.price_factor,
            label=self.label,
            news=[n for n in self.news if n["time"] < cut.timestamp() * 1000],
            now=self.now,
        )


def _daily_last(f: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    if f.is_empty():
        return pl.DataFrame(
            schema={"time": pl.Datetime("ms", "UTC"), **{c: pl.Float64 for c in cols}}
        )
    return (
        f.sort("time")
        .group_by_dynamic("time", every="1d")
        .agg([pl.col(c).last() for c in cols])
        .with_columns(pl.col("time").cast(pl.Datetime("ms", "UTC")))
    )


Fill = Callable[[str, datetime, datetime], pl.DataFrame]


def fill_gaps(d1: pl.DataFrame, symbol: str, end: datetime, fill: Fill) -> pl.DataFrame:
    """Fetch closed daily bars missing from storage (gaps inside the range, or a store that has
    not caught up). Nothing is written back; the filled days are logged."""
    if d1.is_empty():
        return d1
    last = min(end, datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)) - DAY
    have = set(d1["open_time"].to_list())
    t, missing = d1["open_time"][0], []
    while t <= last:
        if t not in have:
            missing.append(t)
        t += DAY
    if not missing:
        return d1
    got = fill(symbol, missing[0], missing[-1] + DAY)
    got = got.filter(pl.col("is_closed") & pl.col("open_time").is_in(missing))
    log.warning(
        "%s: %d daily bars missing from storage, %d fetched from the exchange (%s)",
        symbol,
        len(missing),
        got.height,
        ", ".join(f"{m:%Y-%m-%d}" for m in missing[:5]),
    )
    if got.is_empty():
        return d1
    got = got.select(d1.columns).cast(d1.schema)
    return pl.concat([d1, got]).sort("open_time")


def load(
    paths: DataPaths,
    exchange: str,
    symbol: str,
    start: datetime,
    end: datetime,
    fill: Fill | None = None,
) -> SymbolData:
    """Daily candles and derivatives over [start, end) from curated storage; `fill` fetches
    daily bars the store is missing."""
    d1 = (
        read_curated(
            paths, OHLCV, exchange=exchange, symbol=symbol, timeframe="1d", start=start, end=end
        )
        .filter(pl.col("is_closed"))
        .sort("open_time")
        .unique("open_time", keep="last", maintain_order=True)
    )
    if fill is not None:
        d1 = fill_gaps(d1, symbol, end, fill)
    fu = read_curated(paths, FUNDING, exchange=exchange, symbol=symbol, start=start, end=end)
    fu = fu.select(pl.col("funding_time").alias("time"), "rate").sort("time")
    oi = read_curated(paths, OPEN_INTEREST, exchange=exchange, symbol=symbol, start=start, end=end)
    ls = read_curated(paths, LONG_SHORT, exchange=exchange, symbol=symbol, start=start, end=end)
    if "kind" in ls.columns:
        ls = ls.filter(pl.col("kind") == "global_account")
    return SymbolData(
        symbol=symbol,
        d1=d1,
        funding=fu,
        oi=_daily_last(oi.select("time", "oi_value") if oi.height else oi, ["oi_value"]),
        ls=_daily_last(
            ls.select("time", "ratio", "long_pct") if ls.height else ls, ["ratio", "long_pct"]
        ),
        label=symbol,
    )


def blind(sd: SymbolData, start: datetime) -> SymbolData:
    """Rebase prices to 100 at the last close before `start`; hide the ticker."""
    before = sd.d1.filter(pl.col("open_time") + DAY <= start)
    ref = float(before["close"][-1]) if before.height else float(sd.d1["close"][0])
    k = 100.0 / ref
    sd.d1 = sd.d1.with_columns([pl.col(c) * k for c in PRICE_COLS])
    sd.price_factor = k
    sd.label = "ASSET"
    return sd


# --------------------------------------------------------------------------- labels


def day_label(t: datetime, ref: datetime | None) -> str:
    """Calendar date, or 'D+n' relative to the run start in blind mode."""
    if ref is None:
        return t.strftime("%Y-%m-%d")
    return f"D{(t - ref).days:+d}"


def _r(v: float | None, nd: int = 4) -> float | None:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def _sig(v: float | None) -> float | None:
    """Round to 6 significant digits (prices of any magnitude)."""
    if v is None or math.isnan(v):
        return None
    return float(f"{v:.6g}")


# --------------------------------------------------------------------------- domains


def market_domain(sd: SymbolData, ref: datetime | None = None) -> dict:
    o = sd.d1.tail(400)
    feats = indicators.compute(o).tail(1).to_dicts()[0]
    close = float(o["close"][-1])
    vol20 = float(o["volume"].tail(21).head(20).mean())
    recent = []
    for row in o.tail(10).iter_rows(named=True):
        recent.append(
            {
                "day": day_label(row["open_time"], ref),
                "open": _sig(row["open"]),
                "high": _sig(row["high"]),
                "low": _sig(row["low"]),
                "close": _sig(row["close"]),
                "change_pct": _r(100 * (row["close"] / row["open"] - 1), 2),
                "volume_vs_20d": _r(row["volume"] / vol20, 2) if vol20 else None,
            }
        )
    tb = o.tail(7)
    taker = (
        float(tb["taker_buy_volume"].sum() / tb["volume"].sum())
        if tb["taker_buy_volume"].null_count() == 0 and tb["volume"].sum() > 0
        else None
    )
    yr = o.tail(365)
    ind = {
        k: _sig(feats.get(k))
        for k in (
            "ema_9",
            "ema_21",
            "ema_50",
            "ema_200",
            "sma_20",
            "sma_50",
            "sma_200",
            "bb_upper",
            "bb_mid",
            "bb_lower",
            "macd",
            "macd_signal",
            "macd_hist",
        )
    }
    ind.update(
        {
            "rsi_14": _r(feats.get("rsi"), 1),
            "stoch_k": _r(feats.get("stoch_k"), 1),
            "stoch_d": _r(feats.get("stoch_d"), 1),
            "williams_r": _r(feats.get("willr"), 1),
            "adx_14": _r(feats.get("adx"), 1),
            "roc_10_pct": _r(feats.get("roc"), 2),
            "atr_14_pct_of_price": _r(100 * (feats.get("atr") or 0) / close, 2),
        }
    )
    return {
        "asset": sd.label,
        "timeframe": "1d",
        "last_close": _sig(close),
        "last_10_days": recent,
        "indicators": ind,
        "taker_buy_share_7d": _r(taker, 3),
        "distance_to_365d_high_pct": _r(100 * (close / float(yr["high"].max()) - 1), 2),
        "distance_to_365d_low_pct": _r(100 * (close / float(yr["low"].min()) - 1), 2),
    }


def _pct_change(s: pl.Series, back: int) -> float | None:
    if s.len() <= back or not s[-1 - back]:
        return None
    return 100 * (float(s[-1]) / float(s[-1 - back]) - 1)


def _percentile(window: np.ndarray, v: float) -> float | None:
    window = window[~np.isnan(window)]
    if len(window) < 10:
        return None
    return float(100 * np.mean(window <= v))


def derivatives_domain(sd: SymbolData, ref: datetime | None = None) -> dict:
    out: dict = {"asset": sd.label}
    fu = sd.funding
    if fu.height >= 3:
        rates = fu["rate"].to_numpy().astype(float) * 100  # % per settlement
        per_day = 3  # 8h settlements
        avg7 = float(np.mean(rates[-7 * per_day :]))
        rolling7 = np.convolve(rates, np.ones(7 * per_day) / (7 * per_day), "valid")
        out["funding"] = {
            "last_3_settlements_pct": [_r(x, 4) for x in rates[-3:]],
            "avg_7d_pct": _r(avg7, 4),
            "avg_30d_pct": _r(float(np.mean(rates[-30 * per_day :])), 4),
            "annualized_7d_pct": _r(avg7 * per_day * 365, 1),
            "percentile_of_7d_avg_vs_365d": _r(_percentile(rolling7[-365 * per_day :], avg7), 0),
        }
    if sd.oi.height >= 2:
        s = sd.oi["oi_value"]
        out["open_interest"] = {
            "change_1d_pct": _r(_pct_change(s, 1), 2),
            "change_7d_pct": _r(_pct_change(s, 7), 2),
            "change_30d_pct": _r(_pct_change(s, 30), 2),
            "price_change_7d_pct": _r(_pct_change(sd.d1["close"], 7), 2),
        }
        if ref is None:
            out["open_interest"]["value_usd"] = _sig(float(s[-1]))
    if sd.ls.height >= 2:
        r = sd.ls["ratio"].to_numpy().astype(float)
        out["long_short_global_accounts"] = {
            "ratio_last": _r(r[-1], 3),
            "ratio_7d_ago": _r(r[-8], 3) if len(r) > 7 else None,
            "ratio_30d_avg": _r(float(np.nanmean(r[-30:])), 3),
            # long_pct is missing in the dumps; ratio = longs / shorts gives the same number
            "long_accounts_pct": _r(100 * r[-1] / (1 + r[-1]), 1),
            "percentile_vs_90d": _r(_percentile(r[-90:], r[-1]), 0),
        }
    if len(out) == 1:
        out["note"] = "no derivatives data stored for this period"
    return out


def news_domain(sd: SymbolData, ref: datetime | None = None, limit: int = 25) -> dict:
    coin = sd.symbol.split("-")[0].upper()
    items = sorted(sd.news, key=lambda n: n["time"], reverse=True)
    mine = [n for n in items if coin in (n.get("coins") or [])]
    general = [n for n in items if not n.get("coins")]
    pick = (mine + general)[:limit]
    return {
        "asset": sd.label,
        "headlines": [
            {
                "time_utc": datetime.fromtimestamp(n["time"] / 1000, UTC).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "source": n["source"],
                "title": n["title"],
                "about_this_asset": coin in (n.get("coins") or []),
            }
            for n in pick
        ],
    }


BUILDERS = {"market": market_domain, "derivatives": derivatives_domain, "news": news_domain}
