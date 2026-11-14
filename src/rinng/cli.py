"""Điểm vào dòng lệnh: `rinng <lệnh>`."""

import asyncio
import logging
from pathlib import Path

import typer

from rinng.config import DEFAULT_CONFIG, load_settings
from rinng.exchanges.check import run_checks

app = typer.Typer(no_args_is_help=True, help="rinng: phân tích quant cho crypto")


@app.command()
def check() -> None:
    """Kiểm tra kết nối tới Binance và OKX, in giới hạn tốc độ đang áp dụng."""
    results = run_checks()
    for r in results:
        mark = "OK  " if r.ok else "LỖI "
        latency = f"{r.latency_ms} ms" if r.latency_ms is not None else "-"
        typer.echo(f"{mark}{r.name:<14} HTTP {r.status}  {latency}  {r.detail}")
        for limit in r.rate_limits:
            typer.echo(f"      {limit}")
    if not all(r.ok for r in results):
        raise typer.Exit(code=1)


@app.command()
def config(path: Path = DEFAULT_CONFIG) -> None:
    """Đọc file cấu hình và in ra nội dung đã kiểm tra."""
    settings = load_settings(path)
    typer.echo(f"data_dir: {settings.data_dir}")
    typer.echo(f"nến gốc: {settings.base_timeframe}; khung phân tích: {settings.timeframes}")
    for inst in settings.instruments:
        typer.echo(f"  {inst.id} ({inst.kind})  binance={inst.binance}  okx={inst.okx}")


@app.command()
def collect(
    duration: float = typer.Option(None, help="Dừng sau số giây này; bỏ trống để chạy mãi"),
    path: Path = DEFAULT_CONFIG,
) -> None:
    """Chạy bộ thu realtime (WebSocket + poller 5 phút), ghi vào data/raw."""
    from rinng.ingest.collector.service import collect as run

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stats = asyncio.run(run(load_settings(path), duration))
    for exchange, values in stats.items():
        typer.echo(f"{exchange}: {values}")


def _date(value: str):
    from datetime import date

    return date.fromisoformat(value)


@app.command()
def backfill(
    start: str = typer.Option("2020-01-01", help="Ngày bắt đầu, YYYY-MM-DD"),
    exchange: list[str] = typer.Option(["binance"], help="binance và/hoặc okx"),
    dataset: list[str] = typer.Option(
        ["klines_1m", "funding", "metrics"],
        help="Dump Binance: klines_1m, funding, metrics, agg_trades, book_depth",
    ),
    path: Path = DEFAULT_CONFIG,
) -> None:
    """Tải lịch sử vào data/raw rồi chạy curate."""
    from rinng.ingest.backfill import backfill as run
    from rinng.pipeline.curate import curate as do_curate
    from rinng.store.paths import DataPaths

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = load_settings(path)
    reports = run(settings, _date(start), exchanges=tuple(exchange), datasets=tuple(dataset))
    for key, r in reports.items():
        missing = f", thiếu {len(r.missing)} file" if r.missing else ""
        typer.echo(f"{key}: tải {r.downloaded} file dump{missing}, REST {r.rest_rows}")
    totals = do_curate(DataPaths(settings.data_dir), settings)
    typer.echo(f"curate: {totals}")


@app.command()
def curate(path: Path = DEFAULT_CONFIG) -> None:
    """Đưa mọi file mới trong data/raw vào data/curated."""
    from rinng.pipeline.curate import curate as do_curate
    from rinng.store.paths import DataPaths

    settings = load_settings(path)
    typer.echo(do_curate(DataPaths(settings.data_dir), settings))


@app.command()
def resample(path: Path = DEFAULT_CONFIG) -> None:
    """Gộp nến 1m đã curated lên các khung trong cấu hình."""
    from rinng.store.paths import DataPaths
    from rinng.store.reader import read_curated
    from rinng.store.resample import resample_ohlcv
    from rinng.store.schemas import OHLCV
    from rinng.store.writer import write_curated

    settings = load_settings(path)
    paths = DataPaths(settings.data_dir)
    for inst in settings.instruments:
        for ex in ("binance", "okx"):
            base = read_curated(paths, OHLCV, exchange=ex, symbol=inst.id, timeframe="1m")
            if base.is_empty():
                continue
            for tf in settings.timeframes:
                out = resample_ohlcv(base, tf)
                write_curated(paths, OHLCV, out)
                typer.echo(f"{ex} {inst.id} {tf}: {out.height} nến")


@app.command()
def validate(
    sample_days: int = typer.Option(3, help="Số ngày gần nhất để so nến 1h với sàn (0 = bỏ)"),
    path: Path = DEFAULT_CONFIG,
) -> None:
    """Báo cáo nến thiếu/trùng/vô lý, so nến tự gộp với sàn, so hai sàn."""
    from datetime import UTC, datetime, timedelta

    from rinng.exchanges.binance import Binance
    from rinng.exchanges.okx import Okx
    from rinng.pipeline.validate import check_candles, compare_with_exchange, cross_exchange
    from rinng.store.paths import DataPaths
    from rinng.store.reader import read_curated
    from rinng.store.schemas import OHLCV

    settings = load_settings(path)
    paths = DataPaths(settings.data_dir)
    apis = {"binance": Binance(), "okx": Okx()}
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for inst in settings.instruments:
        base = {}
        for ex in ("binance", "okx"):
            m1 = read_curated(paths, OHLCV, exchange=ex, symbol=inst.id, timeframe="1m")
            if m1.is_empty():
                continue
            base[ex] = m1
            r = check_candles(m1)
            typer.echo(
                f"{ex} {inst.id} 1m: {r.rows} nến {r.first} → {r.last}; thiếu {r.missing} "
                f"({len(r.gaps)} khoảng); trùng {r.duplicates}; OHLC vô lý {r.invalid_ohlc}"
            )
            for a, b in r.gaps[:5]:
                typer.echo(f"    thiếu {a} → {b}")
            if sample_days:
                h1 = read_curated(paths, OHLCV, exchange=ex, symbol=inst.id, timeframe="1h")
                if not h1.is_empty():
                    venue = getattr(inst, ex)
                    res = compare_with_exchange(
                        h1, apis[ex], venue, "1h", end - timedelta(days=sample_days), end
                    )
                    typer.echo(f"    1h tự gộp so với sàn: {res}")
        if len(base) == 2:
            typer.echo(f"  binance vs okx 1m: {cross_exchange(base['binance'], base['okx'])}")


def _when(value: str | None):
    from datetime import UTC, datetime

    return datetime.fromisoformat(value).replace(tzinfo=UTC) if value else None


@app.command()
def analyze(
    symbol: str = typer.Option("BTC-USDT-PERP"),
    timeframe: str = typer.Option("4h"),
    exchange: str = typer.Option("binance"),
    module: list[str] = typer.Option([], help="Bỏ trống = mọi module"),
    start: str = typer.Option(None, help="YYYY-MM-DD"),
    path: Path = DEFAULT_CONFIG,
) -> None:
    """Chạy các module phân tích, ghi vào data/features và data/events."""
    from rinng.pipeline.run import analyze as run
    from rinng.store.paths import DataPaths

    settings = load_settings(path)
    out = run(
        DataPaths(settings.data_dir),
        exchange,
        symbol,
        timeframe,
        module or None,
        start=_when(start),
    )
    for name, (features, events) in out.items():
        f = "-" if features is None else f"{features.height} dòng × {features.width} cột"
        e = (
            "-"
            if events is None
            else ", ".join(f"{k}={n}" for k, n in events.group_by("kind").len().sort("kind").rows())
        )
        typer.echo(f"{name}: features {f}; events {e}")


@app.command()
def backtest(
    strategy: list[str] = typer.Option(
        ["smc_break", "ema_cross", "linreg", "buy_hold"],
        help="smc_break, ema_cross, linreg, buy_hold",
    ),
    symbol: str = typer.Option("BTC-USDT-PERP"),
    timeframe: str = typer.Option("4h"),
    exchange: str = typer.Option("binance"),
    start: str = typer.Option(None, help="YYYY-MM-DD"),
    split: str = typer.Option(None, help="Mốc tách in/out-of-sample, YYYY-MM-DD"),
    path: Path = DEFAULT_CONFIG,
) -> None:
    """Chạy backtest có phí, slippage, funding; so các chiến lược; lưu vào data/results."""
    import uuid

    import polars as pl

    from rinng.analysis import smc, structure
    from rinng.backtest import engine, report
    from rinng.backtest.costs import CostModel
    from rinng.pipeline.run import load_ohlcv
    from rinng.store.paths import DataPaths
    from rinng.store.reader import read_curated
    from rinng.store.schemas import FUNDING
    from rinng.strategy.baselines import BuyAndHold, EmaCross, LinearRegression
    from rinng.strategy.smc_break import StructureBreak

    settings = load_settings(path)
    paths = DataPaths(settings.data_dir)
    ohlcv = load_ohlcv(paths, exchange, symbol, timeframe, _when(start))
    if ohlcv.is_empty():
        raise typer.BadParameter(f"không có nến {exchange} {symbol} {timeframe}")
    funding = read_curated(paths, FUNDING, exchange=exchange, symbol=symbol)
    events = pl.concat([structure.swings(ohlcv, 5), smc.events(ohlcv)])
    makers = {
        "smc_break": StructureBreak,
        "ema_cross": lambda: EmaCross(20, 50),
        "linreg": lambda: LinearRegression(40),
        "buy_hold": BuyAndHold,
    }
    costs = CostModel()
    segments = {"all": None}
    if split:
        segments = {"in": ("<", _when(split)), "out": (">=", _when(split))}
    previous = sum(1 for _ in paths.results.glob("*/config.json")) if paths.results.exists() else 0
    for seg, cond in segments.items():
        results = {}
        for name in strategy:
            strat = makers[name]()
            signals = strat.signals(ohlcv, None, events)
            bars = ohlcv
            if cond is not None:
                op, when = cond
                keep = (pl.col("time") < when) if op == "<" else (pl.col("time") >= when)
                signals = signals.filter(keep)
                bars = ohlcv.filter(
                    (pl.col("open_time") < when) if op == "<" else (pl.col("open_time") >= when)
                )
            result = engine.run(signals, bars, costs, funding)
            run_id = f"{bars['open_time'][0]:%Y%m%d}-{name}-{seg}-{uuid.uuid4().hex[:6]}"
            report.save_result(
                result,
                paths.results / run_id,
                {
                    "strategy": name,
                    "params": strat.params,
                    "segment": seg,
                    "exchange": exchange,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "costs": costs.__dict__,
                },
            )
            results[name] = result
        table = report.compare(results)
        cols = [
            c
            for c in (
                "name",
                "total_return",
                "cagr",
                "sharpe",
                "max_drawdown",
                "n_trades",
                "win_rate",
                "profit_factor",
            )
            if c in table.columns
        ]
        typer.echo(
            f"\n== {seg} ({bars['open_time'][0]:%Y-%m-%d} → {bars['open_time'][-1]:%Y-%m-%d})"
        )
        with pl.Config(tbl_rows=20, tbl_cols=12, float_precision=3):
            typer.echo(table.select(cols))
    typer.echo(
        f"\nĐã lưu vào {paths.results}. Số lần chạy backtest đã lưu trước lần này: {previous}"
        " (càng thử nhiều cấu hình, kết quả tốt nhất càng dễ là do may)."
    )


@app.command()
def dashboard(path: Path = DEFAULT_CONFIG, port: int = 8501) -> None:
    """Mở dashboard Streamlit (chart có lớp phủ, kết quả backtest)."""
    import os
    import subprocess
    import sys

    import rinng.viz

    script = Path(rinng.viz.__file__).parent / "dashboard" / "app.py"
    env = {**os.environ, "RINNG_CONFIG": str(path.resolve())}
    cmd = [sys.executable, "-m", "streamlit", "run", str(script), "--server.port", str(port)]
    raise typer.Exit(subprocess.call(cmd, env=env))


@app.command()
def vpchart(
    symbol: str = typer.Option("BTCUSDT", help="Tên trên Binance USDⓈ-M"),
    weeks: int = typer.Option(10, help="Số tuần"),
    base: str = typer.Option("15m", help="Khung nến để dựng profile"),
    display: str = typer.Option("4h", help="Khung nến để vẽ"),
    out: Path = typer.Option(None, help="File HTML; mặc định data/charts/vp_<symbol>.html"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
    path: Path = DEFAULT_CONFIG,
) -> None:
    """Vẽ volume profile từng tuần kèm nhãn D / P / b / DD từ dữ liệu Binance mới nhất."""
    import webbrowser

    from rinng.viz.vp_chart import fetch_live, figure, weekly_profiles

    base_df, display_df = fetch_live(symbol, base, display, weeks)
    profiles = weekly_profiles(base_df)
    for p in profiles:
        state = "đóng" if p["closed"] else "chưa đóng"
        typer.echo(
            f"tuần {p['start']:%Y-%m-%d} ({state}): {p['shape']:<2}  POC {p['poc']:,.0f}  "
            f"VA {p['val']:,.0f} – {p['vah']:,.0f}"
        )
    settings = load_settings(path)
    target = out or Path(settings.data_dir) / "charts" / f"vp_{symbol}.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    title = f"{symbol} perpetual — volume profile tuần ({base}), nến {display}"
    figure(display_df, profiles, title).write_html(target, include_plotlyjs="cdn")
    typer.echo(f"Đã ghi {target}")
    if open_browser:
        webbrowser.open(target.resolve().as_uri())


@app.command()
def web(
    port: int = typer.Option(8000),
    host: str = typer.Option(
        "127.0.0.1", help="Chỉ mở cho máy này; đổi sang 0.0.0.0 để máy khác vào"
    ),
    path: Path = DEFAULT_CONFIG,
) -> None:
    """Mở web rinng: nhiều tab, mỗi tab nhiều chart với lens riêng."""
    import uvicorn

    from rinng.web.app import create_app

    typer.echo(f"rinng web: http://{host}:{port}")
    uvicorn.run(create_app(load_settings(path)), host=host, port=port, log_level="warning")
