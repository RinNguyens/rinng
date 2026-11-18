"""Rinng.market and GET /api/market: one row per listed USDT perp, tier B only for stored coins."""

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from rinng.config import load_settings
from rinng.exchanges.listing import Catalog
from rinng.service import BadRequest, Offline, Rinng
from rinng.store.paths import DataPaths
from rinng.store.schemas import LONG_SHORT, OPEN_INTEREST, rows_to_frame
from rinng.store.writer import write_curated
from rinng.web.app import create_app

CATALOG = {
    "binance": lambda: {"BTC": "BTCUSDT", "XRP": "XRPUSDT"},
    "okx": lambda: {"BTC": "BTC-USDT-SWAP", "XRP": "XRP-USDT-SWAP"},
}
BTC, XRP = "BTC-USDT-PERP", "XRP-USDT-PERP"
NEXT_FUNDING = 1_763_391_600  # seconds


class Calls:
    """REST calls made by fake exchange clients, across instances."""

    names: list[str] = []


class FakeBinance:
    fail: Exception | None = None

    def _hit(self, name: str) -> None:
        Calls.names.append(name)
        if FakeBinance.fail is not None:
            raise FakeBinance.fail

    def tickers_24h(self):
        self._hit("binance.tickers_24h")
        return [
            {"symbol": "BTCUSDT", "price": 91000.0, "chg_24h": 1.24, "volume_24h": 1.2e10},
            {"symbol": "XRPUSDT", "price": 0.5, "chg_24h": -3.0, "volume_24h": 4.0e8},
            # delivery contract, stable-coin pair and an unlisted coin: not rows
            {"symbol": "BTCUSDT_250328", "price": 92000.0, "chg_24h": 1.0, "volume_24h": 1.0e6},
            {"symbol": "BTCUSDC", "price": 91001.0, "chg_24h": 1.2, "volume_24h": 1.0e9},
            {"symbol": "NEWUSDT", "price": 1.0, "chg_24h": 0.0, "volume_24h": 10.0},
        ]

    def premium_index(self):
        self._hit("binance.premium_index")
        return [
            {"symbol": "BTCUSDT", "funding_rate": 0.0001, "next_funding": NEXT_FUNDING},
            {"symbol": "XRPUSDT", "funding_rate": -0.00005, "next_funding": NEXT_FUNDING + 3600},
        ]


class FakeOkx:
    fail: Exception | None = None

    def _hit(self, name: str) -> None:
        Calls.names.append(name)
        if FakeOkx.fail is not None:
            raise FakeOkx.fail

    def swap_tickers(self):
        self._hit("okx.swap_tickers")
        return [
            {
                "inst_id": "BTC-USDT-SWAP",
                "price": 110.0,
                "open_24h": 100.0,
                "volume_24h_base": 1000.0,
            },
            {
                "inst_id": "XRP-USDT-SWAP",
                "price": 0.5,
                "open_24h": 0.5,
                "volume_24h_base": 2.0e6,
            },
            {
                "inst_id": "BTC-USD-SWAP",  # coin-margined: not a USDT perp
                "price": 110.0,
                "open_24h": 100.0,
                "volume_24h_base": 5.0,
            },
        ]

    def funding_rates(self):
        self._hit("okx.funding_rates")
        return [
            {"inst_id": "BTC-USDT-SWAP", "funding_rate": 0.0002, "next_funding": NEXT_FUNDING},
            {"inst_id": "XRP-USDT-SWAP", "funding_rate": 0.0, "next_funding": NEXT_FUNDING},
        ]


@pytest.fixture(autouse=True)
def fake_clients(monkeypatch):
    Calls.names = []
    FakeBinance.fail = None
    FakeOkx.fail = None
    monkeypatch.setattr("rinng.exchanges.binance.Binance", FakeBinance)
    monkeypatch.setattr("rinng.exchanges.okx.Okx", FakeOkx)


@pytest.fixture
def settings(tmp_path):
    return load_settings().model_copy(update={"data_dir": tmp_path})


@pytest.fixture
def svc(settings):
    return Rinng(settings, catalog=Catalog(settings, fetchers=CATALOG))


def by_symbol(snapshot: dict) -> dict[str, dict]:
    return {r["symbol"]: r for r in snapshot["rows"]}


def store_derivatives(settings, exchange: str = "binance") -> None:
    """Hourly OI (100 -> 102 base over the last 24 h, 8.1e9 USDT now) and L/S 1.08 for BTC."""
    paths = DataPaths(settings.data_dir)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    oi, ls = [], []
    for h in range(27):
        t = int((end - timedelta(hours=26 - h)).timestamp() * 1000)
        last = h == 26
        oi.append({"time": t, "oi_base": 102.0 if last else 100.0, "oi_value": 8.1e9})
        ls.append({"time": t, "ratio": 1.08, "long_pct": 0.52, "short_pct": 0.48})
    write_curated(
        paths,
        OPEN_INTEREST,
        rows_to_frame(OPEN_INTEREST, oi, exchange=exchange, symbol=BTC, source="api"),
    )
    write_curated(
        paths,
        LONG_SHORT,
        rows_to_frame(
            LONG_SHORT, ls, exchange=exchange, symbol=BTC, source="api", kind="global_account"
        ),
    )


# --------------------------------------------------------------------------- tier A


def test_rows_have_tier_a_for_every_perp(svc):
    snap = svc.market("binance")
    assert snap["exchange"] == "binance"
    assert abs(snap["time"] - time.time()) < 60
    rows = by_symbol(snap)
    # only USDT perps in the catalog: no delivery contract, no USDC pair, no unlisted coin
    assert set(rows) == {BTC, XRP}
    btc, xrp = rows[BTC], rows[XRP]
    assert (btc["base"], btc["name"]) == ("BTC", "Bitcoin")  # configured coin keeps its name
    assert (xrp["base"], xrp["name"]) == ("XRP", "XRP")  # others: name is the base
    assert btc["price"] == 91000.0
    assert btc["chg_24h"] == pytest.approx(1.24)
    assert btc["volume_24h"] == pytest.approx(1.2e10)
    assert btc["funding_rate_pct"] == pytest.approx(0.01)  # 0.0001 * 100
    assert btc["next_funding"] == NEXT_FUNDING
    assert xrp["funding_rate_pct"] == pytest.approx(-0.005)
    assert xrp["chg_24h"] == pytest.approx(-3.0)


def test_okx_rows_derive_change_and_quote_volume(svc):
    rows = by_symbol(svc.market("okx"))
    assert set(rows) == {BTC, XRP}  # BTC-USD-SWAP ignored
    btc, xrp = rows[BTC], rows[XRP]
    assert btc["price"] == 110.0
    assert btc["chg_24h"] == pytest.approx(10.0)  # (last / open - 1) * 100
    assert btc["volume_24h"] == pytest.approx(110_000.0)  # volCcy24h (base) * last
    assert btc["funding_rate_pct"] == pytest.approx(0.02)
    assert btc["next_funding"] == NEXT_FUNDING
    assert xrp["chg_24h"] == pytest.approx(0.0)
    assert xrp["volume_24h"] == pytest.approx(1.0e6)


def test_binance_uses_two_rest_calls_for_tier_a(svc):
    svc.market("binance")
    assert sorted(Calls.names) == ["binance.premium_index", "binance.tickers_24h"]


# --------------------------------------------------------------------------- tier B


def test_uncollected_rows_have_null_tier_b(svc):
    row = by_symbol(svc.market("binance"))[XRP]
    assert row["collected"] is False
    assert row["oi_value"] is None
    assert row["oi_chg_24h"] is None
    assert row["ls_ratio"] is None


def test_configured_coin_without_stored_data_is_not_collected(svc):
    row = by_symbol(svc.market("binance"))[BTC]
    assert row["collected"] is False
    assert (row["oi_value"], row["oi_chg_24h"], row["ls_ratio"]) == (None, None, None)


def test_collected_row_has_oi_and_ls_from_stored_data(settings, svc):
    store_derivatives(settings)
    rows = by_symbol(svc.market("binance"))
    btc = rows[BTC]
    assert btc["collected"] is True
    assert btc["oi_value"] == pytest.approx(8.1e9)
    assert btc["oi_chg_24h"] == pytest.approx(2.0)  # 100 -> 102 base
    assert btc["ls_ratio"] == pytest.approx(1.08)
    assert btc["price"] == 91000.0  # tier A still from REST
    assert rows[XRP]["collected"] is False  # stored data of one coin does not leak to others


def test_stored_data_is_per_exchange(settings, svc):
    store_derivatives(settings, exchange="binance")
    assert by_symbol(svc.market("okx"))[BTC]["collected"] is False


# --------------------------------------------------------------------------- cache, errors


def test_second_call_within_30s_makes_no_rest_call(svc):
    first = svc.market("binance")
    n = len(Calls.names)
    assert n > 0
    assert svc.market("binance") == first
    assert len(Calls.names) == n


def test_cache_is_per_exchange(svc):
    svc.market("binance")
    svc.market("okx")
    assert {"binance.tickers_24h", "okx.swap_tickers"} <= set(Calls.names)


def test_snapshot_refreshes_after_30s(svc, monkeypatch):
    svc.market("binance")
    n = len(Calls.names)
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 31)
    svc.market("binance")
    assert len(Calls.names) > n


def test_offline_service_raises_offline(settings):
    svc = Rinng(settings, catalog=Catalog(settings, fetchers=CATALOG), offline=True)
    with pytest.raises(Offline):
        svc.market("binance")
    assert Calls.names == []


def test_unknown_exchange_is_a_bad_request(svc):
    with pytest.raises(BadRequest):
        svc.market("kraken")
    assert Calls.names == []


# --------------------------------------------------------------------------- web


def test_web_market_returns_the_snapshot(settings):
    client = TestClient(create_app(settings, catalog=Catalog(settings, fetchers=CATALOG)))
    r = client.get("/api/market", params={"exchange": "binance"})
    assert r.status_code == 200
    body = r.json()
    assert body["exchange"] == "binance"
    assert {row["symbol"] for row in body["rows"]} == {BTC, XRP}
    assert client.get("/api/market", params={"exchange": "okx"}).json()["exchange"] == "okx"


def test_web_bad_exchange_is_400(settings):
    client = TestClient(create_app(settings, catalog=Catalog(settings, fetchers=CATALOG)))
    assert client.get("/api/market", params={"exchange": "bad"}).status_code == 400


def test_web_exchange_error_is_502(settings, caplog):
    FakeBinance.fail = httpx.ConnectError("boom")
    client = TestClient(
        create_app(settings, catalog=Catalog(settings, fetchers=CATALOG)),
        raise_server_exceptions=False,
    )
    with caplog.at_level("WARNING"):
        res = client.get("/api/market", params={"exchange": "binance"})
    assert res.status_code == 502
    assert res.json()["detail"] == "exchange error: ConnectError"
    assert any(r.exc_info for r in caplog.records)


def test_web_exchange_http_status_is_in_the_detail(settings):
    req = httpx.Request("GET", "https://x.test")
    FakeBinance.fail = httpx.HTTPStatusError(
        "bad", request=req, response=httpx.Response(429, request=req)
    )
    client = TestClient(
        create_app(settings, catalog=Catalog(settings, fetchers=CATALOG)),
        raise_server_exceptions=False,
    )
    res = client.get("/api/market", params={"exchange": "binance"})
    assert res.status_code == 502
    assert res.json()["detail"] == "exchange error: HTTPStatusError 429"
