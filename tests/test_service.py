"""rinng.service.Rinng: coin lookup, curated-vs-REST choice, argument checks, HTTP error mapping."""

import polars as pl
import pytest
from fastapi.testclient import TestClient

from rinng.config import load_settings
from rinng.exchanges.listing import Catalog
from rinng.service import BadRequest, NotFound, Rinng, symbol_candidates
from rinng.store.paths import DataPaths
from rinng.store.schemas import OHLCV
from rinng.store.writer import write_curated
from rinng.web.app import create_app
from tests.analysis.helpers import recent_ohlcv


def _no_network():
    raise AssertionError("catalog fetched from the network")


OFFLINE = {"binance": _no_network, "okx": _no_network}
FAKE = {
    "binance": lambda: {"BTC": "BTCUSDT", "XRP": "XRPUSDT"},
    "okx": lambda: {"BTC": "BTC-USDT-SWAP", "XRP": "XRP-USDT-SWAP"},
}


@pytest.fixture
def settings(tmp_path):
    return load_settings().model_copy(update={"data_dir": tmp_path})


@pytest.fixture
def svc(settings):
    return Rinng(settings, catalog=Catalog(settings, fetchers=OFFLINE))


class Refuse:
    """Stands in for an exchange client: any REST call fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"unexpected REST call {name}")


@pytest.fixture
def no_rest(monkeypatch):
    monkeypatch.setattr("rinng.exchanges.binance.Binance", Refuse)
    monkeypatch.setattr("rinng.exchanges.okx.Okx", Refuse)


# --------------------------------------------------------------------------- coin lookup


@pytest.mark.parametrize(
    "text", ["BTC-USDT-PERP", "btc", "BTC", "BTCUSDT", "btc/usdt", "BTC-USDT-SWAP", " btc "]
)
def test_loose_spellings_resolve_to_the_configured_coin_offline(svc, text):
    assert svc.instrument(text).id == "BTC-USDT-PERP"


def test_symbol_candidates_end_with_the_perp_id():
    assert symbol_candidates("sol/usdt")[-1] == "SOL-USDT-PERP"
    assert symbol_candidates("1000PEPEUSDT")[-1] == "1000PEPE-USDT-PERP"


def test_unconfigured_coin_comes_from_the_catalog(settings):
    svc = Rinng(settings, catalog=Catalog(settings, fetchers=FAKE))
    xrp = svc.instrument("xrp")
    assert (xrp.id, xrp.binance, xrp.okx) == ("XRP-USDT-PERP", "XRPUSDT", "XRP-USDT-SWAP")


def test_unknown_coin_suggests_matches(settings):
    svc = Rinng(settings, catalog=Catalog(settings, fetchers=FAKE))
    with pytest.raises(NotFound, match="unknown instrument NOPE"):
        svc.instrument("NOPE")
    with pytest.raises(NotFound, match="did you mean XRP-USDT-PERP"):
        svc.instrument("XR")


# --------------------------------------------------------------------------- data source


def test_candles_use_curated_when_the_window_is_stored(svc, no_rest):
    write_curated(DataPaths(svc.settings.data_dir), OHLCV, recent_ohlcv("1h", 24 * 6))
    o, source = svc.candles("binance", "BTC-USDT-PERP", "1h", 5)
    assert source == "curated"
    assert o.height >= 0.9 * 24 * 5


def test_candles_fall_back_to_rest_when_nothing_is_stored(svc, monkeypatch):
    seen = {}
    bars = recent_ohlcv("1h", 48)

    class FakeBinance:
        def klines(self, symbol, tf, start, end):
            seen["call"] = (symbol, tf)
            rows = bars.with_columns(
                (pl.col("open_time").dt.epoch("ms")).alias("open_time")
            ).to_dicts()
            yield rows

    monkeypatch.setattr("rinng.exchanges.binance.Binance", FakeBinance)
    o, source = svc.candles("binance", "BTC-USDT-PERP", "1h", 2)
    assert source == "live"
    assert seen["call"] == ("BTCUSDT", "1h")
    assert o.height == 48
    assert o["symbol"].unique().to_list() == ["BTC-USDT-PERP"]


def test_summary_on_stored_data_with_a_loose_symbol(svc, no_rest):
    paths = DataPaths(svc.settings.data_dir)
    for tf, n in (("1h", 24 * 31), ("4h", 6 * 181), ("1d", 1001)):
        write_curated(paths, OHLCV, recent_ohlcv(tf, n, exchange="okx"))
    out = svc.summary("btc", "okx")
    assert (out["symbol"], out["exchange"]) == ("BTC-USDT-PERP", "okx")
    assert {"price", "derivatives", "structure", "profile", "liquidity", "wyckoff", "momentum"} <= (
        out.keys()
    )
    assert svc.summary("BTC-USDT-PERP", "okx") is out  # cached under the canonical id


def test_status_reports_the_newest_stored_minute(svc):
    m1 = recent_ohlcv("1m", 30)
    write_curated(DataPaths(svc.settings.data_dir), OHLCV, m1)
    btc = next(i for i in svc.status()["instruments"] if i["id"] == "BTC-USDT-PERP")
    assert btc["binance"]["last_1m"] == m1["open_time"][-1].isoformat()
    assert btc["binance"]["age_minutes"] <= 2
    assert btc["okx"] == {"last_1m": None, "age_minutes": None}


# --------------------------------------------------------------------------- argument checks


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"lens": "nope"}, NotFound),
        ({"tf": "2h"}, BadRequest),
        ({"exchange": "kraken"}, BadRequest),
        ({"days": 1}, BadRequest),
        ({"symbol": "NOPE"}, NotFound),
    ],
)
def test_chart_rejects_bad_arguments(svc, kwargs, error):
    with pytest.raises(error):
        svc.chart(**kwargs)


def test_desk_and_summary_reject_unknown_exchange(svc):
    with pytest.raises(BadRequest):
        svc.summary("BTC", "kraken")
    with pytest.raises(BadRequest):
        svc.desk("BTC", "kraken")


# --------------------------------------------------------------------------- web mapping


def test_web_maps_service_errors_to_http(settings):
    client = TestClient(create_app(settings, catalog=Catalog(settings, fetchers=FAKE)))
    r = client.get("/api/chart", params={"lens": "nope"})
    assert r.status_code == 404 and "unknown lens" in r.json()["detail"]
    assert client.get("/api/chart", params={"tf": "2h"}).status_code == 400
    assert client.get("/api/summary", params={"symbol": "NOPE"}).status_code == 404
    assert client.get("/api/desk", params={"exchange": "kraken"}).status_code == 400
    assert client.get("/api/instrument", params={"symbol": "btc"}).json()["id"] == "BTC-USDT-PERP"
    status = client.get("/api/status").json()
    assert status["live"] is False and status["stored"] is False
