"""Tiến trình `rinng live`: collector + cập nhật curated tăng dần + web, trên cùng event loop.

- Collector như `rinng collect`, thêm stream nến 1m; mọi bản ghi đi qua LiveHub.
- Updater: nến 1m đóng → ghi curated + resample đuôi → báo LiveHub (nến khung lớn đóng thì
  client vẽ lại lens). Lúc khởi động và mỗi phút: lấp nến 1m thiếu bằng REST (mất kết nối,
  máy ngủ...). Mỗi 5 phút: curate các bảng phái sinh mà poller ghi vào raw.
- Web: FastAPI như `rinng web`, thêm WebSocket /ws/live.
"""

import asyncio
import contextlib
import logging
import signal
from datetime import UTC, datetime, timedelta

import polars as pl
import uvicorn

from rinng.config import Settings
from rinng.exchanges.binance import Binance
from rinng.exchanges.listing import Catalog
from rinng.exchanges.okx import Okx
from rinng.ingest.collector.poller import run_poller
from rinng.ingest.collector.sink import Sink
from rinng.ingest.collector.ws import binance_feed, okx_candle_feed, okx_feed, run_feed
from rinng.live.hub import LiveHub
from rinng.live.tail import curate_tail, latest_1m_open
from rinng.pipeline.curate import curate
from rinng.store.paths import DataPaths
from rinng.timeframes import bucket_start_ms, timeframe_ms

log = logging.getLogger(__name__)

DERIVED_TABLES = {"funding", "open_interest", "long_short", "taker_volume", "mark_price"}
MAX_GAP_FILL = timedelta(days=3)  # thiếu lâu hơn thì nên chạy `rinng backfill`


def _ms_rows(frame: pl.DataFrame) -> list[dict]:
    return frame.with_columns(pl.col("open_time").dt.epoch("ms")).to_dicts()


class Updater:
    def __init__(self, settings: Settings, paths: DataPaths, hub: LiveHub):
        self.settings = settings
        self.paths = paths
        self.hub = hub
        self.apis = {"binance": Binance(), "okx": Okx()}
        self.pairs = [
            (ex, inst.id, getattr(inst, ex))
            for inst in settings.instruments
            if inst.kind == "perp"
            for ex in ("binance", "okx")
            if getattr(inst, ex)
        ]

    def _apply(self, exchange: str, symbol: str, bars: list[dict]) -> None:
        tails = curate_tail(self.paths, exchange, symbol, bars, self.settings.timeframes)
        for tf, frame in tails.items():
            self.hub.set_tail(exchange, symbol, tf, _ms_rows(frame))

    def _fill_gap(self, exchange: str, symbol: str, venue: str) -> int:
        """Lấy nến 1m đã đóng từ REST cho phần curated còn thiếu tới hiện tại."""
        last = latest_1m_open(self.paths, exchange, symbol)
        now = datetime.now(UTC)
        start = (last + timedelta(minutes=1)) if last else now - timedelta(days=1)
        start = max(start, now - MAX_GAP_FILL)
        rows: list[dict] = []
        if now - start >= timedelta(minutes=2):
            for page in self.apis[exchange].klines(venue, "1m", start, now):
                rows += [r for r in page if r["is_closed"]]
        self._apply(exchange, symbol, rows)
        return len(rows)

    def fill_all(self) -> None:
        for ex, sym, venue in self.pairs:
            try:
                n = self._fill_gap(ex, sym, venue)
                if n:
                    log.info("%s %s: lấp %d nến 1m bằng REST", ex, sym, n)
            except Exception as exc:  # một sàn lỗi không làm dừng sàn kia
                log.warning("%s %s: lấp nến thất bại: %s", ex, sym, exc)

    async def run(self, stop: asyncio.Event) -> None:
        await asyncio.to_thread(self.fill_all)
        loop = asyncio.get_running_loop()
        next_gap = loop.time() + 60
        next_curate = loop.time()
        while not stop.is_set():
            batch: dict[tuple[str, str], list[dict]] = {}
            try:
                ex, sym, row = await asyncio.wait_for(self.hub.closed_queue.get(), 1.0)
                batch.setdefault((ex, sym), []).append(row)
                await asyncio.sleep(0.3)  # gom nến của các symbol khác đóng cùng phút
                while not self.hub.closed_queue.empty():
                    ex, sym, row = self.hub.closed_queue.get_nowait()
                    batch.setdefault((ex, sym), []).append(row)
            except TimeoutError:
                pass
            for (ex, sym), rows in batch.items():
                try:
                    await asyncio.to_thread(self._apply, ex, sym, rows)
                except Exception as exc:
                    log.warning("%s %s: ghi nến thất bại: %s", ex, sym, exc)
            now = loop.time()
            if now >= next_gap:
                next_gap = now + 60
                await asyncio.to_thread(self.fill_all)
            if now >= next_curate:
                next_curate = now + 300
                try:
                    await asyncio.to_thread(curate, self.paths, self.settings, only=DERIVED_TABLES)
                except Exception as exc:
                    log.warning("curate phái sinh thất bại: %s", exc)


class _Server(uvicorn.Server):
    """uvicorn không tự bắt tín hiệu; tiến trình live tự dừng mọi thứ theo thứ tự."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


async def _status_loop(hub: LiveHub, stop: asyncio.Event) -> None:
    while not stop.is_set():
        hub.broadcast_status()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), 2.0)


class _NullSink:
    """Coin mở thêm khi tìm kiếm: chỉ dùng cho realtime, không lưu raw."""

    written_rows = 0

    def add(self, records) -> None:
        pass

    def flush(self) -> int:
        return 0


class OnDemandFeeds:
    """Mở feed WebSocket cho coin ngoài cấu hình khi có client xem nó (tối đa `cap` coin;
    vượt thì đóng coin lâu nhất)."""

    def __init__(self, hub: LiveHub, catalog: Catalog, paths: DataPaths, cap: int = 8):
        self.hub = hub
        self.catalog = catalog
        self.paths = paths
        self.cap = cap
        self.apis = {"binance": Binance(), "okx": Okx()}
        self.running: dict[tuple[str, str], tuple[asyncio.Event, list[asyncio.Task]]] = {}
        self.pending: set[tuple[str, str]] = set()

    async def ensure(self, key: tuple[str, str]) -> None:
        if key in self.running or key in self.pending or self.hub.covers(key):
            return
        self.pending.add(key)
        try:
            await self._start(key)
        except Exception as exc:
            log.warning("%s %s: không mở được feed realtime: %s", key[0], key[1], exc)
        finally:
            self.pending.discard(key)

    async def _start(self, key: tuple[str, str]) -> None:
        exchange, symbol = key
        inst = await asyncio.to_thread(self.catalog.resolve, symbol)
        venue = getattr(inst, exchange)
        if not venue:
            return
        # Nền cho nến đang chạy của mọi khung: nến 1m đã đóng từ đầu nến lớn nhất hiện tại.
        now = datetime.now(UTC)
        longest = max(self.hub.timeframes, key=timeframe_ms)
        start = datetime.fromtimestamp(
            bucket_start_ms(int(now.timestamp() * 1000), longest) / 1000, UTC
        )
        api = self.apis[exchange]
        rows = await asyncio.to_thread(
            lambda: [r for p in api.klines(venue, "1m", start, now) for r in p if r["is_closed"]]
        )
        self.hub.seed_adhoc(key, rows)
        if exchange == "binance":
            feeds = [binance_feed({venue: symbol})]
        else:
            ct = await asyncio.to_thread(self.apis["okx"].contract_value, venue)
            feeds = [okx_feed({venue: symbol}, {venue: ct}), okx_candle_feed({venue: symbol})]
        stop = asyncio.Event()
        tasks = []
        for f in feeds:
            f.on_records = self.hub.ingest
            tasks.append(asyncio.create_task(run_feed(f, _NullSink(), self.paths, stop)))
        self.running[key] = (stop, tasks)
        log.info("%s %s: mở feed realtime theo yêu cầu", exchange, symbol)
        while len(self.running) > self.cap:
            old = next(iter(self.running))
            self.stop(old)

    def stop(self, key: tuple[str, str]) -> None:
        ev, _ = self.running.pop(key)
        ev.set()
        self.hub.adhoc.discard(key)

    def stop_all(self) -> None:
        for key in list(self.running):
            self.stop(key)


async def serve_live(settings: Settings, host: str, port: int) -> None:
    from rinng.web.app import create_app

    paths = DataPaths(settings.data_dir)
    hub = LiveHub(settings.timeframes)
    catalog = Catalog(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    perps = [i for i in settings.instruments if i.kind == "perp"]
    bn = {i.binance: i.id for i in perps if i.binance}
    ox = {i.okx: i.id for i in perps if i.okx}
    okx = Okx()
    ct = await asyncio.to_thread(lambda: {s: okx.contract_value(s) for s in ox})
    feeds = [binance_feed(bn), okx_feed(ox, ct), okx_candle_feed(ox)]
    for f in feeds:
        f.on_records = hub.ingest
    hub.tracked = {("binance", i.id) for i in perps if i.binance} | {
        ("okx", i.id) for i in perps if i.okx
    }
    on_demand = OnDemandFeeds(hub, catalog, paths)
    hub.on_new_key = on_demand.ensure

    server = _Server(
        uvicorn.Config(
            create_app(settings, hub, catalog), host=host, port=port, log_level="warning"
        )
    )
    tasks = [asyncio.create_task(run_feed(f, Sink(paths, f.exchange), paths, stop)) for f in feeds]
    tasks += [
        asyncio.create_task(run_poller(api, settings, Sink(paths, api.name), stop))
        for api in (Binance(), okx)
    ]
    tasks.append(asyncio.create_task(Updater(settings, paths, hub).run(stop)))
    tasks.append(asyncio.create_task(_status_loop(hub, stop)))
    web = asyncio.create_task(server.serve())

    await stop.wait()
    on_demand.stop_all()
    server.should_exit = True
    await asyncio.gather(web, *tasks, return_exceptions=True)
