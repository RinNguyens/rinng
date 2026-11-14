"""Collector process: WebSocket + poller for both exchanges, clean shutdown on SIGINT/SIGTERM."""

import asyncio
import logging
import signal

from rinng.config import Settings
from rinng.exchanges.binance import Binance
from rinng.exchanges.okx import Okx
from rinng.ingest.collector.poller import run_poller
from rinng.ingest.collector.sink import Sink
from rinng.ingest.collector.ws import binance_feed, okx_candle_feed, okx_feed, run_feed
from rinng.store.paths import DataPaths

log = logging.getLogger(__name__)


async def collect(settings: Settings, duration: float | None = None) -> dict[str, dict]:
    """Run until stopped (or after `duration` seconds). Returns stats to print."""
    paths = DataPaths(settings.data_dir)
    perps = [i for i in settings.instruments if i.kind == "perp"]
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    binance, okx = Binance(), Okx()
    bn_symbols = {i.binance: i.id for i in perps if i.binance}
    okx_symbols = {i.okx: i.id for i in perps if i.okx}
    contract_values = {s: okx.contract_value(s) for s in okx_symbols}

    poll_sinks = {"binance": Sink(paths, "binance"), "okx": Sink(paths, "okx")}
    feeds = [
        binance_feed(bn_symbols),
        okx_feed(okx_symbols, contract_values),
        okx_candle_feed(okx_symbols),
    ]
    sinks = [Sink(paths, f.exchange) for f in feeds]
    tasks = [
        asyncio.create_task(run_feed(f, sink, paths, stop))
        for f, sink in zip(feeds, sinks, strict=True)
    ]
    tasks += [
        asyncio.create_task(run_poller(api, settings, poll_sinks[api.name], stop))
        for api in (binance, okx)
    ]
    if duration is not None:
        loop.call_later(duration, stop.set)
    await asyncio.gather(*tasks)
    out: dict[str, dict] = {}
    for f, sink in zip(feeds, sinks, strict=True):
        s = out.setdefault(
            f.exchange, {"messages": 0, "reconnects": 0, "ws_rows": 0, "poll_rows": 0}
        )
        s["messages"] += f.stats["messages"]
        s["reconnects"] += f.stats["reconnects"]
        s["ws_rows"] += sink.written_rows
        s["poll_rows"] = poll_sinks[f.exchange].written_rows
    return out
