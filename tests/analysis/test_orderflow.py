import json
from datetime import timedelta

import numpy as np
import polars as pl
import pytest

from rinng.analysis.orderflow import (
    absorption,
    delta_features,
    diagonal_imbalances,
    footprint,
    stacked_imbalances,
    trade_bars,
)
from rinng.analysis.testing import assert_no_lookahead
from rinng.store.schemas import TRADES, conform
from tests.analysis.helpers import T0, make_ohlcv, random_walk

M = timedelta(minutes=1)


def _trades(times, prices, qtys, maker):
    n = len(times)
    return conform(
        pl.DataFrame(
            {
                "exchange": "binance",
                "symbol": "BTC-USDT-PERP",
                "trade_id": list(range(n)),
                "time": times,
                "price": prices,
                "qty": qtys,
                "is_buyer_maker": maker,
            }
        ),
        TRADES,
    )


def _synthetic(n_bars=300, per_bar=40, seed=3):
    """Trades giả và nến 1m dựng từ chính các trades đó (nhất quán)."""
    rng = np.random.default_rng(seed)
    n = n_bars * per_bar
    offsets = np.sort(rng.integers(0, n_bars * 60_000, n))
    times = [T0 + timedelta(milliseconds=int(x)) for x in offsets]
    prices = np.round(100 * np.exp(np.cumsum(rng.normal(0, 0.0005, n))), 2)
    qtys = np.round(rng.exponential(1.0, n), 3)
    maker = rng.random(n) < 0.5
    trades = _trades(times, prices.tolist(), qtys.tolist(), maker.tolist())
    agg = (
        trades.group_by(pl.col("time").dt.truncate("1m").alias("open_time"))
        .agg(
            pl.col("price").first().alias("open"),
            pl.col("price").max().alias("high"),
            pl.col("price").min().alias("low"),
            pl.col("price").last().alias("close"),
            pl.col("qty").sum().alias("volume"),
            pl.col("qty").filter(~pl.col("is_buyer_maker")).sum().alias("taker_buy"),
        )
        .sort("open_time")
    )
    assert agg.height == n_bars  # mỗi phút đều có trade
    ohlcv = make_ohlcv(
        agg["close"].to_list(),
        opens=agg["open"].to_list(),
        highs=agg["high"].to_list(),
        lows=agg["low"].to_list(),
        volumes=agg["volume"].to_list(),
        taker_buy=agg["taker_buy"].to_list(),
        timeframe="1m",
    )
    return trades, ohlcv


def test_delta_features_by_hand():
    o = make_ohlcv(
        [1.0, 2.0, 3.0, 4.0],
        volumes=[10.0, 20.0, 30.0, 0.0001],
        taker_buy=[7.0, 5.0, 15.0, 0.00005],
    )
    f = delta_features(o)
    assert f["delta"].to_list() == pytest.approx([4, -10, 0, 0])
    assert f["cvd"].to_list() == pytest.approx([4, -6, -6, -6])
    assert f["delta_pct"].to_list()[:3] == pytest.approx([0.4, -0.5, 0])
    assert f["known_at"][0] == o["open_time"][0] + timedelta(hours=1)


def test_cvd_reset_day():
    o = make_ohlcv([1.0] * 30, volumes=[10.0] * 30, taker_buy=[6.0] * 30)  # delta = 2 mỗi nến
    f = delta_features(o, cvd_reset="day")
    assert f["cvd"][23] == 48 and f["cvd"][24] == 2 and f["cvd"][29] == 12
    assert delta_features(o)["cvd"][29] == 60
    with pytest.raises(ValueError):
        delta_features(o, cvd_reset="month")


def test_delta_from_bars_matches_trades():
    trades, o = _synthetic()
    from_bars = delta_features(o).select("open_time", "delta")
    from_trades = trade_bars(trades, "1m")
    joined = from_bars.join(from_trades, on="open_time", how="inner", suffix="_t")
    assert joined.height == o.height
    np.testing.assert_allclose(joined["delta"], joined["delta_t"], atol=1e-9)
    np.testing.assert_allclose(from_trades["volume"], o["volume"], atol=1e-9)
    assert from_trades["n_trades"].sum() == trades.height


def _hand_fp_trades():
    # Nến 0 (bin 1): mức 100: mua 1 bán 2; 101: mua 9 bán 1; 102: mua 4 bán .5; 103: mua 6 bán 1
    # Nến 1: mức 200: mua 9 bán 1; 201: mua 9 bán 1 (chỉ 1 mức buy imbalance → không stacked)
    book = [
        (0, 100.5, 1, False), (0, 100.5, 2, True),
        (0, 101.5, 9, False), (0, 101.5, 1, True),
        (0, 102.5, 4, False), (0, 102.5, 0.5, True),
        (0, 103.5, 6, False), (0, 103.5, 1, True),
        (1, 200.5, 9, False), (1, 200.5, 1, True),
        (1, 201.5, 9, False), (1, 201.5, 1, True),
    ]  # fmt: skip
    times = [T0 + bar * M + timedelta(seconds=i) for i, (bar, *_) in enumerate(book)]
    return _trades(times, [b[1] for b in book], [float(b[2]) for b in book], [b[3] for b in book])


def test_footprint_and_diagonal_imbalance():
    fp = footprint(_hand_fp_trades(), "1m", 1.0)
    assert fp.columns == ["open_time", "price_bin", "buy_volume", "sell_volume", "delta"]
    bar0 = fp.filter(pl.col("open_time") == T0)
    assert bar0["price_bin"].to_list() == [100, 101, 102, 103]
    assert bar0["delta"].to_list() == [-1, 8, 3.5, 5]
    imb = diagonal_imbalances(fp, 1.0)
    b0 = imb.filter(pl.col("open_time") == T0)
    # ask(101)=9 >= 3*bid(100)=6; ask(102)=4 >= 3*1; ask(103)=6 >= 3*0.5; mức 100 thấp nhất
    assert b0["buy_imbalance"].to_list() == [False, True, True, True]
    assert not b0["sell_imbalance"].any()
    # ratio 4.5: ask(102)=4 < 4.5*1 → không; ask(101)=9 >= 4.5*2 vẫn có (so sánh >=)
    strict = diagonal_imbalances(fp, 1.0, ratio=4.5).filter(pl.col("open_time") == T0)
    assert strict["buy_imbalance"].to_list() == [False, True, False, True]


def test_stacked_imbalance_events():
    ev = stacked_imbalances(_hand_fp_trades(), "1m", 1.0)
    assert ev.height == 1
    row = ev.row(0, named=True)
    assert (row["kind"], row["price_low"], row["price_high"]) == ("stacked_imbalance", 101, 104)
    assert row["event_time"] == T0 and row["known_at"] == T0 + M
    assert json.loads(row["attrs"]) == {"side": "buy", "levels": 3}
    # nến 1 chỉ có một mức imbalance (mức 200 thấp nhất không được so)
    assert stacked_imbalances(_hand_fp_trades(), "1m", 1.0, min_stack=1).height == 2


def test_absorption_by_hand():
    n = 8
    highs = [102.0] * n
    lows = [100.0] * n
    highs[6], lows[6] = 101.2, 100.8  # biên 0.4 so với ATR 2
    vols = [10.0] * n
    vols[6] = 50.0
    buy = [5.0] * n
    buy[6] = 40.0
    o = make_ohlcv([101.0] * n, highs=highs, lows=lows, volumes=vols, taker_buy=buy)
    ev = absorption(o, window=5)
    assert ev["event_time"].to_list() == [o["open_time"][6]]
    attrs = json.loads(ev["attrs"][0])
    assert attrs["side"] == "buy" and attrs["delta"] == 30
    assert attrs["volume_ratio"] == pytest.approx(5.0)
    assert attrs["range_atr"] == pytest.approx(0.2)
    assert absorption(o, window=5, range_frac=0.1).is_empty()


def test_absorption_with_trades_delta():
    trades, o = _synthetic(120)
    a = absorption(o, window=10, volume_mult=1.2, range_frac=1.0)
    b = absorption(o, window=10, volume_mult=1.2, range_frac=1.0, trades=trades)
    assert a.height > 0
    assert a["event_time"].to_list() == b["event_time"].to_list()
    da = [json.loads(x)["delta"] for x in a["attrs"]]
    db = [json.loads(x)["delta"] for x in b["attrs"]]
    np.testing.assert_allclose(da, db, atol=1e-9)


def test_no_lookahead_candle_functions():
    o = random_walk(400)
    for reset in (None, "day", "week"):
        assert_no_lookahead(lambda x, r=reset: delta_features(x, cvd_reset=r), o, [10, 24, 199])
    compute = lambda x: absorption(x, window=10, volume_mult=1.3, range_frac=0.9)
    assert compute(o).height > 0
    assert_no_lookahead(compute, o, [15, 100, 250, 399])


def test_no_lookahead_trade_functions():
    trades, o = _synthetic(200)

    def upto(x):
        return trades.filter(pl.col("time") < x["open_time"][-1] + M)

    stacked = lambda x: stacked_imbalances(upto(x), "1m", 0.01, ratio=2.0)
    assert stacked(o).height > 0
    assert_no_lookahead(stacked, o, [20, 77, 150])
    absorb = lambda x: absorption(x, window=10, volume_mult=1.2, range_frac=1.0, trades=upto(x))
    assert_no_lookahead(absorb, o, [20, 77, 150])
