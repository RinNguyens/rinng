"""Experiment driver: the TrustTrade ablation, rule baselines, and the forward (live) protocol.

LLM variants (paper Fig. 3c / Fig. 4, cumulative):

    single              1 analyst per domain → trader                 (standard single-LLM agent)
    multi               N analysts per domain, all reports passed on  ("uniform trust")
    consensus           N analysts → selective consensus → trader
    consensus_temporal  + deterministic temporal signals
    trusttrade          + memory bank with short/long reflection     (full method)

All variants share one set of analyst calls per (symbol, day, domain, agent k) through the LLM
cache, so differences come from what each variant does with the same reports. Baselines:
buy_hold, sma_cross, macd, kdj_rsi, zmr and temporal_rule (the temporal module's own proposal).

Backtest: decision at 00:00 UTC of day D from bars closed before D, fill at D's open, mark at D's
close. Live: run once a day after 00:00 UTC; it fills at the last close (≈ the new day's open),
persists state under TrustTrade/live/, and only ever sees data that exists at that moment, which
is the paper's answer to look-ahead leakage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from rinng.trusttrade import agents, consensus, data, memory, sim, temporal
from rinng.trusttrade.llm import DEFAULT_MODEL, LLM, PRICES, LLMError

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3] / "TrustTrade"
DAY = timedelta(days=1)
WARMUP_DAYS = 420  # 360-day horizon + indicator warm-up


@dataclass(frozen=True)
class Variant:
    multi: bool  # N analysts instead of 1
    consensus: bool
    temporal: bool
    memory: bool


VARIANTS: dict[str, Variant] = {
    "single": Variant(False, False, False, False),
    "multi": Variant(True, False, False, False),
    "consensus": Variant(True, True, False, False),
    "consensus_temporal": Variant(True, True, True, False),
    "trusttrade": Variant(True, True, True, True),
}
BASELINES = (*sim.BASELINES, "temporal_rule")


@dataclass
class RunConfig:
    symbols: list[str]
    start: date
    end: date  # inclusive
    exchange: str = "binance"
    analyst_models: list[str] = field(default_factory=lambda: [DEFAULT_MODEL])
    trader_model: str = DEFAULT_MODEL
    n_agents: int = 3
    variants: list[str] = field(default_factory=lambda: list(VARIANTS))
    baselines: list[str] = field(default_factory=lambda: list(BASELINES))
    allocation: str = "partial"
    fee_bps: float = 10.0
    cash: float = 10_000.0
    blind: bool = False
    analyst_effort: str = "low"
    trader_effort: str = "medium"
    reflect_effort: str = "low"
    reflect_every: int = 1
    concurrency: int = 8
    params: consensus.Params = field(default_factory=consensus.Params)
    domains: tuple[str, ...] = data.DOMAINS_BACKTEST

    def to_json(self) -> dict:
        d = asdict(self)
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        return d


def day_list(start: date, end: date) -> list[datetime]:
    t = datetime(start.year, start.month, start.day, tzinfo=UTC)
    out = []
    while t.date() <= end:
        out.append(t)
        t += DAY
    return out


# --------------------------------------------------------------------------- per-strategy book


@dataclass
class Book:
    name: str
    pf: sim.Portfolio
    equity: list[float] = field(default_factory=list)
    exposure: list[float] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    mem: memory.MemoryBank | None = None

    def state(self) -> dict:
        d = {
            "name": self.name,
            "pf": asdict(self.pf),
            "equity": self.equity,
            "exposure": self.exposure,
            "actions": self.actions,
        }
        if self.mem is not None:
            d["memory"] = {
                "records": [r.to_dict() for r in self.mem.records],
                "reflections": self.mem.reflections,
            }
        return d

    @classmethod
    def from_state(cls, s: dict) -> Book:
        b = cls(
            name=s["name"],
            pf=sim.Portfolio(**s["pf"]),
            equity=s["equity"],
            exposure=s["exposure"],
            actions=s["actions"],
        )
        if "memory" in s:
            b.mem = memory.MemoryBank()
            for r in s["memory"]["records"]:
                rec = memory.Record(
                    **{
                        k: v
                        for k, v in r.items()
                        if k not in ("returns", "sharpe", "slope_r", "slope_sr")
                    }
                )
                b.mem.add(rec)
                for k in ("returns", "sharpe", "slope_r", "slope_sr"):
                    setattr(rec, k, {int(h): v for h, v in r[k].items()})
            b.mem.reflections = s["memory"]["reflections"]
        return b


# --------------------------------------------------------------------------- one symbol


class SymbolRun:
    def __init__(
        self, cfg: RunConfig, llm: LLM, sd: data.SymbolData, out: Path, ref: datetime | None
    ):
        self.cfg, self.llm, self.sd, self.out = cfg, llm, sd, out
        self.ref = ref  # blind-mode day zero (None = real dates)
        self.fee = cfg.fee_bps / 10_000
        self.books: dict[str, Book] = {}
        for name in [*cfg.variants, *cfg.baselines]:
            uses_mem = name in VARIANTS and VARIANTS[name].memory
            self.books[name] = Book(
                name,
                sim.Portfolio(cash=cfg.cash, fee=self.fee),
                mem=memory.MemoryBank() if uses_mem else None,
            )
        self.prices: list[float] = []
        self.days: list[str] = []
        self.rules = {b: sim.rule_positions(sd.d1, b) for b in cfg.baselines if b in sim.BASELINES}
        self.row_of = {t: i for i, t in enumerate(sd.d1["open_time"].to_list())}
        self.consensus_log: list[dict] = []

    # ---- logging
    def _log(self, kind: str, row: dict) -> None:
        with (self.out / f"{kind}.jsonl").open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")

    @property
    def n_needed(self) -> int:
        return max(
            (
                self.cfg.n_agents if VARIANTS[v].multi else 1
                for v in self.cfg.variants
                if v in VARIANTS
            ),
            default=0,
        )

    # ---- LLM stages
    async def _analysts(self, snap: data.SymbolData, when: str) -> dict[str, list]:
        """reports[domain][k] (None when that call failed)."""
        jobs, keys = [], []
        for domain in self.cfg.domains:
            payload = data.BUILDERS[domain](snap, self.ref)
            system, user = agents.analyst_prompts(domain, snap.label, when, payload)
            for k in range(self.n_needed):
                model = self.cfg.analyst_models[k % len(self.cfg.analyst_models)]
                jobs.append(
                    self.llm.structured(
                        role=f"analyst:{domain}",
                        model=model,
                        system=system,
                        prompt=user,
                        schema=agents.report_model(domain),
                        effort=self.cfg.analyst_effort,
                        sample=k,
                    )
                )
                keys.append((domain, k))
        res = await asyncio.gather(*jobs, return_exceptions=True)
        reports: dict[str, list] = {d: [None] * self.n_needed for d in self.cfg.domains}
        for (domain, k), r in zip(keys, res, strict=True):
            if isinstance(r, BaseException):
                log.warning("%s %s analyst %s/%d failed: %s", self.sd.symbol, when, domain, k, r)
                self._log(
                    "errors",
                    {
                        "symbol": self.sd.symbol,
                        "day": when,
                        "stage": "analyst",
                        "domain": domain,
                        "agent": k,
                        "error": str(r),
                    },
                )
            else:
                reports[domain][k] = r
        return reports

    async def _reflect(self, book: Book, label: str, when: str) -> None:
        mem = book.mem
        if mem is None or not mem.records:
            return
        last = mem.last_reflection()
        if last and len(self.days) - 1 - last["day"] < self.cfg.reflect_every:
            return
        out = {"day": len(self.days) - 1}
        jobs = []
        for span, hs in (("short-term", memory.SHORT), ("long-term", memory.LONG)):
            system, user = agents.reflect_prompts(
                span=span, horizons=hs, label=label, when=when, table=mem.prompt_table(hs)
            )
            jobs.append(
                self.llm.structured(
                    role=f"reflect:{span}",
                    model=self.cfg.trader_model,
                    system=system,
                    prompt=user,
                    schema=agents.Reflection,
                    effort=self.cfg.reflect_effort,
                )
            )
        res = await asyncio.gather(*jobs, return_exceptions=True)
        for span, r in zip(("short", "long"), res, strict=True):
            if isinstance(r, BaseException):
                self._log(
                    "errors",
                    {
                        "symbol": self.sd.symbol,
                        "day": when,
                        "stage": "reflect",
                        "span": span,
                        "error": str(r),
                    },
                )
            else:
                out[span] = r.model_dump()
        mem.reflections.append(out)

    def _sections(
        self, v: Variant, book: Book, reports: dict, cons: dict, tsig: temporal.TemporalSignals
    ) -> list[tuple[str, str]]:
        sec: list[tuple[str, str]] = []
        n = self.cfg.n_agents
        for domain in self.cfg.domains:
            if v.consensus:
                sec.append(
                    (
                        f"Cross-checked {domain} evidence (claims that {n} independent "
                        "analysts agree on)",
                        cons[domain].evidence(),
                    )
                )
            elif v.multi:
                parts = [
                    f"### Analyst {k + 1}\n" + (agents.report_text(r) if r else "(report failed)")
                    for k, r in enumerate(reports[domain][:n])
                ]
                sec.append((f"{domain.title()} analyst reports ({n} analysts)", "\n\n".join(parts)))
            else:
                r = reports[domain][0]
                sec.append(
                    (
                        f"{domain.title()} analyst report",
                        agents.report_text(r) if r else "(report failed)",
                    )
                )
        if v.temporal:
            sec.append(
                (
                    "Deterministic temporal signals (computed from prices, no model)",
                    tsig.table(label_dates=self.ref is None),
                )
            )
        if v.memory and book.mem is not None:
            sec.append(
                (
                    "Your recent decisions and their outcomes",
                    book.mem.prompt_table(memory.SHORT, last=10),
                )
            )
            ref = book.mem.last_reflection()
            if ref:
                for span in ("short", "long"):
                    if span in ref:
                        r = ref[span]
                        sec.append(
                            (
                                f"Reflection ({span}-term)",
                                f"Worked: {r['strengths']}\nDid not: {r['weaknesses']}\n"
                                f"Next: {r['recommendation']} (posture: {r['risk_posture']})",
                            )
                        )
        return sec

    async def _trade(
        self,
        name: str,
        book: Book,
        snap: data.SymbolData,
        when: str,
        reports: dict,
        cons: dict,
        price: float,
    ) -> dict:
        v = VARIANTS[name]
        holding = book.pf.qty > 0
        tsig = temporal.compute(snap.d1, holding=holding, as_of=when)
        value = book.pf.value(price)
        position = {
            "equity": round(value, 2),
            "cash_pct": round(100 * book.pf.cash / value, 1) if value else 0,
            "asset_pct": round(100 * book.pf.qty * price / value, 1) if value else 0,
        }
        system, user = agents.trader_prompts(
            label=snap.label,
            when=when,
            fee_pct=self.cfg.fee_bps / 100,
            allocation=self.cfg.allocation,
            position=position,
            sections=self._sections(v, book, reports, cons, tsig),
        )
        try:
            d = await self.llm.structured(
                role=f"trader:{name}",
                model=self.cfg.trader_model,
                system=system,
                prompt=user,
                schema=agents.Decision,
                effort=self.cfg.trader_effort,
            )
            out = d.model_dump()
        except LLMError as e:
            out = {
                "action": "HOLD",
                "pct": 0,
                "confidence": 0,
                "rationale": "",
                "key_evidence": [],
                "error": str(e),
            }
        if out["action"] == "HOLD" or out["pct"] == 0:
            out["action"], out["pct"] = "HOLD", 0
        elif self.cfg.allocation == "full":
            out["pct"] = 100
        return out

    # ---- one day
    async def step(self, t: datetime, exec_price: float, mark_price: float) -> None:
        snap = self.sd.asof(t)
        if snap.d1.height < 60:
            raise ValueError(f"{self.sd.symbol}: fewer than 60 daily bars before {t:%Y-%m-%d}")
        when = data.day_label(t, self.ref)
        i = len(self.days)
        self.days.append(when)
        self.prices.append(exec_price)
        llm_names = [n for n in self.cfg.variants if n in VARIANTS]

        reports: dict = {}
        cons: dict[str, consensus.Result] = {}
        if llm_names:
            reports = await self._analysts(snap, when)
            asof = None if self.ref else t.strftime("%Y-%m-%d")
            for domain in self.cfg.domains:
                claims = [
                    c
                    for k, r in enumerate(reports[domain][: self.cfg.n_agents])
                    if r is not None
                    for c in agents.to_claims(r, k, domain)
                ]
                cons[domain] = consensus.score(
                    claims, self.cfg.n_agents, domain, as_of=asof, params=self.cfg.params
                )
                self._log(
                    "consensus", {"symbol": self.sd.symbol, "day": when, **cons[domain].to_dict()}
                )
                self.consensus_log.append(
                    {
                        "domain": domain,
                        "kept": cons[domain].kept_share,
                        "high": len(cons[domain].high),
                        "leaked": len(cons[domain].leaked),
                    }
                )
            for domain, rs in reports.items():
                for k, r in enumerate(rs):
                    if r is not None:
                        self._log(
                            "reports",
                            {
                                "symbol": self.sd.symbol,
                                "day": when,
                                "domain": domain,
                                "agent": k,
                                **r.model_dump(),
                            },
                        )

        for b in self.books.values():
            if b.mem is not None:
                b.mem.backfill(i, self.prices, b.equity)
        await asyncio.gather(
            *(
                self._reflect(self.books[n], snap.label, when)
                for n in llm_names
                if self.books[n].mem is not None
            )
        )
        decisions = await asyncio.gather(
            *(
                self._trade(n, self.books[n], snap, when, reports, cons, exec_price)
                for n in llm_names
            )
        )
        chosen = dict(zip(llm_names, decisions, strict=True))

        prev_row = self.row_of.get(t - DAY)
        for name in self.cfg.baselines:
            holding = self.books[name].pf.qty > 0
            if name == "temporal_rule":
                ts = temporal.compute(snap.d1, holding=holding, as_of=when)
                act, pct = ts.action, ts.pct
                if self.cfg.allocation == "full" and act != "HOLD":
                    pct = 100
            else:
                want = self.rules[name][prev_row] if prev_row is not None else 0.0
                act, pct = sim.to_action(want, holding)
            chosen[name] = {"action": act, "pct": pct}

        for name, d in chosen.items():
            book = self.books[name]
            value_before = book.pf.value(exec_price)
            q = book.pf.execute(d["action"], d["pct"], exec_price)
            if book.mem is not None:
                book.mem.add(
                    memory.Record(
                        day=i,
                        date=when,
                        action=d["action"],
                        pct=d["pct"],
                        qty_change=q,
                        price=exec_price,
                        value=value_before,
                    )
                )
            eq = book.pf.value(mark_price)
            book.equity.append(eq)
            book.exposure.append(book.pf.qty * mark_price / eq if eq else 0.0)
            book.actions.append(d["action"])
            self._log(
                "decisions",
                {
                    "symbol": self.sd.symbol,
                    "day": when,
                    "strategy": name,
                    "price": exec_price,
                    "equity": round(eq, 2),
                    "exposure": round(book.exposure[-1], 3),
                    **d,
                },
            )

    # ---- results
    def metrics(self) -> dict:
        out = {}
        for name, b in self.books.items():
            m = sim.metrics(b.equity, self.cfg.cash, b.exposure)
            acts = [a for a in b.actions]
            m["trades"] = b.pf.trades
            m["fees"] = round(b.pf.fees_paid, 2)
            m["buy_days"] = acts.count("BUY")
            m["sell_days"] = acts.count("SELL")
            out[name] = m
        return out

    def state(self) -> dict:
        return {
            "symbol": self.sd.symbol,
            "days": self.days,
            "prices": self.prices,
            "books": {n: b.state() for n, b in self.books.items()},
        }

    def load_state(self, s: dict) -> None:
        self.days, self.prices = s["days"], s["prices"]
        for n, bs in s["books"].items():
            if n in self.books:
                self.books[n] = Book.from_state(bs)


# --------------------------------------------------------------------------- estimates


TOKENS = {  # rough per-call (input, output) incl. adaptive thinking; refined from usage logs
    "analyst": (2500, 1500),
    "trader": (3000, 900),
    "reflect": (1500, 600),
}


def estimate(cfg: RunConfig, days: int) -> dict:
    llm_variants = [v for v in cfg.variants if v in VARIANTS]
    n = max((cfg.n_agents if VARIANTS[v].multi else 1 for v in llm_variants), default=0)
    per_day = {
        "analyst": n * len(cfg.domains) if llm_variants else 0,
        "trader": len(llm_variants),
        "reflect": 2 * sum(VARIANTS[v].memory for v in llm_variants) / max(cfg.reflect_every, 1),
    }
    calls = {k: v * days * len(cfg.symbols) for k, v in per_day.items()}
    usd = 0.0
    for role, c in calls.items():
        model = cfg.analyst_models[0] if role == "analyst" else cfg.trader_model
        pin, pout = PRICES.get(model, PRICES[DEFAULT_MODEL])
        tin, tout = TOKENS[role]
        usd += c * (tin * pin + tout * pout) / 1e6
    return {
        "calls": {k: round(v) for k, v in calls.items()},
        "total_calls": round(sum(calls.values())),
        "est_cost_usd": round(usd, 2),
    }


# --------------------------------------------------------------------------- backtest


async def backtest(
    cfg: RunConfig, paths, out: Path, *, cache_only: bool = False, fill: data.Fill | None = None
) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jsonl"):  # a re-run of the same name starts clean logs
        old.unlink()
    (out / "config.json").write_text(json.dumps(cfg.to_json(), indent=2, default=str))
    llm = LLM(ROOT / "cache", concurrency=cfg.concurrency, cache_only=cache_only)
    days = day_list(cfg.start, cfg.end)
    start_t = days[0]
    load_from, load_to = start_t - WARMUP_DAYS * DAY, days[-1] + 2 * DAY
    ref = start_t if cfg.blind else None
    t0 = time.time()

    async def one(symbol: str) -> SymbolRun:
        sd = await asyncio.to_thread(
            data.load, paths, cfg.exchange, symbol, load_from, load_to, fill
        )
        if cfg.blind:
            sd = data.blind(sd, start_t)
        run = SymbolRun(cfg, llm, sd, out, ref)
        bars = {r["open_time"]: r for r in sd.d1.iter_rows(named=True)}
        for t in days:
            bar = bars.get(t)
            if bar is None:
                log.warning("%s: no closed daily bar for %s, stopping", symbol, t.date())
                break
            await run.step(t, bar["open"], bar["close"])
            log.info("%s %s done (%.0fs)", symbol, t.date(), time.time() - t0)
        return run

    runs = await asyncio.gather(*(one(s) for s in cfg.symbols))
    result = summarize(cfg, runs, llm)
    (out / "metrics.json").write_text(json.dumps(result, indent=2, default=str))
    (out / "report.md").write_text(render(cfg, result))
    for r in runs:
        eq = pl.DataFrame({"day": r.days, **{n: b.equity for n, b in r.books.items()}})
        eq.write_csv(out / f"equity_{r.sd.symbol}.csv")
    return result


def _mean(xs: list[float]) -> float:
    v = [x for x in xs if x is not None and not (isinstance(x, float) and np.isnan(x))]
    return round(float(np.mean(v)), 3) if v else float("nan")


def rest_fill(svc, exchange: str) -> data.Fill:
    """Fetch daily klines from the exchange's public REST API (read-only)."""
    from rinng.exchanges.binance import Binance
    from rinng.exchanges.okx import Okx
    from rinng.store.schemas import OHLCV, rows_to_frame

    def fill(symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        api = Binance() if exchange == "binance" else Okx()
        rows = [r for p in api.klines(svc.venue(symbol, exchange), "1d", start, end) for r in p]
        return rows_to_frame(OHLCV, rows, exchange=exchange, symbol=symbol, timeframe="1d")

    return fill


def summarize(cfg: RunConfig, runs: list[SymbolRun], llm: LLM) -> dict:
    per_symbol = {r.sd.symbol: r.metrics() for r in runs}
    names = [*cfg.variants, *cfg.baselines]
    avg = {}
    for n in names:
        rows = [per_symbol[s][n] for s in per_symbol if per_symbol[s][n].get("days")]
        if rows:
            avg[n] = {
                k: _mean([r[k] for r in rows])
                for k in ("cr_pct", "mdd_pct", "sharpe", "avg_exposure_pct", "trades")
            }
    cons_stats: dict = {}
    for r in runs:
        for c in r.consensus_log:
            s = cons_stats.setdefault(c["domain"], {"days": 0, "kept": 0.0, "high": 0, "leaked": 0})
            s["days"] += 1
            s["kept"] += c["kept"]
            s["high"] += c["high"]
            s["leaked"] += c["leaked"]
    for s in cons_stats.values():
        s["avg_kept_share"] = round(s.pop("kept") / s["days"], 3)
        s["avg_high_groups"] = round(s.pop("high") / s["days"], 2)
    return {
        "average": avg,
        "per_symbol": per_symbol,
        "consensus": cons_stats,
        "usage": llm.usage_summary(),
    }


def render(cfg: RunConfig, res: dict) -> str:
    lines = [
        f"# TrustTrade run {cfg.start} → {cfg.end}",
        "",
        f"Symbols: {', '.join(cfg.symbols)} · analysts: {cfg.n_agents} × "
        f"{', '.join(cfg.analyst_models)} · trader: {cfg.trader_model} · allocation: "
        f"{cfg.allocation} · fee {cfg.fee_bps} bps · blind: {cfg.blind}",
        "",
        "## Average over symbols",
        "",
        "| strategy | CR % | MDD % | Sharpe | exposure % | trades |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for n, m in res["average"].items():
        lines.append(
            f"| {n} | {m['cr_pct']:+.2f} | {m['mdd_pct']:.2f} | {m['sharpe']:.2f} | "
            f"{m['avg_exposure_pct']:.0f} | {m['trades']:.0f} |"
        )
    for sym, ms in res["per_symbol"].items():
        lines += [
            "",
            f"## {sym}",
            "",
            "| strategy | CR % | MDD % | Sharpe | trades |",
            "|---|---:|---:|---:|---:|",
        ]
        for n, m in ms.items():
            if m.get("days"):
                lines.append(
                    f"| {n} | {m['cr_pct']:+.2f} | {m['mdd_pct']:.2f} | "
                    f"{m['sharpe']:.2f} | {m['trades']} |"
                )
    if res["consensus"]:
        lines += [
            "",
            "## Consensus filter",
            "",
            "| domain | days | kept share | high groups/day | leakage flags |",
            "|---|---:|---:|---:|---:|",
        ]
        for d, s in res["consensus"].items():
            lines.append(
                f"| {d} | {s['days']} | {s['avg_kept_share']:.2f} | "
                f"{s['avg_high_groups']:.1f} | {s['leaked']} |"
            )
    u = res["usage"]["total"]
    lines += [
        "",
        "## API usage",
        "",
        f"{u['calls']} calls ({u['cache_hits']} from cache, {u['errors']} errors), "
        f"{u['input_tokens']:,} input / {u['output_tokens']:,} output tokens, "
        f"≈ ${u['cost_usd']:.4f} at list price.",
        "",
        "Short windows and few symbols: treat differences as anecdotes, not evidence.",
        "Not investment advice.",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- live


async def live_step(cfg: RunConfig, svc, state_dir: Path) -> dict:
    """One forward decision per symbol for today (00:00 UTC), with persisted books."""
    from rinng.news.feed import NewsFeed

    state_dir.mkdir(parents=True, exist_ok=True)
    llm = LLM(ROOT / "cache", concurrency=cfg.concurrency)
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    feed = NewsFeed()
    if "news" in cfg.domains:
        await feed.refresh(force=True)
    report = {}
    for symbol in cfg.symbols:
        path = state_dir / f"{symbol}.json"
        saved = json.loads(path.read_text()) if path.exists() else None
        if saved and saved["days"] and saved["days"][-1] == today.strftime("%Y-%m-%d"):
            report[symbol] = {"skipped": "already decided today"}
            continue
        d1, _ = await asyncio.to_thread(svc.candles, cfg.exchange, symbol, "1d", WARMUP_DAYS + 30)
        d1 = d1.filter(pl.col("open_time") + DAY <= today)
        if d1.is_empty() or d1["open_time"][-1] != today - DAY:
            report[symbol] = {"error": "yesterday's daily bar is not available yet"}
            continue
        dv = await asyncio.to_thread(svc.derivs, cfg.exchange, symbol, today - 400 * DAY)
        fu = dv["funding"]
        fu = fu.select(pl.col("funding_time").alias("time"), "rate") if fu.height else fu
        sd = data.SymbolData(
            symbol=symbol,
            d1=d1,
            funding=fu
            if fu.height
            else pl.DataFrame(schema={"time": pl.Datetime("ms", "UTC"), "rate": pl.Float64}),
            oi=data._daily_last(
                dv["oi"].select("time", "oi_value") if dv["oi"].height else dv["oi"], ["oi_value"]
            ),
            ls=data._daily_last(
                dv["ls"].select("time", "ratio", "long_pct") if dv["ls"].height else dv["ls"],
                ["ratio", "long_pct"],
            ),
            label=symbol,
            news=feed.latest(200),
            now=datetime.now(UTC),
        )
        run = SymbolRun(cfg, llm, sd, state_dir, None)
        if saved:
            run.load_state(saved)
        price = float(d1["close"][-1])
        await run.step(today, price, price)
        path.write_text(json.dumps(run.state(), default=str))
        report[symbol] = {
            name: {"action": b.actions[-1], "equity": round(b.equity[-1], 2), "days": len(b.equity)}
            for name, b in run.books.items()
        }
        (state_dir / f"metrics_{symbol}.json").write_text(json.dumps(run.metrics(), indent=2))
    report["usage"] = llm.usage_summary()["total"]
    return report
