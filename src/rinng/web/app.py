"""rinng web server: JSON API + static UI. Run: `uv run rinng web`.

The analysis itself lives in `rinng.service.Rinng` (shared with the CLI and the MCP server);
this module only maps it to HTTP routes, plus the Solana relay and the live WebSocket.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rinng.config import Settings
from rinng.exchanges.listing import Catalog
from rinng.makemoney import MakeMoney
from rinng.service import NETWORK_ERRORS, TIMEFRAMES, BadRequest, NotFound, Rinng
from rinng.web import solana

if TYPE_CHECKING:
    from rinng.live.hub import LiveHub

log = logging.getLogger(__name__)

# Static build of the React UI (web/ at the repo root, `pnpm build`).
SPA = Path(__file__).resolve().parents[3] / "web" / "dist" / "client"


def create_app(
    settings: Settings, hub: "LiveHub | None" = None, catalog: Catalog | None = None
) -> FastAPI:
    """`hub`: present when run via `rinng live` (realtime data + WebSocket /ws/live).
    `catalog`: exchange coin catalog for opening coins outside the config (data via REST)."""
    app = FastAPI(title="rinng")
    svc = Rinng(settings, hub, catalog)
    app.state.rinng = svc

    @app.exception_handler(NotFound)
    async def not_found(_: Request, e: NotFound):
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.exception_handler(BadRequest)
    async def bad_request(_: Request, e: BadRequest):
        return JSONResponse({"detail": str(e)}, status_code=400)

    async def exchange_unreachable(_: Request, e: Exception):
        log.warning("exchange request failed", exc_info=e)
        detail = f"exchange error: {type(e).__name__}"
        if isinstance(e, httpx.HTTPStatusError):
            detail += f" {e.response.status_code}"
        return JSONResponse({"detail": detail}, status_code=502)

    for error in NETWORK_ERRORS:
        app.add_exception_handler(error, exchange_unreachable)

    mm = MakeMoney(svc, Path(settings.data_dir))
    app.state.makemoney = mm

    app.router.on_startup.append(mm.ensure_guard)  # resting SL/TP keep working

    @app.get("/api/makemoney")
    async def mm_state():
        mm.ensure_guard()
        return mm.snapshot()

    @app.post("/api/makemoney/config")
    async def mm_config(request: Request):
        return mm.update_config(await request.json())

    @app.get("/api/makemoney/symbols")
    async def mm_symbols():
        return await mm.bn.top_symbols()

    @app.post("/api/makemoney/{action}")
    async def mm_action(action: str):
        try:
            if action == "start":
                mm.start()
            elif action == "stop":
                mm.stop()
            elif action == "reset":
                return mm.reset()
            elif action == "tick":
                return await mm.tick()
            else:
                raise HTTPException(404, "unknown action")
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e)) from e
        return mm.snapshot()

    @app.get("/api/meta")
    def meta():
        return svc.meta()

    @app.get("/api/chart")
    def chart(
        lens: str = Query("structure"),
        symbol: str = Query("BTC-USDT-PERP"),
        exchange: str = Query("binance"),
        tf: str = Query("1d"),
        days: int = Query(365, ge=2, le=3000),
        period: str = Query("week"),
        zigzag: str = Query("auto", pattern=r"^(auto|\d{1,2}(\.\d+)?)$"),
    ):
        return svc.chart(lens, symbol, exchange, tf, days, period, zigzag)

    @app.get("/api/market")
    def market_api(exchange: str = Query("binance")):
        """Every listed USDT perp on `exchange`: price, change, volume, funding (+ stored OI)."""
        return svc.market(exchange)

    @app.get("/api/instruments")
    def instruments_api(q: str = Query(""), limit: int = Query(30, ge=1, le=100)):
        """Search coins on Binance/OKX (USDT perps). Empty q: default list from the config."""
        return svc.search(q, limit)

    @app.get("/api/instrument")
    def instrument_api(symbol: str = Query(...)):
        return svc.instrument_info(symbol)

    @app.get("/api/summary")
    def summary_api(
        symbol: str = Query("BTC-USDT-PERP"),
        exchange: str = Query("binance"),
    ):
        return svc.summary(symbol, exchange)

    @app.get("/api/desk")
    def desk_api(
        symbol: str = Query("BTC-USDT-PERP"),
        exchange: str = Query("binance"),
    ):
        """5m chart combining every analysis layer + agent votes and the long/short scenarios."""
        return svc.desk(symbol, exchange)

    @app.get("/api/news")
    async def news_api(
        base: str = Query("", description="coin to build an outlook for, e.g. BTC"),
        limit: int = Query(60, ge=1, le=300),
    ):
        """Latest scored headlines, plus a 24h sentiment outlook for the market and `base`."""
        return await svc.news(base, limit)

    @app.get("/api/status")
    def status_api():
        """What is stored locally and how fresh it is."""
        return svc.status()

    @app.post("/api/solana")
    async def solana_rpc(request: Request):
        """Read-only Solana JSON-RPC relay for the wallet check (see rinng.web.solana)."""
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON") from None
        if why := solana.check(body):
            raise HTTPException(400, why)
        try:
            status, data = await solana.relay(body)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Solana RPC unreachable: {type(e).__name__}") from None
        return JSONResponse(data, status_code=status)

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

    if (SPA / "_shell.html").exists():
        # The React UI (web/) is built: serve it.
        app.mount("/assets", StaticFiles(directory=SPA / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            f = SPA / path
            if path and f.is_file() and SPA in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(SPA / "_shell.html")
    else:

        @app.get("/")
        def index():
            return HTMLResponse(
                "<!doctype html><title>rinng</title><p>The web UI is not built yet. Run "
                "<code>pnpm --dir web install &amp;&amp; pnpm --dir web build</code>, then reload."
                "</p><p>The JSON API is under <code>/api</code>.</p>"
            )

    return app
