# rinng

Quant analysis for crypto (USDT perpetuals on Binance and OKX): data collection, indicators, SMC,
liquidity, volume profile, order flow, derivatives data, Wyckoff/Elliott, backtesting,
a dashboard and Pine Script indicators.

Documentation: [docs/](docs/README.md). Architecture: [docs/08-architecture.md](docs/08-architecture.md).
Roadmap and per-phase status: [docs/09-phase-roadmap.md](docs/09-phase-roadmap.md).

> **Warning:** rinng only analyzes and backtests. It places no orders and is not investment advice.
> Use its output at your own risk.

## Requirements

- macOS or Linux (on Windows, use WSL2)
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you)
- Node.js 22+ and [pnpm](https://pnpm.io/) if you run the web UI
- No API key needed: rinng only uses public Binance and OKX data

## Quick start

```bash
git clone https://github.com/RinNguyens/rinng.git
cd rinng
uv sync                                   # install Python dependencies
uv run rinng check                        # test exchange connectivity
uv run rinng backfill --start 2024-01-01  # download historical data into data/
uv run rinng resample && uv run rinng analyze --timeframe 4h
pnpm --dir web install && pnpm --dir web build
uv run rinng live                         # open http://127.0.0.1:8000
```

If installing `ta-lib` fails, install the C library first (`brew install ta-lib` or `apt install libta-lib-dev`)
and rerun `uv sync`. If the OKX connection hangs, check your IPv6 network. Coin, exchange and timeframe
configuration lives in `configs/`.

## Workflow

```bash
uv run rinng check                      # test both exchanges, print rate limits
uv run rinng backfill --start 2020-01-01  # Binance dump + REST, then curate
uv run rinng backfill --exchange okx --start 2026-08-01 --dataset klines_1m
uv run rinng resample                   # 1m → 15m, 1h, 4h, 1d, 1w
uv run rinng validate                   # missing/duplicate bars, vs. exchange, vs. other exchange
uv run rinng analyze --timeframe 4h     # write data/features, data/events
uv run rinng backtest --timeframe 4h --split 2025-01-01
uv run rinng dashboard                  # http://localhost:8501
uv run rinng collect                    # realtime collector, runs continuously
uv run rinng curate                     # move collector data into curated
```

The realtime collector should run 24/7, because liquidations, open interest and long/short ratio
cannot be fetched retroactively. Service files (not installed) are in [deploy/](deploy/).

## rinng web (dashboard + multi-tab charts)

A React UI (TanStack Start + shadcn/ui, in `web/`) on top of rinng's FastAPI API.

```bash
pnpm --dir web install && pnpm --dir web build   # build once
uv run rinng live                                 # realtime data, open http://127.0.0.1:8000
uv run rinng web                                  # or: browse stored data only
```

`rinng live` runs the collector (Binance + OKX, including 1m bars), updates curated data every minute and pushes
prices, the forming bar and just-closed bars to the browser over the `/ws/live` WebSocket. Analysis (SMC, profile,
Wyckoff…) is recomputed only when a bar of that timeframe closes. If the machine was off for more than 3 days, run
`rinng backfill --start <date>` first. Details: [docs/10-realtime-plan.md](docs/10-realtime-plan.md).

- **Dashboard** tab: price, funding, OI, long/short, 24h delta and 4H structure context,
  weekly volume profile, liquidity, momentum, Wyckoff; the "View chart" button opens a large chart.
- Chart tabs: pick a layout (1 to 6 panes), drag cards from the library into a pane, drag the handle
  at the top of a chart to reorder, maximize a pane. Layouts are saved in the browser.
- The default watchlist has 5 coins (BTC, SOL, ETH, BNB, LINK) with stored history and realtime data.
  The coin search (⌘K or /) opens any USDT perp contract on Binance/OKX (~790 symbols): data comes over REST,
  and `rinng live` opens a realtime feed on demand (up to 8 coins at once). To add a coin to the watchlist,
  edit `configs/instruments.yaml` and run `rinng backfill --symbol <ID>`.
- **Combos** in the chart library: 7 prebuilt chart sets, each answering one question (Top-down
  structure, Value vs. liquidity, Trend health, Positioning & squeeze risk, Market cycle, Risk map,
  Intraday plan), with a suggested reading order. Drag one onto the grid to load it into the current tab, or click "New tab".
- **Projection** lens: a probability cone for the next H bars and the probability of touching price levels, with
  walk-forward validation results shown on the chart. Method and numbers: [docs/11-forecasting.md](docs/11-forecasting.md).
- To work on the UI: run `uv run rinng web`, then `pnpm --dir web dev` (port 3000, /api proxied to 8000).
- The old plain-HTML UI is still at `/classic`.

## Layout

| Directory | Contents |
|---|---|
| `src/rinng/exchanges` | Binance and OKX adapters, rate limiting |
| `src/rinng/ingest` | collector (WebSocket, poller), data.binance.vision dumps, backfill |
| `src/rinng/store` | schema, Parquet read/write, manifest, gaps, DuckDB, resample |
| `src/rinng/analysis` | indicators, structure, smc, liquidity, volume_profile, orderflow, derivatives, wyckoff, elliott |
| `src/rinng/pipeline` | curate, validate, run analysis modules |
| `src/rinng/strategy`, `src/rinng/backtest` | strategies, engine, metrics, reports |
| `src/rinng/viz` | Plotly charts, Streamlit dashboard |
| `src/rinng/web` | web API (chart lenses, dashboard data) |
| `web/` | React + shadcn/ui frontend |
| `pine/` | Pine Script v6 indicators |
| `data/` | data (not committed to git) |

## Testing

```bash
uv run pytest              # no network needed
uv run pytest -m network   # hits the real exchanges
uv run ruff check && uv run ruff format --check
```

The system only analyzes and backtests; it never places orders.

## Contributing

Anyone can clone, use and propose changes through pull requests. Only the repo owner can merge
into `main` and `dev`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Nguyễn Văn Rin
