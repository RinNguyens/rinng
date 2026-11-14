"""Tests for the strategy interface and baselines."""

from datetime import timedelta

import numpy as np
import polars as pl
import pytest

from rinng.analysis.testing import assert_no_lookahead
from rinng.strategy.base import Strategy, signals_frame, validate_signals
from rinng.strategy.baselines import BuyAndHold, EmaCross, LinearRegression
from tests.analysis.helpers import T0, make_ohlcv, random_walk

H = timedelta(hours=1)


def test_baselines_satisfy_protocol():
    for s in (BuyAndHold(), LinearRegression(), EmaCross(3, 8)):
        assert isinstance(s, Strategy)
        assert isinstance(s.params, dict)


def test_validate_signals_fills_defaults():
    out = validate_signals(
        pl.DataFrame({"time": [T0 + H], "side": ["long"]}).cast({"time": pl.Datetime("ms", "UTC")})
    )
    assert out.columns == ["time", "side", "stop", "take_profit", "size", "reason"]
    assert out["size"][0] == 1.0 and out["stop"][0] is None and out["reason"][0] == ""


@pytest.mark.parametrize(
    "row, msg",
    [
        ({"side": "buy"}, "side"),
        ({"side": "long", "size": 1.5}, "size"),
        ({"side": "long", "stop": 110.0, "take_profit": 100.0}, "wrong side"),
        ({"side": "short", "stop": 90.0, "take_profit": 100.0}, "wrong side"),
    ],
)
def test_validate_signals_rejects(row, msg):
    with pytest.raises(ValueError, match=msg):
        signals_frame([{"time": T0 + H, **row}])


def test_validate_signals_rejects_unsorted_and_off_grid():
    with pytest.raises(ValueError, match="ascending"):
        signals_frame([{"time": T0 + 2 * H, "side": "long"}, {"time": T0 + H, "side": "flat"}])
    ohlcv = make_ohlcv([100.0] * 5)
    ok = signals_frame([{"time": T0 + H, "side": "long"}])
    validate_signals(ok, ohlcv)
    off = signals_frame([{"time": T0 + H / 2, "side": "long"}])
    with pytest.raises(ValueError, match="candle close"):
        validate_signals(off, ohlcv)


def test_buy_and_hold_signal_at_first_close():
    sig = BuyAndHold().signals(make_ohlcv([1.0, 2.0, 3.0]), None, None)
    assert sig["time"].to_list() == [T0 + H]
    assert sig["side"].to_list() == ["long"]


def test_linear_regression_slope_and_side():
    up = make_ohlcv([100.0 + 2 * i for i in range(50)])
    lr = LinearRegression(window=40)
    slope = lr.slopes(up)
    assert np.isnan(slope[:39]).all()
    assert slope[39:] == pytest.approx(2.0)
    sig = lr.signals(up, None, None)
    # 40 candles available at index 39, closing at T0 + 40h; emitted once since direction never
    # changes.
    assert sig["time"].to_list() == [T0 + 40 * H]
    assert sig["side"].to_list() == ["long"]
    down = make_ohlcv([200.0 - i for i in range(45)])
    assert lr.signals(down, None, None)["side"].to_list() == ["short"]
    flat = make_ohlcv([100.0] * 45)  # slope = 0 → short (per the paper: otherwise SHORT)
    assert lr.signals(flat, None, None)["side"].to_list() == ["short"]


def test_linear_regression_matches_polyfit():
    ohlcv = random_walk(120)
    slope = LinearRegression(window=40).slopes(ohlcv)
    close = ohlcv["close"].to_numpy()
    for i in (39, 77, 119):
        expected = np.polyfit(np.arange(40), close[i - 39 : i + 1], 1)[0]
        assert slope[i] == pytest.approx(expected)


@pytest.mark.parametrize("strategy", [LinearRegression(window=20), EmaCross(5, 20)])
def test_strategy_signals_no_lookahead(strategy):
    ohlcv = random_walk(300)

    def compute(frame):
        sig = strategy.signals(frame, None, None)
        return sig.with_columns(pl.col("time").alias("known_at"), pl.col("time").alias("open_time"))

    assert_no_lookahead(compute, ohlcv, [60, 150, 299])
