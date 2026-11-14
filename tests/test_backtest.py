"""Test engine backtest, chi phí, metric và lưu kết quả bằng phép tính tay."""

import json
import math
from datetime import timedelta

import numpy as np
import polars as pl
import pytest

from rinng.backtest import metrics
from rinng.backtest.costs import CostModel
from rinng.backtest.engine import run
from rinng.backtest.report import compare, save_result, split_in_out
from rinng.store.schemas import TIME
from rinng.strategy.base import signals_frame
from rinng.strategy.baselines import BuyAndHold, EmaCross, LinearRegression
from tests.analysis.helpers import T0, make_ohlcv, random_walk

H = timedelta(hours=1)
S = 0.0001  # slippage 1 bps
F = 0.0005  # taker
COSTS = CostModel(taker_fee=F, maker_fee=0.0002, slippage_bps=1.0)


def funding_frame(rows):
    return pl.DataFrame(
        {
            "funding_time": [t for t, _, _ in rows],
            "rate": [r for _, r, _ in rows],
            "mark_price": [m for _, _, m in rows],
        },
        schema={"funding_time": TIME, "rate": pl.Float64(), "mark_price": pl.Float64()},
    )


# ---------- EmaCross trên chuỗi dựng tay ----------

CLOSES = [100.0, 100, 100, 100, 104, 106, 107, 103, 98, 95, 96, 97]
OPENS = [100.0, 100, 100, 100, 100.5, 104.5, 106.2, 107.1, 102.4, 97.6, 95.3, 96.4]


def _ema(values, span):
    a = 2 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(a * v + (1 - a) * out[-1])
    return out


def test_ema_cross_signals_match_hand_ema():
    fast, slow = _ema(CLOSES, 2), _ema(CLOSES, 4)
    # Bốn nến đầu phẳng (hai EMA bằng nhau); nến 4 fast > slow; nến 8 fast < slow.
    assert fast[3] == slow[3] and fast[4] > slow[4] and fast[7] > slow[7] and fast[8] < slow[8]
    sig = EmaCross(2, 4).signals(make_ohlcv(CLOSES, opens=OPENS), None, None)
    assert sig["side"].to_list() == ["long", "short"]
    # time = lúc đóng nến 4 và nến 8.
    assert sig["time"].to_list() == [T0 + 5 * H, T0 + 9 * H]


def test_ema_cross_each_trade_matches_hand_calculation():
    ohlcv = make_ohlcv(CLOSES, opens=OPENS)
    res = run(EmaCross(2, 4).signals(ohlcv, None, None), ohlcv, COSTS, initial_equity=10_000)
    t = res.trades.to_dicts()
    assert len(t) == 2

    # Lệnh 1: long, khớp ở giá mở nến 5 (104.5) + slippage; thoát ở giá mở nến 9 (97.6).
    e1 = 104.5 * (1 + S)
    q1 = 10_000 / e1
    x1 = 97.6 * (1 - S)
    fees1 = q1 * e1 * F + q1 * x1 * F
    pnl1 = q1 * (x1 - e1) - fees1
    assert t[0]["side"] == "long"
    assert t[0]["entry_time"] == T0 + 5 * H and t[0]["exit_time"] == T0 + 9 * H
    assert t[0]["entry_price"] == pytest.approx(e1) and t[0]["exit_price"] == pytest.approx(x1)
    assert t[0]["qty"] == pytest.approx(q1)
    assert t[0]["fees"] == pytest.approx(fees1)
    assert t[0]["pnl"] == pytest.approx(pnl1)
    assert t[0]["return"] == pytest.approx(pnl1 / 10_000)
    assert t[0]["exit_reason"] == "signal"

    # Lệnh 2: short ở cùng giá mở nến 9 với vốn còn lại; đóng ở close nến cuối (97) khi hết dữ liệu.
    eq1 = 10_000 + pnl1
    e2 = 97.6 * (1 - S)
    q2 = eq1 / e2
    x2 = 97.0 * (1 + S)
    fees2 = q2 * e2 * F + q2 * x2 * F
    pnl2 = -q2 * (x2 - e2) - fees2
    assert t[1]["side"] == "short"
    assert t[1]["entry_time"] == T0 + 9 * H and t[1]["exit_time"] == T0 + 12 * H
    assert t[1]["entry_price"] == pytest.approx(e2) and t[1]["exit_price"] == pytest.approx(x2)
    assert t[1]["qty"] == pytest.approx(q2)
    assert t[1]["fees"] == pytest.approx(fees2)
    assert t[1]["pnl"] == pytest.approx(pnl2)
    assert t[1]["exit_reason"] == "end"

    assert res.summary["final_equity"] == pytest.approx(10_000 + pnl1 + pnl2)
    # Equity mark-to-market: nến 6 đóng 107 khi đang long lệnh 1.
    eq6 = 10_000 - q1 * e1 * F + q1 * (107 - e1)
    assert res.equity["equity"][6] == pytest.approx(eq6)
    assert res.equity["position"][6] == pytest.approx(q1)
    assert res.equity["position"][3] == 0
    assert res.equity["time"][0] == T0 + H


# ---------- Buy and hold, funding ----------


def test_buy_and_hold_return_is_price_change_minus_costs():
    closes = [100.0, 102, 101, 105, 110, 108]
    opens = [100.0, 101, 102.5, 100.5, 105.5, 110.2]
    ohlcv = make_ohlcv(closes, opens=opens)
    res = run(BuyAndHold().signals(ohlcv, None, None), ohlcv, COSTS)
    entry = 101 * (1 + S)  # giá mở nến 1
    exit_ = 108 * (1 - S)  # close nến cuối
    expected = (exit_ / entry) - 1 - F - F * exit_ / entry
    assert res.summary["total_return"] == pytest.approx(expected)
    no_cost = run(BuyAndHold().signals(ohlcv, None, None), ohlcv, CostModel(0, 0, 0))
    assert no_cost.summary["total_return"] == pytest.approx(108 / 101 - 1)


def _flat_bars(n=6, price=100.0):
    return make_ohlcv([price] * n)


@pytest.mark.parametrize("side, sign", [("long", -1), ("short", 1)])
def test_funding_sign(side, sign):
    ohlcv = _flat_bars()
    sig = signals_frame([{"time": T0 + H, "side": side}])  # vào ở nến 1
    rate, mark = 0.0001, 100.0
    funding = funding_frame(
        [
            (T0, rate, mark),  # trước khi vào → không tính
            (T0 + 2 * H, rate, mark),
            (T0 + 4 * H, -rate / 2, None),  # không có mark → dùng giá mở nến
        ]
    )
    nocost = CostModel(0, 0, 0)
    res = run(sig, ohlcv, nocost, funding=funding)
    qty = 10_000 / 100.0
    expected = sign * (qty * mark * rate) - sign * (qty * 100.0 * rate / 2)
    assert res.trades["funding"][0] == pytest.approx(expected)
    assert res.summary["final_equity"] == pytest.approx(10_000 + expected)
    assert res.summary["funding"] == pytest.approx(expected)


def test_funding_after_exit_not_charged():
    ohlcv = _flat_bars()
    sig = signals_frame([{"time": T0 + H, "side": "long"}, {"time": T0 + 3 * H, "side": "flat"}])
    funding = funding_frame([(T0 + 3 * H, 0.01, 100.0), (T0 + 2 * H, 0.001, 100.0)])
    res = run(sig, ohlcv, CostModel(0, 0, 0), funding=funding)
    # Đóng ở giá mở nến 3 trước khi tính funding lúc T0+3h; chỉ khoản lúc T0+2h bị tính.
    assert res.trades["funding"][0] == pytest.approx(-100 * 100 * 0.001)


# ---------- Stop / take-profit ----------


def test_stop_and_take_profit_same_bar_stop_wins():
    closes = [100.0, 100, 100, 100]
    highs = [100.0, 100.5, 106, 100]
    lows = [100.0, 99.5, 94, 100]
    ohlcv = make_ohlcv(closes, highs=highs, lows=lows)
    sig = signals_frame([{"time": T0 + H, "side": "long", "stop": 95.0, "take_profit": 105.0}])
    res = run(sig, ohlcv, COSTS)
    t = res.trades.row(0, named=True)
    assert t["exit_reason"] == "stop"
    assert t["exit_time"] == T0 + 2 * H
    assert t["exit_price"] == pytest.approx(95.0 * (1 - S))
    assert res.trades.height == 1  # đứng ngoài sau stop


def test_take_profit_only_and_short_stop():
    ohlcv = make_ohlcv([100.0] * 4, highs=[100.0, 100.5, 103, 100], lows=[100.0, 99.5, 99, 100])
    long = signals_frame([{"time": T0 + H, "side": "long", "stop": 95.0, "take_profit": 102.0}])
    t = run(long, ohlcv, COSTS).trades.row(0, named=True)
    assert t["exit_reason"] == "take_profit"
    assert t["exit_price"] == pytest.approx(102.0 * (1 - S))
    limit = CostModel(F, 0.0002, 1.0, take_profit_limit=True)
    t = run(long, ohlcv, limit).trades.row(0, named=True)
    assert t["exit_price"] == pytest.approx(102.0)
    assert t["fees"] == pytest.approx(t["qty"] * 100 * (1 + S) * F + t["qty"] * 102.0 * 0.0002)
    short = signals_frame([{"time": T0 + H, "side": "short", "stop": 102.5, "take_profit": 90.0}])
    t = run(short, ohlcv, COSTS).trades.row(0, named=True)
    assert t["exit_reason"] == "stop"
    assert t["exit_price"] == pytest.approx(102.5 * (1 + S))


def test_gap_through_stop_fills_at_open():
    closes = [100.0, 100, 90, 91]
    opens = [100.0, 100, 92, 90]  # nến 2 mở 92, dưới stop 95
    ohlcv = make_ohlcv(closes, opens=opens)
    sig = signals_frame([{"time": T0 + H, "side": "long", "stop": 95.0}])
    t = run(sig, ohlcv, COSTS).trades.row(0, named=True)
    assert t["exit_reason"] == "stop_gap"
    assert t["exit_time"] == T0 + 2 * H
    assert t["exit_price"] == pytest.approx(92.0 * (1 - S))


# ---------- Chống nhìn trước ----------


def test_signal_never_fills_on_its_own_bar():
    ohlcv = random_walk(300)
    sig = LinearRegression(window=20).signals(ohlcv, None, None)
    res = run(sig, ohlcv, COSTS)
    assert res.trades.height > 3
    opens = dict(zip(ohlcv["open_time"].to_list(), ohlcv["open"].to_list(), strict=True))
    for t in res.trades.iter_rows(named=True):
        # Nến sinh tín hiệu bắt đầu lúc signal_time − 1h; khớp ở nến bắt đầu lúc signal_time.
        assert t["entry_time"] == t["signal_time"]
        assert t["entry_time"] > t["signal_time"] - H
        direction = 1 if t["side"] == "long" else -1
        assert t["entry_price"] == pytest.approx(opens[t["entry_time"]] * (1 + direction * S))


def test_signal_off_grid_fills_at_next_open():
    ohlcv = make_ohlcv([100.0, 101, 102, 103], opens=[100.0, 100.4, 101.3, 102.2])
    # Tín hiệu lúc giữa nến 1 (chưa đóng) → không được khớp ở nến 1, mà ở nến 2.
    sig = signals_frame([{"time": T0 + 1.5 * H, "side": "long"}])
    res = run(sig, ohlcv, CostModel(0, 0, 0))
    assert res.trades["entry_time"][0] == T0 + 2 * H
    assert res.trades["entry_price"][0] == pytest.approx(101.3)


def test_signal_after_last_bar_unfilled_and_same_side_ignored():
    ohlcv = _flat_bars(4)
    sig = signals_frame(
        [
            {"time": T0 + H, "side": "long"},
            {"time": T0 + 2 * H, "side": "long"},  # cùng chiều → bỏ qua
            {"time": T0 + 4 * H, "side": "short"},  # sau nến cuối
        ]
    )
    res = run(sig, ohlcv, COSTS)
    assert res.trades.height == 1
    assert res.summary["signals_ignored"] == 1 and res.summary["signals_unfilled"] == 1


def test_random_walk_has_no_edge_without_costs():
    # Engine không có bug lợi thế: trên random walk, LR không được lãi lớn có hệ thống.
    sharpes = []
    for seed in range(8):
        ohlcv = random_walk(1500, seed=seed)
        res = run(LinearRegression(20).signals(ohlcv, None, None), ohlcv, CostModel(0, 0, 0))
        sharpes.append(res.summary["sharpe"])
    assert abs(np.mean(sharpes)) < 1.5


# ---------- Metric ----------


def test_metrics_on_hand_built_equity():
    equity = np.array([110.0, 99.0, 108.9, 130.68])
    rets = metrics.returns(equity, 100.0)
    assert rets == pytest.approx([0.1, -0.1, 0.1, 0.2])
    mean = 0.075
    sd = math.sqrt(sum((r - mean) ** 2 for r in [0.1, -0.1, 0.1, 0.2]) / 3)
    p = metrics.periods_per_year("1h")
    assert p == 8760
    assert metrics.sharpe(rets, p) == pytest.approx(mean / sd * math.sqrt(8760))
    assert metrics.sortino(rets, p) == pytest.approx(mean / math.sqrt(0.01 / 4) * math.sqrt(8760))
    assert metrics.max_drawdown(equity, 100.0) == pytest.approx(99 / 110 - 1)
    assert metrics.periods_per_year("1d") == 365
    assert metrics.periods_per_year("4h") == 2190


def test_summarize_trade_stats():
    times = [T0 + i * H for i in range(4)]
    equity = pl.DataFrame(
        {"time": times, "equity": [110.0, 99.0, 108.9, 130.68], "position": [1.0, 0, 0, 1]},
        schema={"time": TIME, "equity": pl.Float64(), "position": pl.Float64()},
    )
    trades = pl.DataFrame(
        {
            "pnl": [30.0, -10.0, 20.0],
            "qty": [1.0, 1, 1],
            "entry_price": [100.0, 100, 100],
            "exit_price": [100.0, 100, 100],
            "fees": [0.1, 0.1, 0.1],
            "funding": [0.0, 0, 0],
        }
    )
    s = metrics.summarize(equity, trades, initial_equity=100.0, periods=8760)
    assert s["trades"] == 3
    assert s["win_rate"] == pytest.approx(2 / 3)
    assert s["profit_factor"] == pytest.approx(5.0)
    assert s["expectancy"] == pytest.approx(40 / 3)
    assert s["exposure"] == pytest.approx(0.5)
    assert s["total_return"] == pytest.approx(0.3068)
    years = 4 / 8760
    assert s["cagr"] == pytest.approx(1.3068 ** (1 / years) - 1)
    assert s["calmar"] == pytest.approx(s["cagr"] / (1 - 99 / 110))
    mean_eq = np.mean([110.0, 99.0, 108.9, 130.68])
    assert s["turnover"] == pytest.approx(600 / 2 / mean_eq / years)


# ---------- Report ----------


def test_split_in_out():
    ohlcv = _flat_bars(10)
    ins, outs = split_in_out(ohlcv, T0 + 6 * H)
    assert ins.height == 6 and outs.height == 4
    assert outs["open_time"][0] == T0 + 6 * H


def test_save_result_writes_all_files(tmp_path):
    ohlcv = random_walk(200)
    strat = EmaCross(5, 20)
    res = run(strat.signals(ohlcv, None, None), ohlcv, COSTS)
    out = save_result(res, tmp_path / "run1", {"strategy": strat.name, "params": strat.params})
    for name in ("trades.parquet", "equity.parquet", "summary.json", "config.json"):
        assert (out / name).exists()
    cfg = json.loads((out / "config.json").read_text())
    assert cfg["strategy"] == "ema_cross" and cfg["params"] == {"fast": 5, "slow": 20}
    assert len(cfg["params_hash"]) == 12
    assert cfg["costs"]["taker_fee"] == F
    assert cfg["period"]["start"].startswith("2026-01-05")
    summary = json.loads((out / "summary.json").read_text())
    assert summary["trades"] == res.trades.height
    assert pl.read_parquet(out / "trades.parquet").height == res.trades.height


def test_compare_table():
    ohlcv = random_walk(200)
    results = {
        "bh": run(BuyAndHold().signals(ohlcv, None, None), ohlcv, COSTS),
        "lr": run(LinearRegression(40).signals(ohlcv, None, None), ohlcv, COSTS),
    }
    table = compare(results)
    assert table["name"].to_list() == ["bh", "lr"]
    assert {"sharpe", "max_drawdown", "trades"} <= set(table.columns)
