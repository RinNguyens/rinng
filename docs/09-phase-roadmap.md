# 09 — Phase roadmap

Written 2026-11-13. Breaks [07-implementation-plan.md](07-implementation-plan.md) down into independently deliverable phases, following the architecture in [08-architecture.md](08-architecture.md). Phase 0 is done (commit `c6ae912`); the remaining phases have not started.

## Status (updated 2026-11-13)

| Phase | Code | "Done when" criteria | Remaining |
|---|---|---|---|
| 0–2 | done | met | — |
| 3 Collector | done | partial: tests with a fake WebSocket server pass; ran live for 90 seconds | 72-hour continuous run not done; service files in `deploy/` not installed |
| 4 History | done | see live run results in the session report | aggTrades and bookDepth not downloaded (heavy; command available) |
| 5 Analysis core | done | tests + look-ahead checks pass | not yet visually compared with TradingView |
| 6 SMC, liquidity | done | tests + look-ahead checks pass | not compared with TradingView; no MSS or inverse FVG yet |
| 7 Volume profile, order flow | done | tests pass | VPOC not compared with TradingView; bar-based vs. trade-based versions not compared on real data |
| 8 Derivatives, Wyckoff, Elliott | done | tests + look-ahead checks pass | liquidations only exist since the collector started |
| 9 Backtest | done | tests match hand calculations | no liquidation simulation; no strategy validated as having an edge |
| 10 Dashboard | done | dashboard runs (headless test) | not compared with the sample charts |
| 11 Pine Script | `pine/rinng_overlay.pine` (SMC, liquidity, weekly VP, Wyckoff climax) and `pine/rinng_oscillators.pine` (RSI, MACD, estimated delta/CVD) | passes the Pine Editor checker with no errors or warnings | not yet run on a chart (TradingView requires login to Add to chart) |

Conventions:

- **Size:** S (one small module), M (a few modules), L (many modules or a multi-day trial run). This is relative size, not a time estimate.
- **Done when:** verifiable conditions. If not met, do not move to the next phase.
- Each phase ends with a commit where tests and ruff both pass.

## Overview

| Phase | Name | Size | Depends on | Usable result |
|---|---|---|---|---|
| 0 | Project skeleton | S | — | `rinng check` works (done) |
| 1 | Exchange adapters | M | 0 | bars, funding, OI from both exchanges through one interface |
| 2 | Storage layer | M | 0 | safe Parquet read/write, with a manifest |
| 3 | Realtime collector | L | 1, 2 | liquidations, OI, long/short accumulated continuously |
| 4 | Historical download and cleaning | L | 1, 2 | clean 1-minute bars since 2020, resampled |
| 5 | Analysis core | M | 4 | classic indicators, swings, market structure |
| 6 | SMC and liquidity | M | 5 | BOS, CHoCH, FVG, order block, sweep |
| 7 | Volume profile and order flow | L | 4 | VPOC, value area, delta, CVD, footprint |
| 8 | Derivatives, Wyckoff, Elliott | M | 3, 5 | funding/OI/liquidation features; Wyckoff and Elliott components |
| 9 | Strategy and backtest | L | 5, ideally after 6–8 | backtest results with fees, compared with baselines |
| 10 | Charts and dashboard | M | 5 onward | reproduce the sample charts from project data |
| 11 | Pine Script | S–M | 9 | TradingView indicators matching Python |

Proposed order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11. Phase 3 goes early because every day it is not running is a day of liquidations lost for good. Phase 10 can move up right after phase 5 to see results early; in that case build a minimal chart first.

## Phase 0 — Project skeleton (done)

The pending task is done (2026-11-13): downloaded the BTCUSDT files for 2026-11-10, checksums match.

- `metrics` (288 rows, every 5 minutes, not sorted by time): `create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio`. Compared against the API at the same times: `count_toptrader…` ≈ top traders by account, `sum_toptrader…` ≈ top traders by position, `count_long_short_ratio` ≈ all accounts. The numbers are close but not identical (OI 98691.69 vs 98690.01), so they are stored separately with `source="dump"`. The taker column does not clearly match the API; treat it as unverified. There are no long/short percentages.
- `bookDepth` (every 30 seconds, 12 levels ±0.2/1/2/3/4/5 %): `timestamp, percentage, depth, notional`, cumulative depth.

## Phase 1 — Exchange adapters

**Goal:** the rest of the system gets data through `Exchange` without knowing which exchange.

**Tasks:**
1. `exchanges/ratelimit.py`: the throttle. Binance reads `X-MBX-USED-WEIGHT-1M` and self-limits at 50%; OKX counts requests in a 2-second window per endpoint. On 429 sleep per `Retry-After`; on 418 stop completely and raise an error.
2. `exchanges/binance.py`: `klines`, `funding`, `open_interest`, `long_short`, `taker_volume`, `mark_price_klines` for USDⓈ-M; `klines` for Spot. Paginate with `startTime`.
3. `exchanges/okx.py`: the same methods. Paginate backwards with `after`; check `code` in the body; use `1Dutc` instead of `1D`.
4. Normalize output: UTC milliseconds, float numbers, common column names.
5. Extend `Exchange` in `base.py` to cover all the methods above.

**Extra libraries:** none.

**Done when:**
- Tests with `httpx.MockTransport` for: multi-page pagination, empty pages, 429 with `Retry-After`, 418, OKX code `50011`, unclosed bars.
- A `network`-marked test: fetch 3 days of BTC 1h bars from both exchanges, exactly 72 bars with no duplicates.
- Binance and OKX 1h bars over the same period have the same open times.

**Risks:** actual weight is higher than the docs say (seen once); limits for some `/futures/data/*` endpoints are unverified.

## Phase 2 — Storage layer

**Goal:** read and write data in the defined layout without corrupting files when several processes run at once.

**Tasks:**
1. `store/schemas.py`: schemas of the curated tables (`ohlcv`, `trades`, `funding`, `open_interest`, `long_short`, `liquidations`, `mark_index`).
2. `store/writer.py`: write a temp file and rename; refuse overwrites in `raw/`; deduplicate by key when writing `curated/`.
3. `store/reader.py`: read by instrument, timeframe, time range.
4. `store/catalog.py`: `manifest` (source, time range, row count, checksum, download time) and `gaps`.
5. DuckDB views pointing at Parquet.

**Extra libraries:** `polars`, `duckdb`.

**Done when:**
- Tests: write then read back gives the same data; writing the same key twice produces no duplicate rows; overwriting `raw/` is refused; a process dying midway leaves no partial file at the official path.
- A DuckDB query counts exactly the rows written.

**Decision needed first:** the result of opening the `metrics` file (phase 0).

## Phase 3 — Realtime collector

**Goal:** continuously accumulate the series that cannot be recovered later.

**Tasks:**
1. `ingest/collector/ws.py`: connect to Binance WebSocket (`@forceOrder`, `@markPrice`, `@aggTrade`) and OKX (`liquidation-orders`, mark price, trades). Reconnect with backoff; Binance proactively reconnects before the 24-hour mark; OKX sends `ping` when idle.
2. `ingest/collector/poller.py`: every 5 minutes fetch OI, long/short ratio, taker volume via phase 1.
3. `ingest/collector/gaps.py`: record every disconnect interval in `meta/gaps`.
4. Buffer records in memory, flush to Parquet in batches (by time or row count), flush everything on a stop signal.
5. The `rinng collect` command and service files for automatic restart (launchd on macOS or systemd on a VPS).

**Extra libraries:** `websockets`, `APScheduler`.

**Done when:**
- Tests with a fake WebSocket server: a mid-stream disconnect reconnects and records exactly one gap; a stop signal does not lose buffered records.
- A live 72-hour continuous run that survives at least one Binance 24-hour disconnect; the `gaps` table matches the logs.
- The number of OI records over 72 hours is 864 per instrument per exchange (72 × 12), minus recorded gaps.

**Decision needed first:** run on this Mac or a VPS. If a VPS, run `rinng check` there first and add a step to sync `raw/` to the analysis machine.

**Risks:** the liquidation stream is inherently incomplete on both exchanges; aggTrades storage size has not been estimated, so this stream may have to be turned off and aggTrades taken only from dumps.

## Phase 4 — Historical download and cleaning

**Goal:** a clean, long, resampled set of 1-minute bars; the input to all analysis.

**Tasks:**
1. `ingest/dumps.py`: list and download files from data.binance.vision by date range, verify `.CHECKSUM`, store the original zip files in `raw/`.
2. `ingest/backfill.py`: fill what the dumps do not have yet (the last few days) via REST; download OKX for cross-checking.
3. `pipeline/curate.py`: raw → curated. Handle the microsecond timestamps of Spot dumps from 2025-01-01.
4. `store/resample.py`: 1 minute → 15m, 1h, 4h, 1d, 1w in UTC; weeks start on Monday.
5. `pipeline/validate.py`: report missing and duplicate bars, abnormal prices, divergence between the two exchanges.
6. The `rinng backfill` and `rinng validate` commands.

**Extra libraries:** none.

**Done when:**
- No missing or duplicate bars in the downloaded range, or every missing interval is listed with a reason (exchange maintenance).
- Self-resampled 1h and 1d bars match the exchange's bars value for value over a sample month.
- The overlap between dumps and REST matches.

**Decision needed first:** history depth (proposed: bars since 2020; aggTrades for the last 12 months).

## Phase 5 — Analysis core

**Goal:** build the two output types, Feature and Event, and the building blocks every later module reuses.

**Tasks:**
1. `analysis/types.py`: the `Features`, `Events`, `Params` types and parameter hashing.
2. `analysis/indicators.py`: RSI, MACD, ROC, Stochastic, Williams %R, ATR, Bollinger, EMA/SMA, ADX, OBV, VWAP and anchored VWAP.
3. `analysis/structure.py`: swing high/low with configurable length; HH/HL/LH/LL labels; each swing has `event_time` and `known_at`.
4. `pipeline/run.py`: run one module on one instrument and one timeframe, writing to `features/` or `events/`.

**Extra libraries:** TA-Lib (needs the C library installed via Homebrew), `numpy`.

**Done when:**
- Each indicator has a test on a hand-built series with independently computed expected values.
- Look-ahead test: truncate the data at time T; every row with `known_at` ≤ T must be identical to the result on the full data.
- Visual comparison of RSI, MACD and swings with TradingView on three price segments.

**Risks:** TA-Lib may have no prebuilt binary for this environment; the fallback is writing the indicators in numpy.

## Phase 6 — SMC and liquidity

**Goal:** SMC concepts as clearly defined, testable events.

**Tasks:**
1. `analysis/smc.py`: BOS, CHoCH (break on close or wick is a parameter), FVG with filled state, order block with mitigation and breaker, premium/discount, displacement as an ATR multiple.
2. `analysis/liquidity.py`: equal highs/lows with ATR-based tolerance, liquidity sweeps, liquidity zones below old lows and above old highs.
3. Document the chosen definition of each concept, since SMC has no standard definitions.

**Extra libraries:** none.

**Done when:**
- Each event type has tests on hand-built bar series, including cases where no event should be produced.
- The phase 5 look-ahead test passes for every event type, including `invalidated_at`.
- Visual comparison with a TradingView SMC indicator on three price segments; differences and reasons recorded.

**Risks:** the pseudocode in [03-pine-script-and-smc.md](03-pine-script-and-smc.md) has never run and is only a starting point.

## Phase 7 — Volume profile and order flow

**Goal:** reproduce the weekly volume profile chart with VPOC and delta.

**Tasks:**
1. Approximate `analysis/volume_profile.py`: spread 1-minute bar volume across the price range; VPOC, VAH/VAL (70%), HVN/LVN, naked POC; profiles per session, week, month and arbitrary anchored range.
2. Exact version from aggTrades; measure the deviation from the approximation.
3. `analysis/orderflow.py`: per-bar delta from `taker_buy_volume`, CVD; footprint by price level, imbalance and absorption from aggTrades.
4. Add aggTrades downloading to phase 4 for the needed period.

**Extra libraries:** none.

**Done when:**
- Tests on hand-built data: VPOC, VAH, VAL match hand calculations; total profile volume equals total bar volume.
- Per-bar delta computed from bars matches delta aggregated from aggTrades on a sample day.
- Weekly VPOC is within one bin of TradingView on three sample weeks.

**Decision needed first:** price bin size and the week definition (proposed: Monday 00:00 UTC).

**Risks:** TradingView's value area variant is unverified; aggTrades are very heavy, so only price-level aggregates may be stored.

## Phase 8 — Derivatives, Wyckoff, Elliott

**Goal:** features from derivatives data, and the measurable components of Wyckoff and Elliott.

**Tasks:**
1. `analysis/derivatives.py`: funding (level, z-score, cumulative), basis and premium, OI change, price + OI state table, long/short ratio, liquidation clusters.
2. `analysis/wyckoff.py`: climax volume, trading range bounds, spring and upthrust, effort vs result. No labeling of the full schematic.
3. `analysis/elliott.py`: zigzag pivots, checking the three hard rules for a pivot sequence, Fibonacci ratios between waves. No automatic choice of a single count.

**Extra libraries:** none.

**Done when:**
- Tests on hand-built data for each feature and event.
- Look-ahead tests pass.
- OI and liquidation features are only computed over segments with no gaps in `meta/gaps`.

**Risks:** OI and long/short history depends on the `metrics` files; liquidations only exist since phase 3 started, so there is little data to validate this part at first.

## Phase 9 — Strategy and backtest

**Goal:** measure whether an idea has an edge, after costs, compared with baselines.

**Tasks:**
1. `strategy/base.py` and two baselines: buy-and-hold, 40-bar linear regression (as in the paper).
2. `backtest/costs.py`: maker/taker fees, slippage, funding over the holding period.
3. `backtest/engine.py`: enter on the bar after `known_at`; intrabar stop and take-profit; a convention for when both are hit in the same bar.
4. `backtest/metrics.py` and `report.py`: Sharpe, Sortino, max drawdown, win rate, profit factor, trade count; annualized for a 24/7 market.
5. Split in-sample and out-of-sample; record the number of configurations tried.
6. The `rinng backtest` command.

**Extra libraries:** `quantstats`.

**Done when:**
- An EMA crossover strategy on hand-built data gives exactly the right trades and P&L versus a hand calculation, including fees and funding.
- Buy-and-hold returns the price change minus costs.
- Every run stores the config, parameter hash and code version in `results/`.

**Risks:** trying many parameters leads to overfitting; discipline is needed to keep the out-of-sample set untouched.

## Phase 10 — Charts and dashboard

**Goal:** see the data, events and backtest results.

**Tasks:**
1. `viz/chart.py`: candlesticks with overlays (FVG and order block zones, VPOC and value area lines, BOS/CHoCH labels, swings).
2. `viz/overlays.py`: side volume profile, lower panels for CVD, funding, OI.
3. Dashboard: pick instrument, timeframe, overlays; a backtest results page.

**Extra libraries:** Plotly or `lightweight-charts`, Streamlit.

**Done when:** the weekly volume profile chart and the liquidity zone chart from the sample image set can be reproduced from project data.

## Phase 11 — Pine Script

**Goal:** bring validated signals to TradingView.

**Tasks:** write Pine v6 indicators for each signal group that passed phase 9; use the same parameters as Python.

**Done when:** on the same price segment, the events Pine draws match the Python events, and any differences are explained.

**Risks:** Pine is limited to 500 lines/boxes/labels and has a different execution model, so some events can only show the most recent part.

## Deferred, not yet assigned a phase

- LLM multi-agent layer.
- Paid on-chain data.
- Macro data (Fed rates, gold, DXY), awaiting a decision.
- Live order placement.

## Pending decisions

| Decision | Needed before phase | Default if unspecified |
|---|---|---|
| Download `metrics` and `bookDepth` files to inspect columns | 2 | not downloaded |
| Collector runs on the Mac or a VPS | 3 | this Mac, accepting gaps while it sleeps |
| History depth | 4 | bars since 2020; 12 months of aggTrades |
| Volume profile bin size and week definition | 7 | week starts Monday 00:00 UTC; bin chosen during implementation |
| Whether to do macro | 8 | no |
| Whether the project is commercial | 9 | assume yes, so no vectorbt and no LuxAlgo code |
