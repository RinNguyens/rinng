"""Read-only views over TrustTrade research runs (TrustTrade/runs/<name>/) for the /trusttrade page.

A run folder holds config.json, metrics.json, equity_<symbol>.csv and the decisions / consensus /
reports logs written by `rinng trusttrade backtest`. Nothing here calls the model or the exchange.
Blind runs log days as "D+n" and prices rebased to 100; days are mapped back to calendar dates
from the run's start so every run lines up on one time axis.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from rinng.service import NotFound

RUNS = Path(__file__).resolve().parents[3] / "TrustTrade" / "runs"
LLM_VARIANTS = ("single", "multi", "consensus", "consensus_temporal", "trusttrade")
NAME = re.compile(r"^[A-Za-z0-9._-]+$")
BLIND_DAY = re.compile(r"^D([+-]\d+)$")


def _loads(text: str):
    """JSON with NaN/Infinity (e.g. Sharpe of a strategy that never traded) read as null."""
    return json.loads(text, parse_constant=lambda _: None)


def _folder(root: Path, name: str) -> Path:
    d = root / name
    if not NAME.match(name) or not (d / "metrics.json").is_file():
        raise NotFound(f"no TrustTrade run named {name!r}")
    return d


def _day(label: str, start: date) -> str:
    m = BLIND_DAY.match(label)
    return (start + timedelta(days=int(m.group(1)))).isoformat() if m else label


def _jsonl(path: Path) -> list[dict]:
    return _jsonl_cached(path, path.stat().st_mtime_ns) if path.is_file() else []


@lru_cache(maxsize=16)
def _jsonl_cached(path: Path, _mtime: int) -> list[dict]:
    return [_loads(x) for x in path.read_text().splitlines() if x.strip()]


def _config(d: Path) -> dict:
    return _loads((d / "config.json").read_text())


def _start(cfg: dict) -> date:
    return date.fromisoformat(cfg["start"])


def runs(root: Path) -> list[dict]:
    """Every finished run, oldest first, with its config and the per-strategy averages."""
    out = []
    for m in sorted(root.glob("*/metrics.json"), key=lambda p: p.stat().st_mtime):
        d = m.parent
        if not (d / "config.json").is_file():
            continue
        cfg, met = _config(d), _loads(m.read_text())
        usage = met.get("usage", {}).get("total", {})
        days = max(
            (m.get("days", 0) for s in met.get("per_symbol", {}).values() for m in s.values()),
            default=0,
        )
        out.append(
            {
                "name": d.name,
                "start": cfg["start"],
                "end": cfg["end"],
                "days": days,
                "symbols": cfg["symbols"],
                "blind": cfg.get("blind", False),
                "analyst_models": cfg.get("analyst_models", []),
                "trader_model": cfg.get("trader_model"),
                "n_agents": cfg.get("n_agents"),
                "allocation": cfg.get("allocation"),
                "variants": cfg.get("variants", []),
                "baselines": cfg.get("baselines", []),
                "cost_usd": usage.get("cost_usd"),
                "calls": usage.get("calls"),
                "average": met.get("average", {}),
            }
        )
    return out


def _equity(d: Path, symbol: str, start: date) -> dict:
    f = d / f"equity_{symbol}.csv"
    if not f.is_file():
        return {"days": [], "series": {}}
    with f.open() as fh:
        rows = list(csv.DictReader(fh))
    cols = [c for c in (rows[0].keys() if rows else []) if c != "day"]
    return {
        "days": [_day(r["day"], start) for r in rows],
        "series": {c: [round(float(r[c]), 2) for r in rows] for c in cols},
    }


def _behaviour(decisions: list[dict]) -> dict:
    """Per LLM variant, pooled over symbols: actions, HOLD share, confidence, time in market."""
    by: dict[str, list[dict]] = defaultdict(list)
    for x in decisions:
        if x["strategy"] in LLM_VARIANTS:
            by[x["strategy"]].append(x)
    out = {}
    for v, rows in by.items():
        acts = Counter(r["action"] for r in rows)
        conf = [r["confidence"] for r in rows if r.get("confidence") is not None]
        n = len(rows)
        out[v] = {
            "days": n,
            "buy": acts["BUY"],
            "sell": acts["SELL"],
            "hold": acts["HOLD"],
            "hold_pct": round(100 * acts["HOLD"] / n, 1),
            "avg_confidence": round(sum(conf) / len(conf), 1) if conf else None,
            "in_market_pct": round(100 * sum(r["exposure"] > 0.01 for r in rows) / n, 1),
        }
    return out


def _agreement(reports: list[dict]) -> dict:
    """Per analyst domain: share of days where all analysts took the same stance, and the mix."""
    st: dict[tuple, list[str]] = defaultdict(list)
    for r in reports:
        st[(r["symbol"], r["day"], r["domain"])].append(r["stance"])
    out = {}
    for dom in sorted({k[2] for k in st}):
        groups = [v for k, v in st.items() if k[2] == dom and len(v) > 1]
        if not groups:
            continue
        out[dom] = {
            "days": len(groups),
            "unanimous_pct": round(100 * sum(len(set(v)) == 1 for v in groups) / len(groups), 1),
            "split_pct": round(
                100 * sum({"bullish", "bearish"} <= set(v) for v in groups) / len(groups), 1
            ),
            "stances": dict(Counter(x for v in groups for x in v)),
        }
    return out


def run(root: Path, name: str) -> dict:
    """One run: config, metrics, equity curves per symbol, behaviour and analyst agreement."""
    d = _folder(root, name)
    cfg, met = _config(d), _loads((d / "metrics.json").read_text())
    start = _start(cfg)
    return {
        "name": name,
        "config": cfg,
        "average": met.get("average", {}),
        "per_symbol": met.get("per_symbol", {}),
        "consensus": met.get("consensus", {}),
        "usage": met.get("usage", {}),
        "equity": {s: _equity(d, s, start) for s in cfg["symbols"]},
        "behaviour": _behaviour(_jsonl(d / "decisions.jsonl")),
        "agreement": _agreement(_jsonl(d / "reports.jsonl")),
    }


def decisions(root: Path, name: str, symbol: str, strategy: str) -> list[dict]:
    """Daily decisions of one strategy on one symbol, oldest first."""
    d = _folder(root, name)
    start = _start(_config(d))
    rows = [
        {**x, "day": _day(x["day"], start), "label": x["day"]}
        for x in _jsonl(d / "decisions.jsonl")
        if x["symbol"] == symbol and x["strategy"] == strategy
    ]
    return sorted(rows, key=lambda r: r["day"])


def day(root: Path, name: str, symbol: str, when: str) -> dict:
    """Everything logged for one symbol-day: every strategy's decision, the consensus result per
    domain and each analyst's report. `when` is a calendar date (blind runs are mapped back)."""
    d = _folder(root, name)
    start = _start(_config(d))

    def pick(rows: list[dict]) -> list[dict]:
        return [
            {**x, "day": when, "label": x["day"]}
            for x in rows
            if x["symbol"] == symbol and _day(x["day"], start) == when
        ]

    return {
        "symbol": symbol,
        "day": when,
        "decisions": pick(_jsonl(d / "decisions.jsonl")),
        "consensus": pick(_jsonl(d / "consensus.jsonl")),
        "reports": sorted(
            pick(_jsonl(d / "reports.jsonl")), key=lambda r: (r["domain"], r.get("agent", 0))
        ),
    }
