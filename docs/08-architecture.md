# 08 — rinng architecture

Written 2026-11-13. Scope: crypto, no LLM yet, no live order placement. This is a design; not a single line of code exists yet. The architecture uses the defaults in [07-implementation-plan.md](07-implementation-plan.md) section 1 (BTCUSDT and ETHUSDT perpetuals, Binance as primary, 1-minute base bars, UTC); those defaults have not been confirmed.

## 1. Design principles

1. **Raw data is immutable.** What is downloaded is written once and never modified. Every later layer can be recomputed from it.
2. **One-way dependencies.** A later layer only reads the previous layer's output through Parquet files and never calls back.
3. **Two timestamps.** Every analysis record has `event_time` (when it happened) and `known_at` (when it became known for certain). Backtests may only use `known_at`.
4. **Analysis is pure functions.** Same data and same parameters give the same result; no network calls, no reading the clock.
5. **Parameters live in configuration**, not in code. Every result records the hash of the parameter set used.
6. **Exchanges sit behind a common interface.** The rest of the system does not know whether it is talking to Binance or OKX.

## 2. Overall diagram

```
        Binance REST/WS      OKX REST/WS      data.binance.vision      (FRED, optional)
               │                  │                    │                     │
┌──────────────▼──────────────────▼────────────────────▼─────────────────────▼───────┐
│ L1  INGEST                                                                         │
│   exchanges/   per-exchange adapters (rate limits, pagination, name normalization) │
│   backfill     batch history download        collector   24/7 realtime capture     │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ write
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L2  STORE                                                                          │
│   data/raw       exactly as the exchange returned it, immutable                    │
│   data/curated   common schema, UTC, deduplicated, resampled                       │
│   data/meta      manifest, instrument catalog, gap log                             │
│   DuckDB         only views pointing at Parquet                                    │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ read curated
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L3  ANALYSIS (pure functions, no network I/O)                                      │
│   indicators → structure (swing) → smc · liquidity · wyckoff · elliott             │
│   volume_profile · orderflow · derivatives · (macro)                               │
│   Output: feature tables (one row per bar) and event tables (one row per event)    │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ write data/features, data/events
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L4  STRATEGY + BACKTEST                                                            │
│   strategy    features + events → entry/exit signals, stop, take-profit            │
│   engine      order simulation: fees, slippage, funding, liquidation               │
│   metrics     Sharpe, drawdown, comparison with baselines                          │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ write data/results
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L5  PRESENTATION                                                                   │
│   charts with overlays · dashboard · backtest reports · Pine Script indicators     │
└────────────────────────────────────────────────────────────────────────────────────┘

   (deferred)  L6  LLM interpretation: reads features, events, results only; never writes back
```

## 3. Running processes

The system is not a single program but five kinds of runs sharing the `data/` directory.

| Process | Kind | What it does | Writes to |
|---|---|---|---|
| `collector` | runs continuously 24/7 | WebSocket: liquidations, mark price, aggTrades. Every 5 minutes: OI, long/short ratio, taker volume | `raw/` |
| `backfill` | manual command | downloads dumps and REST for a time range, verifies checksums | `raw/` |
| `pipeline` | scheduled (e.g. hourly) or manual | raw → curated → features → events | `curated/`, `features/`, `events/` |
| `backtest` | manual command | runs one strategy with one parameter set | `results/` |
| `dashboard` | run when needed | reads and displays | nothing |

Only `collector` needs an always-on machine. The other four can run on a personal machine. If `collector` runs on a VPS, its `raw/` directory is synced to the analysis machine; the two do not need a direct connection.

Because several processes write to the same `data/`, the rule is: each process writes only to its own area, writes a temp file and then renames it, and never modifies existing files in `raw/`.

## 4. Modules and responsibilities

```
src/rinng/
  config/          load configuration, validate
  exchanges/       base.py (common interface), binance.py, okx.py, ratelimit.py
  ingest/          backfill.py, dumps.py, collector/ (ws.py, poller.py, gaps.py)
  store/           paths.py, writer.py, reader.py, schemas.py, resample.py, catalog.py
  analysis/
    indicators.py      TA-Lib wrappers
    structure.py       swings, HH/HL/LH/LL
    smc.py             BOS, CHoCH, order block, FVG, premium/discount
    liquidity.py       equal highs/lows, sweeps
    volume_profile.py  VPOC, VAH/VAL, HVN/LVN, naked POC
    orderflow.py       delta, CVD, footprint
    derivatives.py     funding, OI, long/short, liquidations
    wyckoff.py         climax, range, spring/upthrust
    elliott.py         zigzag, hard rules, Fibonacci
    macro.py           optional
  pipeline/        orders the analysis steps, incremental computation
  strategy/        base.py, sample strategies, baselines (buy-and-hold, linear regression)
  backtest/        engine.py, costs.py, metrics.py, report.py
  viz/             chart.py, overlays.py, dashboard/
  cli.py           command-line entry point
pine/              Pine Script v6 indicators
tests/             mirrors the src/ structure
data/              not committed to git
configs/           YAML configuration files
```

Dependency rules between packages:

| Package | May use | Must not use |
|---|---|---|
| `exchanges` | `config` | every other package |
| `ingest` | `exchanges`, `store`, `config` | `analysis` and later |
| `store` | `config` | `exchanges`, `analysis` |
| `analysis` | only numpy, polars, TA-Lib | `store`, `exchanges`, network |
| `pipeline` | `store`, `analysis`, `config` | `exchanges` |
| `strategy` | `analysis` data types | `store`, `exchanges` |
| `backtest` | `strategy`, `store` | `exchanges`, `ingest` |
| `viz` | `store` | `exchanges`, `ingest` |

The most important point: `analysis` takes in-memory tables and returns tables. It does not know where files live. That way tests need no real data, and the same function works for both backtesting and realtime.

Within `analysis`, the dependency order is: `indicators` and `structure` stand alone; `smc`, `liquidity`, `wyckoff`, `elliott` use `structure`; `volume_profile`, `orderflow`, `derivatives` stand alone.

## 5. Data model

### 5.1 Areas

```
data/
  raw/        {exchange}/{dataset}/{symbol}/date=YYYY-MM-DD/*.parquet|zip
  curated/    {dataset}/exchange=…/symbol=…/timeframe=…/year=…/part-*.parquet
  features/   {module}/v{n}/symbol=…/timeframe=…/…
  events/     {module}/v{n}/symbol=…/timeframe=…/…
  results/    {run_id}/trades.parquet, equity.parquet, summary.json, config.yaml
  meta/       manifest.parquet, instruments.parquet, gaps.parquet
```

### 5.2 Main tables in the curated area

| Table | Key | Columns |
|---|---|---|
| `ohlcv` | exchange, symbol, timeframe, open_time | open, high, low, close, volume, quote_volume, trades, taker_buy_volume, is_closed |
| `trades` | exchange, symbol, trade_id | time, price, qty, is_buyer_maker |
| `funding` | exchange, symbol, funding_time | rate, mark_price |
| `open_interest` | exchange, symbol, time | oi_contracts, oi_value |
| `long_short` | exchange, symbol, time, kind | ratio, long_pct, short_pct |
| `liquidations` | exchange, symbol, time | side, price, qty |
| `mark_index` | exchange, symbol, time | mark_price, index_price, premium |

Every time column is UTC with millisecond resolution. Symbol names are normalized to a common form (e.g. `BTC-USDT-PERP`); the `instruments` table keeps each exchange's native name.

The `taker_buy_volume` column only comes with Binance bars; for OKX it must be computed from `trades`.

### 5.3 The two forms of analysis output

**Feature** — continuous values, one row per bar:

| Column | Meaning |
|---|---|
| symbol, timeframe, open_time | key |
| known_at | equal to the bar's close time |
| value columns | e.g. `rsi_14`, `atr_14`, `cvd`, `funding_z` |
| params_hash | hash of the parameter set |

**Event** — discrete events, one row per event:

| Column | Meaning |
|---|---|
| event_id | identifier |
| symbol, timeframe | |
| kind | `swing_high`, `bos_up`, `choch_down`, `fvg_bull`, `order_block`, `sweep_low`, `vpoc`, `naked_poc`… |
| event_time | the bar the event is attached to |
| known_at | the bar at which the event is confirmed |
| price_low, price_high | price level or price zone |
| invalidated_at | when the zone is broken or filled, if ever |
| attrs | type-specific attributes |
| params_hash | |

Example: a swing high with length 5 has `event_time` at the bar that forms the high, while `known_at` is the close of the 5th bar after it. Separating these two forms is the central design decision: SMC, liquidity, Wyckoff and volume profile all produce events and price zones, not one number per bar.

## 6. Interfaces between layers

The four contracts below must stay stable; internals can change freely.

```python
# exchanges/base.py — every exchange implements the same interface
class Exchange(Protocol):
    def klines(self, symbol, timeframe, start, end) -> Iterator[DataFrame]: ...
    def funding(self, symbol, start, end) -> Iterator[DataFrame]: ...
    def open_interest(self, symbol, period, start, end) -> Iterator[DataFrame]: ...
    def stream(self, channels: list[Channel]) -> AsyncIterator[Message]: ...

# analysis — every module follows the same shape
def compute(ohlcv: DataFrame, params: Params) -> Features | Events: ...

# strategy/base.py
class Strategy(Protocol):
    def signals(self, features: DataFrame, events: DataFrame) -> DataFrame:
        """Returns: time, side, entry, stop, take_profit, size_hint, reason."""

# backtest/engine.py
def run(signals: DataFrame, ohlcv: DataFrame, costs: CostModel) -> Result: ...
```

This is a sketch to agree on the shapes, not code that has run.

## 7. Cross-cutting concerns

| Concern | Approach |
|---|---|
| Configuration | YAML in `configs/`, loaded and validated with Pydantic; one file for instruments, one for each module's parameters |
| Rate limiting | one shared throttle in `exchanges/ratelimit.py`; Binance reads the header, OKX counts itself |
| Network errors | retry with backoff; on 429 sleep per `Retry-After`; never retry immediately |
| Data gaps | `collector` records every disconnect in `meta/gaps`; `pipeline` refuses to compute over segments with unfilled gaps |
| Reproducibility | every backtest stores the config, parameter hash, code version and data manifest |
| Logging | structured (JSON) logs, separate per process |
| Testing | unit tests for `analysis` on hand-built data; cross-check tests for `store` (resample matches exchange bars); integration tests for `exchanges` run separately since they need network |
| Secrets | there are no API keys today; if any are added later they live in environment variables, not in the repo |

## 8. Technology

| Concern | Choice |
|---|---|
| Language, environment | Python 3.12, `uv` |
| HTTP, WebSocket | `httpx`, `websockets`; `ccxt` as a fallback and for cross-checking |
| Data frames | `polars`, `numpy` |
| Storage | Parquet, DuckDB |
| Indicators | TA-Lib |
| Scheduling | `APScheduler` in `collector`; cron for `pipeline` |
| Configuration | Pydantic, YAML |
| CLI | `typer` |
| Metrics | `quantstats` |
| Visualization | Plotly or `lightweight-charts`, Streamlit |
| Quality | `pytest`, `ruff` |

I chose to write the exchange adapters with `httpx` rather than relying entirely on `ccxt` because we need endpoints `ccxt` does not fully wrap (the `/futures/data/*` group, dump files, the liquidation stream) and need control over rate limiting. The cost is having to track exchange API changes ourselves.

## 9. Extension points

- **New exchange:** write one file in `exchanges/` implementing the common interface.
- **New indicator:** write a module in `analysis/` that returns Features or Events, and register it in `pipeline`.
- **On-chain:** a new source in L1 and a new table in curated.
- **LLM:** a read-only L6 layer. Since features, events and results are already structured tables with `known_at`, it plugs in without changing anything below.
- **Realtime:** `pipeline` runs incrementally on just-closed bars instead of the whole history; the `analysis` functions stay the same.

## 10. Open questions

1. The defaults in file 07 section 1 have not been confirmed.
2. Where `collector` runs determines whether a `raw/` sync mechanism is needed.
3. Binance's `metrics` file has not been opened; the `open_interest` and `long_short` table schemas may need adjusting accordingly.
4. Incremental computation for swing-based modules (events can be invalidated later) needs more careful design when we get there.
5. aggTrades storage size has not been estimated; we may need to keep only price-level aggregates instead of individual trades.
