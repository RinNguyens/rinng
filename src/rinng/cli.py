"""Điểm vào dòng lệnh: `rinng <lệnh>`."""

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
