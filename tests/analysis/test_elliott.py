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


def test_fib_score_ideal_impulse_scores_high():
    from rinng.analysis.elliott import fib_score

    # wave1 = 100, wave2 = 61.8, wave3 = 161.8, wave4 = 61.8 (0.382 of w3), wave5 = 100
    p0 = 1000.0
    p1 = p0 + 100
    p2 = p1 - 61.8
    p3 = p2 + 161.8
    p4 = p3 - 0.382 * 161.8
    p5 = p4 + 100
    s = fib_score([p0, p1, p2, p3, p4, p5])
    assert s["score"] > 0.95
    # Down impulse mirrors the same score.
    d = fib_score([2 * p0 - x for x in (p0, p1, p2, p3, p4, p5)])
    assert d["score"] == pytest.approx(s["score"])


def test_fib_score_off_ratios_scores_low():
    from rinng.analysis.elliott import fib_score

    # wave2 retraces 10%, wave3 barely longer than wave1, wave4 deep: valid rules, poor Fibonacci.
    s = fib_score([100, 200, 190, 300, 210, 260])
    assert s["score"] < 0.35


def test_best_impulses_drops_overlaps_keeps_best():
    import polars as pl

    from rinng.analysis.elliott import best_impulses

    good = [1000, 1100, 1038.2, 1200, 1138.2, 1238.2]
    rows = [
        {
            "kind": "impulse_candidate",
            "attrs": json.dumps(
                {"indices": [0, 2, 4, 6, 8, 10], "prices": good, "direction": "up"}
            ),
        },
        {
            "kind": "impulse_candidate",
            "attrs": json.dumps(
                {
                    "indices": [2, 4, 6, 8, 10, 12],
                    "prices": [100, 200, 190, 300, 210, 260],
                    "direction": "up",
                }
            ),
        },
        {
            "kind": "impulse_candidate",
            "attrs": json.dumps(
                {"indices": [10, 12, 14, 16, 18, 20], "prices": good, "direction": "up"}
            ),
        },
    ]
    kept = best_impulses(pl.DataFrame(rows), min_score=0.0)
    assert [k["attrs"]["indices"][0] for k in kept] == [0, 10]


def test_lens_zigzag_threshold_and_label_side():
    from rinng.web.lenses import zigzag_threshold

    assert zigzag_threshold("auto", "1w") == 0.12
    assert zigzag_threshold(None, "4h") == 0.05
    assert zigzag_threshold("8", "1w") == 0.08
    with pytest.raises(ValueError):
        zigzag_threshold("150", "1d")


def _piv(prices, running_last=False):
    out = []
    for k, p in enumerate(prices):
        kind = "H" if (k % 2 == 1) == (prices[1] > prices[0]) else "L"
        conf = None if running_last and k == len(prices) - 1 else k * 10 + 5
        out.append((k * 10, kind, float(p), conf))
    return out


def test_correction_after_zigzag_and_expanded_flat():
    from rinng.analysis.elliott import correction_after

    imp = [100, 200, 160, 360, 300, 400]
    idx = [0, 10, 20, 30, 40, 50]
    # A 400->300, B up to 362 (0.62 of A), C down to 200 (1.62 of A): textbook zigzag.
    z = correction_after(idx, _piv(imp + [300, 362, 200]))
    assert z["shape"] == "zigzag" and not z["tentative"] and z["score"] > 0.9
    assert z["direction"] == "down" and z["indices"] == [60, 70, 80]
    # B beyond P5 (1.3 of A): expanded flat; C still running -> tentative.
    f = correction_after(idx, _piv(imp + [300, 430, 280], running_last=True))
    assert f["shape"] == "expanded_flat" and f["tentative"]


def test_correction_after_rejects_and_needs_three_pivots():
    from rinng.analysis.elliott import correction_after

    imp = [100, 200, 160, 360, 300, 400]
    idx = [0, 10, 20, 30, 40, 50]
    forming = correction_after(idx, _piv(imp + [300, 362], running_last=True))  # no C yet
    assert forming["shape"] is None and forming["tentative"] and forming["prices"] == [300, 362]
    assert correction_after(idx, _piv(imp)) is None  # nothing after P5
    assert correction_after(idx, _piv(imp + [300, 600, 200])) is None  # B way past P5
    assert correction_after(idx, _piv(imp + [90, 150, 80])) is None  # A passes P0
    # C not beyond A's end yet: tentative even when confirmed.
    assert correction_after(idx, _piv(imp + [300, 362, 320]))["tentative"]


def test_pivots_running_appends_unconfirmed_extreme():
    from rinng.analysis.elliott import pivots

    o = _path([100, 120, 100, 110, 90], steps=4)
    conf = pivots(o, threshold=0.05)
    run = pivots(o, threshold=0.05, running=True)
    assert run[: len(conf)] == conf
    assert len(run) == len(conf) + 1 and run[-1][3] is None


def test_wyckoff_label_clusters_merge():
    from rinng.web.lenses import _merge_clusters

    ev = [
        {
            "time": t,
            "position": "belowBar",
            "shape": "circle",
            "color": "x",
            "text": "spring",
            "_i": i,
            "_px": px,
        }
        for t, i, px in [(1, 0, 50), (2, 3, 48), (3, 6, 49), (4, 40, 47)]
    ]
    out = _merge_clusters(ev, gap=10)
    assert sorted(m["text"] for m in out) == ["spring", "spring ×3"]
    merged = next(m for m in out if m["text"] == "spring ×3")
    assert merged["time"] == 2 and "_i" not in merged  # deepest bar of the run


def test_correction_after_spans_sub_swings():
    from rinng.analysis.elliott import correction_after

    imp = [100, 200, 160, 360, 300, 400]
    idx = [0, 10, 20, 30, 40, 50]
    # A=300, sub-swings 380/330, B=420 (highest before breaking 300), C runs to 210 via 350.
    piv = _piv(imp + [300, 380, 330, 420, 350, 390, 210], running_last=True)
    c = correction_after(idx, piv)
    assert c["prices"] == [300, 420, 210]
    assert c["shape"] == "expanded_flat" and c["tentative"]


def test_nested_windows_let_wave3_span_sub_swings():
    from rinng.analysis.elliott import nested_windows

    # 100 -> 120 -> 110 -> 150 -> 140 -> 170 -> 150 -> 200: wave 3 can be 110->150 or 110->170.
    piv = _piv([100, 120, 110, 150, 140, 170, 150, 200])
    seqs = {tuple(p[2] for p in w) for w in nested_windows(piv)}
    assert (100, 120, 110, 170, 150, 200) in seqs  # wave 3 spans 150/140
    assert (100, 120, 110, 150, 140, 170) in seqs  # consecutive window still there
    # A wave never contains a pivot beyond its start: 110 -> 150 -> 105 breaks it.
    bad = _piv([100, 120, 110, 150, 105, 170, 150, 200])
    assert all(w[2][2] != 110 or w[3][2] != 170 for w in nested_windows(bad))


def test_impulse_candidates_nested_has_unique_ids_and_no_lookahead():
    o = random_walk(400)
    ev = impulse_candidates(o, threshold=0.02, nested=True)
    assert ev["event_id"].n_unique() == ev.height
    assert ev.height >= impulse_candidates(o, threshold=0.02).height
    assert_no_lookahead(lambda x: impulse_candidates(x, threshold=0.02, nested=True), o, [150, 300])
