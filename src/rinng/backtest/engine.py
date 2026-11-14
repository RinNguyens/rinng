"""Event-driven, candle-by-candle backtest engine for ONE perpetual symbol.

Fill rules:

1. A signal with `time = T` (close of the candle that produced it) fills at the OPEN of the candle
   with `open_time == T`,
   i.e. the next candle. If `time` matches no candle boundary it fills at the first candle with
   `open_time >= time`. So a signal never fills on the candle that produced it.
   Signals after the last candle are not filled (counted in `signals_unfilled`). If several signals
   land on the same candle only the last one takes effect (counted in `signals_ignored`).
2. A new signal replaces the current position: close the old one (reason "signal") then open the
   new one at the same open. "flat" or size = 0 only closes. A signal in the same direction as the
   open position
   is ignored (no resize, no stop/TP change; counted in `signals_ignored`).
3. Entries/exits are market orders: fill price = reference price plus adverse slippage, taker fee on
   filled notional (see rinng.backtest.costs; the limit take-profit option uses the maker fee).
4. Stop/take-profit are checked in every candle from the entry candle on (entry is at the open, so
   the rest of
   that candle is already "after entry"), using high/low:
   - open already beyond the stop (gap) → exit at the open, reason "stop_gap";
   - open already beyond the take-profit → exit at the open, reason "take_profit_gap";
   - stop and take-profit both hit in one candle → assume the STOP hit first (conservative), reason
     "stop";
   - only one level hit → exit exactly at that level, reason "stop" or "take_profit".
   After a stop/TP exit, stay flat until the next signal.
5. Position size: qty = size × equity at entry × leverage / entry fill price. Equity at entry = cash
   after closing the old position; the entry fee is also deducted from cash (so notional + fee
   slightly exceeds equity
   at size = 1). No new entries when equity <= 0.
6. Funding: each funding row is assigned to the candle with open_time <= funding_time < next
   open_time and
   applied to the position after filling signals at that candle's open, before checking stop/TP.
   With
   funding_time on a candle open (the common case) this means a position opened exactly at
   funding_time is charged, one closed at that moment is not.
7. Equity is marked to market at each candle close; the equity `time` column is the candle close.
   A position still open at the end of data is closed at the last close (reason "end", with
   slippage and fees);
   the last candle's equity already includes this closing cost.

Limitations: no simulation of liquidation, margin, partial fills or volume limits. At leverage 1,
a long cannot lose more than its capital; a short can still drive equity negative if price more
than doubles — the engine only
stops opening new positions, it does not liquidate. With leverage > 1 results are optimistic near
the liquidation price.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration, check_ohlcv
from rinng.backtest import metrics
from rinng.backtest.costs import CostModel
from rinng.store.schemas import TIME
from rinng.strategy.base import validate_signals

TRADE_SCHEMA: dict[str, pl.DataType] = {
    "signal_time": TIME,
    "entry_time": TIME,
    "exit_time": TIME,
    "side": pl.String(),
    "entry_price": pl.Float64(),
    "exit_price": pl.Float64(),
    "qty": pl.Float64(),
    "fees": pl.Float64(),
    "funding": pl.Float64(),
    "pnl": pl.Float64(),
    "return": pl.Float64(),
    "entry_reason": pl.String(),
    "exit_reason": pl.String(),
}

EQUITY_SCHEMA: dict[str, pl.DataType] = {
    "time": TIME,
    "equity": pl.Float64(),
    "position": pl.Float64(),  # signed qty at candle close: > 0 long, < 0 short
}


@dataclass
class Result:
    trades: pl.DataFrame
    equity: pl.DataFrame
    summary: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Position:
    direction: int
    qty: float
    entry_price: float
    entry_time: Any
    signal_time: Any
    entry_fee: float
    reason: str
    stop: float | None
    take_profit: float | None
    funding: float = 0.0


def _ms(series: pl.Series) -> np.ndarray:
    return series.dt.epoch("ms").to_numpy()


def _funding_by_bar(funding: pl.DataFrame | None, open_ms: np.ndarray, end_ms: int) -> dict:
    out: dict[int, list[tuple[float, float | None]]] = {}
    if funding is None or funding.is_empty():
        return out
    frame = funding.sort("funding_time")
    marks = frame["mark_price"].to_list() if "mark_price" in frame.columns else [None] * len(frame)
    for t, rate, mark in zip(
        _ms(frame["funding_time"]), frame["rate"].to_list(), marks, strict=True
    ):
        if t < open_ms[0] or t >= end_ms or rate is None:
            continue
        i = int(np.searchsorted(open_ms, t, side="right")) - 1
        out.setdefault(i, []).append((float(rate), mark))
    return out


def _beyond(direction: int, level: float | None, price: float, adverse: bool) -> bool:
    """Whether price touched/crossed `level`. adverse=True: adverse side (stop), False: favourable
    side (take-profit). Adverse for long is price <= level, for short price >= level."""
    if level is None:
        return False
    return (price <= level) if (direction > 0) == adverse else (price >= level)


def run(
    signals: pl.DataFrame,
    ohlcv: pl.DataFrame,
    costs: CostModel | None = None,
    funding: pl.DataFrame | None = None,
    initial_equity: float = 10_000,
    leverage: float = 1.0,
) -> Result:
    """Run a backtest. See the fill rules in the module docstring.

    `ohlcv`: curated candles of one symbol and timeframe. `funding`: the `funding` table
    (funding_time, rate, optional mark_price) of the same symbol. The engine does not read files.
    """
    costs = costs or CostModel()
    if initial_equity <= 0 or leverage <= 0:
        raise ValueError("initial_equity and leverage must be > 0")
    sig = validate_signals(signals)
    symbol, timeframe = check_ohlcv(ohlcv)
    duration = bar_duration(timeframe)
    dur_ms = int(duration.total_seconds() * 1000)

    open_times = ohlcv["open_time"].to_list()
    open_ms = _ms(ohlcv["open_time"])
    o, h, lo, c = (ohlcv[k].to_numpy().astype(float) for k in ("open", "high", "low", "close"))
    n = len(o)
    end_ms = int(open_ms[-1]) + dur_ms

    pending: dict[int, dict[str, Any]] = {}
    unfilled = ignored = 0
    for row, bar in zip(
        sig.iter_rows(named=True),
        np.searchsorted(open_ms, _ms(sig["time"]), side="left"),
        strict=True,
    ):
        if bar >= n:
            unfilled += 1
            continue
        if int(bar) in pending:
            ignored += 1
        pending[int(bar)] = row
    fund = _funding_by_bar(funding, open_ms, end_ms)

    cash = float(initial_equity)
    pos: _Position | None = None
    trades: list[dict[str, Any]] = []
    eq_values = np.empty(n)
    eq_pos = np.zeros(n)

    def close(price: float, time: Any, reason: str, maker: bool = False) -> None:
        nonlocal cash, pos
        assert pos is not None
        fee = costs.fee(pos.qty, price, maker=maker)
        gross = pos.direction * pos.qty * (price - pos.entry_price)
        cash += gross - fee
        pnl = gross - pos.entry_fee - fee + pos.funding
        margin = pos.qty * pos.entry_price / leverage
        trades.append(
            {
                "signal_time": pos.signal_time,
                "entry_time": pos.entry_time,
                "exit_time": time,
                "side": "long" if pos.direction > 0 else "short",
                "entry_price": pos.entry_price,
                "exit_price": price,
                "qty": pos.qty,
                "fees": pos.entry_fee + fee,
                "funding": pos.funding,
                "pnl": pnl,
                "return": pnl / margin,
                "entry_reason": pos.reason,
                "exit_reason": reason,
            }
        )
        pos = None

    for i in range(n):
        # 1. Fill signals at the open.
        s = pending.get(i)
        if s is not None:
            target = (
                0 if s["side"] == "flat" or s["size"] == 0 else (1 if s["side"] == "long" else -1)
            )
            if pos is not None and pos.direction == target:
                ignored += 1
            else:
                if pos is not None:
                    close(costs.fill_price(o[i], buy=pos.direction < 0), open_times[i], "signal")
                if target != 0 and cash > 0:
                    price = costs.fill_price(o[i], buy=target > 0)
                    qty = s["size"] * cash * leverage / price
                    fee = costs.fee(qty, price)
                    cash -= fee
                    pos = _Position(
                        target, qty, price, open_times[i], s["time"], fee, s["reason"],
                        s["stop"], s["take_profit"],
                    )  # fmt: skip

        # 2. Funding on the open position.
        for rate, mark in fund.get(i, ()):
            if pos is not None:
                flow = costs.funding_flow(pos.direction, pos.qty, mark or o[i], rate)
                cash += flow
                pos.funding += flow

        # 3. Stop / take-profit within the candle.
        if pos is not None:
            d, stop, tp = pos.direction, pos.stop, pos.take_profit
            exit_px = reason = None
            if _beyond(d, stop, o[i], adverse=True):
                exit_px, reason = o[i], "stop_gap"
            elif _beyond(d, tp, o[i], adverse=False):
                exit_px, reason = o[i], "take_profit_gap"
            elif _beyond(d, stop, lo[i] if d > 0 else h[i], adverse=True):
                exit_px, reason = stop, "stop"
            elif _beyond(d, tp, h[i] if d > 0 else lo[i], adverse=False):
                exit_px, reason = tp, "take_profit"
            if reason is not None:
                limit = costs.take_profit_limit and reason.startswith("take_profit")
                fill = exit_px if limit else costs.fill_price(exit_px, buy=d < 0)
                close(fill, open_times[i], reason, maker=limit)

        # 4. Mark to market at the close.
        if pos is not None:
            eq_values[i] = cash + pos.direction * pos.qty * (c[i] - pos.entry_price)
            eq_pos[i] = pos.direction * pos.qty
        else:
            eq_values[i] = cash

    if pos is not None:
        close(costs.fill_price(c[-1], buy=pos.direction < 0), open_times[-1] + duration, "end")
        eq_values[-1] = cash

    trades_df = (
        pl.DataFrame(trades, schema=TRADE_SCHEMA) if trades else pl.DataFrame(schema=TRADE_SCHEMA)
    )
    equity_df = pl.DataFrame(
        {"time": ohlcv["open_time"] + duration, "equity": eq_values, "position": eq_pos},
        schema=EQUITY_SCHEMA,
    )
    summary = metrics.summarize(
        equity_df,
        trades_df,
        initial_equity=float(initial_equity),
        periods=metrics.periods_per_year(timeframe),
    )
    summary.update(signals_total=sig.height, signals_unfilled=unfilled, signals_ignored=ignored)
    meta = {
        "symbol": symbol,
        "timeframe": timeframe,
        "start": open_times[0].isoformat(),
        "end": (open_times[-1] + duration).isoformat(),
        "costs": costs.to_dict(),
        "initial_equity": float(initial_equity),
        "leverage": leverage,
    }
    return Result(trades_df, equity_df, summary, meta)
