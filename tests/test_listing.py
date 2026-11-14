"""Any-coin lookup: exchange catalog, id resolution, LiveHub resampling for unconfigured coins."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from rinng.config import load_settings
from rinng.exchanges.listing import Catalog, icon_symbol
from rinng.ingest.collector.messages import Record
from rinng.live.hub import LiveHub
from rinng.web.app import create_app

FAKE = {
    "binance": lambda: {"BTC": "BTCUSDT", "XRP": "XRPUSDT", "1000PEPE": "1000PEPEUSDT"},
    "okx": lambda: {"BTC": "BTC-USDT-SWAP", "XRP": "XRP-USDT-SWAP", "PEPE": "PEPE-USDT-SWAP"},
}


@pytest.fixture
def catalog():
    return Catalog(load_settings(), fetchers=FAKE)


def test_resolve_prefers_config_then_listing(catalog):
    assert catalog.resolve("BTC-USDT-PERP").name == "Bitcoin"  # from config
    xrp = catalog.resolve("XRP-USDT-PERP")
    assert (xrp.binance, xrp.okx) == ("XRPUSDT", "XRP-USDT-SWAP")
    assert catalog.resolve("1000PEPE-USDT-PERP").okx is None
    with pytest.raises(KeyError):
        catalog.resolve("NOPE-USDT-PERP")


def test_search_ranks_exact_then_prefix(catalog):
    ids = [i.id for i in catalog.search("pepe")]
    assert set(ids) == {"PEPE-USDT-PERP", "1000PEPE-USDT-PERP"}
    assert catalog.search("xrp/usdt")[0].id == "XRP-USDT-PERP"
    assert [i.id for i in catalog.search("")][:2] == ["BTC-USDT-PERP", "SOL-USDT-PERP"]


def test_icon_symbol_strips_multiplier():
    assert icon_symbol("1000PEPE") == "PEPE"
    assert icon_symbol("1MBABYDOGE") == "BABYDOGE"
    assert icon_symbol("BTC") == "BTC"


def test_instruments_api(catalog, tmp_path):
    settings = load_settings().model_copy(update={"data_dir": tmp_path})
    client = TestClient(create_app(settings, catalog=catalog))
    meta = client.get("/api/meta").json()
    assert [i["base"] for i in meta["instruments"]] == ["BTC", "SOL", "ETH", "BNB", "LINK"]
    hits = client.get("/api/instruments", params={"q": "pepe"}).json()
    assert {h["icon"] for h in hits} == {"PEPE"}
    assert client.get("/api/instrument", params={"symbol": "NOPE-USDT-PERP"}).status_code == 404


T = 1_794_621_600_000  # 02:00 UTC, start of a 1h candle


def _bar(t: int, close: float, closed: bool = True) -> dict:
    return {
        "open_time": t,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1.0,
        "quote_volume": 1.0,
        "trades": 1,
        "taker_buy_volume": 0.5,
        "is_closed": closed,
    }


def test_adhoc_hub_aggregates_and_closes_bars():
    async def run():
        clock = iter(range(10_000))
        hub = LiveHub(["15m"], clock=lambda: float(next(clock)))
        key = ("binance", "XRP-USDT-PERP")
        # 13 closed 1m candles of the 02:00 15m candle (REST), then the feed sends minutes 13 and
        # 14.
        hub.seed_adhoc(key, [_bar(T + i * 60_000, 10 + i) for i in range(13)])
        c = hub.connect()
        c.exchange, c.symbol, c.timeframes = key[0], key[1], {"15m"}
        bar = hub.forming(key, "15m", _bar(T + 13 * 60_000, 50, closed=False))
        assert (bar["open"], bar["high"], bar["volume"]) == (10, 51, 14.0)
        for i in (13, 14):
            hub.ingest("binance", [Record("ohlcv", key[1], _bar(T + i * 60_000, 30), "1m")])
        events = [c.queue.get_nowait() for _ in range(c.queue.qsize())]
        closes = [e for e in events if e["type"] == "close"]
        assert closes == [
            {
                "type": "close",
                "exchange": "binance",
                "symbol": "XRP-USDT-PERP",
                "tf": "15m",
                "time": T // 1000,
            }
        ]
        assert hub.last_closed[(*key, "15m")] == T
        assert hub.closed_queue.empty()  # coins outside the config do not go through the updater

    asyncio.run(run())
