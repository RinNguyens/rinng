# 07 — Step-by-step implementation plan (crypto, no LLM yet)

Written 2026-11-13. API limit figures come from [02-exchange-apis.md](02-exchange-apis.md); wherever that file says "unverified", this one says so too. No step has been carried out yet.

## 1. Default decisions

These are the values I propose so the plan is concrete. They can change, but should be settled before step 1.

| Item | Default | Reason |
|---|---|---|
| Trading pairs | BTCUSDT, ETHUSDT | highest liquidity, longest data; adding symbols later does not change the architecture |
| Contract type | USDT perpetual primarily, spot for cross-checking | funding, OI and liquidations only exist for perpetuals |
| Primary exchange | Binance; OKX as a second source | Binance has a more complete dump archive and keeps funding history longer |
| Base stored bar | 1 minute | every larger timeframe is resampled from it; volume profile needs 1 minute |
| Analysis timeframes | 15m, 1h, 4h, 1D, 1W | match the sample charts |
| Time zone | UTC for everything | OKX `1D` bars open at UTC+8 by default; `1Dutc` must be used |
| API key | none | all the data needed is public |

## 2. Limits and blocking on Binance and OKX

### 2.1 Summary

Public market data on both exchanges needs no API key and is free. Rate limits are far more generous than the project needs. The real risks are in three places: the history depth of some series, IP bans if 429 errors are ignored, and regional blocking of the host machine.

### 2.2 Rate limits

| | Binance | OKX |
|---|---|---|
| Accounting | by weight, per IP | per endpoint, "N requests / 2 seconds", per IP |
| Level | Spot 6000 weight/min; Futures 2400 weight/min (USDⓈ-M and COIN-M shared) | candles 40/2s; history-candles 20/2s; `rubik` statistics group 5/2s |
| Knowing usage | `X-MBX-USED-WEIGHT-1M` header | no header, count yourself |
| When exceeded | HTTP 429 with `Retry-After` | code `50011` in the body, HTTP still 200 |
| If you keep sending | HTTP 418, IP ban from 2 minutes to 3 days, escalating | docs do not describe the penalty (unverified) |
| Specific limits | `fundingRate` 500 requests/5 min; `/futures/data/*` group 1000 requests/5 min | funding 10/2s per IP + instrument |
| Other | HTTP 403 on WAF violations | — |

Estimated time to download 1-minute bars over REST, running at half the limit:

- Binance Futures: 1500 bars/request, weight 10, i.e. about 120 requests/min = 180,000 bars/min. One year (525,600 bars) takes about 3 minutes.
- OKX: 300 bars/request, about 300 requests/min = 90,000 bars/min. One year takes about 6 minutes.

These are calculations from the documented numbers, not measured. A test call with `limit=1500` raised the weight counter more than the table says, so the downloader must read the header rather than add up weights itself.

### 2.3 History depth (the most important limit)

| Data | Binance via REST | Binance via dump (data.binance.vision) | OKX via REST | OKX via dump |
|---|---|---|---|---|
| Bars | complete | yes, 1s to 1mo | `candles` only the latest 1440 bars; `history-candles` "recent years" | 1-minute bars from 2023-07 |
| aggTrades / trades | Futures only 48 hours | yes, daily and monthly | 3 months | from 2021-09 |
| Funding rate | complete, 1000 records/request | yes, monthly | only 3 months | from 2022-03 |
| Open interest | only 30 days | in the `metrics` files (columns unverified) | latest 1440 records | not found |
| Long/short ratio | only 30 days | possibly in `metrics` (unverified) | latest 1440 records | not found |
| Taker buy/sell volume | 30 days (limit unverified) | derivable from the bars' taker buy column | latest 1440 records | derive from trades |
| Liquidations | no public REST | none (test path returns 404) | REST no longer in the docs | none |
| Order book | current snapshot only | `bookDepth` (columns unverified) | current snapshot only | L2 from 2023-03 |

Consequences:

1. Bars, trades and funding can be fully recovered at any time.
2. Open interest and long/short ratio: beyond 30 days, depends on Binance's `metrics` files. The first thing to do is download one and inspect the columns.
3. Liquidations have no history anywhere. They exist only from when the WebSocket collector starts, and even then are incomplete: Binance only pushes the latest order every 1000 ms, and OKX states explicitly that its feed is incomplete.

### 2.4 Regional blocking

- From this machine, on 2026-11-13, `api.binance.com`, `fapi.binance.com` and `dapi.binance.com` all returned 200.
- Binance's API docs do not list blocked regions (unverified). From my general knowledge, not from the documents consulted, Binance blocks US IPs. If renting a VPS, pick the region and call `GET /api/v3/ping` and `GET /fapi/v1/ping` before paying long term.
- OKX: accounts registered in the US and Australia use `us.okx.com`; the EU uses `eea.okx.com`; elsewhere uses `openapi.okx.com`. The list of restricted countries could not be read (unverified).

### 2.5 WebSocket

- Binance: a connection lives at most 24 hours and must reconnect itself. Futures has split its URLs into `/public`, `/market`, `/private`.
- OKX: the client must send `ping` after 30 seconds of silence; the exchange drops connections during upgrades, with 60 seconds' notice.
- Both require the collector to have reconnect logic and to record gaps.

### 2.6 Rules for writing a downloader that does not get banned

1. Read `rateLimits` from `exchangeInfo` at startup; do not hard-code numbers.
2. Self-limit to 50% of the allowance.
3. Binance: read `X-MBX-USED-WEIGHT-1M` after every call; on 429, sleep exactly `Retry-After`, do not retry immediately.
4. OKX: check `code` in the body of every response, since errors still return HTTP 200.
5. Get long history from dumps first; REST only fills what is missing.
6. Realtime uses WebSocket, not REST polling.

## 3. What each indicator needs

The "Extra needs" column is anything beyond 1-minute OHLCV bars.

### 3.1 OHLCV only

| Group | Indicator | Tool | Parameters to settle | Extra needs |
|---|---|---|---|---|
| Momentum | RSI, MACD, ROC, Stochastic, Williams %R | TA-Lib | periods; number of warm-up bars discarded | none |
| Volatility | ATR, Bollinger Bands | TA-Lib | period, number of standard deviations | none |
| Trend | EMA/SMA, ADX, OLS regression channel | TA-Lib, numpy | periods, window length | none |
| Volume | OBV, VWAP, anchored VWAP | custom | anchor point (week start, month start, swing) | none; accurate VWAP needs 1-minute bars |
| Structure | swing high/low, HH/HL/LH/LL | custom | swing length (bars on each side) | none |
| SMC | BOS, CHoCH, order block, FVG, premium/discount, displacement | custom | swing length; break on close or wick; ATR-based displacement threshold | none |
| Liquidity | equal highs/lows, liquidity sweep, zones below old lows | custom | ATR-based "equal" tolerance; bars to confirm a sweep | none |
| Wyckoff (components) | climax volume, trading range bounds, spring/upthrust, effort vs result | custom | volume z-score threshold; how to define the range | none |
| Elliott (components) | zigzag pivots, 3 hard rules, Fibonacci ratios | custom | zigzag threshold (% or ATR) | none |
| Sessions | kill zones, Asia–Europe–US session highs/lows | custom | UTC hours of each session | none |

General note for this group: every swing-based signal is only confirmed after N bars. The confirmation time must be stored, otherwise the backtest looks into the future.

### 3.2 Needs data beyond bars

| Indicator | Extra needs | Source | History available? |
|---|---|---|---|
| Approximate volume profile (VPOC, VAH/VAL, HVN/LVN, naked POC) | none, spread 1-minute bar volume across the price range | bars | yes |
| Exact volume profile | individual trades | aggTrades from Binance dumps | yes |
| Per-bar delta, CVD | the taker buy volume column already in Binance bars (delta = 2 × taker buy − volume) | Binance bars | yes |
| Delta by price level, footprint, imbalance, absorption | individual trades with taker side | aggTrades (field `m`) | yes via dumps; Futures REST only 48 hours |
| Funding rate, extreme funding | funding history | Binance REST or dump | yes |
| Basis, premium | mark price, index price, premium index | `markPriceKlines`, `premiumIndexKlines` | yes |
| Open interest, price + OI | 5-minute OI | REST (30 days) + `metrics` files + collector | depends on `metrics` files |
| Long/short ratio | 5-minute ratio | as above | depends on `metrics` files |
| Liquidations, liquidation clusters | liquidation stream | WebSocket `@forceOrder`, `liquidation-orders` | no, only from when we collect |
| Liquidation heatmap | OI + leverage assumptions | own model | an estimate, cannot be validated |
| Order walls, book depth | order book | WebSocket depth; `bookDepth` dump | partial |
| Macro (Fed rates, yields) | FRED series | FRED API, needs a free registered key | yes |
| Gold, DXY | source outside FRED | not chosen | unverified |
| On-chain (MVRV, SOPR, exchange flows) | paid provider | Glassnode, CryptoQuant | pricing unverified |

Volume profile has two parameters that determine the result and must be settled first: the price bin size, and the definition of a "week" (proposed: Monday 00:00 UTC). The value area expansion variant TradingView uses is unverified, so results may differ slightly from your charts.

## 4. Steps

Each step has done criteria. Do not move on until they are met.

### Step 0 — Settle the scope
- Tasks: confirm the table in section 1; decide whether to do the macro part; decide which machine runs the 24/7 collector.
- Done when: the items in sections 1 and 5 have answers.

### Step 1 — Project skeleton and connectivity check
- Tasks: create the git repo, `uv` environment, directory structure, `pytest`, `ruff`. Write a script that calls `ping` and `exchangeInfo` on both exchanges and prints the rate limits in effect. Download one Binance `metrics` file and one `bookDepth` file to inspect the columns.
- Tools: `uv`, `httpx`, `ccxt`.
- Done when: the script runs on the machine that will run the collector; we know for sure whether `metrics` has OI and long/short ratio.

### Step 2 — Realtime collector (do early because the data cannot be recovered)
- Tasks: a WebSocket process recording liquidations, mark price, aggTrades; a 5-minute periodic job recording OI, long/short ratio and taker volume over REST. With reconnects, gap recording, batched Parquet writes.
- Tools: `websockets`, `APScheduler`, `polars`.
- Done when: it runs continuously for 72 hours, survives at least one Binance 24-hour disconnect, and reports gaps accurately.

### Step 3 — Historical download
- Tasks: download Binance dumps (1-minute bars, funding, aggTrades for the needed period), verify checksums; fill the latest part via REST; download OKX for cross-checking.
- Note: Spot dumps from 2025-01-01 use microsecond timestamps; Futures still uses milliseconds.
- Done when: no missing or duplicate bars in the downloaded range; dump and REST bars match where they overlap.

### Step 4 — Storage layer
- Tasks: normalize the schema (UTC, numeric types, common column names for both exchanges); resample 1 minute up to the analysis timeframes; DuckDB views; a manifest table recording source and time range.
- Done when: self-resampled 1h and 1D bars match the 1h and 1D bars the exchange returns.

### Step 5 — Analysis modules, in dependency order
1. Classic indicators (TA-Lib wrappers).
2. Swings and market structure. Everything in 3, 4, 7 depends on this.
3. SMC: BOS, CHoCH, FVG, order block, premium/discount.
4. Liquidity: equal highs/lows, sweeps.
5. Approximate volume profile, then the exact version from aggTrades.
6. Order flow: per-bar delta, CVD, then footprint.
7. Wyckoff and Elliott components.
8. Derivatives features: funding, OI, long/short, liquidations.
9. Macro, if kept.

- Done when (per module): unit tests on hand-built data; every signal has a confirmation time; visual cross-check against TradingView on at least three price segments.

### Step 6 — Backtesting
- Tasks: an engine that takes signals and simulates orders with maker/taker fees, slippage and funding; metrics; comparison against buy-and-hold and linear regression; in-sample/out-of-sample split.
- Done when: a trivial strategy (e.g. an EMA crossover) gives results matching a hand calculation.

### Step 7 — Visualization
- Tasks: candlestick charts with overlays (zones, VPOC, structure labels), a dashboard, backtest reports.
- Tools: Plotly or `lightweight-charts`, Streamlit.
- Done when: your sample charts can be reproduced from the project's data.

### Step 8 — Pine Script
- Tasks: write v6 indicators for the signals that passed step 6.
- Done when: signals on TradingView match the Python signals on the same price segment.

### Deferred
- LLM multi-agent layer.
- Paid on-chain data.
- Live order placement.

## 5. Decisions needed from you

1. Initial list of trading pairs (default BTCUSDT, ETHUSDT).
2. Where the 24/7 collector runs: this Mac (data lost while it sleeps) or a VPS.
3. Whether to keep the macro part (Fed rates, gold, DXY).
4. How deep the history needs to be (proposed: bars from 2020, aggTrades for the last 12 months because of their size).
5. Whether the project is commercial. The answer decides whether vectorbt can be used and LuxAlgo code consulted.
