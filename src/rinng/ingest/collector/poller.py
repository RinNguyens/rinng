"""Gọi REST định kỳ cho các chuỗi sàn chỉ giữ ngắn hạn: OI, long/short, taker volume, funding.

Mỗi vòng hỏi lại một cửa sổ trùng với vòng trước (mặc định 1 giờ) để lấp các điểm bị lỡ;
dòng trùng được khử ở bước curate. Lỗi của một lời gọi chỉ được ghi log, không dừng vòng.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from rinng.config import Settings
from rinng.exchanges.base import Exchange
from rinng.exchanges.ratelimit import ExchangeError
from rinng.ingest.collector.messages import Record
from rinng.ingest.collector.sink import Sink

log = logging.getLogger(__name__)

PERIOD = "5m"
# (phương thức của bộ chuyển đổi, bảng, cột cố định)
STATS = (
    ("open_interest", "open_interest", {"source": "api"}),
    ("long_short", "long_short", {"source": "api", "kind": "global_account"}),
    ("taker_volume", "taker_volume", {"source": "api"}),
)


def poll_once(
    api: Exchange, settings: Settings, sink: Sink, now: datetime, lookback: timedelta
) -> int:
    """Một vòng hỏi cho mọi instrument. Trả về số dòng nhận được."""
    start = now - lookback
    received = 0
    for inst in settings.instruments:
        symbol = getattr(inst, api.name, None)
        if symbol is None or inst.kind != "perp":
            continue
        calls = [(m, t, c, (symbol, PERIOD, start, now)) for m, t, c in STATS]
        calls.append(("funding", "funding", {}, (symbol, now - timedelta(days=1), now)))
        for method, tbl, constants, args in calls:
            try:
                rows = [r for page in getattr(api, method)(*args) for r in page]
            except (ExchangeError, httpx.HTTPError, OSError) as exc:
                log.warning("%s %s %s: %s", api.name, method, symbol, exc)
                continue
            sink.add([Record(tbl, inst.id, {**r, **constants}) for r in rows])
            received += len(rows)
    sink.flush()
    return received


async def run_poller(
    api: Exchange,
    settings: Settings,
    sink: Sink,
    stop: asyncio.Event,
    *,
    interval: float = 300.0,
    lookback: timedelta = timedelta(hours=1),
) -> None:
    while not stop.is_set():
        now = datetime.now(UTC)
        received = await asyncio.to_thread(poll_once, api, settings, sink, now, lookback)
        log.info("%s poller: %d dòng", api.name, received)
        try:
            await asyncio.wait_for(stop.wait(), interval)
        except TimeoutError:
            pass
