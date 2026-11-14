"""Nến 1m từ WebSocket, LiveHub và WebSocket /ws/live."""

import asyncio
import json

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from rinng.config import load_settings
from rinng.ingest.collector.messages import Record, parse_binance, parse_okx
from rinng.ingest.collector.sink import Sink
from rinng.live.hub import LiveHub
from rinng.store.paths import DataPaths
from rinng.web.app import create_app

T = 1_794_621_600_000  # 2026-11-14 02:00 UTC, đầu một nến 1h


def _kline(t: int, close: float, closed: bool) -> str:
    k = {
        "t": t,
        "s": "BTCUSDT",
        "i": "1m",
        "o": "10",
        "h": "12",
        "l": "9",
        "c": str(close),
        "v": "5",
        "q": "50",
        "n": 7,
        "V": "3",
        "x": closed,
    }
    return json.dumps({"data": {"e": "kline", "k": k}})


def test_parse_binance_kline():
    [r] = parse_binance(_kline(T, 11.0, True), {"BTCUSDT": "BTC-USDT-PERP"})
    assert (r.table, r.symbol, r.timeframe) == ("ohlcv", "BTC-USDT-PERP", "1m")
    assert r.row["open_time"] == T and r.row["is_closed"] is True
    assert r.row["taker_buy_volume"] == 3.0 and r.row["trades"] == 7


def test_parse_okx_candle():
    msg = {
        "arg": {"channel": "candle1m", "instId": "BTC-USDT-SWAP"},
        "data": [[str(T), "10", "12", "9", "11", "500", "5", "50", "0"]],
    }
    [r] = parse_okx(json.dumps(msg), {"BTC-USDT-SWAP": "BTC-USDT-PERP"}, {})
    assert r.row["volume"] == 5.0  # đồng base, không phải số hợp đồng
    assert r.row["is_closed"] is False


def test_sink_drops_forming_candles(tmp_path):
    sink = Sink(DataPaths(tmp_path), "binance")
    rows = [
        parse_binance(_kline(T, 11, False), {"BTCUSDT": "B"})[0],
        parse_binance(_kline(T, 11, True), {"BTCUSDT": "B"})[0],
    ]
    sink.add(rows)
    assert sink.flush() == 1


def _rec(t: int, o: float, h: float, low: float, c: float, closed: bool) -> Record:
    row = {
        "open_time": t,
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": 1.0,
        "quote_volume": 1.0,
        "trades": 1,
        "taker_buy_volume": 0.5,
        "is_closed": closed,
    }
    return Record("ohlcv", "BTC-USDT-PERP", row, "1m")


@pytest.fixture
def hub():
    clock = iter(range(0, 10_000))  # mỗi lần gọi tăng 1 giây: không bị throttle
    return LiveHub(["1h"], clock=lambda: float(next(clock)))


def test_forming_bar_merges_base_and_running_minute(hub):
    async def run():
        c = hub.connect()
        c.exchange, c.symbol, c.timeframes = "binance", "BTC-USDT-PERP", {"1h"}
        # Nền: các nến 1m đã đóng trong giờ 02:00 (do updater báo).
        hub.set_tail(
            "binance",
            "BTC-USDT-PERP",
            "1h",
            [
                {
                    "open_time": T,
                    "open": 100.0,
                    "high": 110.0,
                    "low": 95.0,
                    "close": 105.0,
                    "volume": 10.0,
                    "is_closed": False,
                }
            ],
        )
        hub.ingest("binance", [_rec(T + 5 * 60_000, 105, 120, 104, 118, False)])
        events = [c.queue.get_nowait() for _ in range(c.queue.qsize())]
        bar = [e for e in events if e["type"] == "bar"][-1]["bar"]
        assert bar == {
            "time": T // 1000,
            "open": 100.0,
            "high": 120.0,
            "low": 95.0,
            "close": 118.0,
            "volume": 11.0,
        }

    asyncio.run(run())


def test_close_event_and_other_symbols_filtered(hub):
    async def run():
        c = hub.connect()
        c.exchange, c.symbol, c.timeframes = "binance", "BTC-USDT-PERP", {"1h"}
        prev = {
            "open_time": T - 3_600_000,
            "is_closed": True,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        }
        assert hub.set_tail("binance", "BTC-USDT-PERP", "1h", [prev]) is False  # lần đầu
        now = {**prev, "open_time": T}
        assert hub.set_tail("binance", "BTC-USDT-PERP", "1h", [prev, now]) is True
        hub.set_tail("binance", "ETH-USDT-PERP", "1h", [prev])
        hub.set_tail("binance", "ETH-USDT-PERP", "1h", [prev, now])
        events = [c.queue.get_nowait() for _ in range(c.queue.qsize())]
        assert events == [
            {
                "type": "close",
                "exchange": "binance",
                "symbol": "BTC-USDT-PERP",
                "tf": "1h",
                "time": T // 1000,
            }
        ]
        assert hub.last_closed[("binance", "BTC-USDT-PERP", "1h")] == T

    asyncio.run(run())


def test_closed_minute_goes_to_updater_queue(hub):
    hub.ingest("okx", [_rec(T, 1, 2, 0.5, 1.5, True)])
    ex, sym, row = hub.closed_queue.get_nowait()
    assert (ex, sym, row["open_time"]) == ("okx", "BTC-USDT-PERP", T)


def test_ws_live_streams_snapshot(tmp_path):
    settings = load_settings().model_copy(update={"data_dir": tmp_path})
    hub = LiveHub(["1h"])
    hub.price[("binance", "BTC-USDT-PERP")] = {"price": 123.0, "time": T}
    client = TestClient(create_app(settings, hub))
    assert client.get("/api/meta").json()["live"] is True
    with client.websocket_connect("/ws/live") as ws:
        ws.send_json({"op": "sub", "symbol": "BTC-USDT-PERP", "exchange": "binance", "tfs": ["1h"]})
        first, second = ws.receive_json(), ws.receive_json()
        assert first["type"] == "status"
        assert second == {
            "type": "tick",
            "exchange": "binance",
            "symbol": "BTC-USDT-PERP",
            "price": 123.0,
            "time": T,
        }


def test_ws_live_refused_without_hub(tmp_path):
    settings = load_settings().model_copy(update={"data_dir": tmp_path})
    client = TestClient(create_app(settings))
    assert client.get("/api/meta").json()["live"] is False
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/live") as ws:
        ws.receive_json()
