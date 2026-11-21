"""MakeMoney: a paper-trading USDT-M futures account driven by Claude Haiku.

No exchange account is touched; orders are simulated against live Binance USDT-M public data
so the paper account behaves like a real isolated-margin account:

- Market fills at the live best bid/ask plus slippage, taker fee on both sides.
- Quantity rounded down to the symbol's stepSize; minQty / minNotional enforced; stop and
  take-profit prices rounded to tickSize.
- Isolated-margin liquidation price from Binance's formula with the tier-1 maintenance margin
  rate, triggered by *mark-price* 1m candles; liquidation forfeits the whole isolated margin.
- Stop-market / take-profit-market orders triggered by *last-price* 1m candles between steps
  (a gap through the trigger fills at the bar open); if one bar touches both, the stop wins.
- Funding settled at each real nextFundingTime with the live rate, paid from isolated margin.
- A guard loop scans every few seconds whether or not the Haiku bot is running, the same way
  resting exchange orders keep working while you are away; after downtime it replays missed bars.

State and the API key live under `data/makemoney/` (gitignored).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from rinng.makemoney_signals import Strategy, analyse

if TYPE_CHECKING:
    from rinng.service import Rinng

log = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
BINANCE = "https://fapi.binance.com"
DEFAULT_MODEL = "claude-haiku-5-5"
GUARD_SEC = 10


@dataclass
class Config:
    api_key: str = ""
    model: str = DEFAULT_MODEL
    symbols: list[str] = field(default_factory=lambda: ["BTC-USDT-PERP", "ETH-USDT-PERP"])
    exchange: str = "binance"  # context data for Haiku; fills always use Binance USDT-M
    starting_balance: float = 1000.0
    max_leverage: int = 5
    risk_per_trade_pct: float = 2.0  # % of equity lost if the stop fills (fees included)
    max_positions: int = 2
    interval_sec: int = 300
    taker_fee_pct: float = 0.05  # Binance regular tier taker
    slippage_bps: float = 2.0  # beyond best bid/ask on market and stop fills
    auto_signal: bool = True  # open a simulated order as soon as a 5m signal fires
    strategy: dict = field(default_factory=dict)  # makemoney_signals.Strategy overrides
    auto_train: bool = True  # re-tune on fresh data on a schedule (adopt only if it holds up)
    train_every_h: float = 12.0
    train_days: int = 90
    train_tfs: list[str] = field(default_factory=lambda: ["5m", "15m", "1h"])
    notes: str = ""

    def public(self) -> dict:
        d = asdict(self)
        k = d.pop("api_key")
        src = "page" if k else ("env" if env_api_key() else "")
        k = k or env_api_key()
        d["api_key_set"] = bool(k)
        d["api_key_hint"] = f"…{k[-4:]} ({'.env' if src == 'env' else 'saved'})" if k else ""
        return d


def env_api_key() -> str:
    """CLAUDE_API_KEY from the environment, else from .env (cwd or repo root; never committed)."""
    if v := os.environ.get("CLAUDE_API_KEY"):
        return v.strip()
    for env in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "CLAUDE_API_KEY":
                return v.strip().strip("'\"")
    return ""


def venue_symbol(sym: str) -> str:
    """BTC-USDT-PERP -> BTCUSDT."""
    return sym.upper().replace("-PERP", "").replace("-SWAP", "").replace("-", "")


def _floor(v: float, step: float) -> float:
    return math.floor(v / step + 1e-9) * step if step else v


def _round(v: float, step: float) -> float:
    return round(round(v / step) * step, 12) if step else v


def _mmr(sym: str) -> float:
    """Tier-1 maintenance margin rate (small notional) on Binance USDT-M."""
    return 0.004 if venue_symbol(sym) in ("BTCUSDT", "ETHUSDT") else 0.01


def liq_price(p: dict) -> float:
    """Binance isolated one-way liquidation price (tier 1, maintenance amount 0)."""
    q, e, wb, m = p["qty"], p["entry"], p["margin"], _mmr(p["symbol"])
    if p["side"] == "long":
        return max((q * e - wb) / (q * (1 - m)), 0.0)
    return (q * e + wb) / (q * (1 + m))


def _empty_state(balance: float) -> dict:
    return {"balance": balance, "positions": [], "trades": [], "log": [], "equity": []}


class Binance:
    """Public USDT-M endpoints the simulator needs."""

    def __init__(self) -> None:
        self.cl = httpx.AsyncClient(base_url=BINANCE, timeout=15)
        self.filters: dict[str, dict] = {}

    async def get(self, path: str, **params: Any) -> Any:
        r = await self.cl.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def symbol_filters(self, sym: str) -> dict:
        v = venue_symbol(sym)
        if not self.filters:
            info = await self.get("/fapi/v1/exchangeInfo")
            for s in info["symbols"]:
                f = {x["filterType"]: x for x in s["filters"]}
                self.filters[s["symbol"]] = {
                    "tick": float(f["PRICE_FILTER"]["tickSize"]),
                    "step": float(f["MARKET_LOT_SIZE"]["stepSize"]),
                    "min_qty": float(f["MARKET_LOT_SIZE"]["minQty"]),
                    "max_qty": float(f["MARKET_LOT_SIZE"]["maxQty"]),
                    "min_notional": float(f.get("MIN_NOTIONAL", {}).get("notional", 5)),
                    "status": s["status"],
                }
        if v not in self.filters:
            raise ValueError(f"{sym} is not a Binance USDT-M perpetual")
        return self.filters[v]

    async def top_symbols(self, limit: int = 100) -> list[dict]:
        """Tradable USDT perpetuals, most 24h quote volume first, as rinng ids."""
        info, tick = await asyncio.gather(
            self.get("/fapi/v1/exchangeInfo"), self.get("/fapi/v1/ticker/24hr")
        )
        live = {
            s["symbol"]: s["baseAsset"]
            for s in info["symbols"]
            if s["contractType"] == "PERPETUAL"
            and s["quoteAsset"] == "USDT"
            and s["status"] == "TRADING"
        }
        vol = {t["symbol"]: float(t["quoteVolume"]) for t in tick if t["symbol"] in live}
        top = sorted(vol, key=vol.get, reverse=True)[:limit]
        return [{"id": f"{live[s]}-USDT-PERP", "base": live[s], "volume": vol[s]} for s in top]

    async def quote(self, sym: str) -> dict:
        v = venue_symbol(sym)
        book, prem = await asyncio.gather(
            self.get("/fapi/v1/ticker/bookTicker", symbol=v),
            self.get("/fapi/v1/premiumIndex", symbol=v),
        )
        return {
            "bid": float(book["bidPrice"]),
            "ask": float(book["askPrice"]),
            "mark": float(prem["markPrice"]),
            "last": (float(book["bidPrice"]) + float(book["askPrice"])) / 2,
            "funding_rate": float(prem["lastFundingRate"]),
            "next_funding": int(prem["nextFundingTime"]),
        }

    async def klines(self, sym: str, tf: str = "5m", limit: int = 1500) -> list[list[float]]:
        raw = await self.get("/fapi/v1/klines", symbol=venue_symbol(sym), interval=tf, limit=limit)
        return [[float(x) for x in b[:6]] for b in raw]

    async def bars(self, sym: str, start_ms: int, mark: bool = False) -> list[list]:
        """1m bars from start_ms (up to 1500, ~25h) as [open_ms, o, h, l, c]."""
        path = "/fapi/v1/markPriceKlines" if mark else "/fapi/v1/klines"
        raw = await self.get(
            path, symbol=venue_symbol(sym), interval="1m", startTime=start_ms, limit=1500
        )
        return [[int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4])] for b in raw]


class MakeMoney:
    def __init__(self, svc: Rinng, root: Path):
        self.svc = svc
        self.dir = root / "makemoney"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cfg = self._load_config()
        self.state = self._load_state()
        self.bn = Binance()
        self.running = False
        self.busy = False
        self.lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._guard: asyncio.Task | None = None
        self.last_error: str | None = None
        self.last_tick: float | None = None
        self.last_guard: float | None = None
        self._analysis: dict[str, tuple[float, dict]] = {}
        self._bt_running = False
        self._train_running = False
        self._train_task: asyncio.Task | None = None
        self._bt_error: str | None = None

    # ---------- persistence ----------
    def _load_config(self) -> Config:
        p = self.dir / "config.json"
        if p.exists():
            raw = json.loads(p.read_text())
            return Config(**{k: v for k, v in raw.items() if k in Config.__dataclass_fields__})
        return Config()

    def _save_config(self) -> None:
        p = self.dir / "config.json"
        p.write_text(json.dumps(asdict(self.cfg), indent=2))
        p.chmod(0o600)

    def _load_state(self) -> dict:
        p = self.dir / "state.json"
        if p.exists():
            s = json.loads(p.read_text())
            # number orders opened before ids existed, oldest first
            seq = 0
            for t in reversed(s["trades"]):
                if "id" not in t:
                    seq += 1
                    t["id"] = seq
            s.setdefault("seq", max([t["id"] for t in s["trades"]] + [0]))
            # positions opened by the earlier, simpler simulator lack the exchange fields
            s["positions"] = [p for p in s["positions"] if "next_funding" in p]
            return s
        return _empty_state(self.cfg.starting_balance)

    def _save_state(self) -> None:
        (self.dir / "state.json").write_text(json.dumps(self.state))

    # ---------- config / control ----------
    def update_config(self, patch: dict) -> dict:
        for k, v in patch.items():
            if k not in Config.__dataclass_fields__:
                continue
            if k == "api_key" and not v:
                continue  # empty field keeps the stored key
            setattr(self.cfg, k, v)
        self.cfg.max_leverage = max(1, min(int(self.cfg.max_leverage), 125))
        self.cfg.interval_sec = max(60, int(self.cfg.interval_sec))
        self.cfg.max_positions = max(1, int(self.cfg.max_positions))
        self.cfg.slippage_bps = max(0.0, float(self.cfg.slippage_bps))
        self.cfg.taker_fee_pct = max(0.0, float(self.cfg.taker_fee_pct))
        self._save_config()
        return self.cfg.public()

    def reset(self) -> dict:
        self.stop()
        self.state = _empty_state(self.cfg.starting_balance)
        self._save_state()
        return self.snapshot()

    def start(self) -> None:
        if not (self.cfg.api_key or env_api_key()):
            raise ValueError("Set CLAUDE_API_KEY in .env or enter a key on the page")
        self.ensure_guard()
        if self._task and not self._task.done():
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None

    def ensure_guard(self) -> None:
        if self._guard is None or self._guard.done():
            self._guard = asyncio.create_task(self._guard_loop())
        if self._train_task is None or self._train_task.done():
            self._train_task = asyncio.create_task(self._train_loop())

    async def _train_loop(self) -> None:
        while True:
            try:
                runs = self.state.get("training", [])
                last = runs[0]["t"] if runs else 0
                due = time.time() - last >= self.cfg.train_every_h * 3600
                if self.cfg.auto_train and due and not self._train_running:
                    await self._training("schedule")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("makemoney training loop: %s", e)
            await asyncio.sleep(60)

    def start_training(self) -> dict:
        if not self._train_running:
            asyncio.create_task(self._training("manual"))
            self._train_running = True
        return self.training_state()

    def training_state(self) -> dict:
        runs = self.state.get("training", [])
        last = runs[0]["t"] if runs else None
        return {
            "running": self._train_running,
            "auto": self.cfg.auto_train,
            "every_h": self.cfg.train_every_h,
            "days": self.cfg.train_days,
            "tfs": self.cfg.train_tfs,
            "next": (last + self.cfg.train_every_h * 3600)
            if (last and self.cfg.auto_train)
            else None,
            "current": self.strategy.to_dict() | {"rules": self.strategy.describe()},
            "runs": runs[:30],
        }

    async def _training(self, why: str) -> None:
        from rinng import makemoney_backtest as bt

        self._train_running = True
        try:
            c = self.cfg
            data = {
                s: await bt.history(self.bn, s, c.train_days, self.dir / "history")
                for s in c.symbols
            }
            filt = {s: await self.bn.symbol_filters(s) for s in c.symbols}
            acct = bt.Account(
                balance=c.starting_balance,
                risk_pct=c.risk_per_trade_pct,
                leverage=c.max_leverage,
                max_positions=c.max_positions,
                taker_fee=self.fee,
                slippage=self.slip,
            )
            res = await asyncio.to_thread(
                bt.train, data, filt, acct, self.strategy, tuple(c.train_tfs)
            )
            res |= {"trigger": why, "symbols": c.symbols, "days": c.train_days}
            async with self.lock:
                runs = self.state.setdefault("training", [])
                runs.insert(0, res)
                del runs[50:]
                if res["adopt"]:
                    self.cfg.strategy = res["candidate"]
                    self._save_config()
                    self._analysis.clear()
                    self._note(
                        f"TRAINING adopted a new {res['candidate']['tf']} "
                        f"{res['candidate']['mode']} setup: out of sample "
                        f"{res['candidate_test']['return_pct']:+.1f}% vs current "
                        f"{res['current_test']['return_pct']:+.1f}%"
                    )
                else:
                    failed = [k for k, ok in res["checks"].items() if not ok]
                    self._note("TRAINING kept the current setup (" + ", ".join(failed) + ")")
                self._save_state()
        except Exception as e:
            log.exception("makemoney training failed")
            self._note(f"TRAINING failed: {e}")
        finally:
            self._train_running = False

    async def _loop(self) -> None:
        while self.running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # keep the loop alive; surface the error in the UI
                log.exception("makemoney tick failed")
                self.last_error = str(e)
            await asyncio.sleep(self.cfg.interval_sec)

    async def _guard_loop(self) -> None:
        while True:
            try:
                if self.state["positions"]:
                    async with self.lock:
                        await self.guard()
                if self.cfg.auto_signal:
                    await self.scan_signals()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("makemoney guard failed: %s", e)
            await asyncio.sleep(GUARD_SEC)

    # ---------- accounting ----------
    @property
    def fee(self) -> float:
        return self.cfg.taker_fee_pct / 100

    @property
    def slip(self) -> float:
        return self.cfg.slippage_bps / 10_000

    @staticmethod
    def _pnl(p: dict, price: float) -> float:
        d = 1 if p["side"] == "long" else -1
        return d * (price - p["entry"]) * p["qty"]

    def equity_now(self) -> float:
        """Wallet balance + isolated margins + unrealized PnL at mark (as Binance shows it)."""
        eq = self.state["balance"]
        for p in self.state["positions"]:
            eq += p["margin"] + self._pnl(p, p.get("mark", p["entry"]))
        return eq

    def _note(self, msg: str) -> None:
        self.state["log"].insert(0, {"t": time.time(), "msg": msg})
        del self.state["log"][300:]

    def _partial(self, p: dict, fill: float, frac: float, why: str) -> None:
        """Close `frac` of the original size at `fill` and keep the rest open."""
        qx = min(p.get("qty0", p["qty"]) * frac, p["qty"])
        pnl = self._pnl(p, fill) * qx / p["qty"]
        fee = fill * qx * self.fee
        freed = p["margin"] * qx / p["qty"]
        self.state["balance"] += freed + pnl - fee
        p["margin"] -= freed
        p["qty"] -= qx
        p["realized"] = p.get("realized", 0.0) + pnl
        p["partial_fees"] = p.get("partial_fees", 0.0) + fee
        p.setdefault("partials", []).append(
            {"t": time.time(), "price": fill, "qty": qx, "why": why}
        )
        self._note(
            f"{why.upper()} #{p.get('id', '?')} {p['symbol']} closed {qx:g} @ {fill:.6g} "
            f"({pnl - fee:+.2f} USDT); stop → break-even {p['entry']:.6g}"
        )

    def _close(self, p: dict, fill: float, why: str, t: float | None = None) -> None:
        done = p.get("realized", 0.0)  # gross PnL already banked by partial take-profits
        done_fees = p.get("partial_fees", 0.0)
        if why == "liquidated":
            # what is left of the isolated margin (funding included) goes to the insurance fund
            fee, pnl = 0.0, -p["margin"]
            net = done - done_fees - p["margin_in"] * (p["qty"] / p.get("qty0", p["qty"]))
            net -= p["open_fee"]
        else:
            pnl = self._pnl(p, fill)
            fee = fill * p["qty"] * self.fee
            self.state["balance"] += p["margin"] + pnl - fee
            net = done + pnl - done_fees - fee - p["open_fee"] + p["funding"]
        self.state["positions"].remove(p)
        for j in self.state.get("signal_log", []):
            if j.get("order_id") is not None and j["order_id"] == p.get("id"):
                j["result"], j["exit_reason"] = net, why
                break
        self.state["trades"].insert(
            0,
            {
                **p,
                "exit": fill,
                "closed": t or time.time(),
                "pnl": net,
                "gross_pnl": done + pnl,
                "exit_fee": fee + done_fees,
                "fees": p["open_fee"] + fee + done_fees,
                "qty": p.get("qty0", p["qty"]),
                "roe_pct": net / p["margin_in"] * 100,
                "exit_reason": why,
            },
        )
        self._note(
            f"CLOSE #{p.get('id', '?')} {p['side']} {p['symbol']} @ {fill:.6g} ({why}) "
            f"net {net:+.2f} USDT"
        )

    # ---------- orders ----------
    @property
    def strategy(self) -> Strategy:
        return Strategy.from_dict(self.cfg.strategy)

    async def analysis(self, sym: str) -> dict:
        """5m analysis (see makemoney_signals), cached for 15s per symbol."""
        hit = self._analysis.get(sym)
        if hit and time.time() - hit[0] < 15:
            return hit[1]
        bars = await self.bn.klines(sym, self.strategy.tf)
        a = await asyncio.to_thread(analyse, bars, self.strategy)
        self._analysis[sym] = (time.time(), a)
        return a

    async def scan_signals(self) -> None:
        """Open a simulated order for a signal on the most recently closed 5m bar."""
        for sym in self.cfg.symbols:
            a = await self.analysis(sym)
            if len(a["candles"]) < 2 or not a["signals"]:
                continue
            sig = a["signals"][-1]
            if sig["time"] != a["candles"][-2]["time"]:  # not the bar that just closed
                continue
            key = f"{sym}:{sig['time']}:{sig['side']}"
            taken = self.state.setdefault("taken_signals", [])
            if key in taken:
                continue
            async with self.lock:
                taken.append(key)
                del taken[:-500]
                held = any(p["symbol"] == sym for p in self.state["positions"])
                why = f"SIGNAL {sig['side']}: " + "; ".join(sig["reasons"])
                entry = {
                    "t": time.time(),
                    "symbol": sym,
                    "side": sig["side"],
                    "bar": sig["time"],
                    "tf": self.strategy.tf,
                    "price": sig["entry"],
                    "stop": sig["stop"],
                    "tp1": sig["tp1"],
                    "take": sig["take"],
                    "reasons": sig["reasons"],
                    "action": "opened",
                    "detail": "",
                    "order_id": None,
                    "result": None,
                }
                journal = self.state.setdefault("signal_log", [])
                journal.insert(0, entry)
                del journal[200:]
                if held:
                    entry["action"], entry["detail"] = "skipped", "position already open"
                    self._note(f"SIGNAL {sig['side']} {sym} skipped: position already open")
                elif len(self.state["positions"]) >= self.cfg.max_positions:
                    entry["action"], entry["detail"] = "skipped", "max positions reached"
                    self._note(f"SIGNAL {sig['side']} {sym} skipped: max positions reached")
                else:
                    err = None
                    for lev in range(self.cfg.max_leverage, 0, -1):
                        try:
                            await self._open(
                                sym,
                                sig["side"],
                                lev,
                                sig["stop"],
                                sig["take"],
                                why,
                                "signal",
                                plan={
                                    "tp1": sig["tp1"],
                                    "tp1_frac": self.strategy.tp1_frac,
                                    "deadline": time.time() + self.strategy.max_bars * 300,
                                },
                            )
                            err = None
                            break
                        except ValueError as e:
                            err = e
                            if "liquidation" not in str(e):
                                break
                    if err:
                        entry["action"], entry["detail"] = "rejected", str(err)
                        self._note(f"SIGNAL {sig['side']} {sym} rejected: {err}")
                    else:
                        pos = self.state["positions"][-1]
                        entry["order_id"] = pos["id"]
                        entry["detail"] = f"filled {pos['entry']:.6g} x{pos['leverage']}"
                self._save_state()

    async def _open(
        self,
        sym: str,
        side: str,
        lev: int,
        stop: float,
        take: float,
        why: str,
        source: str = "haiku",
        plan: dict | None = None,
    ):
        f = await self.bn.symbol_filters(sym)
        if f["status"] != "TRADING":
            raise ValueError(f"{sym} is {f['status']}")
        q = await self.bn.quote(sym)
        fill = q["ask"] * (1 + self.slip) if side == "long" else q["bid"] * (1 - self.slip)
        fill = _round(fill, f["tick"])
        stop, take = _round(stop, f["tick"]), _round(take, f["tick"])
        ok = (stop < fill < take) if side == "long" else (take < fill < stop)
        if not ok:
            raise ValueError(f"stop/take on the wrong side of the {side} fill {fill}")

        lev = max(1, min(lev, self.cfg.max_leverage))
        equity = self.equity_now()
        risk = equity * self.cfg.risk_per_trade_pct / 100
        # loss at stop = distance + stop slippage + entry and exit fees
        per_unit = abs(fill - stop) + stop * self.slip + (fill + stop) * self.fee
        qty = risk / per_unit
        avail = self.state["balance"]
        max_qty = avail / (fill / lev + fill * self.fee)  # initial margin + open fee must fit
        qty = _floor(min(qty, max_qty, f["max_qty"]), f["step"])
        if qty < f["min_qty"] or qty * fill < f["min_notional"]:
            raise ValueError(
                f"size {qty} ({qty * fill:.2f} USDT) below Binance minimum "
                f"(minQty {f['min_qty']}, minNotional {f['min_notional']})"
            )
        margin = qty * fill / lev
        open_fee = qty * fill * self.fee
        self.state["seq"] = self.state.get("seq", len(self.state["trades"])) + 1
        pos = {
            "id": self.state["seq"],
            "symbol": sym,
            "side": side,
            "qty": qty,
            "qty0": qty,
            "entry": fill,
            "leverage": lev,
            "margin": margin,
            "margin_in": margin,
            "stop": stop,
            "take": take,
            "tp1": _round(plan["tp1"], f["tick"]) if plan and plan.get("tp1") else None,
            "tp1_frac": (plan or {}).get("tp1_frac", 0.0),
            "be": False,
            "deadline": (plan or {}).get("deadline"),
            "opened": time.time(),
            "reason": why,
            "source": source,
            "open_fee": open_fee,
            "funding": 0.0,
            "mark": q["mark"],
            "next_funding": q["next_funding"],
            "scanned_ms": int(time.time() // 60 * 60_000),
        }
        liq = liq_price(pos)
        if (side == "long" and stop <= liq) or (side == "short" and stop >= liq):
            raise ValueError(
                f"stop {stop} is beyond the liquidation price {liq:.6g}; lower leverage"
            )
        self.state["balance"] -= margin + open_fee
        self.state["positions"].append(pos)
        self._note(
            f"OPEN #{pos['id']} {side} {sym} {qty:g} x{lev} @ {fill:.6g} "
            f"(book {q['bid']}/{q['ask']}) "
            f"SL {stop:.6g} TP {take:.6g} liq {liq:.6g} fee {open_fee:.3f} — {why}"
        )

    async def _market_close(self, p: dict, why: str) -> None:
        f = await self.bn.symbol_filters(p["symbol"])
        q = await self.bn.quote(p["symbol"])
        fill = q["bid"] * (1 - self.slip) if p["side"] == "long" else q["ask"] * (1 + self.slip)
        self._close(p, _round(fill, f["tick"]), why)

    # ---------- the exchange side: triggers, liquidation, funding ----------
    async def guard(self) -> None:
        now_ms = int(time.time() * 1000)
        for p in list(self.state["positions"]):
            sym = p["symbol"]
            q = await self.bn.quote(sym)
            p["mark"] = q["mark"]

            # funding settlements that happened since we last looked
            while now_ms >= p["next_funding"]:
                pay = p["qty"] * q["mark"] * q["funding_rate"]
                amt = -pay if p["side"] == "long" else pay
                p["margin"] += amt
                p["funding"] += amt
                self._note(f"FUNDING {sym} rate {q['funding_rate'] * 100:.4f}% → {amt:+.4f} USDT")
                p["next_funding"] += 8 * 3600 * 1000

            last, mark = await asyncio.gather(
                self.bn.bars(sym, p["scanned_ms"]), self.bn.bars(sym, p["scanned_ms"], mark=True)
            )
            marks = {b[0]: b for b in mark}
            long_ = p["side"] == "long"
            f = await self.bn.symbol_filters(sym)
            if p.get("deadline") and time.time() >= p["deadline"]:
                await self._market_close(p, "time")
                continue
            for b in last:
                t, o, h, lo, _c = b
                liq = liq_price(p)
                mb = marks.get(t)
                stop_hit = lo <= p["stop"] if long_ else h >= p["stop"]
                take_hit = h >= p["take"] if long_ else lo <= p["take"]
                liq_hit = mb is not None and (mb[3] <= liq if long_ else mb[2] >= liq)
                if liq_hit and not (stop_hit and (p["stop"] > liq if long_ else p["stop"] < liq)):
                    self._close(p, liq, "liquidated", t / 1000)
                    break
                if stop_hit:  # stop wins if the same bar touched both
                    gap = (o <= p["stop"]) if long_ else (o >= p["stop"])
                    trig = o if gap else p["stop"]
                    fill = trig * (1 - self.slip) if long_ else trig * (1 + self.slip)
                    why = "breakeven" if p.get("be") else "stop"
                    self._close(p, _round(fill, f["tick"]), why, t / 1000)
                    break
                tp1 = p.get("tp1")
                if tp1 and not p.get("be") and (h >= tp1 if long_ else lo <= tp1):
                    fill = tp1 * (1 - self.slip) if long_ else tp1 * (1 + self.slip)
                    self._partial(p, _round(fill, f["tick"]), p.get("tp1_frac", 0.5), "tp1")
                    p["stop"], p["be"] = p["entry"], True
                if take_hit:
                    gap = (o >= p["take"]) if long_ else (o <= p["take"])
                    trig = o if gap else p["take"]
                    fill = trig * (1 - self.slip) if long_ else trig * (1 + self.slip)
                    self._close(p, _round(fill, f["tick"]), "take-profit", t / 1000)
                    break
            else:
                if last:  # rescan the still-forming bar next time
                    p["scanned_ms"] = last[-1][0]
        self.last_guard = time.time()
        self._save_state()

    # ---------- the brain ----------
    def _prompt(self, ctx: dict) -> str:
        c = self.cfg
        return f"""You manage a simulated Binance USDT-M futures account (isolated margin).
It behaves like the real exchange: market fills at bid/ask plus slippage, {c.taker_fee_pct}%
taker fee each side, funding every 8h, liquidation at the mark price forfeits the margin.
Goal: grow equity while protecting it. Doing nothing is a valid choice.
Each symbol has `analysis_5m` from a rule-based 5m engine (trend, structure, support and
resistance, last signal and its recent hit rate). When auto-signal is on, that engine opens
orders itself; positions show `source` ("signal" or "haiku"). Manage all of them.

Rules:
- Max leverage {c.max_leverage}x, max {c.max_positions} open positions, one per symbol.
- Each new trade risks {c.risk_per_trade_pct}% of equity at the stop, fees included (sizing is
  automatic). The stop must sit before the liquidation price, so prefer modest leverage.
- Every open needs a stop and take-profit on the correct side of price, reward:risk >= 1.5.
{("Extra instructions from the owner: " + c.notes) if c.notes else ""}

Account and market data (JSON):
{json.dumps(ctx, default=str)}

Reply with ONLY a JSON object:
{{"actions": [
  {{"type": "open", "symbol": "...", "side": "long|short", "leverage": 3,
   "stop": 0.0, "take": 0.0, "reason": "short why"}},
  {{"type": "close", "symbol": "...", "reason": "..."}},
  {{"type": "move_stop", "symbol": "...", "stop": 0.0, "reason": "..."}}
], "view": "one-sentence market view"}}
Use an empty actions list to hold."""

    async def _ask(self, prompt: str) -> dict:
        async with httpx.AsyncClient(timeout=60) as cl:
            r = await cl.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": self.cfg.api_key or env_api_key(),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.cfg.model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if r.status_code != 200:
            raise RuntimeError(f"Claude API {r.status_code}: {r.text[:300]}")
        text = "".join(b.get("text", "") for b in r.json()["content"])
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise RuntimeError(f"No JSON in model reply: {text[:200]}")
        return json.loads(m.group(0))

    async def tick(self) -> dict:
        if self.busy:
            return self.snapshot()
        self.busy = True
        self.ensure_guard()
        try:
            async with self.lock:
                if self.state["positions"]:
                    await self.guard()
                market: dict[str, Any] = {}
                for sym in self.cfg.symbols:
                    s = await asyncio.to_thread(self.svc.summary, sym, self.cfg.exchange)
                    q = await self.bn.quote(sym)
                    market[sym] = {
                        k: s.get(k)
                        for k in ("derivatives", "structure", "profile", "wyckoff", "momentum")
                    }
                    # analysis blocks are computed on closed candles; `live` is the tradable
                    # price right now, which is what orders fill against
                    market[sym]["last_closed_1h_candle"] = {
                        k: v for k, v in (s.get("price") or {}).items() if k != "spark"
                    }
                    market[sym]["live"] = q | {"time_utc": time.strftime("%H:%M:%S", time.gmtime())}
                    a5 = await self.analysis(sym)
                    market[sym]["analysis_5m"] = a5["summary"] | {
                        "resistance": a5["resistance"],
                        "support": a5["support"],
                    }
                ctx = {
                    "equity": round(self.equity_now(), 2),
                    "available_balance": round(self.state["balance"], 2),
                    "positions": [
                        {
                            k: p[k]
                            for k in (
                                "symbol",
                                "side",
                                "qty",
                                "entry",
                                "leverage",
                                "stop",
                                "take",
                                "mark",
                                "source",
                            )
                            if k in p
                        }
                        | {"upnl": round(self._pnl(p, p["mark"]), 2), "liq": round(liq_price(p), 6)}
                        for p in self.state["positions"]
                    ],
                    "recent_trades": [
                        {k: t[k] for k in ("symbol", "side", "entry", "exit", "pnl", "exit_reason")}
                        for t in self.state["trades"][:5]
                    ],
                    "market": market,
                }
            decision = await self._ask(self._prompt(ctx))
            async with self.lock:
                await self._apply(decision)
                if decision.get("view"):
                    self._note(f"VIEW {decision['view']}")
                self.state["equity"].append([time.time(), round(self.equity_now(), 2)])
                del self.state["equity"][:-2000]
                self.last_error = None
                self.last_tick = time.time()
                self._save_state()
            return self.snapshot()
        finally:
            self.busy = False

    async def _apply(self, decision: dict) -> None:
        held = {p["symbol"]: p for p in self.state["positions"]}
        for a in decision.get("actions", []) or []:
            try:
                sym = a.get("symbol")
                if sym not in self.cfg.symbols:
                    raise ValueError(f"unknown symbol {sym}")
                t = a.get("type")
                if t == "close" and sym in held:
                    await self._market_close(held.pop(sym), a.get("reason", "model"))
                elif t == "move_stop" and sym in held:
                    p = held[sym]
                    f = await self.bn.symbol_filters(sym)
                    stop = _round(float(a["stop"]), f["tick"])
                    bad = stop >= p["mark"] if p["side"] == "long" else stop <= p["mark"]
                    if bad:
                        raise ValueError(
                            f"stop {stop} would trigger immediately (mark {p['mark']})"
                        )
                    p["stop"] = stop
                    self._note(f"STOP {sym} -> {stop:.6g} — {a.get('reason', '')}")
                elif t == "open":
                    if sym in held:
                        raise ValueError(f"{sym} already open")
                    if len(self.state["positions"]) >= self.cfg.max_positions:
                        raise ValueError("max positions reached")
                    if a.get("side") not in ("long", "short"):
                        raise ValueError("side must be long or short")
                    await self._open(
                        sym,
                        a["side"],
                        int(a.get("leverage", 1)),
                        float(a["stop"]),
                        float(a["take"]),
                        a.get("reason", ""),
                    )
                    held[sym] = self.state["positions"][-1]
            except Exception as e:
                self._note(f"REJECTED {a.get('type')} {a.get('symbol')}: {e}")

    # ---------- projection of open orders ----------
    async def projections(self) -> dict:
        """Analog projection for every open order (makemoney_projection), cached 30s."""
        from rinng.makemoney_projection import project

        hit = getattr(self, "_proj", None)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        tf = self.strategy.tf
        bar_sec = {"5m": 300, "15m": 900, "1h": 3600}.get(tf, 300)
        out: dict[str, Any] = {}
        for p in list(self.state["positions"]):
            bars = (await self.bn.klines(p["symbol"], tf))[:-1]  # closed bars only
            left = (p.get("deadline") or time.time() + 48 * bar_sec) - time.time()
            horizon = int(min(max(left // bar_sec, 3), 96))
            res = await asyncio.to_thread(project, bars, p, horizon, self.fee)
            out[str(p.get("id"))] = res
        data = {"t": time.time(), "tf": tf, "orders": out}
        self._proj = (time.time(), data)
        return data

    # ---------- backtest ----------
    def backtest_state(self) -> dict:
        p = self.dir / "backtest.json"
        last = json.loads(p.read_text()) if p.exists() else None
        return {"running": self._bt_running, "error": self._bt_error, "result": last}

    def start_backtest(self, days: int) -> dict:
        if self._bt_running:
            return self.backtest_state()
        self._bt_running, self._bt_error = True, None
        asyncio.create_task(self._backtest(max(7, min(int(days), 180))))
        return self.backtest_state()

    async def _backtest(self, days: int) -> None:
        from rinng import makemoney_backtest as bt

        try:
            c = self.cfg
            data = {s: await bt.history(self.bn, s, days, self.dir / "history") for s in c.symbols}
            filt = {s: await self.bn.symbol_filters(s) for s in c.symbols}
            acct = bt.Account(
                balance=c.starting_balance,
                risk_pct=c.risk_per_trade_pct,
                leverage=c.max_leverage,
                max_positions=c.max_positions,
                taker_fee=self.fee,
                slippage=self.slip,
            )
            res = await asyncio.to_thread(bt.report, data, filt, self.strategy, acct)
            res |= {"days": days, "symbols": c.symbols, "ran_at": time.time()}
            (self.dir / "backtest.json").write_text(json.dumps(res, default=float))
        except Exception as e:
            log.exception("makemoney backtest failed")
            self._bt_error = str(e)
        finally:
            self._bt_running = False

    def snapshot(self) -> dict:
        trades = self.state["trades"]
        wins = [t for t in trades if t["pnl"] > 0]
        eq = self.equity_now()
        return {
            "config": self.cfg.public(),
            "strategy": self.strategy.to_dict() | {"rules": self.strategy.describe()},
            "running": self.running,
            "busy": self.busy,
            "last_tick": self.last_tick,
            "last_guard": self.last_guard,
            "last_error": self.last_error,
            "balance": self.state["balance"],
            "equity": eq,
            "return_pct": (eq / self.cfg.starting_balance - 1) * 100,
            "win_rate": (len(wins) / len(trades) * 100) if trades else None,
            "fees_paid": sum(t.get("fees", 0) for t in trades)
            + sum(p["open_fee"] for p in self.state["positions"]),
            "funding_paid": sum(t.get("funding", 0) for t in trades)
            + sum(p["funding"] for p in self.state["positions"]),
            "positions": [
                p | {"upnl": self._pnl(p, p.get("mark", p["entry"])), "liq": liq_price(p)}
                for p in self.state["positions"]
            ],
            "trades": trades[:100],
            "log": self.state["log"][:100],
            "equity_curve": self.state["equity"],
            "margin_used": sum(p["margin"] for p in self.state["positions"]),
            "upnl": sum(self._pnl(p, p.get("mark", p["entry"])) for p in self.state["positions"]),
            "realized": sum(t["pnl"] for t in trades),
            "realized_today": sum(
                t["pnl"] for t in trades if t["closed"] >= time.time() - time.time() % 86400
            ),
            "signal_log": self.state.get("signal_log", [])[:60],
            "auto_signal": self.cfg.auto_signal,
        }
