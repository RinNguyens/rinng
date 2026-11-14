"""Dự báo xác suất: không nhìn trước tương lai, phân vị hợp lệ, hiệu chỉnh trên random walk."""

import numpy as np
import pytest

from rinng.analysis import forecast as F
from tests.analysis.helpers import make_ohlcv


def _walk(n: int, seed: int = 1, vol: float = 0.01):
    rng = np.random.default_rng(seed)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0, vol, n))))
    opens = [closes[0]] + closes[:-1]
    noise = np.abs(rng.normal(0, vol / 3, n))
    highs = [max(o, c) * (1 + e) for o, c, e in zip(opens, closes, noise, strict=True)]
    lows = [min(o, c) * (1 - e) for o, c, e in zip(opens, closes, noise, strict=True)]
    volumes = list(rng.uniform(5, 15, n))
    return make_ohlcv(closes, opens=opens, highs=highs, lows=lows, volumes=volumes)


def test_no_lookahead():
    o = _walk(1200)
    origin, h = 1000, 24
    full = F.forecast_at(F.prepare(o), origin, h)
    cut = F.forecast(o.head(origin + 1), h)
    np.testing.assert_allclose(full.quantiles, cut.quantiles)
    np.testing.assert_allclose(full.weights, cut.weights)
    # walk_forward dùng quỹ đạo tính sẵn trên toàn bộ dữ liệu: phải cho cùng kết quả.
    fast = F.forecast_at(
        F.prepare(o), origin, h, paths=F.all_paths(F.prepare(o), h), last_only=True
    )
    np.testing.assert_allclose(fast.quantiles[:, -1], full.quantiles[:, -1])


def test_quantiles_are_ordered_and_widen():
    fc = F.forecast(_walk(1500), 30)
    q = fc.quantiles
    assert np.all(np.diff(q, axis=0) >= 0)  # 5% <= 10% <= ... <= 95% ở mọi bước
    width = q[-1] - q[0]
    assert width[-1] > width[0] * 2  # nón mở rộng theo thời gian


def test_touch_probability_is_monotone():
    fc = F.forecast(_walk(1500), 30)
    c = fc.close
    near, far = fc.touch_probability(c * 1.01), fc.touch_probability(c * 1.10)
    assert 0 <= far <= near <= 1
    assert fc.touch_probability(c * 0.99) >= fc.touch_probability(c * 0.90)


def test_not_enough_history():
    assert F.forecast(_walk(400), 30) is None


@pytest.mark.parametrize("seed", [2, 3])
def test_bands_are_calibrated_on_random_walk(seed):
    wf = F.walk_forward(_walk(4000, seed), 24, max_origins=200)
    assert abs(wf["coverage"][80] - 0.8) < 0.1
    assert abs(wf["coverage"][50] - 0.5) < 0.12
    # Không có gì để đoán: kỹ năng so với đối chứng phải xấp xỉ 0, không được "ảo".
    assert abs(wf["skill"]) < 0.05
