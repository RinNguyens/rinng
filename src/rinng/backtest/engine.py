"""Engine backtest event-driven theo nến cho MỘT symbol perpetual.

Quy tắc khớp lệnh:

1. Tín hiệu có `time = T` (lúc đóng nến sinh ra nó) khớp ở GIÁ MỞ của nến có `open_time == T`,
   tức nến kế tiếp. Nếu `time` không trùng mốc nến nào thì khớp ở nến đầu tiên có
   `open_time >= time`. Vì vậy một tín hiệu không bao giờ khớp ở chính nến sinh ra nó.
   Tín hiệu sau nến cuối không được khớp (đếm vào `signals_unfilled`). Nhiều tín hiệu rơi
   vào cùng một nến thì chỉ tín hiệu sau cùng có hiệu lực (đếm vào `signals_ignored`).
2. Một tín hiệu mới thay thế vị thế hiện tại: đóng vị thế cũ (lý do "signal") rồi mở vị thế
   mới ở cùng giá mở. "flat" hoặc size = 0 chỉ đóng. Tín hiệu cùng chiều với vị thế đang mở
   bị bỏ qua (không đổi cỡ, không đổi stop/TP; đếm vào `signals_ignored`).
3. Lệnh vào/ra là market: giá khớp = giá tham chiếu cộng slippage bất lợi, phí taker trên
   notional khớp (xem rinng.backtest.costs; tùy chọn take-profit dạng limit dùng phí maker).
4. Stop/take-profit kiểm trong từng nến kể từ nến vào lệnh (vào ở giá mở nên phần còn lại của
   nến đó đã là "sau khi vào"), bằng high/low:
   - giá mở đã vượt qua stop (gap) → thoát ở giá mở, lý do "stop_gap";
   - giá mở đã vượt qua take-profit → thoát ở giá mở, lý do "take_profit_gap";
   - stop và take-profit cùng chạm trong một nến → coi STOP chạm trước (bảo thủ), lý do "stop";
   - chỉ một mức chạm → thoát ở đúng mức đó, lý do "stop" hoặc "take_profit".
   Thoát bởi stop/TP thì đứng ngoài tới tín hiệu kế tiếp.
5. Cỡ vị thế: qty = size × equity lúc vào × leverage / giá khớp vào. Equity lúc vào = tiền mặt
   sau khi đóng vị thế cũ; phí vào trừ thêm vào tiền mặt (nên notional + phí nhỉnh hơn equity
   một chút ở size = 1). Không vào lệnh mới khi equity <= 0.
6. Funding: mỗi dòng funding gán vào nến có open_time <= funding_time < open_time kế tiếp và
   tính trên vị thế sau khi khớp tín hiệu ở giá mở nến đó, trước khi kiểm stop/TP. Với
   funding_time trùng mốc mở nến (trường hợp thường gặp) điều này nghĩa là vị thế mở đúng lúc
   funding_time được tính, vị thế đóng đúng lúc đó thì không.
7. Equity mark-to-market theo giá đóng mỗi nến; cột `time` của equity là lúc đóng nến.
   Hết dữ liệu mà còn vị thế thì đóng ở giá đóng nến cuối (lý do "end", có slippage và phí);
   equity của nến cuối đã gồm chi phí đóng này.

Giới hạn: không mô phỏng thanh lý, margin, khớp một phần hay giới hạn khối lượng. Ở đòn bẩy 1,
long không thể lỗ quá vốn; short vẫn có thể làm equity âm nếu giá tăng hơn gấp đôi — engine chỉ
ngừng mở lệnh mới, không thanh lý. Với leverage > 1 kết quả lạc quan hơn thực tế ở vùng gần
giá thanh lý.
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
    "position": pl.Float64(),  # qty có dấu lúc đóng nến: > 0 long, < 0 short
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
    """Giá đã chạm/vượt mức `level` chưa. adverse=True: phía bất lợi (stop), False: phía có
    lợi (take-profit). Long bất lợi là giá <= mức, short bất lợi là giá >= mức."""
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
    """Chạy backtest. Xem quy tắc khớp lệnh ở docstring của module.

    `ohlcv`: nến curated của một symbol, một khung thời gian. `funding`: bảng `funding`
    (funding_time, rate, mark_price tùy chọn) của cùng symbol. Engine không đọc file.
    """
    costs = costs or CostModel()
    if initial_equity <= 0 or leverage <= 0:
        raise ValueError("initial_equity và leverage phải > 0")
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
        # 1. Khớp tín hiệu ở giá mở.
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

        # 2. Funding trên vị thế đang mở.
        for rate, mark in fund.get(i, ()):
            if pos is not None:
                flow = costs.funding_flow(pos.direction, pos.qty, mark or o[i], rate)
                cash += flow
                pos.funding += flow

        # 3. Stop / take-profit trong nến.
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

        # 4. Mark-to-market ở giá đóng.
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
