"""rinng web server: JSON API + static UI. Run: `uv run rinng web`.

Data source: curated data in data/ first; when the range is missing, fetch directly from the
exchange REST API (candles, and recent funding/OI/long-short on Binance). Lens results are
cached in memory for 60 seconds.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rinng.config import Settings
from rinng.exchanges.base import timeframe_ms
from rinng.exchanges.listing import Catalog, icon_symbol
from rinng.news.feed import NewsFeed
from rinng.news.score import outlook
from rinng.pipeline.run import load_ohlcv
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.resample import resample_ohlcv
from rinng.store.schemas import FUNDING, LONG_SHORT, OHLCV, OPEN_INTEREST, rows_to_frame
from rinng.web import desk, summary
from rinng.web.lenses import LENSES, candles_json, to_native

if TYPE_CHECKING:
    from rinng.live.hub import LiveHub

STATIC = Path(__file__).parent / "static"
# Static build of the React UI (web/ at the repo root, `pnpm build`).
SPA = Path(__file__).resolve().parents[3] / "web" / "dist" / "client"
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w"]
DESK_DAYS = 70  # 5m history behind the desk projection (~20k candles)
MAX_BARS = 3000


def _instrument_json(i, configured: bool) -> dict:
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


def create_app(
    settings: Settings, hub: "LiveHub | None" = None, catalog: Catalog | None = None
) -> FastAPI:
    """`hub`: present when run via `rinng live` (realtime data + WebSocket /ws/live).
    `catalog`: exchange coin catalog for opening coins outside the config (data via REST)."""
    app = FastAPI(title="rinng")
    catalog = catalog or Catalog(settings)
    paths = DataPaths(settings.data_dir)
    cache: dict[tuple, tuple[float, object]] = {}
    news = NewsFeed()
    # Live: cache keyed by the latest closed bar of that timeframe (a new close recomputes);
    # not live: data only changes when curate runs, so a 60-second expiry is enough.
    ttl = 3600.0 if hub is not None else 60.0

    def stamp(exchange: str, symbol: str, tf: str) -> int | None:
        return None if hub is None else hub.last_closed.get((exchange, symbol, tf))

    def cached(key: tuple, fn):
        # Last key is the closed-bar time; without one (off-config coin, no feed) 60 s.
        life = ttl if key[-1] is not None else 60.0
        hit = cache.get(key)
        if hit and time.time() - hit[0] < life:
            return hit[1]
        value = fn()
        if len(cache) > 256:
            for old in sorted(cache, key=lambda k: cache[k][0])[:64]:
                cache.pop(old, None)
        cache[key] = (time.time(), value)
        return value

    def instrument(symbol: str):
        try:
            return catalog.resolve(symbol)
        except KeyError:
            raise HTTPException(404, f"unknown instrument {symbol}") from None

    def venue(symbol: str, exchange: str) -> str:
        v = getattr(instrument(symbol), exchange, None)
        if not v:
            raise HTTPException(404, f"{symbol} is not listed on {exchange}")
        return v

    def from_1m(exchange: str, symbol: str, tf: str, start: datetime) -> pl.DataFrame:
        """Closed `tf` bars aggregated from 1m bars in curated (empty if nothing stored)."""
        m1 = load_ohlcv(paths, exchange, symbol, "1m", start)
        if m1.height < 2:
            return m1
        return resample_ohlcv(m1, tf).filter(pl.col("is_closed")).sort("open_time")

    def candles(exchange: str, symbol: str, tf: str, days: int) -> tuple[pl.DataFrame, str]:
        start = datetime.now(UTC) - timedelta(days=days)
        o = load_ohlcv(paths, exchange, symbol, tf, start)
        need = days * 86_400_000 / timeframe_ms(tf)
        if o.height >= 0.9 * min(need, MAX_BARS) and o.height > 2:
            return o.tail(MAX_BARS), "curated"
        if tf == "5m":
            # 5m not fully stored yet (timeframe added recently): aggregate from stored 1m bars.
            o = from_1m(exchange, symbol, tf, start)
            if o.height >= 0.9 * min(need, MAX_BARS):
                return o.tail(MAX_BARS), "curated"
        from rinng.exchanges.binance import Binance
        from rinng.exchanges.okx import Okx

        api = Binance() if exchange == "binance" else Okx()
        rows = [
            r for p in api.klines(venue(symbol, exchange), tf, start, datetime.now(UTC)) for r in p
        ]
        f = rows_to_frame(OHLCV, rows, exchange=exchange, symbol=symbol, timeframe=tf)
        return f.filter(pl.col("is_closed")).sort("open_time").tail(MAX_BARS), "live"

    def derivs(exchange: str, symbol: str, start: datetime) -> dict:
        out = {}
        for key, tbl, extra in (
            ("funding", FUNDING, {}),
            ("oi", OPEN_INTEREST, {}),
            ("ls", LONG_SHORT, {"kind": "global_account"}),
        ):
            f = read_curated(paths, tbl, exchange=exchange, symbol=symbol, start=start)
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
        if out["funding"].is_empty() and exchange == "binance":
            from rinng.exchanges.binance import Binance

            api, now = Binance(), datetime.now(UTC)
            sym = venue(symbol, exchange)
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

    @app.get("/api/meta")
    def meta():
        return {
            "instruments": [_instrument_json(i, True) for i in settings.instruments],
            "exchanges": ["binance", "okx"],
            "timeframes": TIMEFRAMES,
            "lenses": {k: v[0] for k, v in LENSES.items()},
            "live": hub is not None,
        }

    @app.get("/api/chart")
    def chart(
        lens: str = Query("structure"),
        symbol: str = Query("BTC-USDT-PERP"),
        exchange: str = Query("binance"),
        tf: str = Query("4h"),
        days: int = Query(180, ge=2, le=3000),
        period: str = Query("week"),
    ):
        if lens not in LENSES:
            raise HTTPException(404, f"unknown lens {lens}")
        if tf not in TIMEFRAMES:
            raise HTTPException(400, f"timeframe {tf} not supported")

        def build():
            o, source = candles(exchange, symbol, tf, days)
            if o.height < 30:
                raise HTTPException(404, "not enough candles")
            ctx: dict = {"period": period, "asset": instrument(symbol).base}
            if lens == "profile":
                base_tf = "15m" if days <= 45 else "1h" if days <= 400 else "4h"
                if timeframe_ms(base_tf) > timeframe_ms(tf):
                    base_tf = tf
                ctx["base"] = candles(exchange, symbol, base_tf, days)[0]
            if lens == "forecast":
                # Long history for the past-trajectory set; ends exactly at the last displayed bar.
                hist = load_ohlcv(paths, exchange, symbol, tf)
                hist = hist.filter(pl.col("open_time") <= o["open_time"][-1]).tail(20_000)
                if hist.height < 2_000:
                    # Coin with no stored data: fetch up to MAX_BARS bars via REST instead.
                    need = MAX_BARS * timeframe_ms(tf) / 86_400_000
                    more = candles(exchange, symbol, tf, int(need) + 1)[0]
                    hist = more if more.height > hist.height else hist
                ctx["history"] = hist if hist.height >= o.height else o
            if lens == "derivatives":
                ctx.update(derivs(exchange, symbol, o["open_time"][0]))
            payload = LENSES[lens][1](o, ctx)
            return to_native({"candles": candles_json(o), "source": source, **payload})

        return cached(
            (lens, symbol, exchange, tf, days, period, stamp(exchange, symbol, tf)), build
        )

    @app.get("/api/instruments")
    def instruments_api(q: str = Query(""), limit: int = Query(30, ge=1, le=100)):
        """Search coins on Binance/OKX (USDT perps). Empty q: default list from the config."""
        return [_instrument_json(i, catalog.is_configured(i.id)) for i in catalog.search(q, limit)]

    @app.get("/api/instrument")
    def instrument_api(symbol: str = Query(...)):
        return _instrument_json(instrument(symbol), catalog.is_configured(symbol))

    @app.get("/api/summary")
    def summary_api(
        symbol: str = Query("BTC-USDT-PERP"),
        exchange: str = Query("binance"),
    ):
        def build():
            h1 = candles(exchange, symbol, "1h", 30)[0]
            h4 = candles(exchange, symbol, "4h", 180)[0]
            d1 = candles(exchange, symbol, "1d", 1000)[0]
            if h1.height < 30 or h4.height < 30 or d1.height < 30:
                raise HTTPException(404, "not enough candles")
            d = derivs(exchange, symbol, h1["open_time"].max() - timedelta(days=8))
            return to_native(
                {
                    "symbol": symbol,
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

        return cached(("summary", symbol, exchange, stamp(exchange, symbol, "1h")), build)

    @app.get("/api/desk")
    def desk_api(
        symbol: str = Query("BTC-USDT-PERP"),
        exchange: str = Query("binance"),
    ):
        """5m chart combining every analysis layer + agent votes and the long/short scenarios."""

        def build():
            # Display part: full 5m bars (curated if complete, else REST). The long history
            # before it only serves as the forecast trajectory set:
            # aggregated from stored 1m bars, may have gaps.
            hist, source = candles(exchange, symbol, desk.TF, 4)
            if hist.height < 60:
                raise HTTPException(404, "not enough candles")
            old = from_1m(exchange, symbol, desk.TF, datetime.now(UTC) - timedelta(days=DESK_DAYS))
            old = old.filter(pl.col("open_time") < hist["open_time"][0])
            if old.height:
                hist = pl.concat([old, hist], how="diagonal_relaxed")
            h1 = candles(exchange, symbol, "1h", 30)[0]
            d = derivs(exchange, symbol, h1["open_time"].max() - timedelta(days=8))
            block = summary.derivatives_block(d["funding"], d["oi"], d["ls"])
            return to_native(desk.build(hist, h1, block, source))

        return cached(("desk", symbol, exchange, stamp(exchange, symbol, desk.TF)), build)

    @app.get("/api/news")
    async def news_api(
        base: str = Query("", description="coin to build an outlook for, e.g. BTC"),
        limit: int = Query(60, ge=1, le=300),
    ):
        """Latest scored headlines, plus a 24h sentiment outlook for the market and `base`."""
        await news.refresh()
        items = news.latest(news.keep)
        now = int(time.time() * 1000)
        b = base.upper() or None
        return {
            "updated": int(news.updated * 1000),
            "items": items[:limit],
            "market": outlook(items, now),
            "coin": outlook(items, now, b) | {"base": b} if b else None,
            "coin_items": [it for it in items if b in it["coins"]][:20] if b else [],
        }

    @app.websocket("/ws/live")
    async def live_ws(ws: WebSocket):
        """Client sends {"op": "sub", "symbol", "exchange", "tfs": [...]}; server pushes events
        tick, mark, bar (running bar), close (just-closed bar), liq, status."""
        if hub is None:
            await ws.close(code=1013, reason="live data is not running (use `rinng live`)")
            return
        await ws.accept()
        client = hub.connect()

        async def reader():
            while True:
                msg = await ws.receive_json()
                if msg.get("op") != "sub":
                    continue
                client.exchange = msg.get("exchange")
                client.symbol = msg.get("symbol")
                client.timeframes = set(msg.get("tfs") or []) & set(TIMEFRAMES)
                key = (client.exchange, client.symbol)
                if hub.on_new_key is not None and not hub.covers(key):
                    asyncio.create_task(hub.on_new_key(key))
                for event in hub.snapshot(key, client.timeframes):
                    if not client.queue.full():
                        client.queue.put_nowait(event)

        read_task = asyncio.create_task(reader())
        try:
            while True:
                get = asyncio.create_task(client.queue.get())
                done, _ = await asyncio.wait({get, read_task}, return_when=asyncio.FIRST_COMPLETED)
                if read_task in done:
                    get.cancel()
                    break
                await ws.send_json(get.result())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.disconnect(client)
            read_task.cancel()

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    if (SPA / "_shell.html").exists():
        # The React UI (web/) is built: serve it; the old UI stays at /classic.
        app.mount("/assets", StaticFiles(directory=SPA / "assets"), name="assets")

        @app.get("/classic")
        def classic():
            return FileResponse(STATIC / "index.html")

        @app.get("/{path:path}")
        def spa(path: str):
            f = SPA / path
            if path and f.is_file() and SPA in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(SPA / "_shell.html")
    else:

        @app.get("/")
        def index():
            return FileResponse(STATIC / "index.html")

    return app
