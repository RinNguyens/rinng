"""Số liệu dashboard (rinng.web.summary) trên nến giả."""

from datetime import timedelta

import polars as pl
import pytest

from rinng.web import summary
from tests.analysis.helpers import T0, make_ohlcv, random_walk


def test_price_block_changes_and_delta():
    # 6 ngày giá 100, 1 ngày 105, 1 ngày 110: mốc 24h trước là nến 105, mốc 7 ngày trước là 100.
    closes = [100.0] * 24 * 6 + [105.0] * 24 + [110.0] * 24
    o = make_ohlcv(closes, volumes=[10.0] * len(closes), taker_buy=[6.0] * len(closes))
    p = summary.price_block(o)
    assert p["close"] == 110.0
    assert p["chg_24h"] == pytest.approx((110 / 105 - 1) * 100)
    assert p["chg_7d"] == pytest.approx(10.0)
    # Mỗi nến: mua 6, bán 4 → delta 2; 24 nến trong 24h.
    assert p["delta_24h"] == pytest.approx(48.0)
    assert len(p["spark"]) == 24 * 7


def test_derivatives_block_reads_latest_and_changes():
    funding = pl.DataFrame(
        {"funding_time": [T0, T0 + timedelta(hours=8)], "rate": [0.0001, 0.0002]}
    )
    times = [T0 + timedelta(hours=i) for i in range(24 * 8)]
    oi = pl.DataFrame(
        {
            "time": times,
            "oi_base": [100.0] * (len(times) - 1) + [110.0],
            "oi_value": [1.0] * len(times),
        }
    )
    ls = pl.DataFrame({"time": [T0], "ratio": [2.0], "long_pct": [0.667]})
    d = summary.derivatives_block(funding, oi, ls)
    assert d["funding"]["rate_pct"] == pytest.approx(0.02)
    assert d["funding"]["annual_pct"] == pytest.approx(0.0002 * 3 * 365 * 100)
    assert d["oi"]["chg_24h"] == pytest.approx(10.0)
    assert d["ls"]["long_pct"] == pytest.approx(66.7)


def test_derivatives_block_handles_missing_data():
    empty = pl.DataFrame()
    assert summary.derivatives_block(empty, empty, empty) == {
        "funding": None,
        "oi": None,
        "ls": None,
    }


def test_context_blocks_run_on_random_walk():
    h1 = random_walk(24 * 30, timeframe="1h")
    h4 = random_walk(600, timeframe="4h")
    d1 = random_walk(400, timeframe="1d")
    st = summary.structure_block(h4)
    assert st["trend"] in {"up", "down", None}
    pr = summary.profile_block(h1)
    assert pr["current"]["shape"] in {"D", "P", "b", "DD"}
    assert pr["current"]["val"] <= pr["current"]["poc"] <= pr["current"]["vah"]
    lq = summary.liquidity_block(h1)
    close = float(h1["close"][-1])
    assert lq["bsl"] is None or lq["bsl"] > close
    assert lq["ssl"] is None or lq["ssl"] < close
    summary.wyckoff_block(d1)
    m = summary.momentum_block(h4)
    assert m["rsi"] is None or 0 <= m["rsi"] <= 100
