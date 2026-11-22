import json
from datetime import timedelta

import polars as pl
import pytest

from rinng.analysis import smc
from rinng.analysis.testing import assert_no_lookahead
from tests.analysis.helpers import T0, make_ohlcv, random_walk


def bars(rows):
    """Candles from a list of (open, high, low, close)."""
    o, h, lo, c = (list(x) for x in zip(*rows, strict=True))
    return make_ohlcv(c, opens=o, highs=h, lows=lo)


# Swing length 2: swing high at candle 2 (12) known at close of candle 4; swing low at candle 4
# (9.6) known at close of candle 6.
BASE = [
    (10.0, 10.5, 9.5, 10.0),  # 0
    (10.0, 11.0, 9.8, 10.8),  # 1
    (10.8, 12.0, 10.5, 11.0),  # 2  swing high 12
    (11.0, 11.2, 10.0, 10.2),  # 3
    (10.2, 10.5, 9.6, 9.8),  # 4  swing low 9.6, last down candle before the rally
]
# BOS up at candle 6 (close 13.2 > 12), CHoCH down at candle 8 (close 9.2 < 9.6).
BREAK = BASE + [
    (9.8, 10.4, 9.7, 10.3),  # 5
    (10.3, 13.5, 10.2, 13.2),  # 6  bullish displacement, breaks 12
    (13.2, 13.3, 12.5, 12.8),  # 7
    (12.8, 12.9, 9.0, 9.2),  # 8  breaks 9.6
    (9.2, 11.0, 9.1, 10.9),  # 9
]


def rows_of(ev):
    return ev.select("kind", "event_time", "known_at", "price_low", "price_high").rows()


def test_bos_then_choch():
    o = bars(BREAK)
    t = o["open_time"].to_list()
    ev = smc.structure_breaks(o, swing_length=2)
    hour = t[1] - t[0]
    assert rows_of(ev) == [
        ("bos_bull", t[6], t[6] + hour, 12.0, 12.0),
        ("choch_bear", t[8], t[8] + hour, 9.6, 9.6),
    ]
    attrs = json.loads(ev["attrs"][0])
    assert attrs["swing_index"] == 2 and attrs["break_index"] == 6


def test_break_close_vs_wick():
    wick_only = BASE + [(9.8, 10.4, 9.7, 10.3), (10.3, 12.5, 10.2, 11.8), (11.8, 11.9, 11.0, 11.5)]
    o = bars(wick_only)
    assert smc.structure_breaks(o, swing_length=2, break_on="close").is_empty()
    ev = smc.structure_breaks(o, swing_length=2, break_on="wick")
    assert ev["kind"].to_list() == ["bos_bull"]
    with pytest.raises(ValueError):
        smc.structure_breaks(o, break_on="body")


def test_no_break_inside_range():
    inside = BASE + [(9.8, 10.4, 9.7, 10.3), (10.3, 11.5, 10.0, 11.0), (11.0, 11.6, 9.9, 10.0)]
    assert smc.structure_breaks(bars(inside), swing_length=2).is_empty()


def test_displacement():
    calm = [(10.0, 10.3, 9.8, 10.1)] * 8
    o = bars(calm + [(10.1, 12.2, 10.0, 12.0)])
    ev = smc.displacement(o, k=1.5, atr_length=3)
    assert ev["kind"].to_list() == ["displacement_bull"]
    assert ev["event_time"][0] == o["open_time"][8]
    assert (ev["price_low"][0], ev["price_high"][0]) == (10.1, 12.0)
    down = bars(calm + [(10.1, 10.2, 8.0, 8.1)])
    assert smc.displacement(down, k=1.5, atr_length=3)["kind"].to_list() == ["displacement_bear"]
    # body 0.6 does not exceed 1.5 × ATR (~0.5)
    assert smc.displacement(bars(calm + [(10.1, 10.8, 10.0, 10.7)]), atr_length=3).is_empty()


def test_fvg_bull_and_full_fill():
    o = bars(
        [
            (10.0, 10.5, 9.5, 10.2),
            (10.2, 12.0, 10.1, 11.9),
            (11.9, 12.5, 11.0, 12.3),  # low 11 > high[0] 10.5
            (12.3, 12.4, 10.8, 11.0),  # touches the zone but does not fill it
            (11.0, 11.2, 10.4, 10.6),  # low 10.4 <= 10.5: fully filled
        ]
    )
    t = o["open_time"].to_list()
    ev = smc.fair_value_gaps(o)
    assert sorted(ev["kind"]) == ["fvg_bull", "fvg_bull_mitigated"]
    assert ev.filter(pl.col("kind") == "fvg_bull_mitigated")["event_time"][0] == t[3]
    row = ev.filter(pl.col("kind") == "fvg_bull").row(0, named=True)
    assert row["event_time"] == t[1] and row["known_at"] == t[3]
    assert (row["price_low"], row["price_high"]) == (10.5, 11.0)
    assert row["invalidated_at"] == t[4] + (t[1] - t[0])
    # not filled if stopping before candle 4
    assert smc.fair_value_gaps(o.head(4))["invalidated_at"][0] is None


def test_fvg_bear_and_none():
    o = bars([(12.0, 12.5, 11.5, 11.8), (11.8, 11.9, 10.0, 10.1), (10.1, 11.0, 9.8, 10.0)])
    ev = smc.fair_value_gaps(o)
    assert ev["kind"].to_list() == ["fvg_bear"]
    assert (ev["price_low"][0], ev["price_high"][0]) == (11.0, 11.5)
    overlap = bars([(10.0, 11.0, 9.5, 10.5), (10.5, 11.5, 10.0, 11.0), (11.0, 11.8, 10.9, 11.5)])
    assert smc.fair_value_gaps(overlap).is_empty()
    # size filter by ATR
    assert smc.fair_value_gaps(o, min_size_atr=10.0, atr_length=2).is_empty()


def test_order_blocks_mitigation_and_breaker():
    o = bars(BREAK)
    t = o["open_time"].to_list()
    hour = t[1] - t[0]
    ev = smc.order_blocks(o, swing_length=2, atr_length=3)
    cols = ("kind", "event_time", "known_at", "price_low", "price_high", "invalidated_at")
    got = {r[0]: r for r in ev.select(cols).rows()}
    # Bull OB = last down candle (candle 4) before the BOS at candle 6; closed below 9.6 at candle
    # 8.
    assert got["ob_bull"] == ("ob_bull", t[4], t[6] + hour, 9.6, 10.5, t[8] + hour)
    assert got["ob_bull_mitigated"][1:3] == (t[8], t[8] + hour)
    # Breaker bear emitted at candle 8, closed back above 10.5 at candle 9.
    assert got["breaker_bear"] == ("breaker_bear", t[8], t[8] + hour, 9.6, 10.5, t[9] + hour)
    # Bear OB = last up candle (candle 6) before the CHoCH at candle 8; retested at candle 9 (high
    # 11 >= 10.2).
    assert got["ob_bear"][1:5] == (t[6], t[8] + hour, 10.2, 13.5)
    assert got["ob_bear"][5] is None
    assert got["ob_bear_mitigated"][1] == t[9]
    assert json.loads(ev.filter(kind="ob_bull")["attrs"][0])["break_kind"] == "bos_bull"


def test_order_blocks_need_displacement():
    o = bars(BREAK)
    assert smc.order_blocks(o, swing_length=2, atr_length=3, displacement_k=50).is_empty()
    loose = smc.order_blocks(o, swing_length=2, displacement_k=50, require_displacement=False)
    assert "ob_bull" in loose["kind"].to_list()
    inside = BASE + [(9.8, 10.4, 9.7, 10.3), (10.3, 11.5, 10.0, 11.0)]
    assert smc.order_blocks(bars(inside), swing_length=2, atr_length=3).is_empty()


def test_premium_discount():
    rows = BASE + [
        (9.8, 10.4, 9.7, 10.3),  # 5
        (10.3, 11.0, 10.2, 10.8),  # 6: L = 9.6 known from this row, H = 12
        (10.8, 11.5, 10.7, 11.4),  # 7
        (11.4, 11.5, 9.9, 10.2),  # 8
    ]
    f = smc.premium_discount(bars(rows), swing_length=2)
    assert f["pd_position"].to_list()[:6] == [None] * 6  # no swing low yet
    assert f["pd_zone"][5] is None
    assert f["pd_range_high"][6] == 12.0 and f["pd_range_low"][6] == 9.6
    assert f["pd_equilibrium"][6] == pytest.approx(10.8)
    assert f["pd_position"][6] == pytest.approx(0.5)
    assert f["pd_zone"].to_list()[6:] == ["equilibrium", "premium", "discount"]
    assert f["pd_position"][7] == pytest.approx(0.75)
    assert f["pd_position"][8] == pytest.approx(0.25)
    wide = smc.premium_discount(bars(rows), swing_length=2, equilibrium_band=0.3)
    assert wide["pd_zone"].to_list()[6:] == ["equilibrium"] * 3
    # beyond the range it is clipped to 1
    g = smc.premium_discount(bars(BREAK), swing_length=2)
    assert g["pd_position"][6] == 1.0


def test_events_combined():
    o = bars(BREAK)
    ev = smc.events(
        o, {"breaks": {"swing_length": 2}, "order_blocks": {"swing_length": 2, "atr_length": 3}}
    )
    kinds = set(ev["kind"])
    assert {"bos_bull", "choch_bear", "ob_bull", "breaker_bear"} <= kinds
    assert ev["event_id"].n_unique() == ev.height


@pytest.mark.parametrize(
    "fn",
    [
        lambda x: smc.structure_breaks(x, 5),
        lambda x: smc.structure_breaks(x, 3, break_on="wick"),
        lambda x: smc.displacement(x, k=1.2),
        lambda x: smc.fair_value_gaps(x),
        lambda x: smc.fair_value_gaps(x, min_size_atr=0.1),
        lambda x: smc.order_blocks(x, 3, require_displacement=False),
        lambda x: smc.order_blocks(x, 3, invalidate_on="wick", displacement_k=1.0),
        lambda x: smc.premium_discount(x, 5),
        lambda x: smc.events(x),
        lambda x: smc.previous_levels(x, "1d"),
        lambda x: smc.previous_levels(x, "4h"),
        lambda x: smc.sessions(x, "london"),
        lambda x: smc.sessions(x, "sydney"),
        lambda x: smc.retracements(x, 3),
    ],
)
def test_smc_no_lookahead(fn):
    o = random_walk(300)
    assert not fn(o).is_empty()
    assert_no_lookahead(fn, o, [40, 120, 121, 250])


def test_fvg_first_touch_before_fill():
    # Bull FVG [10.5, 11.5] from candles 0..2; candle 3 dips to 11.0 (half), candle 4 fills.
    o = bars(
        [
            (10.0, 10.5, 9.8, 10.4),
            (10.4, 12.0, 10.3, 11.9),
            (11.9, 12.5, 11.5, 12.4),
            (12.4, 12.6, 11.0, 12.0),
            (12.0, 12.1, 10.0, 10.2),
        ]
    )
    ev = smc.fair_value_gaps(o)
    bull = ev.filter(pl.col("kind") == "fvg_bull").row(0, named=True)
    touch = ev.filter(pl.col("kind") == "fvg_bull_mitigated").row(0, named=True)
    assert (bull["price_low"], bull["price_high"]) == (10.5, 11.5)
    assert touch["event_time"] == o["open_time"][3]
    assert json.loads(touch["attrs"])["depth"] == pytest.approx(0.5)
    assert bull["invalidated_at"] == o["open_time"][4] + timedelta(hours=1)


def test_previous_levels_daily():
    # 1h candles from Monday 00:00: day 0 high 105 / low 95 (with a bump), day 1 trades above 105.
    closes = [100.0] * 48
    highs = [101.0] * 48
    lows = [99.0] * 48
    highs[5], lows[7] = 105.0, 95.0
    highs[30] = 106.0
    o = make_ohlcv(closes, highs=highs, lows=lows)
    ev = smc.previous_levels(o, "1d")
    # Only day 0 is emitted: day 1 completes exactly at the data end, so it is emitted too.
    hi = ev.filter(pl.col("kind") == "prev_high").sort("event_time")
    assert hi["price_high"].to_list() == [105.0, 106.0]
    first = hi.row(0, named=True)
    assert first["known_at"] == o["open_time"][24]
    assert first["invalidated_at"] == o["open_time"][31]
    lo = ev.filter(pl.col("kind") == "prev_low").row(0, named=True)
    assert lo["price_low"] == 95.0 and lo["invalidated_at"] is None
    # An incomplete last day is not emitted.
    assert smc.previous_levels(o.head(40), "1d").height == 2


def test_previous_levels_skips_partial_first_period():
    o = make_ohlcv([100.0] * 30, start=T0 + timedelta(hours=3))
    ev = smc.previous_levels(o, "1d")
    assert ev.is_empty()


def test_sessions_reset_and_midnight_cross():
    highs = [100.0 + i for i in range(48)]
    o = make_ohlcv([100.0] * 48, highs=highs)
    f = smc.sessions(o, start="22:00", end="02:00")
    active = f["session_active"].to_list()
    assert [i for i in range(24) if active[i]] == [0, 1, 22, 23]
    sh = f["session_high"].to_list()
    # 22:00, 23:00 of day 0 and 00:00, 01:00 of day 1 are one instance; 00:00-01:00 of day 0 is
    # the previous one and must not leak in.
    assert sh[1] == highs[1]
    assert sh[22] == highs[22] and sh[25] == highs[25]
    assert sh[3] is None
    with pytest.raises(ValueError):
        smc.sessions(o, "nowhere")


def test_retracements_up_leg():
    # Swing low (L=2) at candle 2, then a rally to 20 and a pullback.
    closes = [12.0, 11.0, 10.0, 12.0, 14.0, 20.0, 17.0, 15.0]
    o = make_ohlcv(closes)
    f = smc.retracements(o, 2)
    row = f.row(6, named=True)
    assert row["leg_dir"] == 1
    # origin 10, extreme 20, close 17 → 30 %.
    assert row["retrace_pct"] == pytest.approx(30.0)
    assert f.row(6, named=True)["deepest_pct"] == pytest.approx(30.0)
    # The swing high at candle 5 becomes known at the close of candle 7: the leg flips down.
    assert f.row(7, named=True)["leg_dir"] == -1
    assert f["leg_dir"][3] is None  # swing low at 2 is only known at the close of candle 4


# --- Containment merging + fractals -------------------------------------------------------------

CHAN = [
    (10.0, 10.5, 9.5, 10.2),  # 0
    (10.2, 11.0, 10.0, 10.8),  # 1  up
    (10.8, 12.0, 10.6, 11.5),  # 2  high 12
    (11.5, 11.8, 10.9, 11.0),  # 3  inside 2 -> merged up: high 12 (idx 2), low 10.9 (idx 3)
    (11.0, 11.2, 10.2, 10.3),  # 4  lower: confirms nothing yet (bar 4 is still open)
    (10.3, 10.6, 9.0, 9.2),  # 5  lower low: merged bar 3 (candle 4) final -> top confirmed here
    (9.2, 10.0, 9.1, 9.9),  # 6  inside 5 -> merged down: high 10.0, low 9.0 (idx 5)
    (9.9, 11.5, 9.6, 11.4),  # 7  breaks out -> bar(5,6) final; bottom needs one more final bar
    (11.4, 12.5, 11.3, 12.4),  # 8  bar 7 final -> bottom at candle 5 confirmed here
]


def test_merged_bars_containment():
    mb = smc.merged_bars(bars(CHAN))
    assert mb.select("start_index", "end_index").rows() == [
        (0, 0),
        (1, 1),
        (2, 3),
        (4, 4),
        (5, 6),
        (7, 7),
        (8, 8),
    ]
    row = mb.row(2, named=True)
    assert (row["high"], row["high_index"], row["low"], row["low_index"]) == (12.0, 2, 10.9, 3)
    row = mb.row(4, named=True)  # down merge: min high, min low
    assert (row["high"], row["low"], row["low_index"]) == (10.0, 9.0, 5)
    assert mb["final_index"].to_list() == [1, 2, 4, 5, 7, 8, None]


def test_fractals_timing_and_extreme():
    ev = smc.fractals(bars(CHAN))
    got = [(k, t, ka, p) for k, t, ka, p, _ in rows_of(ev)]
    hour = timedelta(hours=1)
    assert got == [
        ("fractal_top", T0 + 2 * hour, T0 + 6 * hour, 12.0),
        ("fractal_bottom", T0 + 5 * hour, T0 + 9 * hour, 9.0),
    ]
    attrs = json.loads(ev["attrs"][0])
    assert attrs["merged_start"] == 2 and attrs["merged_end"] == 3 and attrs["confirm_index"] == 5


def test_fractals_no_lookahead():
    o = random_walk(300, seed=7)
    assert_no_lookahead(smc.fractals, o, [30, 77, 150, 151, 299])
