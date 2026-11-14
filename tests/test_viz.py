import polars as pl

from rinng.analysis.structure import swings
from rinng.analysis.types import events_frame
from rinng.viz.chart import candles, equity
from tests.analysis.helpers import random_walk


def test_candles_with_events_panels_and_profile():
    o = random_walk(200)
    ev = swings(o, 5)
    t = o["open_time"].to_list()
    zone = events_frame(
        [
            {
                "kind": "fvg_bull",
                "event_time": t[10],
                "known_at": t[12],
                "price_low": 99.0,
                "price_high": 100.0,
                "invalidated_at": t[40],
            },
            {
                "kind": "vpoc",
                "event_time": t[20],
                "known_at": t[30],
                "price_low": 101.0,
                "price_high": 101.0,
            },
        ],
        symbol="BTC-USDT-PERP",
        timeframe="1h",
        phash="x",
    )
    panel = o.select("open_time", pl.col("close").rolling_mean(10).alias("sma10"))
    profile = pl.DataFrame(
        {"price_low": [99.0, 100.0], "price_high": [100.0, 101.0], "volume": [5.0, 9.0]}
    )
    fig = candles(o, events=pl.concat([ev, zone]), panels={"SMA": panel}, profile=profile)
    shapes = [s.type for s in fig.layout.shapes]
    assert shapes.count("rect") == 1
    assert shapes.count("line") == 1
    names = [tr.name for tr in fig.data]
    assert {"price", "swing", "sma10", "volume profile"} <= set(names)


def test_candles_kind_filter_and_equity():
    o = random_walk(100)
    fig = candles(o, events=swings(o, 3), kinds=["swing_low"])
    assert all(tr.name != "swing" or len(tr.x) > 0 for tr in fig.data)
    eq = pl.DataFrame({"time": o["open_time"], "equity": [1.0] * o.height})
    assert len(equity(eq, {"buy&hold": eq}).data) == 2
