"""`rinng search/summary/signal/lens/status`: output, --json view, exit codes."""

import json

import pytest
from typer.testing import CliRunner

from rinng.cli import app
from rinng.store.paths import DataPaths
from rinng.store.schemas import OHLCV
from rinng.store.writer import write_curated
from rinng.views import DISCLAIMER
from tests.analysis.helpers import recent_ohlcv

runner = CliRunner()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Config with stored OKX candles for BTC (no network needed with --exchange okx)."""
    monkeypatch.delenv("RINNG_DATA", raising=False)
    paths = DataPaths(tmp_path / "data")
    for tf, n in (("1h", 24 * 31), ("4h", 6 * 181), ("1d", 1001)):
        write_curated(paths, OHLCV, recent_ohlcv(tf, n, exchange="okx"))
    file = tmp_path / "instruments.yaml"
    file.write_text(
        f"data_dir: {paths.root}\nbase_timeframe: 1m\ntimeframes: [1h]\ninstruments:\n"
        "  - {id: BTC-USDT-PERP, kind: perp, binance: BTCUSDT, okx: BTC-USDT-SWAP}\n"
    )
    return str(file)


def test_summary_text_and_json(cfg):
    r = runner.invoke(app, ["summary", "btc", "-e", "okx", "--offline", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert r.output.startswith("BTC-USDT-PERP on okx")
    assert DISCLAIMER in r.output
    r = runner.invoke(
        app, ["summary", "BTCUSDT", "-e", "okx", "--offline", "--json", "--config", cfg]
    )
    view = json.loads(r.output)
    assert (view["kind"], view["symbol"], view["schema_version"]) == ("summary", "BTC-USDT-PERP", 1)
    assert "spark" not in view["price"]
    assert view["price"]["time"].endswith("Z")
    assert "warning" not in view  # fresh synthetic data


def test_lens_json_with_candles(cfg):
    args = ["lens", "btc", "-l", "indicators", "--tf", "4h", "-e", "okx", "--candles", "5"]
    r = runner.invoke(app, [*args, "--offline", "--json", "--config", cfg])
    assert r.exit_code == 0, r.output
    view = json.loads(r.output)
    assert view["lens"] == "indicators" and view["source"] == "curated"
    assert {s["name"] for s in view["series_last"]} >= {"EMA 21", "RSI"}
    assert len(view["candles"]["close"]) == 5


@pytest.mark.parametrize(
    ("args", "code"),
    [
        (["summary", "btc", "-e", "kraken", "--offline"], 2),  # bad exchange
        (["summary", "NOPE", "--offline"], 3),  # not in config, offline cannot look it up
        (["lens", "btc", "--tf", "2h", "--offline"], 2),  # bad timeframe
        (["lens", "btc", "-l", "nope", "--offline"], 3),  # unknown lens → NotFound
        (["summary", "btc", "--offline"], 3),  # binance: nothing stored, offline
    ],
)
def test_exit_codes(cfg, args, code):
    r = runner.invoke(app, [*args, "--config", cfg])
    assert r.exit_code == code, r.output
    assert "error:" in r.output


def test_status_and_offline_search(cfg):
    r = runner.invoke(app, ["status", "--json", "--config", cfg])
    btc = json.loads(r.output)["instruments"][0]
    assert btc["binance"]["last_1m"] is None
    r = runner.invoke(app, ["search", "btc", "--offline", "--config", cfg])
    assert r.exit_code == 0 and "BTC-USDT-PERP" in r.output and "(in config)" in r.output
