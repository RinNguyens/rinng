import json

import pytest

from rinng.analysis import liquidity
from rinng.analysis.testing import assert_no_lookahead
from tests.analysis.helpers import make_ohlcv, random_walk


def bars(rows):
    """Nến từ danh sách (open, high, low, close)."""
    o, h, lo, c = (list(x) for x in zip(*rows, strict=True))
    return make_ohlcv(c, opens=o, highs=h, lows=lo)


# Swing length 2: swing high 12 ở nến 2 (biết lúc đóng nến 4), swing low 9.6 ở nến 4
# (biết lúc đóng nến 6), swing high 11.95 ở nến 6 (biết lúc đóng nến 8).
EQ = [
    (10.0, 10.5, 9.5, 10.0),  # 0
    (10.0, 11.0, 9.8, 10.8),  # 1
    (10.8, 12.0, 10.5, 11.0),  # 2  swing high 12
    (11.0, 11.2, 10.0, 10.2),  # 3
    (10.2, 10.5, 9.6, 9.8),  # 4  swing low 9.6
    (9.8, 11.0, 9.7, 10.9),  # 5
    (10.9, 11.95, 10.8, 11.2),  # 6  swing high 11.95
    (11.2, 11.5, 10.3, 10.4),  # 7
    (10.4, 10.6, 9.9, 10.1),  # 8
]
SWEEP = (10.1, 12.2, 10.0, 11.5)  # wick qua 12 và 11.95, đóng lại bên dưới
BREAKOUT = (10.1, 12.4, 10.0, 12.3)  # đóng trên cả hai mức


def test_liquidity_levels_and_taken():
    o = bars(EQ + [SWEEP])
    t = o["open_time"].to_list()
    hour = t[1] - t[0]
    ev = liquidity.liquidity_levels(o, swing_length=2)
    bsl = ev.filter(kind="liquidity_bsl").sort("event_time")
    assert bsl["price_low"].to_list() == [12.0, 11.95]
    assert bsl["known_at"].to_list() == [t[4] + hour, t[8] + hour]
    # cả hai bị lấy bởi wick 12.2 ở nến 9
    assert bsl["invalidated_at"].to_list() == [t[9] + hour] * 2
    ssl = ev.filter(kind="liquidity_ssl")
    assert ssl["price_low"].to_list() == [9.6]
    assert ssl["invalidated_at"][0] is None


def test_no_levels_without_swings():
    flat = bars([(10.0, 10.5, 9.5, 10.0)] * 10)
    assert liquidity.liquidity_levels(flat, swing_length=2).is_empty()
    assert liquidity.equal_levels(flat, swing_length=2).is_empty()
    assert liquidity.sweeps(flat, swing_length=2).is_empty()


def test_equal_highs():
    o = bars(EQ + [SWEEP])
    t = o["open_time"].to_list()
    hour = t[1] - t[0]
    ev = liquidity.equal_levels(o, swing_length=2, tolerance_atr=0.1, atr_length=3)
    assert ev["kind"].to_list() == ["eqh"]
    row = ev.row(0, named=True)
    assert row["event_time"] == t[6] and row["known_at"] == t[8] + hour
    assert (row["price_low"], row["price_high"]) == (11.95, 12.0)
    assert row["invalidated_at"] == t[9] + hour
    attrs = json.loads(row["attrs"])
    assert attrs["count"] == 2 and attrs["swing_indices"] == [2, 6]


def test_equal_highs_rejected():
    o = bars(EQ)
    # dung sai quá chặt: 0.01 × ATR (~1.2) < 0.05
    assert liquidity.equal_levels(o, swing_length=2, tolerance_atr=0.01, atr_length=3).is_empty()
    # swing_length 1: nến 4 nằm giữa hai đỉnh và vượt 12 → mức đã bị lấy, không còn equal
    # highs (đỉnh 12.5 ở nến 4 cách hai đỉnh kia quá dung sai).
    assert not liquidity.equal_levels(o, swing_length=1, atr_length=3).filter(kind="eqh").is_empty()
    broken = list(EQ)
    broken[4] = (10.2, 12.5, 9.6, 9.8)
    eq = liquidity.equal_levels(bars(broken), swing_length=1, atr_length=3)
    assert eq.filter(kind="eqh").is_empty()


def test_sweep_same_bar():
    o = bars(EQ + [SWEEP])
    t = o["open_time"].to_list()
    ev = liquidity.sweeps(o, swing_length=2)
    assert ev["kind"].to_list() == ["sweep_bsl", "sweep_bsl"]
    assert set(ev["event_time"]) == {t[9]}
    assert set(ev["known_at"]) == {t[10 - 1] + (t[1] - t[0])}
    levels = sorted(json.loads(a)["level"] for a in ev["attrs"])
    assert levels == [11.95, 12.0]
    assert set(ev["price_high"]) == {12.2}


def test_breakout_is_not_sweep_unless_back_within_n():
    o = bars(EQ + [BREAKOUT, (12.3, 12.35, 11.5, 11.8)])
    t = o["open_time"].to_list()
    assert liquidity.sweeps(o, swing_length=2, max_bars=1).filter(kind="sweep_bsl").is_empty()
    ev = liquidity.sweeps(o, swing_length=2, max_bars=2).filter(kind="sweep_bsl")
    assert ev.height == 2
    assert set(ev["event_time"]) == {t[9]}
    assert set(ev["known_at"]) == {t[10] + (t[1] - t[0])}
    assert {json.loads(a)["bars"] for a in ev["attrs"]} == {2}
    with pytest.raises(ValueError):
        liquidity.sweeps(o, max_bars=0)


def test_ssl_sweep():
    o = bars(EQ[:7] + [(11.2, 11.5, 9.4, 10.0)])  # wick dưới 9.6, đóng trên
    ev = liquidity.sweeps(o, swing_length=2)
    assert ev["kind"].to_list() == ["sweep_ssl"]
    assert (ev["price_low"][0], ev["price_high"][0]) == (9.4, 9.6)


@pytest.mark.parametrize(
    "fn",
    [
        lambda x: liquidity.liquidity_levels(x, 5),
        lambda x: liquidity.equal_levels(x, 3, tolerance_atr=0.5),
        lambda x: liquidity.sweeps(x, 5),
        lambda x: liquidity.sweeps(x, 3, max_bars=3),
    ],
)
def test_liquidity_no_lookahead(fn):
    o = random_walk(300)
    assert not fn(o).is_empty()
    assert_no_lookahead(fn, o, [40, 120, 121, 250])
