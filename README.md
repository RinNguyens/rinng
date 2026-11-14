# rinng

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
![Exchanges](https://img.shields.io/badge/exchanges-Binance%20%7C%20OKX-orange.svg)

**rinng** is an open-source quant analysis toolkit for crypto USDT perpetuals on Binance and OKX.
It collects market and derivatives data, stores it locally as Parquet/DuckDB, runs a full analysis
pipeline (indicators, market structure, Smart Money Concepts, liquidity, volume profile, order flow,
Wyckoff, Elliott), backtests strategies, and shows everything in a realtime web dashboard. It also
ships matching Pine Script indicators for TradingView.

> [!WARNING]
> rinng only analyzes and backtests. It never places orders and nothing it produces is investment
> advice. Use its output at your own risk.

## Features

- **Data pipeline**: historical backfill from data.binance.vision and exchange REST APIs, a 24/7
  realtime collector (WebSocket + pollers), validation for missing or duplicate bars and cross-exchange
  checks, resampling from 1m to 15m, 1h, 4h, 1d and 1w.
- **Analysis modules**: indicators, market structure, SMC (order blocks, FVGs, BOS/CHoCH), liquidity
  pools, volume profile, order flow and delta, funding / open interest / long-short positioning,
  Wyckoff phases and Elliott waves.
- **Backtesting**: an event-driven engine with fees and slippage, baseline and SMC strategies,
  train/test splits and metric reports.
- **Forecasting**: a probability cone for the next bars and the probability of touching price levels,
  with walk-forward validation.
- **Web app**: a React dashboard with multi-pane chart tabs, drag-and-drop chart library, prebuilt
  chart combos, a live desk and a news feed, streamed over WebSocket.
- **Pine Script v6** overlay and oscillator indicators.
- **No API keys**: only public Binance and OKX market data is used.

## Requirements

- macOS or Linux (on Windows, use WSL2)
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 for you
- Node.js 22+ and [pnpm](https://pnpm.io/) for the web UI

## Quick start

```bash
git clone https://github.com/RinNguyens/rinng.git
cd rinng
uv sync                                    # install Python dependencies
uv run rinng check                         # test exchange connectivity
uv run rinng backfill --start 2024-01-01   # download history into data/
uv run rinng resample                      # build higher timeframes
uv run rinng analyze --timeframe 4h        # run the analysis pipeline
pnpm --dir web install && pnpm --dir web build
uv run rinng live                          # open http://127.0.0.1:8000
```

### Troubleshooting

- **`ta-lib` fails to install**: install the C library first (`brew install ta-lib` on macOS,
  `apt install libta-lib-dev` on Debian/Ubuntu), then rerun `uv sync`.
- **OKX connection hangs**: some networks have broken IPv6. Check your IPv6 setup or force IPv4.
- **The machine was off for more than 3 days**: run `uv run rinng backfill --start <date>` before
  `rinng live` to fill the gap.

## CLI

| Command | What it does |
|---|---|
| `rinng check` | Test both exchanges and print rate limits |
| `rinng backfill --start 2020-01-01` | Download Binance dumps + REST data, then curate |
| `rinng backfill --exchange okx --dataset klines_1m --start <date>` | Backfill one exchange or dataset |
| `rinng backfill --symbol <ID>` | Backfill a single instrument |
| `rinng resample` | Resample 1m bars to 15m, 1h, 4h, 1d, 1w |
| `rinng validate` | Check for missing/duplicate bars and compare against the exchange and the other exchange |
| `rinng analyze --timeframe 4h` | Write features and events to `data/features` and `data/events` |
| `rinng backtest --timeframe 4h --split 2025-01-01` | Run backtests with a train/test split |
| `rinng collect` | Run the realtime collector continuously |
| `rinng curate` | Move collector data into the curated store |
| `rinng live` | Collector + web app with realtime updates |
| `rinng web` | Web app over stored data only |
| `rinng dashboard` | Legacy Streamlit dashboard at http://localhost:8501 |

Run any command with `uv run`, e.g. `uv run rinng check`, and add `--help` for options.

Liquidations, open interest and long/short ratios cannot be fetched after the fact, so run the
collector 24/7 if you want that history. Example launchd and systemd service files are in
[deploy/](deploy/).

## Web app

`rinng live` runs the collector for Binance and OKX, refreshes curated data every minute, and pushes
prices, the forming bar and closed bars to the browser over the `/ws/live` WebSocket. Heavier analysis
(SMC, profiles, Wyckoff…) is recomputed only when a bar of that timeframe closes.
See [docs/10-realtime-plan.md](docs/10-realtime-plan.md).

- **Dashboard**: price, funding, open interest, long/short, 24h delta, 4H structure, weekly volume
  profile, liquidity, momentum and Wyckoff context, with a "View chart" shortcut.
- **Chart tabs**: layouts from 1 to 6 panes. Drag cards from the library into a pane, drag a chart's
  handle to reorder, maximize a pane. Layouts are saved in the browser.
- **Watchlist and search**: 5 default coins (BTC, SOL, ETH, BNB, LINK) with stored history. Search
  (⌘K or `/`) opens any of ~790 USDT perps on Binance/OKX; `rinng live` opens realtime feeds on
  demand for up to 8 coins at once. To add a coin permanently, edit `configs/instruments.yaml` and
  run `rinng backfill --symbol <ID>`.
- **Combos**: 7 prebuilt chart sets that each answer one question (top-down structure, value vs.
  liquidity, trend health, positioning and squeeze risk, market cycle, risk map, intraday plan), with
  a suggested reading order.
- **Projection lens**: forecast cone and level-touch probabilities with walk-forward results on the
  chart. See [docs/11-forecasting.md](docs/11-forecasting.md).
- The old plain-HTML UI is still available at `/classic`.

To work on the UI, run `uv run rinng web` and then `pnpm --dir web dev` (port 3000, `/api` is proxied
to port 8000).

## Project layout

| Path | Contents |
|---|---|
| `src/rinng/exchanges` | Binance and OKX adapters, rate limiting |
| `src/rinng/ingest` | Realtime collector (WebSocket, pollers), Binance dumps, backfill |
| `src/rinng/store` | Schemas, Parquet read/write, manifest, gap tracking, DuckDB, resampling |
| `src/rinng/analysis` | Indicators, structure, SMC, liquidity, volume profile, order flow, derivatives, Wyckoff, Elliott, forecasting |
| `src/rinng/pipeline` | Curate, validate, run analysis modules |
| `src/rinng/strategy`, `src/rinng/backtest` | Strategies, backtest engine, metrics, reports |
| `src/rinng/live`, `src/rinng/web` | Live hub and FastAPI web API |
| `src/rinng/viz` | Plotly charts, Streamlit dashboard |
| `web/` | React frontend (TanStack Start + shadcn/ui) |
| `pine/` | Pine Script v6 indicators |
| `configs/` | Instruments, exchanges and timeframes |
| `docs/` | Research notes, architecture and roadmap |
| `data/` | Local data store (not committed) |

## Documentation

- [Docs index](docs/README.md)
- [Architecture](docs/08-architecture.md)
- [Roadmap and phase status](docs/09-phase-roadmap.md)
- [Analysis methods](docs/04-analysis-methods.md)
- [Backtesting and data](docs/05-quant-backtest-and-data.md)

## Development

```bash
uv sync                                    # includes dev dependencies
uv run pytest                              # offline tests
uv run pytest -m network                   # tests that call the real exchanges
uv run ruff check src tests && uv run ruff format --check src tests
pnpm --dir web lint && pnpm --dir web typecheck
```

## Contributing

Contributions are welcome. Fork the repo, create a branch from `dev`, and open a pull request against
`dev`. Only the maintainer merges into `dev` and `main`. See [CONTRIBUTING.md](CONTRIBUTING.md).
Bugs and feature ideas go to [Issues](https://github.com/RinNguyens/rinng/issues).

## License

[MIT](LICENSE) © 2026 Nguyễn Văn Rin
