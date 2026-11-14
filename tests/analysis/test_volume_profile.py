import json
import time
from datetime import timedelta

import numpy as np
import polars as pl
import pytest

from rinng.analysis.testing import assert_no_lookahead
from rinng.analysis.volume_profile import (
    profile_events,
    profile_from_ohlcv,
    profile_from_trades,
    value_area,
    volume_nodes,
)
from rinng.store.schemas import TRADES, conform
from tests.analysis.helpers import T0, make_ohlcv, random_walk

H = timedelta(hours=1)


def _hand_bars():
    #      bin:     99  100  101  102  103  104
    # candle 0 100-103:     10   10   10            (30 spread over 3 bins)
    # candle 1 101-102:          20                 (high exactly on an edge: no spill into 102)
    # candle 2 101-103:           5    5
    # candle 3 103-105:                     4    4
    # candle 4  99-100:  6
    # total:            6  10   35   15    4    4  = 74
    lows = [100, 101, 101, 103, 99]
    highs = [103, 102, 103, 105, 100]
    return make_ohlcv(
        [101.0, 101.5, 102.0, 104.0, 99.5],
        lows=lows,
        highs=highs,
        volumes=[30.0, 20.0, 10.0, 8.0, 6.0],
        taker_buy=[15.0, 5.0, 10.0, 0.0, 6.0],
    )


def test_profile_from_ohlcv_by_hand():
    prof = profile_from_ohlcv(_hand_bars(), bin_size=1.0)
    assert prof["price_low"].to_list() == [99, 100, 101, 102, 103, 104]
    assert prof["price_high"].to_list() == [100, 101, 102, 103, 104, 105]
    assert prof["volume"].to_list() == pytest.approx([6, 10, 35, 15, 4, 4])
    # buy: candle 0 15/3, candle 1 5, candle 2 10/2, candle 4 6
    assert prof["buy_volume"].to_list() == pytest.approx([6, 5, 15, 10, 0, 0])
    assert (prof["buy_volume"] + prof["sell_volume"]).to_list() == pytest.approx(
        prof["volume"].to_list()
    )


def test_value_area_by_hand():
    va = value_area(profile_from_ohlcv(_hand_bars(), bin_size=1.0))
    # POC 101 (35). Target 0.7*74 = 51.8. Step 1: above 15+4=19 > below 10+6=16 → take 102,103,
    # cumulative 54 >= 51.8 → stop.
    assert (va.poc_low, va.poc_high, va.poc) == (101, 102, 101.5)
    assert (va.val, va.vah) == (101, 104)
    assert va.va_volume == pytest.approx(54)
    assert va.total_volume == pytest.approx(74)


def test_value_area_tie_and_single_bin_edge():
    vols = [5.0, 1.0, 8.0, 10.0, 3.0, 2.0, 9.0]
    prof = pl.DataFrame(
        {
            "price_low": [float(i) for i in range(7)],
            "price_high": [float(i + 1) for i in range(7)],
            "volume": vols,
        }
    )
    va = value_area(prof)
    # POC idx3 (10), target 26.6. below 8+1=9 > above 3+2=5 → lo=1 (19).
    # one bin left below: 5 = above 5 → tie picks above → hi=5 (24). one bin left above 9 > 5 →
    # hi=6.
    assert (va.val, va.vah) == (1.0, 7.0)
    assert va.va_volume == pytest.approx(33)


def test_poc_tie_prefers_middle():
    prof = pl.DataFrame(
        {
            "price_low": [0.0, 1, 2, 3, 4],
            "price_high": [1.0, 2, 3, 4, 5],
            "volume": [9.0, 1, 9, 1, 9],
        }
    )
    assert value_area(prof).poc_low == 2.0


@pytest.mark.parametrize("kw", [{"bin_size": 0.1}, {"bin_size": 0.73}, {"n_bins": 40}])
def test_profile_total_equals_bar_volume(kw):
    o = random_walk(400)
    prof = profile_from_ohlcv(o, **kw)
    assert prof["volume"].sum() == pytest.approx(o["volume"].sum(), rel=1e-9)
    assert prof["buy_volume"].sum() == pytest.approx(o["taker_buy_volume"].sum(), rel=1e-9)
    assert (prof["volume"] >= -1e-9).all()
    assert prof["price_low"][0] <= o["low"].min()
    assert prof["price_high"][-1] >= o["high"].max() - 1e-9
    if "n_bins" in kw:
        assert prof.height == kw["n_bins"]


def test_profile_from_trades_exact():
    trades = conform(
        pl.DataFrame(
            {
                "exchange": "binance",
                "symbol": "BTC-USDT-PERP",
                "trade_id": [1, 2, 3, 4],
                "time": [T0 + timedelta(seconds=i) for i in range(4)],
                "price": [100.2, 100.9, 102.5, 101.0],
                "qty": [1.0, 2.0, 3.0, 4.0],
                "is_buyer_maker": [False, True, False, True],
            }
        ),
        TRADES,
    )
    prof = profile_from_trades(trades, bin_size=1.0)
    assert prof["price_low"].to_list() == [100, 101, 102]
    assert prof["volume"].to_list() == [3, 4, 3]
    assert prof["buy_volume"].to_list() == [1, 0, 3]
    assert prof["sell_volume"].to_list() == [2, 4, 0]


def test_volume_nodes():
    v = [0.0, 1, 5, 1, 0, 0, 1, 6, 1, 0]
    prof = pl.DataFrame(
        {"price_low": [float(i) for i in range(10)], "price_high": [i + 1.0 for i in range(10)]}
    ).with_columns(volume=pl.Series(v))
    nodes = volume_nodes(prof, sigma_bins=0)
    assert nodes.filter(kind="hvn")["price_low"].to_list() == [2.0, 7.0]
    lvn = nodes.filter(kind="lvn")
    assert lvn["price_low"].to_list() == [4.0]  # plateau low: take the first bin
    assert lvn["prominence"].to_list() == [5.0]
    # prominence too high leaves no nodes
    assert volume_nodes(prof, sigma_bins=0, min_prominence=0.9).filter(kind="hvn").height == 1


def _days(n_bars):
    return random_walk(n_bars, timeframe="1h")


def test_only_closed_periods_emitted():
    o = _days(24 * 3 + 5)
    ev = profile_events(o, "day", bin_size=0.5)
    vpoc = ev.filter(kind="vpoc")
    assert vpoc["event_time"].to_list() == [T0, T0 + 24 * H, T0 + 48 * H]
    assert vpoc["known_at"].to_list() == [T0 + 24 * H, T0 + 48 * H, T0 + 72 * H]
    assert set(ev["kind"]) >= {"vpoc", "value_area", "naked_poc", "hvn", "lvn"}
    # data ends exactly at the close of day 3: day 3 is closed
    assert profile_events(_days(72), "day", bin_size=0.5).filter(kind="vpoc").height == 3
    assert profile_events(_days(71), "day", bin_size=0.5).filter(kind="vpoc").height == 2


def test_period_values_match_direct_profile():
    o = _days(24 * 2)
    ev = profile_events(o, "day", bin_size=0.5).filter(kind="value_area")
    va = value_area(profile_from_ohlcv(o.slice(24, 24), bin_size=0.5))
    row = ev.row(1, named=True)
    assert (row["price_low"], row["price_high"]) == (va.val, va.vah)
    assert json.loads(row["attrs"])["poc"] == va.poc


def test_week_and_month_boundaries():
    o = random_walk(24 * 40, timeframe="1h")  # 2026-01-05 (Monday) → Feb 13
    weeks = profile_events(o, "week", n_bins=30).filter(kind="vpoc")
    assert weeks["event_time"].dt.weekday().to_list() == [1] * 5
    assert weeks["event_time"][0] == T0
    months = profile_events(o, "month", n_bins=30).filter(kind="vpoc")
    # January is closed (data starts mid-month), February is not
    assert months["event_time"].dt.month().to_list() == [1]
    assert json.loads(months["attrs"][0])["n_bars"] == 27 * 24


def test_anchored_ranges():
    o = _days(24)
    ranges = [(T0 + 2 * H, T0 + 10 * H), (T0 + 2 * H, T0 + 30 * H)]
    ev = profile_events(o, ranges, n_bins=20)
    vpoc = ev.filter(kind="vpoc")
    assert vpoc.height == 1  # the second range is not closed yet
    assert vpoc["known_at"][0] == T0 + 10 * H
    va = value_area(profile_from_ohlcv(o.slice(2, 8), n_bins=20))
    assert vpoc["price_low"][0] == va.poc_low
    assert ev["event_id"].n_unique() == ev.height


def test_naked_poc_invalidated_on_right_bar():
    lows = [100.0] * 24 + [110.0] * 24 + [110.0] * 5 + [100.2] + [110.0] * 18
    highs = [101.0] * 24 + [111.0] * 48
    o = make_ohlcv(
        [(lo + hi) / 2 for lo, hi in zip(lows, highs, strict=True)], lows=lows, highs=highs
    )
    naked = profile_events(o, "day", bin_size=1.0).filter(kind="naked_poc").sort("event_time")
    assert naked["price_low"].to_list() == [100.5, 110.5, 110.5]
    times = o["open_time"]
    # day 0: candle 53 is the first to touch 100.5; invalidated_at = close of candle 53
    assert naked["invalidated_at"][0] == times[53] + H
    # day 1: the first candle of day 2 (48) touches immediately
    assert naked["invalidated_at"][1] == times[48] + H
    assert naked["invalidated_at"][2] is None


def test_profile_events_no_lookahead():
    o = random_walk(24 * 6, timeframe="1h")
    assert_no_lookahead(lambda x: profile_events(x, "day", bin_size=0.5), o, [30, 48, 49, 100])
    assert_no_lookahead(lambda x: profile_events(x, "day", n_bins=25), o, [24, 72, 97])


def test_bad_params():
    o = _days(30)
    with pytest.raises(ValueError):
        profile_events(o, "day")
    with pytest.raises(ValueError):
        profile_events(o, "day", bin_size=1.0, n_bins=10)
    with pytest.raises(ValueError):
        profile_events(o, "year", bin_size=1.0)


def test_week_of_1m_is_fast():
    o = random_walk(7 * 1440, timeframe="1m")
    started = time.perf_counter()
    ev = profile_events(o, "week", bin_size=0.05)
    ev_day = profile_events(o, "day", bin_size=0.05)
    elapsed = time.perf_counter() - started
    assert ev.filter(kind="vpoc").height == 1 and ev_day.filter(kind="vpoc").height == 7
    assert elapsed < 1.0, elapsed
    assert np.isfinite(ev["price_low"].to_numpy()).all()


# --- profile shape ---


def _shape_profile(volumes):
    import polars as pl

    n = len(volumes)
    return pl.DataFrame(
        {
            "price_low": [float(i) for i in range(n)],
            "price_high": [float(i + 1) for i in range(n)],
            "volume": [float(x) for x in volumes],
        }
    )


def test_classify_shape_d_p_b_dd():
    import numpy as np

    from rinng.analysis.volume_profile import classify_shape

    x = np.arange(50)
    bell = lambda c, w: np.exp(-((x - c) ** 2) / (2 * w**2))  # noqa: E731
    assert classify_shape(_shape_profile(bell(25, 6) + 0.05)) == "D"
    assert classify_shape(_shape_profile(bell(40, 4) + 0.2 * (x < 40))) == "P"
    assert classify_shape(_shape_profile(bell(9, 4) + 0.2 * (x > 9))) == "b"
    assert classify_shape(_shape_profile(bell(12, 3) + 0.8 * bell(38, 3) + 0.01)) == "DD"


def test_classify_shape_shallow_valley_is_not_dd():
    import numpy as np

    from rinng.analysis.volume_profile import classify_shape

    x = np.arange(50)
    two = np.exp(-((x - 18) ** 2) / 50) + np.exp(-((x - 32) ** 2) / 50)  # high middle valley
    assert classify_shape(_shape_profile(two)) == "D"
