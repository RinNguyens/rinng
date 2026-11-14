"""LiveHub: trạng thái realtime trong bộ nhớ và phát sự kiện cho các client WebSocket.

Nhận bản ghi từ collector (cùng event loop), giữ:
- giá khớp cuối, mark price/funding, nến 1m đang chạy của từng (sàn, symbol);
- "nền" của nến đang chạy ở mỗi khung = gộp các nến 1m đã đóng trong nến đó (do updater cập
  nhật sau mỗi lần ghi curated), để ghép với nến 1m đang chạy thành nến khung lớn đang chạy;
- mốc mở của nến đã đóng gần nhất mỗi khung (dùng làm khóa cache cho lens).

Sự kiện gửi đi là dict JSON-được; mỗi client có một hàng đợi riêng, đầy thì bỏ bớt sự kiện cũ
thay vì làm chậm collector.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from rinng.ingest.collector.messages import Record
from rinng.timeframes import bucket_start_ms, timeframe_ms

Key = tuple[str, str]  # (exchange, symbol)
THROTTLE = 0.25  # giây giữa hai lần gửi tick/nến của cùng một khóa


@dataclass(eq=False)  # so sánh theo danh tính để bỏ vào set
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
        self.base: dict[tuple[str, str, str], dict] = {}  # (ex, sym, tf) → nền nến đang chạy
        self.last_closed: dict[tuple[str, str, str], int] = {}  # → open_time (ms) nến đã đóng
        self.last_message: dict[str, float] = {}  # exchange → time.time() lần nhận cuối
        self.clients: set[Client] = set()
        self.closed_queue: asyncio.Queue[tuple[str, str, dict]] = asyncio.Queue()
        self._sent: dict[tuple, float] = {}
        # Coin trong cấu hình: nến đóng đi qua updater (ghi curated). Coin mở thêm khi tìm kiếm
        # (adhoc): hub tự gộp nến 1m thành nến khung lớn và tự báo nến đóng.
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
        """Sự kiện gửi ngay khi client đăng ký để màn hình có số liệu không cần chờ tick."""
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

    # ------------------------------------------------------------------ dữ liệu vào

    def ingest(self, exchange: str, records: list[Record]) -> None:
        """Callback của collector cho mọi bản ghi WebSocket."""
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
        # Giá cũng lấy từ nến nếu sàn đó không gửi trade (an toàn khi feed trade bị trễ).
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

    # ------------------------------------------------------------------ nến đang chạy

    def forming(self, key: Key, tf: str, latest: dict | None = None) -> dict | None:
        """Nến `tf` đang chạy = nền (1m đã đóng trong nến) + nến 1m mới nhất. Thời gian: giây."""
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
            base = None  # nền thuộc nến trước: nến mới vừa bắt đầu
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
        """Updater báo đuôi vừa resample (open_time ms, is_closed). Trả True nếu có nến mới đóng."""
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

    # ------------------------------------------------------------------ coin mở thêm

    def seed_adhoc(self, key: Key, closed_1m: list[dict]) -> None:
        """Bắt đầu theo dõi một coin ngoài cấu hình: nền mỗi khung = nến 1m đã đóng (REST) từ
        đầu nến hiện tại của khung đó."""
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
        """Nến 1m cuối cùng của một nến khung lớn vừa đóng → nến khung lớn đóng."""
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
