import json
from datetime import timedelta

import numpy as np
import pytest

from rinng.analysis.elliott import (
    impulse_candidates,
    impulse_ratios,
    impulse_rules,
    zigzag,
    zigzag_pivots,
    zigzag_table,
)
from rinng.analysis.testing import assert_no_lookahead
from tests.analysis.helpers import T0, make_ohlcv, random_walk

H = timedelta(hours=1)


def _path(points, steps=4):
    prices = [float(points[0])]
    for a, b in zip(points, points[1:], strict=False):
        prices += np.linspace(a, b, steps + 1)[1:].tolist()
    return make_ohlcv(prices, opens=prices, highs=prices, lows=prices)


# Hand-built pivots at candles 0, 4, 8, ..., 24 (4 candles per leg).
PATH = [100, 120, 110, 150, 135, 160, 140, 150]


def test_zigzag_percent_pivots_and_known_at():
    o = _path(PATH)
    table = zigzag_table(zigzag(o, threshold=0.05))
    assert table["index"].to_list() == [0, 4, 8, 12, 16, 20, 24]
    assert table["price"].to_list() == [100, 120, 110, 150, 135, 160, 140]
    assert table["kind"].to_list() == ["zigzag_low", "zigzag_high"] * 3 + ["zigzag_low"]
    # hand-computed confirming candles: 1, 7, 9, 14, 18, 22, 27
    confirms = [1, 7, 9, 14, 18, 22, 27]
    assert table["known_at"].to_list() == [T0 + (c + 1) * H for c in confirms]
    # the final 150 high has not reversed 5% yet, so it is not a pivot
    assert table["event_time"][-1] == T0 + 24 * H


def test_zigzag_pivot_needs_later_bar_and_ties_take_first():
    high = np.array([10.0, 12.0, 12.0, 11.0, 9.0])
    low = high.copy()
    piv = zigzag_pivots(high, low, pct=0.2)
    assert piv == [(0, "L", 10.0, 1), (1, "H", 12.0, 4)]
    # candle 2 sets a new high and has a deep low: the high is not confirmed within that candle
    high2 = np.array([10.0, 13.0, 14.0, 13.5])
    low2 = np.array([10.0, 12.9, 10.0, 13.4])
    assert zigzag_pivots(high2, low2, pct=0.2) == [(0, "L", 10.0, 1)]


def test_zigzag_atr_mode():
    high = np.array([10.0, 11.0, 12.0, 11.0, 10.0])
    low = high.copy()
    dist = np.array([np.nan, np.nan, 1.5, 1.5, 1.5])
    # no ATR at candle 1, so the low of 10 is only confirmed at candle 2
    assert zigzag_pivots(high, low, dist) == [(0, "L", 10.0, 2), (2, "H", 12.0, 4)]
    ev = zigzag(random_walk(300), threshold=3.0, mode="atr")
    kinds = zigzag_table(ev)["kind"].to_list()
    assert len(kinds) > 4 and all(a != b for a, b in zip(kinds, kinds[1:], strict=False))
    with pytest.raises(ValueError):
        zigzag(random_walk(10), mode="pct")


@pytest.mark.parametrize(
    ("prices", "expected"),
    [
        ([100, 120, 110, 150, 135, 160], (True, True, True)),
        ([100, 120, 95, 150, 135, 160], (False, True, True)),  # wave 2 passes the origin
        ([100, 120, 100, 150, 135, 160], (False, True, True)),  # touching the origin: fails
        ([100, 130, 120, 135, 131, 160], (True, False, True)),  # wave 3 is the shortest
        ([100, 120, 110, 150, 115, 160], (True, True, False)),  # wave 4 overlaps wave 1
        ([200, 180, 190, 150, 165, 140], (True, True, True)),  # bearish impulse
        ([200, 180, 205, 150, 175, 140], (False, True, True)),
    ],
)
def test_impulse_rules(prices, expected):
    rules = impulse_rules(prices, log=False)
    assert tuple(rules.values()) == expected
    assert list(rules) == ["wave2_within_wave1", "wave3_not_shortest", "wave4_no_overlap"]


def test_impulse_rule2_depends_on_scale_and_input_checks():
    # linear: wave 3 (12) longer than wave 1 (10); log: wave 3 shorter than both wave 1 and wave 5
    prices = [10, 20, 18, 30, 28, 60]
    assert impulse_rules(prices, log=False)["wave3_not_shortest"] is True
    assert impulse_rules(prices, log=True)["wave3_not_shortest"] is False
    with pytest.raises(ValueError):
        impulse_rules([1, 2, 3, 4, 5])
    with pytest.raises(ValueError):
        impulse_rules([100, 110, 120, 130, 125, 140])  # not alternating


def test_impulse_ratios():
    r = impulse_ratios([100, 120, 110, 150, 135, 160])
    assert r == pytest.approx(
        {
            "wave2_wave1": 0.5,
            "wave3_wave1": 2.0,
            "wave4_wave3": 0.375,
            "wave5_wave1": 1.25,
            "wave5_wave1to3": 0.5,
        }
    )


def test_impulse_candidates_lists_valid_windows_only():
    o = _path(PATH)
    ev = impulse_candidates(o, threshold=0.05, log=False)
    assert ev.height == 1  # the second window (starting at the 120 high) fails rule 1
    row = ev.row(0, named=True)
    assert row["kind"] == "impulse_candidate"
    assert row["event_time"] == T0 + 20 * H
    assert row["known_at"] == T0 + 23 * H  # P5 confirmed at candle 22
    assert (row["price_low"], row["price_high"]) == (100, 160)
    attrs = json.loads(row["attrs"])
    assert attrs["direction"] == "up" and attrs["indices"] == [0, 4, 8, 12, 16, 20]
    assert attrs["ratios"]["wave3_wave1"] == pytest.approx(2.0)


def test_impulse_candidates_keeps_overlapping_and_none_case():
    # two overlapping bullish impulses: every valid window is kept
    o = _path([100, 120, 110, 150, 135, 180, 165, 200, 180])
    ev = impulse_candidates(o, threshold=0.05, log=False)
    assert ev.height == 2
    flat = _path([100, 120, 100, 120, 100, 120, 100, 120])  # wave 2 returns exactly to the origin
    assert impulse_candidates(flat, threshold=0.05, log=False).is_empty()


def test_elliott_no_lookahead():
    o = random_walk(500)
    cuts = [100, 250, 251, 400]
    assert_no_lookahead(lambda x: zigzag(x, threshold=0.02), o, cuts)
    assert_no_lookahead(lambda x: zigzag(x, threshold=2.0, mode="atr"), o, cuts)
    ev = impulse_candidates(o, threshold=0.02)
    assert not ev.is_empty()
    assert_no_lookahead(lambda x: impulse_candidates(x, threshold=0.02), o, cuts)
