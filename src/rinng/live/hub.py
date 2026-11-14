"""LiveHub: in-memory realtime state and event broadcast to WebSocket clients.

Receives records from the collector (same event loop) and keeps:
- last trade price, mark price/funding, running 1m candle per (exchange, symbol);
- the "base" of each timeframe's running candle = aggregate of closed 1m candles in it (updated by
  the updater after each curated write), merged with the running 1m candle into the running
  higher-TF candle;
- open time of the latest closed candle per timeframe (used as the lens cache key).

Events are JSON-serializable dicts; each client has its own queue, when full, old events are
dropped rather than slowing the collector.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from rinng.ingest.collector.messages import Record
from rinng.timeframes import bucket_start_ms, timeframe_ms

Key = tuple[str, str]  # (exchange, symbol)
THROTTLE = 0.25  # seconds between two tick/candle sends for the same key


@dataclass(eq=False)  # compare by identity so it can go in a set
class Client:
    queue: asyncio.Queue
    exchange: str | None = None
    symbol: str | None = None
    timeframes: set[str] = field(default_factory=set)

    def wants(self, key: Key) -> bool:
        return (self.exchange, self.symbol) == key


class LiveHub:
    def __init__(self, timeframes: list[str], clock: Callable[[], float] = time.monotonic):
        self.timeframes = list(timeframes)
        self._clock = clock
        self.price: dict[Key, dict] = {}
        self.mark: dict[Key, dict] = {}
        self.forming_1m: dict[Key, dict] = {}
        self.base: dict[tuple[str, str, str], dict] = {}  # (ex, sym, tf) → running candle base
        self.last_closed: dict[
            tuple[str, str, str], int
        ] = {}  # → open_time (ms) of the closed candle
        self.last_message: dict[str, float] = {}  # exchange → time.time() of the last message
        self.clients: set[Client] = set()
        self.closed_queue: asyncio.Queue[tuple[str, str, dict]] = asyncio.Queue()
        self._sent: dict[tuple, float] = {}
        # Configured coins: closed candles go through the updater (curated write). Coins opened
        # from search (adhoc): the hub builds higher-TF candles from 1m and reports closes.
        self.tracked: set[Key] = set()
        self.adhoc: set[Key] = set()
        self.on_new_key: Callable[[Key], Awaitable[None]] | None = None

    def covers(self, key: Key) -> bool:
        return key in self.tracked or key in self.adhoc

    # ------------------------------------------------------------------ client

    def connect(self, maxsize: int = 500) -> Client:
        c = Client(asyncio.Queue(maxsize=maxsize))
        self.clients.add(c)
        return c

    def disconnect(self, c: Client) -> None:
        self.clients.discard(c)

    def snapshot(self, key: Key, timeframes: set[str]) -> list[dict]:
        """Events sent on subscribe so the screen has data without waiting for a tick."""
        ex, sym = key
        out = [self.status()]
        if key in self.price:
            out.append({"type": "tick", "exchange": ex, "symbol": sym, **self.price[key]})
        if key in self.mark:
            out.append({"type": "mark", "exchange": ex, "symbol": sym, **self.mark[key]})
        for tf in timeframes:
            bar = self.forming(key, tf)
            if bar is not None:
                out.append({"type": "bar", "exchange": ex, "symbol": sym, "tf": tf, "bar": bar})
        return out

    def _send(self, event: dict, key: Key | None = None, tf: str | None = None) -> None:
        for c in list(self.clients):
            if key is not None and not c.wants(key):
                continue
            if tf is not None and tf not in c.timeframes:
                continue
            if c.queue.full():
                try:
                    c.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            c.queue.put_nowait(event)

    def _due(self, tag: tuple) -> bool:
        now = self._clock()
        if now - self._sent.get(tag, float("-inf")) < THROTTLE:
            return False
        self._sent[tag] = now
        return True

    def status(self) -> dict:
        now = time.time()
        return {
            "type": "status",
            "feeds": {ex: round(now - t, 1) for ex, t in self.last_message.items()},
        }

    # ------------------------------------------------------------------ input

    def ingest(self, exchange: str, records: list[Record]) -> None:
        """Collector callback for every WebSocket record."""
        self.last_message[exchange] = time.time()
        for r in records:
            key = (exchange, r.symbol)
            if r.table == "trades":
                self.price[key] = {"price": r.row["price"], "time": r.row["time"]}
                if self._due(("tick", key)):
                    self._send(
                        {
                            "type": "tick",
                            "exchange": exchange,
                            "symbol": r.symbol,
                            **self.price[key],
                        },
                        key,
                    )
            elif r.table == "mark_price":
                old = self.mark.get(key, {})
                self.mark[key] = {
                    "mark": r.row["mark_price"],
                    "index": r.row["index_price"] or old.get("index"),
                    "funding_rate": r.row["funding_rate"]
                    if r.row["funding_rate"] is not None
                    else old.get("funding_rate"),
                    "time": r.row["time"],
                }
                if self._due(("mark", key)):
                    self._send(
                        {
                            "type": "mark",
                            "exchange": exchange,
                            "symbol": r.symbol,
                            **self.mark[key],
                        },
                        key,
                    )
            elif r.table == "liquidations":
                self._send({"type": "liq", "exchange": exchange, "symbol": r.symbol, **r.row}, key)
            elif r.table == "ohlcv" and r.timeframe == "1m":
                self._on_1m(key, r.row)

    def _on_1m(self, key: Key, row: dict) -> None:
        if row["is_closed"]:
            self.forming_1m.pop(key, None)
            if key in self.adhoc:
                self._adhoc_closed(key, row)
            else:
                self.closed_queue.put_nowait((key[0], key[1], row))
        else:
            self.forming_1m[key] = row
        # Price also comes from candles if the exchange sends no trades (e.g. trade feed lags).
        self.price.setdefault(key, {"price": row["close"], "time": row["open_time"]})
        if not self._due(("bar", key)):
            return
        for tf in self.timeframes:
            bar = self.forming(key, tf, row)
            if bar is not None:
                self._send(
                    {"type": "bar", "exchange": key[0], "symbol": key[1], "tf": tf, "bar": bar},
                    key,
                    tf,
                )

    # ------------------------------------------------------------------ running candles

    def forming(self, key: Key, tf: str, latest: dict | None = None) -> dict | None:
        """Running `tf` candle = base (closed 1m within it) + latest 1m candle. Times in seconds."""
        m = latest or self.forming_1m.get(key)
        base = self.base.get((*key, tf))
        start = None
        if m is not None:
            start = bucket_start_ms(m["open_time"], tf)
        elif base is not None:
            start = base["open_time"]
        if start is None:
            return None
        if base is not None and base["open_time"] != start:
            base = None  # base belongs to the previous candle: a new candle just started
        parts = [p for p in (base, m) if p is not None and not (p is m and p["is_closed"])]
        if not parts:
            return None
        return {
            "time": start // 1000,
            "open": parts[0]["open"],
            "high": max(p["high"] for p in parts),
            "low": min(p["low"] for p in parts),
            "close": parts[-1]["close"],
            "volume": sum(p["volume"] for p in parts),
        }

    def set_tail(self, exchange: str, symbol: str, tf: str, bars: list[dict]) -> bool:
        """Updater reports a resampled tail (open_time ms, is_closed). True if a candle closed."""
        k = (exchange, symbol, tf)
        closed = [b for b in bars if b["is_closed"]]
        forming = [b for b in bars if not b["is_closed"]]
        if forming:
            self.base[k] = forming[-1]
        else:
            self.base.pop(k, None)
        if not closed:
            return False
        newest = closed[-1]["open_time"]
        before = self.last_closed.get(k)
        self.last_closed[k] = newest
        if before is not None and newest > before:
            self._send(
                {
                    "type": "close",
                    "exchange": exchange,
                    "symbol": symbol,
                    "tf": tf,
                    "time": newest // 1000,
                },
                (exchange, symbol),
            )
            return True
        return False

    # ------------------------------------------------------------------ ad-hoc coins

    def seed_adhoc(self, key: Key, closed_1m: list[dict]) -> None:
        """Start tracking an unconfigured coin: each timeframe's base = closed 1m candles (REST)
        since the start of that timeframe's current candle."""
        self.adhoc.add(key)
        rows = sorted(closed_1m, key=lambda r: r["open_time"])
        if not rows:
            return
        last = rows[-1]["open_time"]
        for tf in self.timeframes:
            start = bucket_start_ms(last, tf)
            part = [r for r in rows if r["open_time"] >= start]
            self.base.pop((*key, tf), None)
            for r in part:
                self._merge_base(key, tf, r)
            self._finish_if_complete(key, tf, rows[-1])

    def _merge_base(self, key: Key, tf: str, row: dict) -> None:
        k = (*key, tf)
        start = bucket_start_ms(row["open_time"], tf)
        b = self.base.get(k)
        if b is None or b["open_time"] != start:
            self.base[k] = {
                "open_time": start,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "is_closed": False,
            }
        else:
            b["high"] = max(b["high"], row["high"])
            b["low"] = min(b["low"], row["low"])
            b["close"] = row["close"]
            b["volume"] += row["volume"]

    def _finish_if_complete(self, key: Key, tf: str, row: dict) -> bool:
        """Last 1m candle of a higher-TF candle that just closed → the higher-TF candle closes."""
        k = (*key, tf)
        b = self.base.get(k)
        if b is None or row["open_time"] + 60_000 != b["open_time"] + timeframe_ms(tf):
            return False
        self.base.pop(k)
        self.last_closed[k] = b["open_time"]
        return True

    def _adhoc_closed(self, key: Key, row: dict) -> None:
        for tf in self.timeframes:
            self._merge_base(key, tf, row)
            if self._finish_if_complete(key, tf, row):
                self._send(
                    {
                        "type": "close",
                        "exchange": key[0],
                        "symbol": key[1],
                        "tf": tf,
                        "time": self.last_closed[(*key, tf)] // 1000,
                    },
                    key,
                )

    def broadcast_status(self) -> None:
        self._send(self.status())
