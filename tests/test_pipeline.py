import json
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from rinng.cli import app
from rinng.pipeline.run import MODULES, analyze, read_derived
from rinng.store.paths import DataPaths
from rinng.store.schemas import FUNDING, OHLCV, rows_to_frame
from rinng.store.writer import write_curated
from tests.analysis.helpers import random_walk


def _seed(tmp_path):
    paths = DataPaths(tmp_path / "data")
    o = random_walk(800, timeframe="1h")
    write_curated(paths, OHLCV, o)
    t0 = int(o["open_time"][0].timestamp() * 1000)
    rows = [
        {"funding_time": t0 + i * 8 * 3_600_000, "rate": 0.0001, "mark_price": None}
        for i in range(100)
    ]
    write_curated(
        paths, FUNDING, rows_to_frame(FUNDING, rows, exchange="binance", symbol="BTC-USDT-PERP")
    )
    return paths


def test_analyze_runs_every_module_and_writes(tmp_path):
    paths = _seed(tmp_path)
    out = analyze(paths, "binance", "BTC-USDT-PERP", "1h")
    assert set(out) == set(MODULES)
    assert read_derived(paths, "features", "indicators", "BTC-USDT-PERP", "1h").height == 800
    smc_events = read_derived(paths, "events", "smc", "BTC-USDT-PERP", "1h")
    assert smc_events["kind"].str.starts_with("fvg").any()
    funding = read_derived(paths, "features", "derivatives", "BTC-USDT-PERP", "1h")
    assert funding["funding_rate"].drop_nulls().len() > 0


def test_cli_analyze_and_backtest(tmp_path):
    paths = _seed(tmp_path)
    cfg = tmp_path / "instruments.yaml"
    cfg.write_text(
        f"data_dir: {paths.root}\nbase_timeframe: 1m\ntimeframes: [1h]\ninstruments:\n"
        "  - {id: BTC-USDT-PERP, kind: perp, binance: BTCUSDT, okx: BTC-USDT-SWAP}\n"
    )
    runner = CliRunner()
    r = runner.invoke(app, ["analyze", "--timeframe", "1h", "--module", "smc", "--path", str(cfg)])
    assert r.exit_code == 0, r.output
    assert "smc:" in r.output
    first = random_walk(800)["open_time"][400].strftime("%Y-%m-%d")
    r = runner.invoke(app, ["backtest", "--timeframe", "1h", "--split", first, "--path", str(cfg)])
    assert r.exit_code == 0, r.output
    assert "== in" in r.output and "== out" in r.output
    configs = list((paths.root / "results").glob("*/config.json"))
    assert len(configs) == 8  # 4 strategies × 2 segments
    assert {json.loads(c.read_text())["segment"] for c in configs} == {"in", "out"}
    for c in configs:
        assert pl.read_parquet(c.parent / "equity.parquet").height > 0


def test_dashboard_renders_both_pages(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    import rinng.viz

    script = str(Path(rinng.viz.__file__).parent / "dashboard" / "app.py")
    paths = _seed(tmp_path)
    cfg = tmp_path / "instruments.yaml"
    cfg.write_text(
        f"data_dir: {paths.root}\nbase_timeframe: 1m\ntimeframes: [1h]\ninstruments:\n"
        "  - {id: BTC-USDT-PERP, kind: perp, binance: BTCUSDT}\n"
    )
    monkeypatch.setenv("RINNG_CONFIG", str(cfg))
    at = AppTest.from_file(script, default_timeout=60).run()
    assert not at.exception, at.exception
    at.sidebar.slider[0].set_value(1500).run()
    assert not at.exception, at.exception
    assert not at.warning, [w.value for w in at.warning]
    at.sidebar.radio[0].set_value("Backtest").run()
    assert not at.exception, at.exception
