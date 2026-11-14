import json

import pytest

from rinng.analysis import smc
from rinng.analysis.testing import assert_no_lookahead
from tests.analysis.helpers import make_ohlcv, random_walk


def bars(rows):
    """Nến từ danh sách (open, high, low, close)."""
    o, h, lo, c = (list(x) for x in zip(*rows, strict=True))
    return make_ohlcv(c, opens=o, highs=h, lows=lo)


# Swing length 2: swing high ở nến 2 (12) biết lúc đóng nến 4; swing low ở nến 4 (9.6)
# biết lúc đóng nến 6.
BASE = [
    (10.0, 10.5, 9.5, 10.0),  # 0
    (10.0, 11.0, 9.8, 10.8),  # 1
    (10.8, 12.0, 10.5, 11.0),  # 2  swing high 12
    (11.0, 11.2, 10.0, 10.2),  # 3
    (10.2, 10.5, 9.6, 9.8),  # 4  swing low 9.6, nến giảm cuối trước đợt tăng
]
# BOS lên ở nến 6 (close 13.2 > 12), CHoCH xuống ở nến 8 (close 9.2 < 9.6).
BREAK = BASE + [
    (9.8, 10.4, 9.7, 10.3),  # 5
    (10.3, 13.5, 10.2, 13.2),  # 6  displacement tăng, phá 12
    (13.2, 13.3, 12.5, 12.8),  # 7
    (12.8, 12.9, 9.0, 9.2),  # 8  phá 9.6
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
    # thân 0.6 không vượt 1.5 × ATR (~0.5)
    assert smc.displacement(bars(calm + [(10.1, 10.8, 10.0, 10.7)]), atr_length=3).is_empty()


def test_fvg_bull_and_full_fill():
    o = bars(
        [
            (10.0, 10.5, 9.5, 10.2),
            (10.2, 12.0, 10.1, 11.9),
            (11.9, 12.5, 11.0, 12.3),  # low 11 > high[0] 10.5
            (12.3, 12.4, 10.8, 11.0),  # chạm vùng nhưng chưa lấp hết
            (11.0, 11.2, 10.4, 10.6),  # low 10.4 <= 10.5: lấp hoàn toàn
        ]
    )
    t = o["open_time"].to_list()
    ev = smc.fair_value_gaps(o)
    assert ev.height == 1
    row = ev.row(0, named=True)
    assert row["kind"] == "fvg_bull"
    assert row["event_time"] == t[1] and row["known_at"] == t[3]
    assert (row["price_low"], row["price_high"]) == (10.5, 11.0)
    assert row["invalidated_at"] == t[4] + (t[1] - t[0])
    # chưa lấp nếu dừng trước nến 4
    assert smc.fair_value_gaps(o.head(4))["invalidated_at"][0] is None


def test_fvg_bear_and_none():
    o = bars([(12.0, 12.5, 11.5, 11.8), (11.8, 11.9, 10.0, 10.1), (10.1, 11.0, 9.8, 10.0)])
    ev = smc.fair_value_gaps(o)
    assert ev["kind"].to_list() == ["fvg_bear"]
    assert (ev["price_low"][0], ev["price_high"][0]) == (11.0, 11.5)
    overlap = bars([(10.0, 11.0, 9.5, 10.5), (10.5, 11.5, 10.0, 11.0), (11.0, 11.8, 10.9, 11.5)])
    assert smc.fair_value_gaps(overlap).is_empty()
    # lọc kích thước theo ATR
    assert smc.fair_value_gaps(o, min_size_atr=10.0, atr_length=2).is_empty()


def test_order_blocks_mitigation_and_breaker():
    o = bars(BREAK)
    t = o["open_time"].to_list()
    hour = t[1] - t[0]
    ev = smc.order_blocks(o, swing_length=2, atr_length=3)
    cols = ("kind", "event_time", "known_at", "price_low", "price_high", "invalidated_at")
    got = {r[0]: r for r in ev.select(cols).rows()}
    # Bull OB = nến giảm cuối (nến 4) trước BOS ở nến 6; bị đóng dưới 9.6 ở nến 8.
    assert got["ob_bull"] == ("ob_bull", t[4], t[6] + hour, 9.6, 10.5, t[8] + hour)
    assert got["ob_bull_mitigated"][1:3] == (t[8], t[8] + hour)
    # Breaker bear sinh ở nến 8, bị đóng lại trên 10.5 ở nến 9.
    assert got["breaker_bear"] == ("breaker_bear", t[8], t[8] + hour, 9.6, 10.5, t[9] + hour)
    # Bear OB = nến tăng cuối (nến 6) trước CHoCH ở nến 8; chạm lại ở nến 9 (high 11 >= 10.2).
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
        (10.3, 11.0, 10.2, 10.8),  # 6: L = 9.6 biết từ dòng này, H = 12
        (10.8, 11.5, 10.7, 11.4),  # 7
        (11.4, 11.5, 9.9, 10.2),  # 8
    ]
    f = smc.premium_discount(bars(rows), swing_length=2)
    assert f["pd_position"].to_list()[:6] == [None] * 6  # chưa có swing low
    assert f["pd_zone"][5] is None
    assert f["pd_range_high"][6] == 12.0 and f["pd_range_low"][6] == 9.6
    assert f["pd_equilibrium"][6] == pytest.approx(10.8)
    assert f["pd_position"][6] == pytest.approx(0.5)
    assert f["pd_zone"].to_list()[6:] == ["equilibrium", "premium", "discount"]
    assert f["pd_position"][7] == pytest.approx(0.75)
    assert f["pd_position"][8] == pytest.approx(0.25)
    wide = smc.premium_discount(bars(rows), swing_length=2, equilibrium_band=0.3)
    assert wide["pd_zone"].to_list()[6:] == ["equilibrium"] * 3
    # vượt dải thì cắt về 1
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
    ],
)
def test_smc_no_lookahead(fn):
    o = random_walk(300)
    assert not fn(o).is_empty()
    assert_no_lookahead(fn, o, [40, 120, 121, 250])
