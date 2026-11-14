import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest
import websockets

from rinng.config import Instrument, Settings
from rinng.ingest.collector.messages import OkxControl, Record, parse_binance, parse_okx
from rinng.ingest.collector.poller import poll_once
from rinng.ingest.collector.sink import Sink
from rinng.ingest.collector.ws import Feed, run_feed
from rinng.store import catalog
from rinng.store.paths import DataPaths

BN = {"BTCUSDT": "BTC-USDT-PERP"}
OK = {"BTC-USDT-SWAP": "BTC-USDT-PERP"}
CT = {"BTC-USDT-SWAP": 0.01}
TS = 1794582883315


@pytest.fixture
def paths(tmp_path) -> DataPaths:
    return DataPaths(tmp_path / "data")


# --- parse: samples from real messages on 2026-11-13 ---


def test_binance_agg_trade():
    raw = json.dumps(
        {
            "stream": "btcusdt@aggTrade",
            "data": {
                "e": "aggTrade",
                "E": TS + 100,
                "a": 3520326524,
                "s": "BTCUSDT",
                "p": "68718.00",
                "q": "0.180",
                "f": 1,
                "l": 5,
                "T": TS,
                "m": True,
            },
        }
    )
    assert parse_binance(raw, BN) == [
        Record(
            "trades",
            "BTC-USDT-PERP",
            {
                "trade_id": 3520326524,
                "time": TS,
                "price": 68718.0,
                "qty": 0.18,
                "is_buyer_maker": True,
            },
        )
    ]


def test_binance_mark_price():
    raw = json.dumps(
        {
            "stream": "btcusdt@markPrice@1s",
            "data": {
                "e": "markPriceUpdate",
                "E": TS,
                "s": "BTCUSDT",
                "p": "68718.8",
                "i": "68757.9",
                "r": "0.00002336",
                "T": TS + 3600_000,
            },
        }
    )
    [rec] = parse_binance(raw, BN)
    assert rec.table == "mark_price"
    assert rec.row == {
        "time": TS,
        "mark_price": 68718.8,
        "index_price": 68757.9,
        "funding_rate": 0.00002336,
    }


def test_binance_force_order_uses_filled_qty_and_avg_price():
    raw = json.dumps(
        {
            "stream": "btcusdt@forceOrder",
            "data": {
                "e": "forceOrder",
                "E": TS,
                "o": {
                    "s": "BTCUSDT",
                    "S": "SELL",
                    "q": "0.5",
                    "p": "68000",
                    "ap": "68100",
                    "z": "0.4",
                    "T": TS,
                },
            },
        }
    )
    [rec] = parse_binance(raw, BN)
    assert rec == Record(
        "liquidations", "BTC-USDT-PERP", {"time": TS, "side": "sell", "price": 68100.0, "qty": 0.4}
    )


def test_binance_unknown_symbol_ignored():
    raw = json.dumps(
        {
            "stream": "x",
            "data": {
                "e": "forceOrder",
                "E": 1,
                "o": {
                    "s": "TQQQUSDT",
                    "S": "SELL",
                    "q": "1",
                    "p": "1",
                    "ap": "1",
                    "z": "1",
                    "T": 1,
                },
            },
        }
    )
    assert parse_binance(raw, BN) == []


def test_okx_trade_converts_contracts_to_base():
    raw = json.dumps(
        {
            "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "tradeId": "3072831206",
                    "px": "68719.1",
                    "sz": "11",
                    "side": "buy",
                    "ts": str(TS),
                }
            ],
        }
    )
    [rec] = parse_okx(raw, OK, CT)
    assert rec.row == {
        "trade_id": 3072831206,
        "time": TS,
        "price": 68719.1,
        "qty": pytest.approx(0.11),
        "is_buyer_maker": False,
    }


def test_okx_liquidation_filters_instrument_and_converts():
    raw = json.dumps(
        {
            "arg": {"channel": "liquidation-orders", "instType": "SWAP"},
            "data": [
                {
                    "instId": "ETH-USDT-SWAP",
                    "details": [{"bkPx": "1947", "side": "sell", "sz": "2", "ts": "1"}],
                },
                {
                    "instId": "BTC-USDT-SWAP",
                    "details": [{"bkPx": "68000", "side": "buy", "sz": "300", "ts": str(TS)}],
                },
            ],
        }
    )
    assert parse_okx(raw, OK, CT) == [
        Record(
            "liquidations",
            "BTC-USDT-PERP",
            {"time": TS, "side": "buy", "price": 68000.0, "qty": 3.0},
        )
    ]


def test_okx_control_and_pong():
    assert parse_okx("pong", OK, CT) is None
    notice = parse_okx(json.dumps({"event": "notice", "code": "64008", "msg": "upgrade"}), OK, CT)
    assert notice == OkxControl("notice", "64008", "upgrade")


# --- sink ---


def _mark(t: int) -> Record:
    return Record(
        "mark_price",
        "BTC-USDT-PERP",
        {"time": t, "mark_price": 1.0, "index_price": None, "funding_rate": None},
    )


def test_sink_flushes_by_size_and_splits_by_day(paths):
    sink = Sink(paths, "binance", max_rows=3)
    midnight = int(datetime(2026, 11, 13, tzinfo=UTC).timestamp() * 1000)
    sink.add([_mark(midnight - 1000), _mark(midnight + 1000)])
    assert sink.written_rows == 0
    sink.add([_mark(midnight + 2000)])
    assert sink.written_rows == 3
    days = {p.parent.name for p in paths.raw.rglob("*.parquet")}
    assert days == {"date=2026-11-12", "date=2026-11-13"}
    total = sum(pl.read_parquet(p).height for p in paths.raw.rglob("*.parquet"))
    assert total == 3


def test_sink_flushes_by_age(paths):
    now = [0.0]
    sink = Sink(paths, "okx", max_rows=1000, max_age=60, clock=lambda: now[0])
    sink.add([_mark(TS)])
    assert sink.written_rows == 0
    now[0] = 61
    sink.add([_mark(TS + 1)])
    assert sink.written_rows == 2


# --- poller ---


class FakeApi:
    name = "binance"

    def __init__(self, fail: str | None = None):
        self.fail = fail

    def _rows(self, method, row):
        if method == self.fail:
            from rinng.exchanges.ratelimit import ExchangeError

            raise ExchangeError("boom")
        return iter([[row]])

    def open_interest(self, s, p, a, b):
        return self._rows("open_interest", {"time": TS, "oi_base": 1.0, "oi_value": 2.0})

    def long_short(self, s, p, a, b):
        return self._rows(
            "long_short", {"time": TS, "ratio": 2.0, "long_pct": 0.6, "short_pct": 0.3}
        )

    def taker_volume(self, s, p, a, b):
        return self._rows("taker_volume", {"time": TS, "buy_volume": 1.0, "sell_volume": 1.0})

    def funding(self, s, a, b):
        return self._rows("funding", {"funding_time": TS, "rate": 0.0001, "mark_price": None})


SETTINGS = Settings(
    data_dir="data",
    base_timeframe="1m",
    timeframes=["1h"],
    instruments=[
        Instrument(id="BTC-USDT-PERP", kind="perp", binance="BTCUSDT", okx="BTC-USDT-SWAP")
    ],
)


def test_poller_writes_every_dataset(paths):
    sink = Sink(paths, "binance")
    n = poll_once(FakeApi(), SETTINGS, sink, datetime.now(UTC), timedelta(hours=1))
    assert n == 4
    tables = sorted({p.relative_to(paths.raw).parts[1] for p in paths.raw.rglob("*.parquet")})
    assert tables == ["funding", "long_short", "open_interest", "taker_volume"]


def test_poller_survives_one_failing_endpoint(paths):
    n = poll_once(
        FakeApi(fail="long_short"),
        SETTINGS,
        Sink(paths, "binance"),
        datetime.now(UTC),
        timedelta(hours=1),
    )
    assert n == 3


# --- run_feed against a fake WebSocket server ---


def test_feed_reconnects_records_gap_and_flushes_on_stop(paths):
    connections = []

    async def scenario():
        async def handler(ws):
            connections.append(ws)
            for i in range(3):
                await ws.send(
                    json.dumps(
                        {
                            "stream": "s",
                            "data": {
                                "e": "markPriceUpdate",
                                "E": TS + len(connections) * 1000 + i,
                                "s": "BTCUSDT",
                                "p": "1",
                                "i": "1",
                                "r": "0",
                            },
                        }
                    )
                )
            if len(connections) == 1:
                await ws.close()  # first time: drop mid-stream
            else:
                await asyncio.sleep(10)

        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            feed = Feed(
                "binance",
                f"ws://127.0.0.1:{port}",
                BN,
                parse=lambda raw: parse_binance(raw, BN),
                datasets=("mark_price",),
            )
            sink = Sink(paths, "binance", max_rows=10_000, max_age=3600)
            stop = asyncio.Event()

            async def stopper():
                while len(connections) < 2 or feed.stats["messages"] < 6:
                    await asyncio.sleep(0.05)
                stop.set()

            await asyncio.wait_for(asyncio.gather(run_feed(feed, sink, paths, stop), stopper()), 15)
            return feed, sink

    feed, sink = asyncio.run(scenario())
    assert feed.stats["reconnects"] == 1
    assert sink.written_rows == 6  # rows still in memory are flushed on stop
    gaps = catalog.read_meta(paths, "gaps")
    assert gaps.height == 1
    assert gaps["dataset"][0] == "mark_price"
    assert gaps["end"][0] > gaps["start"][0]


def test_raw_partition_date_type(paths):
    assert paths.raw_partition("okx", "trades", "X", date(2026, 1, 2)).name == "date=2026-01-02"
