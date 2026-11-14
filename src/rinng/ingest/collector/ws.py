"""Kết nối WebSocket có tự nối lại và ghi nhận khoảng trống.

Mỗi lần mất kết nối, khoảng từ message cuối cùng nhận được tới message đầu tiên sau khi
nối lại được ghi vào meta/gaps cho mọi (bảng, symbol) mà kết nối đó phụ trách.
"""

import asyncio
import logging
import socket
import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import certifi
import websockets

from rinng.ingest.collector.messages import (
    OkxControl,
    Record,
    binance_streams,
    okx_candle_subscribe,
    okx_subscribe,
    parse_binance,
    parse_okx,
)
from rinng.ingest.collector.sink import Sink
from rinng.store import catalog
from rinng.store.paths import DataPaths

log = logging.getLogger(__name__)

BINANCE_WS = "wss://fstream.binance.com/market/stream"
OKX_WS = "wss://ws.okx.com/ws/v5/public"  # cổng 8443 sắp bị bỏ (thông báo 64010)
OKX_BUSINESS_WS = "wss://ws.okx.com/ws/v5/business"  # kênh nến
DATASETS = ("trades", "mark_price", "liquidations")


class Reconnect(Exception):
    """Sàn báo sắp ngắt hoặc kết nối đã quá tuổi: đóng và nối lại."""


@dataclass
class Feed:
    """Một kết nối WebSocket của một sàn."""

    exchange: str
    url: str
    symbols: dict[str, str]  # tên trên sàn → tên chuẩn
    parse: Callable[[str], list[Record] | OkxControl | None]
    on_open: Callable[[websockets.ClientConnection], Awaitable[None]] | None = None
    idle_ping: float | None = None  # gửi chuỗi "ping" khi im lặng quá số giây này
    max_lifetime: float | None = None  # chủ động nối lại trước khi sàn tự ngắt
    datasets: tuple[str, ...] = DATASETS
    stats: dict[str, int] = field(default_factory=lambda: {"messages": 0, "reconnects": 0})
    last_message: datetime | None = None
    # Gọi với mọi bản ghi vừa nhận (kể cả nến đang chạy), dùng cho dữ liệu realtime.
    on_records: Callable[[str, list[Record]], None] | None = None


def binance_feed(symbols: dict[str, str], url: str = BINANCE_WS) -> Feed:
    streams = "/".join(binance_streams(list(symbols)))
    return Feed(
        exchange="binance",
        url=f"{url}?streams={streams}",
        symbols=symbols,
        parse=lambda raw: parse_binance(raw, symbols),
        max_lifetime=23 * 3600,  # Binance ngắt sau 24 giờ
        datasets=(*DATASETS, "ohlcv"),
    )


def okx_feed(symbols: dict[str, str], contract_values: dict[str, float], url: str = OKX_WS) -> Feed:
    async def subscribe(ws):
        await ws.send(okx_subscribe(list(symbols)))

    return Feed(
        exchange="okx",
        url=url,
        symbols=symbols,
        parse=lambda raw: parse_okx(raw, symbols, contract_values),
        on_open=subscribe,
        idle_ping=20.0,  # OKX ngắt sau 30 giây im lặng
    )


def okx_candle_feed(symbols: dict[str, str], url: str = OKX_BUSINESS_WS) -> Feed:
    async def subscribe(ws):
        await ws.send(okx_candle_subscribe(list(symbols)))

    return Feed(
        exchange="okx",
        url=url,
        symbols=symbols,
        parse=lambda raw: parse_okx(raw, symbols, {}),
        on_open=subscribe,
        idle_ping=20.0,
        datasets=("ohlcv",),
    )


def _ssl_for(url: str) -> ssl.SSLContext | None:
    # Python cài từ python.org trên macOS không dùng kho chứng chỉ của hệ thống.
    return ssl.create_default_context(cafile=certifi.where()) if url.startswith("wss") else None


def _family_for(url: str) -> int:
    # OKX qua IPv6 treo ở bước bắt tay trên một số mạng (giống REST, xem exchanges/okx.py):
    # ép IPv4 cho OKX, sàn khác để hệ thống tự chọn.
    return socket.AF_INET if "okx.com" in url else socket.AF_UNSPEC


async def _receive(feed: Feed, ws, sink: Sink, on_first: Callable[[], None]) -> None:
    opened = time.monotonic()
    first = True
    while True:
        timeout = feed.idle_ping
        if feed.max_lifetime is not None:
            remaining = feed.max_lifetime - (time.monotonic() - opened)
            if remaining <= 0:
                raise Reconnect("kết nối đã quá tuổi tối đa")
            timeout = remaining if timeout is None else min(timeout, remaining)
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout)
        except TimeoutError:
            if feed.idle_ping is not None:
                await ws.send("ping")
            continue
        result = feed.parse(raw)
        if isinstance(result, OkxControl):
            if result.event == "error":
                raise RuntimeError(f"{feed.exchange} báo lỗi {result.code}: {result.message}")
            if result.code == "64008":
                raise Reconnect("sàn báo sắp ngắt để nâng cấp")
            continue
        if result is None:
            continue
        feed.stats["messages"] += 1
        if first:
            on_first()
            first = False
        sink.add(result)
        feed.last_message = datetime.now(UTC)
        if feed.on_records is not None and result:
            feed.on_records(feed.exchange, result)


async def run_feed(
    feed: Feed,
    sink: Sink,
    paths: DataPaths,
    stop: asyncio.Event,
    *,
    max_backoff: float = 60.0,
) -> None:
    """Chạy tới khi `stop` được bật. Mất kết nối thì chờ giãn cách rồi nối lại."""
    last_seen: datetime | None = None
    backoff = 1.0

    def mark_resumed() -> None:
        nonlocal backoff
        backoff = 1.0
        now = datetime.now(UTC)
        if last_seen is not None:
            for dataset in feed.datasets:
                for symbol in feed.symbols.values():
                    catalog.record_gap(
                        paths,
                        dataset=dataset,
                        exchange=feed.exchange,
                        symbol=symbol,
                        start=last_seen,
                        end=now,
                        reason="websocket reconnect",
                    )

    while not stop.is_set():
        try:
            async with websockets.connect(
                feed.url,
                ssl=_ssl_for(feed.url),
                family=_family_for(feed.url),
                open_timeout=15,
                max_size=2**22,
            ) as ws:
                if feed.on_open is not None:
                    await feed.on_open(ws)
                receiver = asyncio.create_task(_receive(feed, ws, sink, mark_resumed))
                stopper = asyncio.create_task(stop.wait())
                done, _ = await asyncio.wait(
                    {receiver, stopper}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in (receiver, stopper):
                    task.cancel()
                if receiver in done and not receiver.cancelled():
                    receiver.result()  # đẩy lỗi ra ngoài
        except Reconnect as exc:
            log.info("%s: nối lại (%s)", feed.exchange, exc)
            backoff = 0.0
        except (OSError, websockets.WebSocketException, RuntimeError, TimeoutError) as exc:
            log.warning("%s: mất kết nối: %s", feed.exchange, exc)
        if stop.is_set():
            break
        last_seen = feed.last_message or datetime.now(UTC)
        feed.stats["reconnects"] += 1
        try:
            await asyncio.wait_for(stop.wait(), backoff)
        except TimeoutError:
            pass
        backoff = min(max(backoff * 2, 1.0), max_backoff)
    sink.flush()
