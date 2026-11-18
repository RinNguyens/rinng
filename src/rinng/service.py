"""rinng's read-only analysis service: one coin in, JSON-ready analysis out.

The web app, the CLI and the MCP server all call this class, so they return the same numbers.

Data source: curated data in data/ first; when the range is missing, fetch directly from the
exchange REST API (candles, and recent funding/OI/long-short on Binance). Results are cached in
memory: 60 seconds without a live hub; with one, until the next bar of that timeframe closes.

Errors: `NotFound` (unknown coin, not enough data) and `BadRequest` (invalid argument). Front ends
map them to HTTP 404/400, CLI exit codes or MCP tool errors. Exchange/network failures surface as
one of `NETWORK_ERRORS`.

`offline=True` never touches the network: only stored data and configured coins.
"""

import math
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import polars as pl

from rinng.config import Instrument, Settings
from rinng.exchanges.base import timeframe_ms
from rinng.exchanges.listing import Catalog, icon_symbol
from rinng.exchanges.ratelimit import ExchangeError
from rinng.news.feed import NewsFeed
from rinng.news.score import outlook
from rinng.pipeline.run import load_ohlcv
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.resample import resample_ohlcv
from rinng.store.schemas import FUNDING, LONG_SHORT, OHLCV, OPEN_INTEREST, rows_to_frame
from rinng.store.writer import PART_FILE
from rinng.web import desk, summary
from rinng.web.lenses import LENSES, candles_json, to_native

if TYPE_CHECKING:
    from rinng.live.hub import LiveHub

EXCHANGES = ("binance", "okx")
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w"]
DESK_DAYS = 70  # 5m history behind the desk projection (~20k candles)
MAX_BARS = 3000
MIN_DAYS, MAX_DAYS = 2, 3000
CACHE_SIZE = 256
MARKET_TTL = 30.0
NOT_STORED = {"collected": False, "oi_value": None, "oi_chg_24h": None, "ls_ratio": None}


class NotFound(LookupError):
    """Unknown coin or lens, or not enough data to analyse."""


class BadRequest(ValueError):
    """An argument is outside what the service accepts."""


class UnknownSymbol(NotFound):
    """No coin matches what the user typed."""


class Offline(NotFound):
    """The answer needs the network, but the service runs offline."""


NETWORK_ERRORS: tuple[type[Exception], ...] = (httpx.HTTPError, ExchangeError)


def instrument_json(i: Instrument, configured: bool) -> dict:
    return {
        "id": i.id,
        "kind": i.kind,
        "base": i.base,
        "quote": i.quote,
        "name": i.name,
        "icon": icon_symbol(i.base or ""),
        "binance": bool(i.binance),
        "okx": bool(i.okx),
        "configured": configured,
    }


def symbol_candidates(text: str) -> list[str]:
    """Canonical ids a user's spelling may mean: `BTC`, `btcusdt`, `BTC/USDT`, `BTC-USDT-PERP`."""
    raw = text.strip()
    up = raw.upper()
    out = [raw, up, up.replace("/", "-").replace("_", "-")]
    base = up
    for sep in ("/", "-", "_", " "):
        base = base.replace(sep, "")
    for suffix in ("PERP", "SWAP", "USDT"):
        base = base.removesuffix(suffix)
    if base:
        out.append(f"{base}-USDT-PERP")
    return list(dict.fromkeys(c for c in out if c))


class Rinng:
    def __init__(
        self,
        settings: Settings,
        hub: "LiveHub | None" = None,
        catalog: Catalog | None = None,
        news: NewsFeed | None = None,
        offline: bool = False,
    ):
        """`hub`: present when run via `rinng live` (realtime data, cache keyed by closed bars).
        `catalog`: exchange coin catalog for opening coins outside the config (data via REST)."""
        self.settings = settings
        self.offline = offline
        self.hub = hub
        self.catalog = catalog or Catalog(settings)
        self.paths = DataPaths(settings.data_dir)
        self.news_feed = news or NewsFeed()
        # Live: cache keyed by the latest closed bar of that timeframe (a new close recomputes);
        # not live: data only changes when curate runs, so a 60-second expiry is enough.
        self.ttl = 3600.0 if hub is not None else 60.0
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ plumbing

    def stamp(self, exchange: str, symbol: str, tf: str) -> int | None:
        return None if self.hub is None else self.hub.last_closed.get((exchange, symbol, tf))

    def cached(self, key: tuple, fn: Callable[[], Any], ttl: float | None = None) -> Any:
        # Last key is the closed-bar time; without one (off-config coin, no feed) 60 s.
        # An explicit `ttl` overrides both.
        life = ttl or (self.ttl if key[-1] is not None else 60.0)
        with self._lock:
            hit = self._cache.get(key)
        if hit and time.time() - hit[0] < life:
            return hit[1]
        value = fn()
        with self._lock:
            if len(self._cache) > CACHE_SIZE:
                for old in sorted(self._cache, key=lambda k: self._cache[k][0])[:64]:
                    self._cache.pop(old, None)
            self._cache[key] = (time.time(), value)
        return value

    def instrument(self, symbol: str) -> Instrument:
        """Resolve a coin by canonical id or a loose spelling (`BTC`, `BTCUSDT`, `BTC/USDT`)."""
        candidates = symbol_candidates(symbol)
        # Configured coins first: no network. Then the exchange catalog (fetched once an hour).
        for candidate in candidates:
            if self.catalog.is_configured(candidate):
                return self.catalog.resolve(candidate)
        if self.offline:
            raise Offline(f"{symbol} is not in the config (offline: the exchange list is not read)")
        for candidate in candidates:
            try:
                return self.catalog.resolve(candidate)
            except KeyError:
                continue
        hits = [i.id for i in self.catalog.search(symbol, 5)] if symbol.strip() else []
        hint = f"; did you mean {', '.join(hits)}?" if hits else ""
        raise UnknownSymbol(f"unknown instrument {symbol}{hint}")

    def venue(self, symbol: str, exchange: str) -> str:
        self._check_exchange(exchange)
        v = getattr(self.instrument(symbol), exchange, None)
        if not v:
            raise NotFound(f"{symbol} is not listed on {exchange}")
        return v

    @staticmethod
    def _check_exchange(exchange: str) -> None:
        if exchange not in EXCHANGES:
            raise BadRequest(f"exchange must be one of {', '.join(EXCHANGES)}")

    @staticmethod
    def _check_tf(tf: str) -> None:
        if tf not in TIMEFRAMES:
            raise BadRequest(f"timeframe {tf} not supported; use one of {', '.join(TIMEFRAMES)}")

    # ------------------------------------------------------------------ data

    def from_1m(self, exchange: str, symbol: str, tf: str, start: datetime) -> pl.DataFrame:
        """Closed `tf` bars aggregated from 1m bars in curated (empty if nothing stored)."""
        m1 = load_ohlcv(self.paths, exchange, symbol, "1m", start)
        if m1.height < 2:
            return m1
        return resample_ohlcv(m1, tf).filter(pl.col("is_closed")).sort("open_time")

    def candles(self, exchange: str, symbol: str, tf: str, days: int) -> tuple[pl.DataFrame, str]:
        """Closed candles over the last `days` (at most MAX_BARS) and their source:
        "curated" when stored data covers ≥90% of the window, else "live" (REST)."""
        start = datetime.now(UTC) - timedelta(days=days)
        o = load_ohlcv(self.paths, exchange, symbol, tf, start)
        need = days * 86_400_000 / timeframe_ms(tf)
        if o.height >= 0.9 * min(need, MAX_BARS) and o.height > 2:
            return o.tail(MAX_BARS), "curated"
        if tf == "5m":
            # 5m not fully stored yet (timeframe added recently): aggregate from stored 1m bars.
            o = self.from_1m(exchange, symbol, tf, start)
            if o.height >= 0.9 * min(need, MAX_BARS):
                return o.tail(MAX_BARS), "curated"
        if self.offline:
            if o.height > 2:  # partial history is still an answer; the caller checks the length
                return o.tail(MAX_BARS), "curated"
            raise Offline(f"no stored {tf} candles for {symbol} on {exchange} (offline)")
        from rinng.exchanges.binance import Binance
        from rinng.exchanges.okx import Okx

        api = Binance() if exchange == "binance" else Okx()
        rows = [
            r
            for p in api.klines(self.venue(symbol, exchange), tf, start, datetime.now(UTC))
            for r in p
        ]
        f = rows_to_frame(OHLCV, rows, exchange=exchange, symbol=symbol, timeframe=tf)
        return f.filter(pl.col("is_closed")).sort("open_time").tail(MAX_BARS), "live"

    def derivs(self, exchange: str, symbol: str, start: datetime) -> dict[str, pl.DataFrame]:
        """Funding, open interest and global long/short since `start`."""
        out = {}
        for key, tbl, extra in (
            ("funding", FUNDING, {}),
            ("oi", OPEN_INTEREST, {}),
            ("ls", LONG_SHORT, {"kind": "global_account"}),
        ):
            f = read_curated(self.paths, tbl, exchange=exchange, symbol=symbol, start=start)
            for col, val in extra.items():
                f = f.filter(pl.col(col) == val)
            if "source" in f.columns and f["source"].n_unique() > 1:
                # Sources differ slightly: use the dump (longer), fill newer points from the api.
                dump = f.filter(pl.col("source") == "dump")
                newer = f.filter(
                    (pl.col("source") == "api") & (pl.col("time") > dump["time"].max())
                )
                f = pl.concat([dump, newer]).with_columns(pl.lit("dump+api").alias("source"))
            out[key] = f
        if out["funding"].is_empty() and exchange == "binance" and not self.offline:
            from rinng.exchanges.binance import Binance

            api, now = Binance(), datetime.now(UTC)
            sym = self.venue(symbol, exchange)
            rows = [r for p in api.funding(sym, start, now) for r in p]
            out["funding"] = rows_to_frame(FUNDING, rows, exchange=exchange, symbol=symbol)
            oi_start = max(start, now - timedelta(days=29))
            rows = [r for p in api.open_interest(sym, "1h", oi_start, now) for r in p]
            out["oi"] = rows_to_frame(
                OPEN_INTEREST, rows, exchange=exchange, symbol=symbol, source="api"
            )
            rows = [r for p in api.long_short(sym, "1h", oi_start, now) for r in p]
            out["ls"] = rows_to_frame(
                LONG_SHORT,
                rows,
                exchange=exchange,
                symbol=symbol,
                source="api",
                kind="global_account",
            )
        return out

    def last_bar(self, exchange: str, symbol: str, tf: str = "1m") -> datetime | None:
        """Open time of the newest stored candle (reads only the latest year file)."""
        base = (
            self.paths.curated_dataset(OHLCV.name)
            / f"exchange={exchange}"
            / f"symbol={symbol}"
            / f"timeframe={tf}"
        )
        files = sorted(base.glob(f"year=*/{PART_FILE}"))
        if not files:
            return None
        return pl.scan_parquet(files[-1]).select(pl.col("open_time").max()).collect().item()

    # ------------------------------------------------------------------ public API

    def meta(self) -> dict:
        return {
            "instruments": [instrument_json(i, True) for i in self.settings.instruments],
            "exchanges": list(EXCHANGES),
            "timeframes": TIMEFRAMES,
            "lenses": {k: v[0] for k, v in LENSES.items()},
            "live": self.hub is not None,
        }

    def search(self, query: str = "", limit: int = 30) -> list[dict]:
        """Coins on Binance/OKX (USDT perps). Empty query: the configured watchlist."""
        return [
            instrument_json(i, self.catalog.is_configured(i.id))
            for i in self.catalog.search(query, limit)
        ]

    def market(self, exchange: str) -> dict:
        """One row per listed USDT perp: price, 24 h change, volume and funding from two bulk REST
        calls (cached 30 s); open interest and long/short only for coins with stored data."""
        self._check_exchange(exchange)
        if self.offline:
            raise Offline("the market table needs the network (offline)")
        return self.cached(("market", exchange), lambda: self._market(exchange), ttl=MARKET_TTL)

    def _market(self, exchange: str) -> dict:
        from rinng.exchanges.binance import Binance
        from rinng.exchanges.okx import Okx

        if exchange == "binance":
            api = Binance()
            funding = {f["symbol"]: f for f in api.premium_index()}
            quotes = {t["symbol"]: t for t in api.tickers_24h()}
        else:
            api = Okx()
            funding = {f["inst_id"]: f for f in api.funding_rates()}
            quotes = {
                t["inst_id"]: {
                    **t,
                    "chg_24h": (t["price"] / t["open_24h"] - 1) * 100 if t["open_24h"] else 0.0,
                    "volume_24h": t["volume_24h_base"] * t["price"],
                }
                for t in api.swap_tickers()
            }
        named = {i.id: i.name for i in self.settings.instruments}
        rows = []
        for inst in self.catalog._listed().values():
            venue = getattr(inst, exchange, None)
            if venue not in quotes or venue not in funding:
                continue
            q, f = quotes[venue], funding[venue]
            rows.append(
                {
                    "symbol": inst.id,
                    "base": inst.base,
                    "name": named.get(inst.id) or inst.base,
                    "price": q["price"],
                    "chg_24h": q["chg_24h"],
                    "volume_24h": q["volume_24h"],
                    "funding_rate_pct": f["funding_rate"] * 100,
                    "next_funding": f["next_funding"],
                    **(self._stored_derivs(exchange, inst.id) if inst.id in named else NOT_STORED),
                }
            )
        return {"time": time.time(), "exchange": exchange, "rows": rows}

    def _stored_derivs(self, exchange: str, symbol: str) -> dict:
        """Open interest (value, 24 h change %) and long/short ratio from curated data only."""
        oi = read_curated(self.paths, OPEN_INTEREST, exchange=exchange, symbol=symbol)
        if oi.is_empty():
            return NOT_STORED
        oi = oi.sort("time")
        now = oi.row(-1, named=True)
        before = oi.filter(pl.col("time") <= now["time"] - timedelta(hours=24))
        chg = None
        if not before.is_empty() and before["oi_base"][-1]:
            chg = (now["oi_base"] / before["oi_base"][-1] - 1) * 100
        ls = read_curated(self.paths, LONG_SHORT, exchange=exchange, symbol=symbol)
        ls = ls.filter(pl.col("kind") == "global_account").sort("time")
        return {
            "collected": True,
            "oi_value": now["oi_value"],
            "oi_chg_24h": chg,
            "ls_ratio": None if ls.is_empty() else ls["ratio"][-1],
        }

    def instrument_info(self, symbol: str) -> dict:
        inst = self.instrument(symbol)
        return instrument_json(inst, self.catalog.is_configured(inst.id))

    def chart(
        self,
        lens: str = "structure",
        symbol: str = "BTC-USDT-PERP",
        exchange: str = "binance",
        tf: str = "4h",
        days: int = 180,
        period: str = "week",
        zigzag: str = "auto",
    ) -> dict:
        """Candles plus one lens's overlays (zones, levels, markers, series)."""
        if lens not in LENSES:
            raise NotFound(f"unknown lens {lens}; use one of {', '.join(LENSES)}")
        self._check_tf(tf)
        self._check_exchange(exchange)
        if not MIN_DAYS <= days <= MAX_DAYS:
            raise BadRequest(f"days must be between {MIN_DAYS} and {MAX_DAYS}")
        inst = self.instrument(symbol)
        sym = inst.id

        def build():
            o, source = self.candles(exchange, sym, tf, days)
            if o.height < 30:
                raise NotFound("not enough candles")
            ctx: dict = {"period": period, "asset": inst.base, "tf": tf, "zigzag": zigzag}
            if lens == "profile":
                base_tf = "15m" if days <= 45 else "1h" if days <= 400 else "4h"
                if timeframe_ms(base_tf) > timeframe_ms(tf):
                    base_tf = tf
                ctx["base"] = self.candles(exchange, sym, base_tf, days)[0]
            if lens == "forecast":
                # Long history for the past-trajectory set; ends exactly at the last displayed bar.
                hist = load_ohlcv(self.paths, exchange, sym, tf)
                hist = hist.filter(pl.col("open_time") <= o["open_time"][-1]).tail(20_000)
                if hist.height < 2_000:
                    # Coin with no stored data: fetch up to MAX_BARS bars via REST instead.
                    need = MAX_BARS * timeframe_ms(tf) / 86_400_000
                    more = self.candles(exchange, sym, tf, int(need) + 1)[0]
                    hist = more if more.height > hist.height else hist
                ctx["history"] = hist if hist.height >= o.height else o
            if lens == "derivatives":
                ctx.update(self.derivs(exchange, sym, o["open_time"][0]))
            payload = LENSES[lens][1](o, ctx)
            return to_native({"candles": candles_json(o), "source": source, **payload})

        key = (lens, sym, exchange, tf, days, period, zigzag, self.stamp(exchange, sym, tf))
        return self.cached(key, build)

    def recent_candles(
        self, symbol: str, exchange: str = "binance", tf: str = "1h", limit: int = 200
    ) -> dict:
        """The last `limit` closed candles (curated if stored, else REST)."""
        self._check_tf(tf)
        self._check_exchange(exchange)
        if not 1 <= limit <= MAX_BARS:
            raise BadRequest(f"limit must be between 1 and {MAX_BARS}")
        sym = self.instrument(symbol).id
        days = math.ceil(limit * timeframe_ms(tf) / 86_400_000) + 1
        o, source = self.candles(exchange, sym, tf, min(max(days, MIN_DAYS), MAX_DAYS))
        return {
            "symbol": sym,
            "exchange": exchange,
            "timeframe": tf,
            "source": source,
            "candles": candles_json(o.tail(limit)),
        }

    def summary(self, symbol: str = "BTC-USDT-PERP", exchange: str = "binance") -> dict:
        """Dashboard figures: price, derivatives, 4h structure, profile, liquidity, Wyckoff,
        momentum."""
        self._check_exchange(exchange)
        sym = self.instrument(symbol).id

        def build():
            h1 = self.candles(exchange, sym, "1h", 30)[0]
            h4 = self.candles(exchange, sym, "4h", 180)[0]
            d1 = self.candles(exchange, sym, "1d", 1000)[0]
            if h1.height < 30 or h4.height < 30 or d1.height < 30:
                raise NotFound("not enough candles")
            d = self.derivs(exchange, sym, h1["open_time"].max() - timedelta(days=8))
            return to_native(
                {
                    "symbol": sym,
                    "exchange": exchange,
                    "price": summary.price_block(h1),
                    "derivatives": summary.derivatives_block(d["funding"], d["oi"], d["ls"]),
                    "structure": summary.structure_block(h4),
                    "profile": summary.profile_block(h1),
                    "liquidity": summary.liquidity_block(h1),
                    "wyckoff": summary.wyckoff_block(d1),
                    "momentum": summary.momentum_block(h4),
                }
            )

        return self.cached(("summary", sym, exchange, self.stamp(exchange, sym, "1h")), build)

    def desk(self, symbol: str = "BTC-USDT-PERP", exchange: str = "binance") -> dict:
        """5m chart combining every analysis layer + agent votes and the long/short scenarios."""
        self._check_exchange(exchange)
        sym = self.instrument(symbol).id

        def build():
            # Display part: full 5m bars (curated if complete, else REST). The long history
            # before it only serves as the forecast trajectory set:
            # aggregated from stored 1m bars, may have gaps.
            hist, source = self.candles(exchange, sym, desk.TF, 4)
            if hist.height < 60:
                raise NotFound("not enough candles")
            since = datetime.now(UTC) - timedelta(days=DESK_DAYS)
            old = self.from_1m(exchange, sym, desk.TF, since)
            old = old.filter(pl.col("open_time") < hist["open_time"][0])
            if old.height:
                hist = pl.concat([old, hist], how="diagonal_relaxed")
            h1 = self.candles(exchange, sym, "1h", 30)[0]
            d = self.derivs(exchange, sym, h1["open_time"].max() - timedelta(days=8))
            block = summary.derivatives_block(d["funding"], d["oi"], d["ls"])
            return to_native(desk.build(hist, h1, block, source))

        return self.cached(("desk", sym, exchange, self.stamp(exchange, sym, desk.TF)), build)

    async def news(self, base: str = "", limit: int = 60) -> dict:
        """Latest scored headlines, plus a 24h sentiment outlook for the market and `base`."""
        if self.offline:
            raise Offline("news needs the network (offline)")
        feed = self.news_feed
        await feed.refresh()
        items = feed.latest(feed.keep)
        now = int(time.time() * 1000)
        b = base.upper() or None
        return {
            "updated": int(feed.updated * 1000),
            "items": items[:limit],
            "market": outlook(items, now),
            "coin": outlook(items, now, b) | {"base": b} if b else None,
            "coin_items": [it for it in items if b in it["coins"]][:20] if b else [],
        }

    def status(self) -> dict:
        """What is stored locally: newest 1m candle per configured coin and exchange."""
        now = datetime.now(UTC)
        coins = []
        for inst in self.settings.instruments:
            row: dict = {"id": inst.id}
            for ex in EXCHANGES:
                if not getattr(inst, ex, None):
                    continue
                last = self.last_bar(ex, inst.id)
                age = None if last is None else int((now - last).total_seconds() // 60)
                iso = None if last is None else last.isoformat()
                row[ex] = {"last_1m": iso, "age_minutes": age}
            coins.append(row)
        return to_native(
            {
                "data_dir": str(self.settings.data_dir),
                "stored": self.paths.curated.exists(),
                "live": self.hub is not None,
                "instruments": coins,
            }
        )
