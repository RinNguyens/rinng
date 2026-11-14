"""Rule-based agents (rinng.analysis.agents) and the 5m desk payload on synthetic candles."""

import numpy as np
import polars as pl
import pytest

from rinng.analysis import agents
from rinng.analysis.agents import Vote
from rinng.web import desk
from tests.analysis.helpers import make_ohlcv, random_walk


def trend(step: float, n: int = 900, buy_share: float = 0.5, noise: float = 0.02) -> pl.DataFrame:
    """5m candles moving one way by `step` per candle, with noise so ATR/RSI are non-zero."""
    rng = np.random.default_rng(3)
    closes = (100 + step * np.arange(n) + rng.normal(0, noise, n)).tolist()
    vol = [10.0] * n
    return make_ohlcv(closes, volumes=vol, taker_buy=[v * buy_share for v in vol], timeframe="5m")


def test_stance_needs_score_and_confidence():
    assert Vote("a", "A", 0.5, 0.6).stance == "buy"
    assert Vote("a", "A", -0.5, 0.6).stance == "sell"
    assert Vote("a", "A", 0.1, 0.9).stance == "wait"
    assert Vote("a", "A", 0.9, 0.0).stance == "wait"


def test_verdict_weights_votes_by_confidence():
    vs = [Vote("a", "A", 1.0, 0.9), Vote("b", "B", -1.0, 0.1), Vote("c", "C", 0.0, 0.0)]
    v = agents.verdict(vs)
    assert v["score"] == pytest.approx(0.8)
    assert v["lean"] == "long"
    assert (v["buy"], v["sell"], v["wait"], v["total"]) == (1, 1, 1, 3)
    assert agents.verdict([Vote("a", "A", 0.1, 0.5)])["lean"] == "none"
    assert agents.verdict([])["score"] == 0.0


def test_momentum_follows_the_trend():
    # Noise large enough that RSI stays out of overbought/oversold (where the agent scores the other
    # way).
    up = agents.momentum_agent(agents.snapshot(trend(+0.05, noise=0.25)))
    # The down series mirrors the up series so noise on the last candle does not skew MACD.
    mirror = [200 - c for c in trend(+0.05, noise=0.25)["close"].to_list()]
    down = agents.momentum_agent(agents.snapshot(make_ohlcv(mirror, timeframe="5m")))
    assert up.stance == "buy" and up.score > 0.3
    assert down.stance == "sell" and down.score < -0.3


def test_momentum_marks_a_stretched_rsi_against_the_trend():
    v = agents.momentum_agent(agents.snapshot(trend(-0.05)))
    assert any("stretched to the downside" in r for r in v.reasons)


def test_profile_reads_acceptance_outside_yesterdays_value():
    # Yesterday ranged around 100, today sits fully above/below that value area.
    flat = [100 + 0.2 * np.sin(i / 5) for i in range(288 * 2)]
    for level, sign in ((103.0, 1), (97.0, -1)):
        o = make_ohlcv(flat + [level] * 100, timeframe="5m")
        s = agents.snapshot(o)
        assert s.prev_day is not None
        v = agents.profile_agent(s)
        assert v.score * sign >= 0.5
        assert v.confidence == 0.5


def test_flow_reads_taker_side_and_degrades_without_it():
    bought = agents.flow_agent(agents.snapshot(trend(0.0, buy_share=0.8)))
    sold = agents.flow_agent(agents.snapshot(trend(0.0, buy_share=0.2)))
    assert bought.score > 0.3 and sold.score < -0.3
    # OKX: candles have no taker volume → delta is not read, low confidence.
    blind = trend(0.0).with_columns(pl.lit(None, dtype=pl.Float64).alias("taker_buy_volume"))
    v = agents.flow_agent(agents.snapshot(blind))
    assert v.score == 0.0 and v.confidence == pytest.approx(0.1)
    assert "No taker-side volume" in v.reasons[0]


def test_flow_uses_derivatives_when_given():
    derivs = {"funding": {"rate_pct": 0.05}, "oi": {"chg_24h": 4.0}}
    s = agents.snapshot(trend(0.0), derivs=derivs, price_chg_24h=-2.0)
    v = agents.flow_agent(s)
    assert v.confidence == pytest.approx(0.6)
    assert any("longs are crowded" in r for r in v.reasons)
    assert any("new shorts" in r for r in v.reasons)


def test_projection_waits_without_a_forecast():
    v = agents.projection_agent(agents.snapshot(trend(0.01)))
    assert v.stance == "wait" and v.confidence == 0.0


@pytest.mark.parametrize("seed", [1, 7, 21])
def test_scenarios_are_geometrically_sound(seed):
    s = agents.snapshot(random_walk(900, seed=seed, timeframe="5m"))
    vs = agents.votes(s)
    assert [v.id for v in vs] == [
        "structure",
        "liquidity",
        "profile",
        "momentum",
        "flow",
        "projection",
    ]
    assert all(-1 <= v.score <= 1 and 0 <= v.confidence <= 1 and v.reasons for v in vs)
    long, short = agents.scenarios(s, vs, agents.verdict(vs)["lean"])
    assert long["side"] == "long" and short["side"] == "short"
    assert long["stop"] < long["entry"] < long["target"]
    assert short["target"] < short["entry"] < short["stop"]
    assert long["entry"] <= s.close <= short["entry"]
    for sc in (long, short):
        assert sc["zone"][0] <= sc["zone"][1]
        assert sc["rr"] >= agents.MIN_REWARD - 1e-9
        assert 0 <= sc["favor"] <= len(vs)


def test_desk_payload_tags_every_overlay_with_a_layer():
    hist = random_walk(1500, seed=5, timeframe="5m")
    h1 = random_walk(24 * 30, seed=6, timeframe="1h")
    d = desk.build(hist, h1, None, "curated")
    assert len(d["candles"]) == desk.SHOWN
    assert d["forecast"]["horizon"] == 48
    for key in ("zones", "levels", "markers", "profiles", "lines"):
        assert all(item["layer"] in desk.LAYERS for item in d[key]), key
    assert {lv["layer"] for lv in d["levels"]} >= {"setups", "projection"}
    assert len(d["agents"]) == 6 and len(d["scenarios"]) == 2
    assert d["verdict"]["lean"] in {"long", "short", "none"}


def test_desk_works_before_there_is_enough_history_to_project():
    d = desk.build(random_walk(300, seed=2, timeframe="5m"), None, None, "live")
    assert "forecast" not in d and d["stats"] is None
    assert next(a for a in d["agents"] if a["id"] == "projection")["stance"] == "wait"
    assert all(sc["p_target"] is None for sc in d["scenarios"])
