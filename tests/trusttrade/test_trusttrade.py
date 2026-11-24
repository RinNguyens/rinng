import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from rinng.trusttrade import agents, consensus, data, memory, sim, temporal
from rinng.trusttrade import run as tr
from rinng.trusttrade.consensus import Claim


def candles(closes, start=datetime(2025, 1, 1, tzinfo=UTC)):
    c = np.asarray(closes, dtype=float)
    n = len(c)
    return pl.DataFrame(
        {
            "exchange": ["binance"] * n,
            "symbol": ["BTC-USDT-PERP"] * n,
            "timeframe": ["1d"] * n,
            "open_time": [start + timedelta(days=i) for i in range(n)],
            "open": np.concatenate([[c[0]], c[:-1]]),
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": np.full(n, 100.0),
            "taker_buy_volume": np.full(n, 55.0),
        }
    ).with_columns(pl.col("open_time").cast(pl.Datetime("ms", "UTC")))


# --------------------------------------------------------------------------- temporal


def test_temporal_uptrend_recommends_buy():
    rng = np.random.default_rng(0)
    closes = 100 * np.exp(np.cumsum(0.01 + 0.005 * rng.standard_normal(400)))
    ts = temporal.compute(candles(closes))
    assert ts.direction == "up"
    assert ts.action == "BUY" and ts.pct > 0
    assert {h.days for h in ts.horizons} == set(temporal.HORIZONS)
    assert "uptrend" in (next(h for h in ts.horizons if h.days == 28).trend or "")
    assert "| Next-day prediction | UP" in ts.table()


def test_temporal_downtrend_sells_only_when_holding():
    closes = 100 * np.exp(np.cumsum(np.full(120, -0.01)))
    assert temporal.compute(candles(closes), holding=False).action == "HOLD"
    held = temporal.compute(candles(closes), holding=True)
    assert held.direction == "down" and held.action == "SELL"


def test_temporal_magnitude_is_bounded():
    rng = np.random.default_rng(1)
    closes = 100 * np.exp(np.cumsum(0.03 * rng.standard_normal(200)))
    ts = temporal.compute(candles(closes))
    vol14 = next(h.vol for h in ts.horizons if h.days == 14)
    assert abs(ts.magnitude) <= 1.5 * vol14 + 1e-12


def test_trend_z_sign():
    assert temporal.trend_z(np.linspace(100, 120, 30), 0.01) > 1
    assert temporal.trend_z(np.linspace(120, 100, 30), 0.01) < -1


# --------------------------------------------------------------------------- consensus


def claim(agent, subject, predicate, polarity="bullish", value=None, date=None):
    return Claim(agent, "market", subject, predicate, polarity, value, None, date)


def test_consensus_keeps_agreement_and_drops_singletons():
    claims = [
        claim(0, "moving_averages", "close above the 50-day EMA"),
        claim(1, "moving_averages", "price closed above 50-day EMA"),
        claim(2, "moving_averages", "close holding above the 50 day EMA"),
        claim(0, "rsi", "RSI near overbought", "bearish", 71.0),
        claim(1, "volume", "volume spike on the last candle", "neutral"),
    ]
    res = consensus.score(claims, 3, "market")
    assert len(res.high) == 1
    g = res.high[0]
    assert g.agents == 3 and g.support == 1.0 and g.polarity == "bullish"
    assert sum(len(x.claims) for x in res.low) == 2
    assert "3/3 analysts" in res.evidence()
    assert res.kept_share == pytest.approx(3 / 5)


def test_consensus_opposite_polarity_never_joins():
    claims = [
        claim(0, "trend", "daily trend is up", "bullish"),
        claim(1, "trend", "daily trend is up", "bearish"),
    ]
    res = consensus.score(claims, 2, "market")
    assert not res.high


def test_consensus_numeric_disagreement_lowers_similarity():
    p = consensus.Params()
    a = claim(0, "rsi", "RSI level", "neutral", 50.0)
    b = claim(1, "rsi", "RSI level", "neutral", 51.0)
    c = claim(1, "rsi", "RSI level", "neutral", 90.0)
    v = consensus.tfidf([consensus.tokens(x.predicate) for x in (a, b, c)])
    assert consensus.similarity(a, b, v[0], v[1], p) > consensus.similarity(a, c, v[0], v[2], p)


def test_consensus_same_agent_does_not_build_support():
    claims = [claim(0, "trend", "uptrend intact"), claim(0, "trend", "uptrend intact")]
    res = consensus.score(claims, 3, "market")
    assert not res.high


def test_consensus_flags_future_dated_claims():
    claims = [
        claim(0, "price_action", "big green candle", date="2026-01-05"),
        claim(1, "price_action", "big green candle", date="2026-01-03"),
    ]
    res = consensus.score(claims, 2, "market", as_of="2026-01-04")
    assert len(res.leaked) == 1 and res.leaked[0].agent == 0


# --------------------------------------------------------------------------- memory


def test_memory_backfills_only_after_horizon():
    bank = memory.MemoryBank()
    prices = [100.0, 110.0]
    bank.add(memory.Record(0, "d0", "BUY", 100, 1.0, 100.0, 1000.0))
    bank.backfill(0, prices, [])
    assert bank.records[0].returns[1] is None
    bank.backfill(1, prices, [1000.0])
    assert bank.records[0].returns[1] == pytest.approx(1.0)  # 10 profit on 1000 = 1%
    assert bank.records[0].returns[7] is None


def test_memory_sharpe_and_slope():
    bank = memory.MemoryBank()
    prices = [100.0 + i for i in range(20)]
    equity = [1000.0 * (1 + 0.01 * i + 0.002 * (i % 2)) for i in range(20)]
    for i in range(10):
        bank.add(memory.Record(i, f"d{i}", "BUY", 25, 1.0 + i, prices[i], equity[i]))
    bank.backfill(19, prices, equity[:19])
    r0 = bank.records[0]
    assert r0.sharpe[7] is not None and r0.sharpe[7] > 0
    assert bank.records[-1].slope_r[1] is not None
    assert "Trend of performance" in bank.prompt_table(memory.SHORT)


# --------------------------------------------------------------------------- sim


def test_portfolio_partial_buy_sell_and_fees():
    pf = sim.Portfolio(cash=1000.0, fee=0.001)
    q = pf.execute("BUY", 50, 100.0)
    assert pf.cash == pytest.approx(500.0)
    assert q == pytest.approx(500 * 0.999 / 100)
    sold = pf.execute("SELL", 100, 110.0)
    assert sold == pytest.approx(-q) and pf.qty == pytest.approx(0)
    assert pf.trades == 2
    assert pf.execute("SELL", 50, 110.0) == 0.0  # nothing to sell


def test_metrics_drawdown_and_return():
    m = sim.metrics([110.0, 99.0, 121.0], 100.0)
    assert m["cr_pct"] == pytest.approx(21.0)
    assert m["mdd_pct"] == pytest.approx(10.0)


@pytest.mark.parametrize("name", sim.BASELINES)
def test_rule_positions_are_binary_and_causal(name):
    rng = np.random.default_rng(2)
    closes = 100 * np.exp(np.cumsum(0.02 * rng.standard_normal(150)))
    full = sim.rule_positions(candles(closes), name)
    part = sim.rule_positions(candles(closes[:100]), name)
    assert set(np.unique(full)) <= {0.0, 1.0}
    assert np.array_equal(full[:100], part)  # no look-ahead


# --------------------------------------------------------------------------- end to end


class FakeLLM:
    """Deterministic stand-in: bullish analysts, a trader that buys 25% then holds."""

    def __init__(self):
        self.calls = []

    async def structured(self, *, role, schema, prompt, sample=0, **_):
        self.calls.append((role, sample))
        if role.startswith("analyst"):
            domain = role.split(":")[1]
            subj = agents.SUBJECTS[domain][0]
            return schema.model_validate(
                {
                    "summary": "s",
                    "stance": "bullish",
                    "confidence": 60,
                    "claims": [
                        {
                            "subject": subj,
                            "predicate": "trend points higher",
                            "polarity": "bullish",
                            "value": None,
                            "unit": None,
                            "date": None,
                        },
                        {
                            "subject": agents.SUBJECTS[domain][sample + 1],
                            "predicate": ["long wick", "weekend gap", "doji print"][sample],
                            "polarity": "neutral",
                            "value": None,
                            "unit": None,
                            "date": None,
                        },
                    ],
                }
            )
        if role.startswith("reflect"):
            return schema.model_validate(
                {"strengths": "a", "weaknesses": "b", "recommendation": "c", "risk_posture": "keep"}
            )
        assert "Cross-checked" in prompt or "analyst report" in prompt
        return schema.model_validate(
            {"action": "BUY", "pct": 25, "confidence": 70, "rationale": "r", "key_evidence": ["e"]}
        )

    def usage_summary(self):
        return {
            "total": {
                "calls": len(self.calls),
                "cache_hits": 0,
                "errors": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            },
            "by_role": {},
        }


def symbol_data():
    rng = np.random.default_rng(3)
    closes = 100 * np.exp(np.cumsum(0.003 + 0.02 * rng.standard_normal(500)))
    d1 = candles(closes)
    t = d1["open_time"].to_list()
    fu = pl.DataFrame(
        {
            "time": [x + timedelta(hours=h) for x in t for h in (0, 8, 16)],
            "rate": [0.0001] * (3 * len(t)),
        }
    )
    oi = pl.DataFrame({"time": t, "oi_value": np.linspace(1e9, 2e9, len(t))})
    ls = pl.DataFrame(
        {"time": t, "ratio": np.linspace(1.5, 2.5, len(t)), "long_pct": [None] * len(t)}
    )
    return data.SymbolData("BTC-USDT-PERP", d1, fu, oi, ls, label="BTC-USDT-PERP")


def test_domain_builders_are_point_in_time():
    sd = symbol_data()
    t = datetime(2026, 1, 1, tzinfo=UTC)
    snap = sd.asof(t)
    assert snap.d1["open_time"].max() + timedelta(days=1) <= t
    m = data.market_domain(snap)
    assert m["last_10_days"][-1]["day"] == "2025-12-31"
    d = data.derivatives_domain(snap)
    assert set(d) >= {"funding", "open_interest", "long_short_global_accounts"}
    assert json.dumps(m) and json.dumps(d)


def test_blind_mode_hides_levels_and_dates():
    sd = data.blind(symbol_data(), datetime(2026, 1, 1, tzinfo=UTC))
    snap = sd.asof(datetime(2026, 1, 1, tzinfo=UTC))
    assert snap.d1["close"][-1] == pytest.approx(100.0)
    ref = datetime(2026, 1, 1, tzinfo=UTC)
    m = data.market_domain(snap, ref)
    assert m["asset"] == "ASSET" and m["last_10_days"][-1]["day"] == "D-1"
    assert "value_usd" not in data.derivatives_domain(snap, ref)["open_interest"]


def test_symbol_run_end_to_end(tmp_path):
    cfg = tr.RunConfig(
        symbols=["BTC-USDT-PERP"], start=date(2026, 1, 1), end=date(2026, 1, 5), n_agents=3
    )
    llm = FakeLLM()
    sd = symbol_data()
    run = tr.SymbolRun(cfg, llm, sd, tmp_path, None)
    bars = {r["open_time"]: r for r in sd.d1.iter_rows(named=True)}
    for t in tr.day_list(cfg.start, cfg.end):
        asyncio.run(run.step(t, bars[t]["open"], bars[t]["close"]))
    # analysts: 3 agents × 2 domains per day, shared by all variants
    assert sum(1 for r, _ in llm.calls if r.startswith("analyst")) == 5 * 6
    m = run.metrics()
    assert set(m) == set(cfg.variants) | set(cfg.baselines)
    assert all(v["days"] == 5 for v in m.values())
    assert m["trusttrade"]["trades"] == 5  # BUY 25% of free cash every day
    assert run.books["trusttrade"].mem.records[0].returns[1] is not None
    rows = [json.loads(x) for x in (tmp_path / "consensus.jsonl").read_text().splitlines()]
    assert rows and all(len(r["high"]) == 1 for r in rows)  # the shared bullish claim
    state = run.state()
    again = tr.SymbolRun(cfg, llm, sd, tmp_path, None)
    again.load_state(json.loads(json.dumps(state, default=str)))
    assert again.books["trusttrade"].mem.records[0].returns[1] is not None
    assert again.books["buy_hold"].equity == run.books["buy_hold"].equity


def test_estimate_counts_calls():
    cfg = tr.RunConfig(symbols=["A", "B"], start=date(2026, 1, 1), end=date(2026, 1, 10))
    est = tr.estimate(cfg, 10)
    assert est["calls"]["analyst"] == 2 * 10 * 3 * 2
    assert est["calls"]["trader"] == 2 * 10 * 5
    assert est["calls"]["reflect"] == 2 * 10 * 2


def test_fill_gaps_fetches_only_missing_days():
    d1 = candles(np.linspace(100, 110, 10))
    gap = d1["open_time"][4]
    calls = []

    def fill(symbol, start, end):
        calls.append((start, end))
        return d1.filter(pl.col("open_time") == gap).with_columns(is_closed=pl.lit(True))

    holed = d1.filter(pl.col("open_time") != gap).with_columns(is_closed=pl.lit(True))
    end = d1["open_time"][-1] + timedelta(days=1)
    out = data.fill_gaps(holed, "BTC-USDT-PERP", end, fill)
    assert out.height == 10 and out["open_time"].is_sorted()
    assert calls == [(gap, gap + timedelta(days=1))]
    assert data.fill_gaps(out, "BTC-USDT-PERP", end, fill).height == 10
    assert len(calls) == 1  # nothing missing → no fetch
