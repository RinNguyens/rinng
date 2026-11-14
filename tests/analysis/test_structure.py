import json

import numpy as np
import pytest

from rinng.analysis.structure import pivots, swing_table, swings
from rinng.analysis.testing import assert_no_lookahead
from tests.analysis.helpers import make_ohlcv, random_walk


def test_pivots_basic_and_ties():
    v = np.array([1, 2, 5, 2, 1, 3, 3, 1, 0], dtype=float)
    assert pivots(v, 2, high=True).tolist() == [2, 5]  # đỉnh bằng nhau: chọn cái đầu
    assert pivots(v, 1, high=False).tolist() == [4]


def test_pivots_need_full_window():
    assert pivots(np.array([1.0, 3.0, 1.0]), 2, high=True).tolist() == []
    with pytest.raises(ValueError):
        pivots(np.array([1.0]), 0, high=True)


def test_swings_known_at_and_labels():
    #        0  1  2  3  4  5  6  7  8  9 10 11 12
    highs = [1, 2, 5, 3, 2, 3, 7, 4, 3, 4, 6, 4, 3]
    lows = [h - 1 for h in highs]
    o = make_ohlcv([h - 0.5 for h in highs], highs=highs, lows=lows, opens=[h - 0.5 for h in highs])
    ev = swings(o, length=2)
    table = swing_table(ev).filter(kind="swing_high")
    assert table["index"].to_list() == [2, 6, 10]
    assert table["label"].to_list() == [None, "HH", "LH"]
    first = ev.filter(kind="swing_high").row(0, named=True)
    times = o["open_time"].to_list()
    assert first["event_time"] == times[2]
    assert first["known_at"] == times[5]  # đóng của nến 4 = mở của nến 5
    assert json.loads(first["attrs"])["index"] == 2


def test_swings_no_lookahead():
    o = random_walk(300)
    assert_no_lookahead(lambda x: swings(x, 5), o, [50, 120, 121, 250])


def test_lookahead_checker_catches_cheating():
    from rinng.analysis.types import events_frame

    def cheat(x):
        # gán known_at bằng event_time cho swing cần nến tương lai: phải bị bắt
        ev = swings(x, 5)
        return ev.with_columns(known_at=ev["event_time"])

    with pytest.raises(AssertionError):
        assert_no_lookahead(cheat, random_walk(200), [60, 100, 150])
    assert events_frame([], symbol="x", timeframe="1h", phash="p").is_empty()
