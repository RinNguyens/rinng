# 10. Plan for moving rinng web to realtime data

Written: 2026-11-14. Scope: crypto, Binance + OKX perps, analysis only (no order placement).

## Current state (checked in the code)

| Part | What exists | Missing for realtime |
|---|---|---|
| Collector (`rinng collect`) | Binance WS: `aggTrade`, `markPrice@1s`, `forceOrder`; equivalent OKX WS; 5-minute REST poller for OI, long/short, taker volume, funding | No candle (kline) stream; not running continuously (has not passed the 72h test); service not installed |
| Store | raw → curated via `curate` + `resample` run by hand, reprocessing everything | No incremental updates; when curated is a few hours old, so is the dashboard |
| Web API | Reads curated, falls back to REST; 60-second cache | Does not push data to the browser; cache is time-based rather than bar-close-based |
| Web UI | Chart drawn once on load | No live price, forming bar or connection status |
| Coins | `configs/instruments.yaml` only has id + exchange symbol (BTC, ETH) | No coin name, base asset or icon |

Principle kept as is: **analysis (SMC, profile, Wyckoff…) only runs on closed bars**, so realtime
does just two things: (1) update the price and the forming bar immediately, (2) recompute lenses exactly when a bar
of that timeframe closes. No signals are drawn from unclosed bars → no lookahead.

## Target architecture

```
Binance WS ─┐                          ┌─ Parquet raw/curated (durable)
OKX WS ─────┼─► rinng live (1 process) ─┤
REST poller ┘   • LiveHub: ring buffer     └─ FastAPI ─► /api/* (lens, summary)
                  1m bars + price + mark               └─► WS /ws/live ─► browser
                • Updater: 1m bar closes →                (tick, forming bar,
                  merge into curated, resample tail        closed bar, funding, liquidations)
```

A single `rinng live` process runs both the collector and the web server (asyncio), so ticks go straight from the exchange WS to the
browser WS without rereading disk. The old `rinng web` stays for browsing static data.

## Steps

### Step 0. Catch up on data (do now, ~a few minutes)
- `rinng backfill` + `rinng curate` + `rinng resample` to bring curated up to now.
- Check: the dashboard says "1H candle closed < 1h ago".

### Step 1. Correct coin metadata and icons
- `instruments.yaml`: add `base` (BTC, ETH), `quote` (USDT), `name` (Bitcoin, Ethereum).
- `/api/meta` returns the instrument list as objects instead of strings.
- Icons: the **`@web3icons/react`** package (MIT, updated 2026-11, thousands of tokens, bundled SVGs — no
  network calls, no data leaks, no rate limits). Shown in the pair picker, the dashboard price card, and each chart header.
  Coins without an icon → first-letter badge.
- Fallbacks considered: `cryptocurrency-icons` (CC0) — unmaintained since 2022, missing new coins;
  CoinGecko images — require an external API and respecting its limits.
- Test: every instrument in the config has an icon or a fallback.

### Step 2. 1m candle stream from the exchanges
- Binance: add `<symbol>@kline_1m` to the existing combined stream.
- OKX: the `candle1m` channel lives on the **business** endpoint (`/ws/v5/business`), different from the public endpoint in use →
  add a second feed; still ping every < 30 seconds like the current feed.
- Only write bars the exchange reports as closed (`x=true` on Binance, `confirm=1` on OKX) to raw `ohlcv_1m`;
  the forming bar is kept in memory only.
- On reconnect: fill missed minutes with REST klines (already in the adapter), record the gap as today.
- Test: replay recorded WS messages → correct bar count, correct `is_closed`.

### Step 3. Incremental curated updates
- New function `curate_tail(exchange, symbol, since)`: merges new 1m bars into curated (using the existing `merge_into`)
  and resamples **only the last bucket** of 15m/1h/4h/1d/1w.
- Runs whenever a 1m bar closes (≈ every minute), replacing the full curate.
- Required test: the result of repeated `curate_tail` == full `curate` + `resample` on the same data.

### Step 4. `rinng live`: LiveHub in one process
- LiveHub holds: last price (aggTrade), mark price + next funding, the forming 1m bar, the forming bar
  of each timeframe (aggregated from 1m), the 50 most recent liquidations.
- Emits internal events: `tick`, `bar_update(tf)`, `bar_close(tf)`, `funding`, `liquidation`.
- The `rinng live` command = collector + updater + FastAPI on the same event loop.
- The lens cache is keyed by **the time of the last closed bar** of that timeframe instead of a 60-second TTL.

### Step 5. WebSocket to the browser
- `WS /ws/live?symbol=&exchange=` sends compact JSON:
  - `tick` (throttled to ~4 per second), `bar` (forming bar for the timeframes the client subscribed to),
  - `close` (tf + time of the just-closed bar), `funding`, `liq`.
- Browser:
  - Chart: `series.update()` for the forming bar (drawn fainter to distinguish it); on a `close` for the chart's own
    tf → call `/api/chart` again to redraw the lens.
  - Dashboard: price, 24h %, mark/funding + countdown to the next funding update on each tick; context cards are recomputed
    when a 1H bar closes.
  - One WS connection shared by the whole tab, not one connection per chart.

### Step 6. Reliability and status display
- Status dot in the top bar: **Live** (tick < 5s), **Delayed** (5–60s), **Offline**; plus data age.
- Reconnect with backoff in both directions (exchange → server, server → browser).
- Exchange-side limits to respect: Binance drops every WS connection after 24 hours (reconnect already handled),
  at most 1024 streams per connection; OKX needs a ping after 30 seconds of silence. REST still goes through the existing `WeightLimiter`.
- Log message counts, latency, reconnect counts; `rinng check` gets a "live" section.

### Step 7. Continuous operation
- 72-hour trial run (criterion still owed from Phase 1): no lost bars, gaps filled, stable RAM.
- Install the launchd service from `deploy/` (needs your approval since it is a system change).

### Step 8 (optional). More coins
- Add instruments to the config (e.g. SOL, BNB, XRP), run backfill; icons are already available from Step 1.
- Mind the storage: each extra coin's raw aggTrade data is fairly heavy; trade storage can be turned off for minor coins.

## Status (2026-11-14)

| Step | Status |
|---|---|
| 0 | Done: backfill 2026-11-01 → now for Binance + OKX, resampled |
| 1 | Done: `base/quote/name` in config, `@web3icons/react` icons in the picker, dashboard, chart |
| 2 | Done: `kline_1m` (Binance), `candle1m` via `/ws/v5/business` (OKX); only closed bars written |
| 3 | Done: `rinng.live.tail.curate_tail`, test equivalent to a full resample |
| 4 | Done: `LiveHub`, `rinng live` command, REST gap fill every minute, cache keyed by closed bar |
| 5 | Done: `/ws/live`, forming bar (faded), lens redrawn on bar close, live price/funding on the dashboard, Live/Delayed/Offline dot |
| 6–7 | Not started |

## Proposed order and done criteria

| Step | Done when |
|---|---|
| 0 | Dashboard is never more than 1 hour stale |
| 1 | Correct BTC/ETH icons in the picker, dashboard, chart |
| 2–3 | 1m bars reach curated within < 5 seconds of closing; equivalence test with full curate passes |
| 4–5 | Web price moves with ticks; forming bar updates; lenses redraw automatically on bar close |
| 6 | Unplug the network for 1 minute and reconnect: UI shows Offline → Live, no missing bars |
| 7 | 72 hours continuous without errors |
