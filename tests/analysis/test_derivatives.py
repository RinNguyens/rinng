import json
from datetime import timedelta

import numpy as np
import polars as pl
import pytest

from rinng.analysis.derivatives import (
    basis_features,
    funding_features,
    gap_mask,
    liquidation_clusters,
    liquidation_features,
    long_short_features,
    open_interest_features,
)
from rinng.analysis.testing import assert_no_lookahead
from rinng.store.catalog import GAPS
from rinng.store.schemas import (
    FUNDING,
    LIQUIDATIONS,
    LONG_SHORT,
    MARK_PRICE,
    OPEN_INTEREST,
    conform,
)
from tests.analysis.helpers import T0, make_ohlcv, random_walk

H = timedelta(hours=1)
SYMBOL = "BTC-USDT-PERP"


def _frame(tbl, rows):
    base = {"exchange": "binance", "symbol": SYMBOL}
    return conform(pl.DataFrame([{**base, **r} for r in rows]), tbl)


def _gaps(*spans, dataset="open_interest", symbol=SYMBOL):
    rows = [
        {
            "exchange": "binance",
            "symbol": symbol,
            "dataset": dataset,
            "start": s,
            "end": e,
            "reason": "test",
            "recorded_at": e,
        }
        for s, e in spans
    ]
    return conform(pl.DataFrame(rows), GAPS)


# ---------------------------------------------------------------- funding


def test_funding_asof_uses_points_up_to_close_only():
    o = make_ohlcv([100.0] * 6)
    funding = _frame(
        FUNDING,
        [
            {"funding_time": T0 - 2 * H, "rate": 0.1, "mark_price": 1.0},
            {"funding_time": T0, "rate": 0.2, "mark_price": 1.0},
            {"funding_time": T0 + 2 * H, "rate": 0.3, "mark_price": 1.0},  # = close nến 1
            {"funding_time": T0 + 4.5 * H, "rate": 0.4, "mark_price": 1.0},  # giữa nến 4
            {"funding_time": T0 + 7 * H, "rate": 0.9, "mark_price": 1.0},  # sau nến cuối
        ],
    )
    f = funding_features(o, funding, z_window=3, sum_periods=2)
    assert f["funding_rate"].to_list() == [0.2, 0.3, 0.3, 0.3, 0.4, 0.4]
    assert f["funding_sum"].to_list() == pytest.approx([0.3, 0.5, 0.5, 0.5, 0.7, 0.7])
    # z-score trên chuỗi kỳ funding: [0.1, 0.2, 0.3] -> z của 0.3 = 1
    assert f["funding_z"][0] is None
    assert f["funding_z"][1] == pytest.approx(1.0)
    assert f["known_at"].to_list() == [T0 + (i + 1) * H for i in range(6)]


def test_funding_constant_rate_gives_null_z_and_gap_nulls():
    o = make_ohlcv([100.0] * 4)
    funding = _frame(
        FUNDING,
        [{"funding_time": T0 - i * H, "rate": 0.0001, "mark_price": 1.0} for i in range(5)],
    )
    gaps = _gaps((T0 + 2 * H, T0 + 2.5 * H), dataset="funding")
    f = funding_features(o, funding, z_window=3, sum_periods=2, gaps=gaps)
    assert f["funding_z"].null_count() == 4
    assert f["funding_rate"].to_list() == [0.0001, 0.0001, None, 0.0001]


# ---------------------------------------------------------------- open interest


def _oi_rows(values, source="api", offset=H):
    return [
        {"source": source, "time": T0 + i * H + offset, "oi_base": v, "oi_value": v * 100}
        for i, v in enumerate(values)
    ]


def test_price_oi_states():
    o = make_ohlcv([100.0, 101.0, 102.0, 101.0, 100.0, 100.0])
    oi = _frame(OPEN_INTEREST, _oi_rows([10.0, 11.0, 10.0, 11.0, 10.0, 11.0]))
    f = open_interest_features(o, oi, n=1)
    assert f["price_oi_state"].to_list() == [
        None,
        "long_build",
        "short_cover",
        "short_build",
        "long_liquidation",
        None,  # giá đứng yên
    ]
    assert f["oi_change_pct"][1] == pytest.approx(0.1)
    assert f["price_change_pct"][1] == pytest.approx(0.01)


def test_oi_asof_ignores_points_after_close_and_value_column():
    o = make_ohlcv([100.0, 100.0, 100.0])
    rows = _oi_rows([10.0, 20.0, 30.0]) + [
        {"source": "api", "time": T0 + 1.5 * H, "oi_base": 99.0, "oi_value": 1.0}
    ]
    oi = _frame(OPEN_INTEREST, rows)
    f = open_interest_features(o, oi, n=1)
    # điểm lúc 1h30 nằm trong nến 1 (close 2h) nhưng điểm 2h mới hơn và vẫn <= close
    assert f["oi"].to_list() == [10.0, 20.0, 30.0]
    f2 = open_interest_features(make_ohlcv([100.0, 100.0]), oi.filter(pl.col("oi_base") == 99.0))
    assert f2["oi"].to_list() == [None, 99.0]
    fv = open_interest_features(o, oi, n=1, value="oi_value")
    assert fv["oi"][0] == 1000.0


def test_oi_gap_nulls_level_and_change_window():
    o = make_ohlcv([100.0, 101.0, 102.0, 103.0, 104.0])
    oi = _frame(OPEN_INTEREST, _oi_rows([10.0, 11.0, 12.0, 13.0, 14.0]))
    gaps = pl.concat(
        [
            _gaps((T0 + 2 * H + timedelta(minutes=10), T0 + 2 * H + timedelta(minutes=20))),
            _gaps((T0, T0 + 5 * H), dataset="funding"),  # dataset khác: bỏ qua
            _gaps((T0, T0 + 5 * H), symbol="ETH-USDT-PERP"),  # symbol khác: bỏ qua
        ]
    )
    f = open_interest_features(o, oi, n=1, gaps=gaps)
    assert f["oi"].to_list() == [10.0, 11.0, None, 13.0, 14.0]
    assert f["oi_change_pct"][1] is not None
    assert f["oi_change_pct"][2] is None and f["oi_change_pct"][3] is None
    assert f["oi_change_pct"][4] == pytest.approx(14 / 13 - 1)
    assert f["price_oi_state"][3] is None


def test_gap_mask_boundaries():
    o = make_ohlcv([1.0, 1.0, 1.0])
    # khoảng kết thúc đúng lúc mở nến 1 và bắt đầu đúng lúc đóng nến 1: không giao nến 1
    gaps = _gaps((T0 - H, T0 + H), (T0 + 2 * H, T0 + 3 * H))
    assert gap_mask(o, gaps, "open_interest").tolist() == [True, False, True]
    assert gap_mask(o, None, "open_interest").tolist() == [False] * 3


def test_oi_requires_source_when_ambiguous():
    o = make_ohlcv([100.0, 100.0])
    oi = _frame(OPEN_INTEREST, _oi_rows([1.0, 2.0]) + _oi_rows([5.0, 6.0], source="vision"))
    with pytest.raises(ValueError, match="source"):
        open_interest_features(o, oi)
    assert open_interest_features(o, oi, source="vision")["oi"].to_list() == [5.0, 6.0]


# ---------------------------------------------------------------- long/short


def test_long_short_ratio_and_z():
    o = make_ohlcv([100.0] * 4)
    rows = [
        {
            "source": "api",
            "kind": k,
            "time": T0 + (i + 1) * H,
            "ratio": r,
            "long_pct": 0.5,
            "short_pct": 0.5,
        }
        for k, ratios in (("global_account", [1.0, 2.0, 3.0, 3.0]), ("top_account", [9.0] * 4))
        for i, r in enumerate(ratios)
    ]
    ls = _frame(LONG_SHORT, rows)
    f = long_short_features(o, ls, z_window=3)
    assert f["ls_ratio"].to_list() == [1.0, 2.0, 3.0, 3.0]
    assert f["ls_ratio_z"][2] == pytest.approx(1.0)
    assert f["ls_ratio_z"][3] == pytest.approx((3 - 8 / 3) / np.std([2, 3, 3], ddof=1))
    assert long_short_features(o, ls, kind="top_account")["ls_ratio"][0] == 9.0


# ---------------------------------------------------------------- basis


def test_basis_premium_and_missing_index():
    o = make_ohlcv([100.0] * 3)
    mp = _frame(
        MARK_PRICE,
        [
            {"time": T0 + 0.5 * H, "mark_price": 101.0, "index_price": 100.0, "funding_rate": 0.0},
            {"time": T0 + 1.5 * H, "mark_price": 99.0, "index_price": None, "funding_rate": 0.0},
            {"time": T0 + 3 * H, "mark_price": 98.0, "index_price": 100.0, "funding_rate": 0.0},
        ],
    )
    f = basis_features(o, mp)
    assert f["premium"][0] == pytest.approx(0.01)
    assert f["premium"][1] is None
    assert f["premium"][2] == pytest.approx(-0.02)  # điểm đúng lúc đóng nến 2


# ---------------------------------------------------------------- liquidation


def _liq(rows):
    return _frame(LIQUIDATIONS, rows)


def test_liquidation_sums_per_bar():
    o = make_ohlcv([100.0] * 3)
    liq = _liq(
        [
            {"time": T0 + 0.1 * H, "side": "sell", "price": 100.0, "qty": 1.0},
            {"time": T0 + 0.2 * H, "side": "sell", "price": 90.0, "qty": 2.0},
            {"time": T0 + 0.3 * H, "side": "buy", "price": 101.0, "qty": 2.0},
            {"time": T0 + H, "side": "buy", "price": 50.0, "qty": 1.0},  # mở nến 1 -> nến 1
            {"time": T0 - H, "side": "buy", "price": 50.0, "qty": 1.0},  # trước nến đầu
            {"time": T0 + 3 * H, "side": "buy", "price": 50.0, "qty": 1.0},  # sau nến cuối
        ]
    )
    f = liquidation_features(o, liq)
    assert f["liq_long_qty"].to_list() == [3.0, 0.0, 0.0]
    assert f["liq_long_notional"].to_list() == [280.0, 0.0, 0.0]
    assert f["liq_short_qty"].to_list() == [2.0, 1.0, 0.0]
    assert f["liq_short_notional"].to_list() == [202.0, 50.0, 0.0]
    assert f["liq_notional"].to_list() == [482.0, 50.0, 0.0]
    gaps = _gaps((T0 + 2 * H, T0 + 3 * H), dataset="liquidations")
    assert liquidation_features(o, liq, gaps=gaps)["liq_notional"].to_list() == [482.0, 50.0, None]


def _liq_series(notionals):
    return _liq(
        [
            {
                "time": T0 + i * H + timedelta(minutes=5),
                "side": "sell",
                "price": 100.0,
                "qty": n / 100,
            }
            for i, n in enumerate(notionals)
        ]
    )


BASE = [1000.0, 1200.0, 900.0, 1100.0, 1000.0, 1300.0, 800.0, 1000.0, 1100.0, 900.0] * 3


def test_liquidation_cluster_z_and_quantile():
    notionals = BASE.copy()
    notionals[25] = 20000.0
    o = make_ohlcv([100.0] * len(notionals))
    liq = _liq_series(notionals)
    ev = liquidation_clusters(o, liq, window=10, z_min=3.0)
    assert ev.height == 1
    row = ev.row(0, named=True)
    assert row["kind"] == "liquidation_cluster"
    assert row["event_time"] == T0 + 25 * H
    assert row["known_at"] == T0 + 26 * H
    attrs = json.loads(row["attrs"])
    assert attrs["notional"] == pytest.approx(20000.0)
    assert attrs["long_notional"] == pytest.approx(20000.0) and attrs["method"] == "z"
    # phân vị 0.99 của 10 nến trước: chỉ vượt khi notional lớn hơn gần như mọi nến trước
    evq = liquidation_clusters(o, liq, window=10, quantile=0.99)
    hours = [(t - T0) // H for t in evq["event_time"].to_list()]
    assert 25 in hours and 26 not in hours
    assert (
        json.loads(evq.filter(pl.col("event_time") == T0 + 25 * H)["attrs"][0])["method"]
        == "quantile"
    )


def test_liquidation_cluster_none_without_spike_and_in_gap():
    o = make_ohlcv([100.0] * len(BASE))
    assert liquidation_clusters(o, _liq_series(BASE), window=10, z_min=3.0).is_empty()
    notionals = BASE.copy()
    notionals[25] = 20000.0
    gaps = _gaps((T0 + 20 * H, T0 + 20.5 * H), dataset="liquidations")
    ev = liquidation_clusters(o, _liq_series(notionals), window=10, gaps=gaps)
    assert ev.is_empty()  # cửa sổ 10 nến trước nến 25 chứa khoảng trống


# ---------------------------------------------------------------- chống nhìn trước


def test_derivatives_no_lookahead():
    o = random_walk(200)
    rng = np.random.default_rng(3)
    span = 210
    minutes = [T0 + timedelta(minutes=int(m)) for m in np.sort(rng.integers(0, span * 60, 600))]
    funding = _frame(
        FUNDING,
        [
            {"funding_time": T0 + 8 * i * H, "rate": float(r), "mark_price": 1.0}
            for i, r in enumerate(rng.normal(0, 1e-4, span // 8))
        ],
    )
    oi = _frame(
        OPEN_INTEREST,
        [
            {"source": "api", "time": T0 + i * H / 2, "oi_base": float(v), "oi_value": float(v)}
            for i, v in enumerate(rng.uniform(90, 110, span * 2))
        ],
    )
    ls = _frame(
        LONG_SHORT,
        [
            {
                "source": "api",
                "kind": "global_account",
                "time": T0 + i * H / 4,
                "ratio": float(v),
                "long_pct": 0.5,
                "short_pct": 0.5,
            }
            for i, v in enumerate(rng.uniform(0.5, 2, span * 4))
        ],
    )
    mp = _frame(
        MARK_PRICE,
        [
            {"time": t, "mark_price": 100.0 + i % 3, "index_price": 100.0, "funding_rate": 0.0}
            for i, t in enumerate(minutes)
        ],
    )
    liq = _liq(
        [
            {
                "time": t,
                "side": "sell" if i % 2 else "buy",
                "price": 100.0,
                "qty": float(rng.exponential(1.0)) * (50 if i % 97 == 0 else 1),
            }
            for i, t in enumerate(minutes)
        ]
    )
    gaps = _gaps((T0 + 50 * H, T0 + 52 * H), dataset="open_interest")
    cuts = [30, 90, 91, 150]
    assert_no_lookahead(lambda x: funding_features(x, funding, z_window=10), o, cuts)
    assert_no_lookahead(lambda x: open_interest_features(x, oi, n=4, gaps=gaps), o, cuts)
    assert_no_lookahead(lambda x: long_short_features(x, ls, z_window=12), o, cuts)
    assert_no_lookahead(lambda x: basis_features(x, mp), o, cuts)
    assert_no_lookahead(lambda x: liquidation_features(x, liq), o, cuts)
    assert_no_lookahead(lambda x: liquidation_clusters(x, liq, window=20, z_min=2.0), o, cuts)
