"""Server web rinng: API JSON + giao diện tĩnh. Chạy: `uv run rinng web`.

Nguồn dữ liệu: ưu tiên dữ liệu curated trong data/; nếu khoảng thời gian chưa có thì lấy
thẳng từ REST của Binance (chỉ nến và funding/OI/long-short gần đây). Kết quả lens được
cache trong bộ nhớ 60 giây.
"""

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rinng.config import Settings
from rinng.exchanges.base import timeframe_ms
from rinng.pipeline.run import load_ohlcv
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.schemas import FUNDING, LONG_SHORT, OHLCV, OPEN_INTEREST, rows_to_frame
from rinng.web import summary
from rinng.web.lenses import LENSES, candles_json, to_native

STATIC = Path(__file__).parent / "static"
# Bản build tĩnh của giao diện React (thư mục web/ ở gốc repo, `pnpm build`).
SPA = Path(__file__).resolve().parents[3] / "web" / "dist" / "client"
TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"]
MAX_BARS = 3000


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="rinng")
    paths = DataPaths(settings.data_dir)
    cache: dict[tuple, tuple[float, object]] = {}

    def cached(key: tuple, fn, ttl: float = 60.0):
        hit = cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        value = fn()
        cache[key] = (time.time(), value)
        return value

    def venue(symbol: str, exchange: str) -> str:
        for inst in settings.instruments:
            if inst.id == symbol:
                return getattr(inst, exchange)
        raise HTTPException(404, f"không có instrument {symbol}")

    def candles(exchange: str, symbol: str, tf: str, days: int) -> tuple[pl.DataFrame, str]:
        start = datetime.now(UTC) - timedelta(days=days)
        o = load_ohlcv(paths, exchange, symbol, tf, start)
        need = days * 86_400_000 / timeframe_ms(tf)
        if o.height >= 0.9 * min(need, MAX_BARS) and o.height > 2:
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
                # Hai nguồn cho số hơi khác nhau: dùng dump (dài hơn), lấp phần mới hơn bằng api.
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
            "instruments": [i.id for i in settings.instruments],
            "exchanges": ["binance", "okx"],
            "timeframes": TIMEFRAMES,
            "lenses": {k: v[0] for k, v in LENSES.items()},
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
            raise HTTPException(404, f"không có lens {lens}")
        if tf not in TIMEFRAMES:
            raise HTTPException(400, f"khung {tf} không hỗ trợ")

        def build():
            o, source = candles(exchange, symbol, tf, days)
            if o.height < 30:
                raise HTTPException(404, "chưa đủ nến")
            ctx: dict = {"period": period}
            if lens == "profile":
                base_tf = "15m" if days <= 45 else "1h" if days <= 400 else "4h"
                if timeframe_ms(base_tf) > timeframe_ms(tf):
                    base_tf = tf
                ctx["base"] = candles(exchange, symbol, base_tf, days)[0]
            if lens == "derivatives":
                ctx.update(derivs(exchange, symbol, o["open_time"][0]))
            payload = LENSES[lens][1](o, ctx)
            return to_native({"candles": candles_json(o), "source": source, **payload})

        return cached((lens, symbol, exchange, tf, days, period), build)

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
                raise HTTPException(404, "chưa đủ nến")
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

        return cached(("summary", symbol, exchange), build)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    if (SPA / "_shell.html").exists():
        # Giao diện mới (web/, React + shadcn) đã build: phục vụ nó; giao diện cũ ở /classic.
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
