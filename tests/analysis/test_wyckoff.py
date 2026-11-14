import json
from datetime import timedelta

import numpy as np
import pytest

from rinng.analysis.testing import assert_no_lookahead
from rinng.analysis.wyckoff import atr, climaxes, effort_result, rolling_zscore, trading_ranges
from tests.analysis.helpers import T0, make_ohlcv, random_walk

H = timedelta(hours=1)


def _bars(rows):
    """rows: list (open, high, low, close, volume)."""
    o, h, lo, c, v = (list(map(float, col)) for col in zip(*rows, strict=True))
    return make_ohlcv(c, opens=o, highs=h, lows=lo, volumes=v)


def _baseline(n=50):
    return [
        (100.0, 100.5, 99.7, 100.2, 9.0) if i % 2 == 0 else (100.2, 100.5, 99.7, 100.0, 11.0)
        for i in range(n)
    ]


INSIDE = [(97.0, 98.3, 96.7, 98.0, 10.0), (98.0, 98.3, 96.7, 97.0, 10.0)]


def _scenario():
    """Selling climax at candle 50, range [94, 101] confirmed at candle 65, spring at candles 70-71,
    upthrust at candle 72, breakout from candle 75 and the range breaks at candle 77."""
    rows = _baseline()
    rows.append((100.0, 100.0, 94.0, 95.0, 100.0))  # 50: climax
    rows += [
        (95.0, 96.6, 94.8, 96.5, 12.0),  # 51
        (96.5, 98.0, 96.2, 97.8, 10.0),  # 52
        (97.8, 101.0, 97.5, 98.8, 12.0),  # 53: AR, range top
        (98.8, 99.2, 97.9, 98.0, 10.0),  # 54
        (98.0, 98.4, 97.0, 97.2, 12.0),  # 55: end of reaction
    ]
    rows += [INSIDE[i % 2] for i in range(14)]  # 56..69
    rows.append((97.0, 97.5, 93.0, 93.5, 10.0))  # 70: breaks the low, closes below
    rows.append((93.5, 95.5, 93.2, 95.0, 10.0))  # 71: closes back inside the range
    rows.append((95.0, 101.5, 94.9, 98.0, 10.0))  # 72: single-candle upthrust
    rows += [INSIDE[i % 2] for i in range(2)]  # 73, 74
    rows.append((97.5, 101.8, 97.4, 101.5, 10.0))  # 75: breaks up
    rows += [(101.5, 101.9, 101.3, 101.6, 10.0), (101.6, 102.0, 101.4, 101.7, 10.0)]  # 76, 77
    rows += [(101.7, 102.0, 101.5, 101.8, 10.0)] * 3  # 78..80
    return rows


def test_atr_wilder_and_zscore():
    h = np.array([2.0, 3.0, 4.0, 5.0])
    lo = np.array([1.0, 1.0, 2.0, 3.0])
    c = np.array([1.5, 2.5, 3.5, 4.5])
    a = atr(h, lo, c, 3)
    assert np.isnan(a[:2]).all()
    assert a[2] == pytest.approx(5 / 3)
    assert a[3] == pytest.approx((5 / 3 * 2 + 2) / 3)
    z = rolling_zscore(np.array([1.0, 2.0, 3.0, 3.0, 3.0, 3.0]), 3)
    assert z[2] == pytest.approx(1.0)
    assert np.isnan(z[:2]).all() and np.isnan(z[5])  # std = 0 -> NaN


def test_climax_selling_and_buying():
    o = _bars(_scenario())
    ev = climaxes(o)
    assert ev["kind"].to_list() == ["selling_climax"]
    row = ev.row(0, named=True)
    assert row["event_time"] == T0 + 50 * H and row["known_at"] == T0 + 51 * H
    assert (row["price_low"], row["price_high"]) == (94.0, 100.0)
    attrs = json.loads(row["attrs"])
    assert attrs["volume_z"] > 2.5 and attrs["spread_atr"] > 1.8
    assert attrs["clv"] == pytest.approx(1 / 6)

    rows = _baseline()
    rows.append((100.0, 106.0, 100.0, 105.0, 100.0))
    assert climaxes(_bars(rows))["kind"].to_list() == ["buying_climax"]


def test_no_climax_when_only_volume_or_only_range():
    vol_only = _baseline(80) + [(100.0, 100.3, 99.7, 100.2, 100.0)]
    range_only = _baseline(80) + [(100.0, 100.0, 94.0, 95.0, 10.0)]
    assert climaxes(_bars(vol_only)).is_empty()
    assert climaxes(_bars(range_only)).is_empty()
    f = effort_result(_bars(vol_only))
    last = f.row(-1, named=True)
    assert last["volume_z"] > 3 and last["effort_result_gap"] > 3  # large effort, small result
    assert last["spread_atr"] == pytest.approx(0.6 / 0.8)
    f2 = effort_result(_bars(range_only)).row(-1, named=True)
    assert f2["effort_result_gap"] < -3 and f2["clv"] == pytest.approx(1 / 6)
    assert (
        f["volume_z"][:49].null_count() == 49 and f["spread_z"][:63].null_count() == 63
    )  # window not filled yet


def test_trading_range_spring_upthrust_and_invalidation():
    o = _bars(_scenario())
    ev = trading_ranges(o, reaction_bars=5, min_bars=10, reclaim_bars=3)
    assert ev["kind"].to_list() == ["trading_range", "spring", "upthrust"]
    tr = ev.row(0, named=True)
    assert (tr["price_low"], tr["price_high"]) == (94.0, 101.0)
    assert tr["event_time"] == T0 + 50 * H
    assert tr["known_at"] == T0 + 66 * H  # close of candle 65: the 10th candle in the range
    assert tr["invalidated_at"] == T0 + 78 * H  # close of candle 77: 3 candles outside the range

    spring = ev.row(1, named=True)
    assert spring["event_time"] == T0 + 70 * H
    assert spring["known_at"] == T0 + 72 * H  # close of candle 71
    assert (spring["price_low"], spring["price_high"]) == (93.0, 94.0)
    sa = json.loads(spring["attrs"])
    assert sa["reclaim_bars"] == 2 and sa["penetration"] == pytest.approx(1.0)

    up = ev.row(2, named=True)
    assert up["event_time"] == T0 + 72 * H and up["known_at"] == T0 + 73 * H
    assert json.loads(up["attrs"])["reclaim_bars"] == 1


def test_no_range_when_close_leaves_before_confirmation():
    rows = _scenario()
    rows[60] = (97.0, 102.0, 96.9, 101.5, 10.0)  # closes outside before 10 candles
    ev = trading_ranges(_bars(rows), reaction_bars=5, min_bars=10, reclaim_bars=3)
    assert ev.is_empty()
    assert trading_ranges(_bars(_baseline(80))).is_empty()  # no climax


def test_spring_needs_reclaim_within_m_bars():
    rows = _scenario()
    # candle 71 still closes below the low: with M = 2 the range breaks at candle 71, no spring
    rows[71] = (93.5, 93.9, 93.2, 93.6, 10.0)
    ev = trading_ranges(_bars(rows), reaction_bars=5, min_bars=10, reclaim_bars=2)
    assert ev["kind"].to_list() == ["trading_range"]
    assert ev["invalidated_at"][0] == T0 + 72 * H


def test_wyckoff_no_lookahead():
    o = random_walk(400)
    cuts = [80, 200, 201, 333]
    assert_no_lookahead(lambda x: effort_result(x, window=30), o, cuts)
    assert_no_lookahead(lambda x: climaxes(x, window=30, volume_z_min=1.5, spread_min=1.2), o, cuts)
    loose = dict(window=30, volume_z_min=1.0, spread_min=1.0, min_bars=4, reclaim_bars=2)
    assert not trading_ranges(o, **loose).is_empty()
    assert_no_lookahead(lambda x: trading_ranges(x, **loose), o, cuts)
    scenario = _bars(_scenario())
    assert_no_lookahead(lambda x: trading_ranges(x), scenario, [60, 66, 70, 71, 72, 76, 78])
