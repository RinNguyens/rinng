"""Read-only TrustTrade run views behind /api/trusttrade (rinng.web.trusttrade)."""

import json

import pytest

from rinng.service import NotFound
from rinng.web import trusttrade as tt

SYM = "BTC-USDT-PERP"


def _run(root, name, *, blind=False):
    d = root / name
    d.mkdir(parents=True)
    (d / "config.json").write_text(
        json.dumps({"symbols": [SYM], "start": "2026-09-22", "end": "2026-09-23", "blind": blind})
    )
    (d / "metrics.json").write_text(
        json.dumps(
            {
                "average": {"trusttrade": {"cr_pct": 1.0, "mdd_pct": 0.5, "sharpe": 1.2}},
                "per_symbol": {SYM: {"trusttrade": {"days": 2, "cr_pct": 1.0}}},
                "usage": {"total": {"cost_usd": 0.5, "calls": 4}},
            }
        )
    )
    day = (lambda i: f"D+{i}") if blind else (lambda i: f"2026-09-{22 + i}")
    (d / f"equity_{SYM}.csv").write_text(
        f"day,trusttrade,buy_hold\n{day(0)},10000,10000\n{day(1)},10100,9900\n"
    )
    dec = [
        {"symbol": SYM, "day": day(i), "strategy": s, "price": 100.0, "equity": 1e4,
         "exposure": e, "action": a, "pct": p, "confidence": 60}
        for i, (a, p, e) in enumerate([("BUY", 50, 0.5), ("HOLD", 0, 0.5)])
        for s in ("trusttrade", "buy_hold")
    ]  # fmt: skip
    (d / "decisions.jsonl").write_text("\n".join(json.dumps(x) for x in dec))
    con = {"symbol": SYM, "day": day(1), "domain": "market", "n_agents": 3, "kept_share": 0.8,
           "high": [], "low": [], "leaked": []}  # fmt: skip
    (d / "consensus.jsonl").write_text(json.dumps(con))
    rep = [
        {"symbol": SYM, "day": day(1), "domain": "market", "agent": k, "summary": "",
         "stance": st, "confidence": 50, "claims": []}
        for k, st in enumerate(["bullish", "bullish", "bearish"])
    ]  # fmt: skip
    (d / "reports.jsonl").write_text("\n".join(json.dumps(x) for x in rep))
    return d


def test_runs_lists_finished_runs_with_length_and_cost(tmp_path):
    _run(tmp_path, "a")
    (tmp_path / "unfinished").mkdir()
    [r] = tt.runs(tmp_path)
    assert (r["name"], r["days"], r["cost_usd"], r["calls"]) == ("a", 2, 0.5, 4)
    assert r["average"]["trusttrade"]["cr_pct"] == 1.0


def test_run_detail_equity_behaviour_and_agreement(tmp_path):
    _run(tmp_path, "a")
    r = tt.run(tmp_path, "a")
    assert r["equity"][SYM] == {
        "days": ["2026-09-22", "2026-09-23"],
        "series": {"trusttrade": [10000.0, 10100.0], "buy_hold": [10000.0, 9900.0]},
    }
    b = r["behaviour"]["trusttrade"]
    assert (b["buy"], b["hold"], b["hold_pct"], b["in_market_pct"]) == (1, 1, 50.0, 100.0)
    assert "buy_hold" not in r["behaviour"]  # baselines are not LLM traders
    a = r["agreement"]["market"]
    assert (a["unanimous_pct"], a["split_pct"]) == (0.0, 100.0)


def test_blind_days_map_back_to_calendar_dates(tmp_path):
    _run(tmp_path, "b", blind=True)
    rows = tt.decisions(tmp_path, "b", SYM, "trusttrade")
    assert [(x["day"], x["label"]) for x in rows] == [("2026-09-22", "D+0"), ("2026-09-23", "D+1")]
    assert tt.run(tmp_path, "b")["equity"][SYM]["days"] == ["2026-09-22", "2026-09-23"]
    d = tt.day(tmp_path, "b", SYM, "2026-09-23")
    assert len(d["decisions"]) == 2 and len(d["consensus"]) == 1 and len(d["reports"]) == 3
    assert {x["label"] for x in d["reports"]} == {"D+1"}


def test_nan_metrics_are_read_as_null(tmp_path):
    d = _run(tmp_path, "a")
    m = d / "metrics.json"
    m.write_text(m.read_text().replace('"sharpe": 1.2', '"sharpe": NaN'))
    assert tt.run(tmp_path, "a")["average"]["trusttrade"]["sharpe"] is None
    assert tt.runs(tmp_path)[0]["average"]["trusttrade"]["sharpe"] is None


@pytest.mark.parametrize("name", ["missing", "../a", "a/../a", ""])
def test_unknown_or_unsafe_names_are_not_found(tmp_path, name):
    _run(tmp_path, "a")
    with pytest.raises(NotFound):
        tt.run(tmp_path, name)
