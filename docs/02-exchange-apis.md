# 02 — Exchange APIs: Binance and OKX

> Lookup date: **2026-11-13**. Every figure below comes from the current official documentation or from real calls to public APIs on that day. Exchange APIs change often: before coding, reopen the source URL in each section.

## 0. How to read this document

Confidence markers:

| Marker | Meaning |
|---|---|
| **[docs]** | Read directly from the official documentation (URL given). |
| **[live]** | Called the public endpoint on 2026-11-13 and got the result exactly as described. |
| **[unverified]** | Source page could not be opened, was truncated, or this is only inferred. Do not rely on it without checking yourself. |

Three major changes compared with older knowledge (easy to break code written from memory):

1. **Binance Futures WebSocket split its base URL** into `/public`, `/market`, `/private`. The old URL `wss://fstream.binance.com/ws/...` only receives public-group data (depth, bookTicker); `markPrice`, `kline`, `aggTrade`, `forceOrder` must go through `/market`. [docs]
2. **OKX moved its REST host to `https://openapi.okx.com`** and dropped the order book `checksum` (fixed value 0), replacing it with `seqId`/`prevSeqId`. [docs]
3. **Binance merged COIN-M into the USDⓈ-M infrastructure** (rolling out from 2026-06-24): `fapi` and `dapi` share one rate limit pool of 2400 weight/minute/IP. [docs]

The Binance docs site has also moved to a new structure (`/en/docs/products/...` and `/en/docs/catalog/...`); old-style links `/docs/derivatives/...` redirect automatically. Full-text version: <https://developers.binance.com/en/docs/llms-full.txt>, endpoint index: <https://developers.binance.com/en/docs/llms.txt>.

---

## 1. Binance

### 1.1 Base URLs and versions

| Product | REST mainnet | Prefix / version | WebSocket market data mainnet |
|---|---|---|---|
| Spot | `https://api.binance.com` (fallbacks: `api-gcp`, `api1`–`api4`) | `/api/v3` | `wss://stream.binance.com:9443` or `:443` |
| Spot, public market data only | `https://data-api.binance.vision` | `/api/v3` | `wss://data-stream.binance.vision` |
| USDⓈ-M Futures | `https://fapi.binance.com` | `/fapi/v1` (some `/fapi/v2`, `/fapi/v3`), statistics under `/futures/data` | `wss://fstream.binance.com` + `/public`, `/market`, `/private` |
| COIN-M Futures | `https://dapi.binance.com` | `/dapi/v1`, statistics under `/futures/data` | `wss://dstream.binance.com` |

| Test environment | REST | WebSocket |
|---|---|---|
| Spot Testnet | `https://testnet.binance.vision/api` (fallback `https://api1.testnet.binance.vision/api`) | `wss://stream.testnet.binance.vision` |
| Spot Demo Mode | `https://demo-api.binance.com/api` | `wss://demo-stream.binance.com` (`/ws`, `/stream`), WS API `wss://demo-ws-api.binance.com/ws-api/v3` |
| USDⓈ-M Futures testnet | `https://demo-fapi.binance.com` | `wss://demo-fstream.binance.com` |
| COIN-M Futures testnet | `https://demo-dapi.binance.com` | `wss://demo-dstream.binance.com` |

Sources [docs]:
- Spot REST: <https://developers.binance.com/en/docs/products/spot/rest-api>
- Spot testnet: <https://developers.binance.com/en/docs/products/spot/testnet/general-info>
- Spot demo mode: <https://developers.binance.com/en/docs/products/spot/demo-mode/general-info>
- USDⓈ-M: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info>
- COIN-M: <https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/general-info>

Notes:
- `api1`–`api4` "may be faster but less stable". [docs]
- `data-api.binance.vision` only serves endpoints with security type `NONE` (klines, depth, aggTrades, ticker, exchangeInfo, ping, time...). It returns the `X-MBX-USED-WEIGHT-1M` header like the main host. [docs][live]
- All testnet/demo hosts above return `{}` for `ping`. [live]
- Timestamps: milliseconds by default. Spot alone can request microseconds via the header `X-MBX-TIME-UNIT: MICROSECOND` (REST) or the parameter `timeUnit=MICROSECOND` (WebSocket). Futures is milliseconds only. [docs]
- Data is returned in **ascending** order (oldest first, newest last). [docs]

### 1.2 Spot — public market data endpoints

Source [docs]: <https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market> (old version: <https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints>)

| Data | Endpoint | Weight | Main parameters | Per-call limit |
|---|---|---|---|---|
| Klines | `GET /api/v3/klines` | 2 | `symbol`*, `interval`*, `startTime`, `endTime`, `timeZone` (default `0` = UTC), `limit` | default 500, max **1000** |
| Klines for charts | `GET /api/v3/uiKlines` | 2 | same as above | 500 / 1000 |
| Order book | `GET /api/v3/depth` | 5 (limit 1–100), 25 (101–500), 50 (501–1000), 250 (1001–5000) | `symbol`*, `limit` | default 100, max **5000** |
| Recent trades | `GET /api/v3/trades` | 25 | `symbol`*, `limit` | 500 / 1000 |
| Older trades | `GET /api/v3/historicalTrades` | 25 | `symbol`*, `limit`, `fromId` | 500 / 1000 |
| Aggregate trades | `GET /api/v3/aggTrades` | 4 | `symbol`*, `fromId`, `startTime`, `endTime`, `limit` | 500 / 1000 |
| 24h ticker | `GET /api/v3/ticker/24hr` | 2 (1 symbol) to 80 (all) | `symbol` or `symbols`, `type` (`FULL`/`MINI`) | `symbols` max 100 |
| Rolling window ticker | `GET /api/v3/ticker` | 4 per symbol, cap 200 | `symbol`/`symbols`, `windowSize` (default `1d`) | `symbols` max 100 |
| Trading day ticker | `GET /api/v3/ticker/tradingDay` | 4 per symbol, cap 200 | `symbol`/`symbols`, `timeZone` | max 100 |
| Latest price | `GET /api/v3/ticker/price` | 2 (1 symbol) / 4 | `symbol`/`symbols` | — |
| Best bid/ask | `GET /api/v3/ticker/bookTicker` | 2 (1 symbol) / 4 | `symbol`/`symbols` | — |
| Average price | `GET /api/v3/avgPrice` | 2 | `symbol`* | — |

(* = required)

**Spot kline intervals** (case-sensitive): `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`. [docs]

**Pagination for long history:**
- Klines: set `startTime`, fetch up to 1000 candles, then call again with `startTime = openTime of last candle + 1`. Without `startTime`/`endTime` you get the most recent candles. [docs][live]
- aggTrades: use `fromId` (inclusive) to continue from the last record's `a` + 1; or use a `startTime`/`endTime` window. [docs]
- historicalTrades: use `fromId`. [docs]
- Multi-year history: use the dump files in section 1.9 instead of REST.

### 1.3 USDⓈ-M Futures — public market data endpoints

Source [docs]: <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data> (old version: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api>)

Base: `https://fapi.binance.com`.

| Data | Endpoint | Weight | Main parameters | Limits / notes |
|---|---|---|---|---|
| Klines | `GET /fapi/v1/klines` | by `limit`: 1 (<100), 2 (100–499), 5 (500–1000), 10 (>1000) | `symbol`*, `interval`*, `startTime`, `endTime`, `limit` | default 500, max **1500** |
| Continuous contract klines | `GET /fapi/v1/continuousKlines` | same as klines | `pair`*, `contractType`* (`PERPETUAL`, `CURRENT_QUARTER`, `NEXT_QUARTER`, `TRADIFI_PERPETUAL`), `interval`* | 500 / 1500 |
| Index price klines | `GET /fapi/v1/indexPriceKlines` | same as klines | `pair`*, `interval`* | 500 / 1500 |
| Mark price klines | `GET /fapi/v1/markPriceKlines` | same as klines | `symbol`*, `interval`* | 500 / 1500 |
| Premium index klines | `GET /fapi/v1/premiumIndexKlines` | same as klines | `symbol`*, `interval`* | 500 / 1500 |
| Order book | `GET /fapi/v1/depth` | 2 (limit 5/10/20/50), 5 (100), 10 (500), 20 (1000) | `symbol`*, `limit` ∈ {5, 10, 20, 50, 100, 500, 1000} | default 500, max **1000**; excludes RPI orders |
| Recent trades | `GET /fapi/v1/trades` | 5 | `symbol`*, `limit` | 500 / 1000 |
| Older trades (API key required) | `GET /fapi/v1/historicalTrades` | 200 | `symbol`*, `limit`, `fromId`, header `X-MBX-APIKEY` | 100 / 500; last 1 month only |
| Aggregate trades | `GET /fapi/v1/aggTrades` | 20 | `symbol`*, `fromId`, `startTime`, `endTime`, `limit` | 500 / 1000; **only the last 48 hours can be queried**; if both `startTime` and `endTime` are sent the span must be < 1 hour |
| Current mark price + funding | `GET /fapi/v1/premiumIndex` | 1 (with symbol) / 10 (without) | `symbol` | returns `markPrice`, `indexPrice`, `lastFundingRate`, `nextFundingTime` [live] |
| Funding rate history | `GET /fapi/v1/fundingRate` | shares a **500 requests / 5 minutes / IP** limit with `fundingInfo` | `symbol`, `startTime`, `endTime`, `limit` | default 100, max **1000**; without times returns the latest 200 records; ascending order |
| Funding info (cap/floor, interval) | `GET /fapi/v1/fundingInfo` | 0 (shares 500/5 min/IP) | — | — |
| Current open interest | `GET /fapi/v1/openInterest` | 1 | `symbol`* | — |
| Open interest history | `GET /futures/data/openInterestHist` | 0; separate limit **1000 requests / 5 minutes / IP** | `symbol`*, `period`*, `limit`, `startTime`, `endTime` | 30 / **500**; **last 1 month only**; periods with no trading are left empty, not filled |
| Long/short ratio (all accounts) | `GET /futures/data/globalLongShortAccountRatio` | 0; 1000 requests / 5 minutes / IP | `symbol`*, `period`*, `limit`, `startTime`, `endTime` | 30 / 500; last 30 days only |
| Top trader long/short ratio (accounts) | `GET /futures/data/topLongShortAccountRatio` | [unverified] | same as above [unverified] | [unverified] |
| Top trader long/short ratio (positions) | `GET /futures/data/topLongShortPositionRatio` | [unverified] | `symbol`, `period`, `limit` [live] | [unverified] |
| Taker buy/sell volume | `GET /futures/data/takerlongshortRatio` | [unverified] | `symbol`, `period`, `limit` [live] | returns `buySellRatio`, `buyVol`, `sellVol` [live] |
| Basis | `GET /futures/data/basis` | 0 | `pair`*, `contractType`*, `period`*, `limit` | 30 / 500; last 30 days only |
| 24h ticker | `GET /fapi/v1/ticker/24hr` | [unverified] | `symbol` [live] | — |
| Latest price | `GET /fapi/v1/ticker/price`, `GET /fapi/v2/ticker/price` | [unverified] | `symbol` | — |
| Best bid/ask | `GET /fapi/v1/ticker/bookTicker` | [unverified] | `symbol` | — |
| Index constituents | `GET /fapi/v1/constituents` | 2 | `symbol`* | — |
| Exchange info, filters, rate limits | `GET /fapi/v1/exchangeInfo` | 1 | — | — |

Notes:
- **Futures kline intervals**: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`. The first eight were read from the docs; the rest are hidden on the docs page, so they were confirmed by real calls (all returned 200). `1s` on `/fapi/v1/klines` returns 400; `2m` returns `-1120 Invalid interval`. [live] `continuousKlines` additionally has `1s` per the docs.
- **`period` for the `/futures/data/*` group**: `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d` (the `1d` value is hidden in the docs, test call succeeded). [docs][live]
- Calling klines with `limit=1500` costs more weight than the table above suggests: one test call raised `X-MBX-USED-WEIGHT-1M` to 50 (including earlier calls in that minute). Always read the header instead of summing yourself. [live]
- **[unverified]** rows: the docs page is truncated after the "RPI Order Book" section, so the weight and limits for the alphabetically last endpoints could not be read. The endpoint names are in the official `llms.txt` index and test calls succeeded.
- After the COIN-M merge, the docs say the `fapi` klines endpoints "accept both UM and CM symbols". [docs]
- **Liquidation**: the current REST index **has no** public endpoint returning market-wide liquidations. `GET /fapi/v1/forceOrders` is `USER_DATA` (only the account's own liquidation orders). Public liquidation data arrives only via the WebSocket `@forceOrder` (section 1.5). [docs]

**Pagination:** klines same as Spot (advance `startTime`). `fundingRate`: when data in the range exceeds `limit`, the exchange returns from `startTime` onward, so advance `startTime = last fundingTime + 1`. The `/futures/data/*` group keeps only about 30 days, so long history requires **collecting it yourself periodically** or using the `metrics` files in section 1.9.

### 1.4 COIN-M Futures — main differences

Source [docs]: <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-coin-m-futures/api/rest-api/market-data>, merge notice: <https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/Important-CM-UM-Integration-Notice>

Base: `https://dapi.binance.com`. Symbols look like `BTCUSD_PERP` (perpetual), `BTCUSD_YYMMDD` (delivery); `pair` is `BTCUSD`.

| Data | Endpoint | Weight | Limits / notes |
|---|---|---|---|
| Klines | `GET /dapi/v1/klines` (and `continuousKlines`, `indexPriceKlines`, `markPriceKlines`, `premiumIndexKlines`) | 1 / 2 / 5 / 10 by `limit` | 500 / **1500**; `startTime`–`endTime` span max **200 days** |
| Order book | `GET /dapi/v1/depth` | 2 / 5 / 10 / 20 | 500 / 1000 |
| Trades | `GET /dapi/v1/trades` | 5 | 500 / 1000 |
| Aggregate trades | `GET /dapi/v1/aggTrades` | 20 | 500 / 1000; last 48 hours only; window < 1 hour |
| Mark + index price | `GET /dapi/v1/premiumIndex` | 10 | `symbol` or `pair` |
| Funding rate history | `GET /dapi/v1/fundingRate` | 1 | `symbol`*; 100 / 1000 |
| Open interest | `GET /dapi/v1/openInterest` | 1 | `symbol`* |
| Open interest history | `GET /futures/data/openInterestHist` | 1 | `pair`*, `period`*, `contractType`; 30 / 500; 30 days only |
| Long/short ratio | `GET /futures/data/globalLongShortAccountRatio` | 1 | `pair`*, `period`*; 30 / 500; 30 days only |
| Taker buy/sell volume | `GET /futures/data/takerBuySellVol` | [unverified] | `pair`, `contractType`, `period` [live] |

Note the taker volume endpoint names differ: `takerlongshortRatio` (USDⓈ-M) and `takerBuySellVol` (COIN-M). [docs]

### 1.5 WebSocket market streams

#### Spot

Source [docs]: <https://developers.binance.com/en/docs/products/spot/web-socket-streams>

- Raw stream: `wss://stream.binance.com:9443/ws/<streamName>`. Combined: `/stream?streams=<s1>/<s2>/<s3>`, payload wrapped as `{"stream":"<streamName>","data":{...}}`.
- Symbol names in streams must be **lowercase**.
- Dynamic subscribe:
  ```json
  {"method": "SUBSCRIBE", "params": ["btcusdt@aggTrade", "btcusdt@depth"], "id": 1}
  ```
  Use `UNSUBSCRIBE` with the same structure to cancel. `id` is a 64-bit integer, an alphanumeric string up to 36 characters, or `null`. A response of `"result": null` means success.
- A connection lives only **24 hours**. The server sends a `serverShutdown` event before shutting down.
- **Ping/pong**: the server sends a ping frame every **20 seconds**; if no pong is received within **1 minute** it disconnects. The pong must echo the ping payload. Unsolicited pongs are allowed but do not keep the connection alive.
- **Limits**: 5 outgoing messages per second (including PING, PONG, JSON commands); max **1024 streams** per connection; **300 connections per 5 minutes per IP**. Exceeding limits disconnects you; repeat offenders may get an IP ban.

| Stream | Name | Frequency |
|---|---|---|
| Aggregate trade | `<symbol>@aggTrade` | real-time |
| Trade | `<symbol>@trade` | real-time |
| Kline (UTC) | `<symbol>@kline_<interval>` | 1000 ms for `1s`, 2000 ms for other intervals |
| Kline with timezone offset | `<symbol>@kline_<interval>@+08:00` | same as above |
| Mini ticker | `<symbol>@miniTicker`, `!miniTicker@arr` | 1000 ms |
| 24h ticker | `<symbol>@ticker` | 1000 ms |
| Rolling window ticker | `<symbol>@ticker_<windowSize>` (`1h`, `4h`, `1d`), `!ticker_<windowSize>@arr` | 1000 ms |
| Best bid/ask | `<symbol>@bookTicker` | real-time |
| Average price | `<symbol>@avgPrice` | 1000 ms |
| Partial depth | `<symbol>@depth<levels>` or `@100ms` (`levels` = 5, 10, 20) | 1000 ms or 100 ms |
| Diff depth | `<symbol>@depth` or `<symbol>@depth@100ms` | 1000 ms or 100 ms |

**Building a local order book — Spot** (exactly per the docs):

1. Open a connection to `wss://stream.binance.com:9443/ws/bnbbtc@depth`.
2. Buffer the received events. Note the `U` of the first event.
3. Get a snapshot: `GET https://api.binance.com/api/v3/depth?symbol=BNBBTC&limit=5000`.
4. If the snapshot's `lastUpdateId` is **strictly less than** the `U` from step 2, go back to step 3.
5. In the buffer, drop every event with `u <= lastUpdateId`. The first remaining event must have `lastUpdateId` within `[U; u]`.
6. Set local book = snapshot, update ID = `lastUpdateId`.
7. Apply the buffered events, then new events, in order, with these rules:
   - `u` < the local book's update ID: ignore the event.
   - `U` > the local book's update ID + 1: events were lost, **discard the book and restart from scratch**.
   - Normally the next event's `U` = the previous event's `u` + 1.
   - For each price level in `b` and `a`: the quantity is an **absolute** value; 0 means remove the level; a missing level is added.
   - Set the book's update ID = `u`.

The snapshot has at most 5000 levels per side, so levels outside the snapshot are only known when they change.

#### USDⓈ-M Futures

Sources [docs]:
- Connection: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect>
- URL split notice: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice>
- Stream catalog: <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams>

Three entry points:

| Group | Base | Streams in the group |
|---|---|---|
| Public (high frequency) | `wss://fstream.binance.com/public` | `<symbol>@bookTicker`, `!bookTicker`, `<symbol>@depth<levels>`, `<symbol>@depth` |
| Market | `wss://fstream.binance.com/market` | `<symbol>@aggTrade`, `<symbol>@markPrice`, `!markPrice@arr`, `<symbol>@kline_<interval>`, `<pair>_<contractType>@continuousKline_<interval>`, `<symbol>@miniTicker`, `!miniTicker@arr`, `<symbol>@ticker`, `!ticker@arr`, `<symbol>@forceOrder`, `!forceOrder@arr`, `<symbol>@compositeIndex`, `!contractInfo`, `!assetIndex@arr` |
| Private | `wss://fstream.binance.com/private` | user data (`listenKey` + `events`) |

- Two access styles: `.../market/ws/<streamName>` and `.../market/stream?streams=<s1>/<s2>`.
- Example: `wss://fstream.binance.com/market/stream?streams=bnbusdt@aggTrade/btcusdt@markPrice`.
- Connections **without** a `/public`, `/market`, `/private` prefix receive only Public-group data. The docs say the old URLs (`/ws`, `/stream`) are removed after **2026-04-23**; always use prefixed URLs.
- Connections live 24 hours. The server sends a ping frame every **3 minutes**; if no pong arrives within **10 minutes** it disconnects. Unsolicited pongs are allowed.
- Limits: **10 outgoing messages per second**; max **1024 streams** per connection.
- Dynamic subscribe same as Spot (`{"method":"SUBSCRIBE","params":[...],"id":...}`).

| Stream | Frequency | Notes |
|---|---|---|
| `<symbol>@aggTrade` | 100 ms | aggregates market trades only; excludes insurance fund and ADL |
| `<symbol>@markPrice`, `<symbol>@markPrice@1s` | 3 s or 1 s | mark price, index price, funding rate, next funding time |
| `<symbol>@kline_<interval>` | 250 ms | field `x` tells whether the candle is closed |
| `<symbol>@forceOrder`, `!forceOrder@arr` | 1000 ms | **only pushes the latest liquidation order** in each 1000 ms window, not all of them |
| `<symbol>@ticker` / `!ticker@arr` | 2000 ms / 1000 ms | rolling 24h statistics |
| `<symbol>@depth`, `<symbol>@depth<levels>` (5, 10, 20) | 250 ms default, `@500ms`, `@100ms` | the description says 250 ms but the parameter enum lists only 100 ms and 500 ms — a contradiction in the docs, check yourself |
| `<symbol>@bookTicker` | real-time | — |

**Building a local order book — Futures** (differs from Spot by the `pu` field):

1. Open the stream `wss://fstream.binance.com/public/stream?streams=btcusdt@depth`.
2. Buffer the events. For the same price level, a later event overwrites an earlier one.
3. Get a snapshot: `GET https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000`.
4. Drop every event with `u` < the snapshot's `lastUpdateId`.
5. The first processed event must satisfy `U <= lastUpdateId` **and** `u >= lastUpdateId`.
6. From then on, each new event's `pu` must equal the previous event's `u`; otherwise restart from step 3.
7. The quantity in an event is the **absolute** value for that price level.
8. A quantity of 0 means **remove** the price level.
9. Receiving an event that removes a price level not in the local book is normal.

Source: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly>

#### COIN-M Futures

Source [docs]: <https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/websocket-market-streams/Connect>

Base `wss://dstream.binance.com`, access via `/ws/<streamName>` or `/stream?streams=...`. Same rules as USDⓈ-M: 24 hours, ping every 3 minutes / pong within 10 minutes, 10 messages/second, 1024 streams. The COIN-M Connect page does not yet describe `/public`, `/market` prefixes; whether COIN-M splits URLs like USDⓈ-M is **[unverified]**.

### 1.6 Rate limits

Sources [docs]: <https://developers.binance.com/en/docs/products/spot/rest-api> (Limits section), <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info>

| Product | REQUEST_WEIGHT | ORDERS | Other |
|---|---|---|---|
| Spot | **6000 / minute / IP** | 100 / 10 seconds; 200 000 / day (per account) | RAW_REQUESTS 300 000 / 5 minutes |
| USDⓈ-M + COIN-M (shared) | **2400 / minute / IP** | 1200 / minute; 300 / 10 seconds (per account) | — |

These figures were read from `rateLimits` in `GET /api/v3/exchangeInfo`, `/fapi/v1/exchangeInfo`, `/dapi/v1/exchangeInfo` [live]; that is the canonical source, re-read it at program startup because Binance may change it.

- Weight limits are per **IP**, not per API key. Order limits are per account.
- Response headers: `X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)`, e.g. `X-MBX-USED-WEIGHT-1M`; orders: `X-MBX-ORDER-COUNT-10S`, `X-MBX-ORDER-COUNT-1M`. Letters: `S`, `M`, `H`, `D`.
- **HTTP 429**: rate limit exceeded. You must stop sending (back off).
- **HTTP 418**: IP auto-banned for continuing to send after a 429. Ban duration escalates **from 2 minutes to 3 days**.
- The `Retry-After` header (seconds) comes with 429 and 418: for 429 it is the wait to avoid a ban; for 418 it is the time until the ban lifts.
- **HTTP 403**: WAF violation.
- Some endpoints have separate limits beyond weight: `fundingRate` + `fundingInfo` 500 requests / 5 minutes / IP; the `/futures/data/*` group 1000 requests / 5 minutes / IP.
- The docs recommend using WebSocket for data instead of polling REST.

### 1.7 Common error codes

Sources [docs]: <https://developers.binance.com/en/docs/products/spot/errors>, <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/error-code>

Error payload: `{"code": -1121, "msg": "Invalid symbol."}`.

| Code | Name | Meaning |
|---|---|---|
| `-1003` | `TOO_MANY_REQUESTS` | Too much request weight used |
| `-1007` | `TIMEOUT` | Backend timeout; execution status **unknown** |
| `-1008` | `SERVER_BUSY` | Server overloaded (Futures: throttled; reduce-only orders exempt) |
| `-1015` | `TOO_MANY_ORDERS` | Order count limit exceeded |
| `-1021` | `INVALID_TIMESTAMP` | Timestamp outside `recvWindow` or more than 1000 ms ahead of the server |
| `-1022` | `INVALID_SIGNATURE` | Bad signature |
| `-1100` | `ILLEGAL_CHARS` | Illegal characters in a parameter |
| `-1120` | — | `Invalid interval.` [live] |
| `-1121` | `BAD_SYMBOL` | Invalid symbol |
| `-2014` | `BAD_API_KEY_FMT` | Bad API key format |
| `-2015` | `REJECTED_MBX_KEY` | Invalid API key, IP, or permissions for the action |

HTTP 5XX and 503 with the message "Unknown error..." on Futures mean the status is **unknown**, not a failure; you must re-check via the user data stream or an order query. [docs]

### 1.8 Authentication, API key permissions, security

Sources [docs]: general-info in section 1.1; API key management: <https://www.binance.com/en/support/faq/detail/360002502072>

- The API key is sent in the **`X-MBX-APIKEY`** header. Key and secret are case-sensitive.
- Security types: `NONE` (public), `MARKET_DATA` and `USER_STREAM` (API key only), `TRADE` and `USER_DATA` (API key **and signature** — called `SIGNED`).
- `SIGNED` signature: add the parameters `timestamp` (ms) and `signature`. `signature` = HMAC SHA256 keyed with `secretKey`, over `totalParams` (query string concatenated with the request body); put `signature` last. Case-insensitive.
- `recvWindow`: default 5000 ms; Spot max 60000 ms. The server accepts when `timestamp < serverTime + 1000` and `serverTime - timestamp <= recvWindow`. Sync the clock with `GET /api/v3/time` or `GET /fapi/v1/time`.
- Key types: HMAC (exchange-generated, with secret), **Ed25519** and RSA (generate your own key pair, submit the public key). The Spot docs recommend Ed25519.
- Permissions and constraints per Binance's support page:
  - HMAC keys **without an IP restriction are read-only** (since 2023-01-30).
  - Withdrawal permission requires an IP restriction (IPv4).
  - Full list of permission names and maximum number of keys: **[unverified]** (the support page does not list them all).

Recommendations for this project:
- Research and data collection: **no key needed**. If a key is needed (e.g. `historicalTrades`), create a **read-only** key.
- Trading keys: enable IP whitelist, enable only the permissions needed, **do not enable withdrawal**.
- Test order placement on testnet/demo first, with a key specific to that environment.
- Never commit keys to git; read them from environment variables or a secret manager.

Trading and account endpoint groups (listed only, no detailed guide):

| Group | Spot | USDⓈ-M Futures |
|---|---|---|
| Place / cancel / query orders | `/api/v3/order`, `/api/v3/openOrders`, `/api/v3/allOrders` | `/fapi/v1/order`, `/fapi/v1/batchOrders`, `/fapi/v1/allOrders`, `/fapi/v1/algoOrder` |
| Account, balances, positions | `/api/v3/account`, `/api/v3/myTrades` | `/fapi/v3/account`, `/fapi/v3/balance`, `/fapi/v3/positionRisk`, `/fapi/v1/userTrades`, `/fapi/v1/income` |
| User data stream | via WebSocket API (`userDataStream.*`) | `/fapi/v1/listenKey` |
| Wallet, deposits/withdrawals | `/sapi/v1/capital/...` (e.g. `/sapi/v1/capital/withdraw/apply`) | — |

Full index: <https://developers.binance.com/en/docs/llms.txt>.

### 1.9 Bulk historical data — data.binance.vision

Sources [docs]: <https://github.com/binance/binance-public-data>, file browser: <https://data.binance.vision>

- URL pattern (README example): `https://data.binance.vision/data/spot/monthly/klines/ADABKRW/1h/ADABKRW-1h-2020-08.zip`.
- Each `.zip` file has a `.CHECKSUM` file in the same folder; verify with `shasum -a 256 -c <file>.zip.CHECKSUM` (macOS) or `sha256sum -c` (Linux).
- Daily files appear **the next day**; monthly files appear **on the first Monday of the month**.
- Kline intervals: `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1mo` (`1mo` instead of `1M`).
- **Spot data from 2025-01-01 uses microsecond timestamps**; Futures is still milliseconds. Handle this when stitching series across that date.
- Published files may be updated later.

CSV columns:

| File | Columns |
|---|---|
| Spot and USDⓈ-M klines | open time, open, high, low, close, volume, close time, quote asset volume, number of trades, taker buy base asset volume, taker buy quote asset volume, ignore |
| COIN-M klines | open time, open, high, low, close, volume, close time, base asset volume, number of trades, taker buy volume, taker buy base asset volume, ignore |
| Spot aggTrades | agg tradeId, price, quantity, first tradeId, last tradeId, timestamp, was buyer maker, was best price match |
| Futures aggTrades | same as Spot without the last column |
| Spot trades | trade Id, price, qty, quoteQty, time, isBuyerMaker, isBestMatch |
| USDⓈ-M trades | trade Id, price, qty, quoteQty, time, isBuyerMaker |

Paths checked with HTTP HEAD on 2026-11-13 (the README does not list them all, so these are [live], not [docs]):

| Path under `https://data.binance.vision/data/` | Result |
|---|---|
| `spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` (+ `.CHECKSUM`) | 200 |
| `spot/daily/trades/BTCUSDT/BTCUSDT-trades-2026-11-10.zip` | 200 |
| `spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-10.zip` | 200 |
| `futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-11-10.zip` | 200 |
| `futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/bookDepth/BTCUSDT/BTCUSDT-bookDepth-2026-11-10.zip` | 200 |
| `futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-11-10.zip` | 200 |
| `futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-10.zip` | 200 |
| `futures/cm/daily/klines/BTCUSD_PERP/1m/BTCUSD_PERP-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/bookTicker/...`, `futures/um/daily/liquidationSnapshot/...`, `futures/cm/monthly/fundingRate/...` | 404 for the days/months tried |

The `metrics` files are the way around the 30-day REST limit for open interest and long/short ratio; the column contents of `metrics` and `bookDepth` are **[unverified]** (files not downloaded and read).

### 1.10 Regional restrictions

- Binance's API docs **do not list** restricted regions. The "List of Prohibited Countries" page (<https://www.binance.com/en/legal/list-of-prohibited-countries>) exists but its content could not be read by automated tools: **[unverified]**.
- From the project's development machine (2026-11-13), `api.binance.com`, `fapi.binance.com`, `dapi.binance.com`, `data-api.binance.vision` all returned 200. [live] Servers in other regions may be blocked; check with `GET /api/v3/ping` before deploying.

---

## 2. OKX

Source [docs] for this whole section: <https://www.okx.com/docs-v5/en/> (a single page; the links below are anchors). Vietnamese version of the intro page: <https://www.okx.com/vi/okx-api>.

### 2.1 Base URLs and versions

API version: **v5** (prefix `/api/v5`, WebSocket `/ws/v5`).

| Environment | REST | WebSocket public | WebSocket private | WebSocket business |
|---|---|---|---|---|
| Production | `https://openapi.okx.com` | `wss://ws.okx.com/ws/v5/public` | `wss://ws.okx.com/ws/v5/private` | `wss://ws.okx.com/ws/v5/business` |
| Demo trading | `https://openapi.okx.com` + header `x-simulated-trading: 1` | `wss://wspap.okx.com/ws/v5/public` | `wss://wspap.okx.com/ws/v5/private` | `wss://wspap.okx.com/ws/v5/business` |

Sources: <https://www.okx.com/docs-v5/en/#overview-production-trading-services>, <https://www.okx.com/docs-v5/en/#overview-demo-trading-services>

- Demo trading uses **separate API keys** created in the Demo Trading section; some features (deposits, withdrawals...) are not supported.
- The old host `https://www.okx.com/api/v5/...` still returns data in test calls [live], but the docs now list only `openapi.okx.com`; use the new host.
- The docs announce WebSocket port **8443 will be removed soon**; use port 443 (default).
- Timestamps in data: Unix **milliseconds**, as **strings**. All numbers (price, volume) are strings too.
- REST responses always look like `{"code": "0", "msg": "", "data": [...]}`; a `code` other than `"0"` is an error, even when the HTTP status is 200.

### 2.2 Instrument identifiers

Source: <https://www.okx.com/docs-v5/en/#overview-general-info>

| Type (`instType`) | Example `instId` |
|---|---|
| `SPOT` | `BTC-USDT` |
| `SWAP` (perpetual) USDT-margined | `BTC-USDT-SWAP` |
| `SWAP` coin-margined | `BTC-USD-SWAP` |
| `FUTURES` (dated) | `BTC-USDT-250808`, `BTC-USD-250808` |
| `OPTION` | by `instFamily`, e.g. family `BTC-USD` |

`uly` is the index (e.g. `BTC-USD`); `instFamily` is the instrument family (e.g. `BTC-USDT`). Instrument list: `GET /api/v5/public/instruments?instType=SWAP` (20 requests / 2 seconds, per IP + instType).

### 2.3 Public market data endpoints

Rate limits for all endpoints below are per **IP** (some per IP + instId); no API key required.

| Data | Endpoint | Rate limit | Main parameters | Limits / notes |
|---|---|---|---|---|
| Recent candles | `GET /api/v5/market/candles` | 40 / 2 s | `instId`*, `bar`, `after`, `before`, `limit` | default 100, max **300**; only the **latest 1440 candles** are available |
| Historical candles | `GET /api/v5/market/history-candles` | 20 / 2 s | same as above | 100 / **300** [docs]; data for "recent years"; `1s` candles only 3 months |
| Mark price candles | `GET /api/v5/market/mark-price-candles`, `.../history-mark-price-candles` | 20 / 2 s | `instId`*, `bar`, `after`, `before`, `limit` | max 100 |
| Index candles | `GET /api/v5/market/index-candles`, `.../history-index-candles` | 20 / 2 s, history 10 / 2 s | `instId`* (index, e.g. `BTC-USD`) | max 100 |
| Order book | `GET /api/v5/market/books` | 40 / 2 s | `instId`*, `sz` | `sz` max **400** per side, default 1; updated every 50 ms |
| Full order book | `GET /api/v5/market/books-full` | 10 / 2 s | `instId`*, `sz` | `sz` max **5000** per side; updated every 1 s |
| Recent trades | `GET /api/v5/market/trades` | 100 / 2 s | `instId`*, `limit` | 100 / **500** |
| Historical trades | `GET /api/v5/market/history-trades` | 20 / 2 s | `instId`*, `type` (1 = tradeId, 2 = timestamp), `after`, `before`, `limit` | max and default **100**; last **3 months** only |
| Single instrument ticker | `GET /api/v5/market/ticker` | 20 / 2 s | `instId`* | — |
| Tickers by type | `GET /api/v5/market/tickers` | 20 / 2 s | `instType`*, `instFamily` | — |
| Current funding rate | `GET /api/v5/public/funding-rate` | 10 / 2 s (IP + instId) | `instId`* (or `ANY`) | — |
| Funding rate history | `GET /api/v5/public/funding-rate-history` | 10 / 2 s (IP + instId) | `instId`*, `before`, `after`, `limit` | max and default **400**; **3 months** only |
| Current open interest | `GET /api/v5/public/open-interest` | 20 / 2 s | `instType`*, `instFamily`, `instId` | returns `oi`, `oiCcy`, `oiUsd` [live] |
| Open interest history | `GET /api/v5/rubik/stat/contracts/open-interest-history` | 10 / 2 s | `instId`*, `period`, `begin`, `end`, `limit` | max **100**; latest 1440 records |
| Long/short ratio by contract | `GET /api/v5/rubik/stat/contracts/long-short-account-ratio-contract` | 5 / 2 s | `instId`*, `period`, `begin`, `end`, `limit` | max 100; latest 1440 records |
| Top trader long/short ratio (accounts / positions) | `GET /api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader`, `.../long-short-position-ratio-contract-top-trader` | 5 / 2 s | same as above | top 5% traders by position value |
| Long/short ratio by coin | `GET /api/v5/rubik/stat/contracts/long-short-account-ratio` | 5 / 2 s | `ccy`*, `begin`, `end`, `period` (`5m`, `1H`, `1D`) | `5m` max 2 days, `1H` 30 days, `1D` 180 days |
| Taker volume by contract | `GET /api/v5/rubik/stat/taker-volume-contract` | 5 / 2 s | `instId`*, `period`, `unit` (0 coin, 1 contracts, 2 USD), `begin`, `end`, `limit` | latest 1440 records |
| Taker volume by coin | `GET /api/v5/rubik/stat/taker-volume` | 5 / 2 s | `ccy`*, `instType`* (`SPOT`/`CONTRACTS`), `period` | same time limits as long/short by coin |
| Open interest + volume by coin | `GET /api/v5/rubik/stat/contracts/open-interest-volume` | 5 / 2 s | `ccy`*, `period` | — |
| Mark price | `GET /api/v5/public/mark-price` | 10 / 2 s (IP + instId) | `instType`*, `instFamily`, `instId` | — |
| Index ticker | `GET /api/v5/market/index-tickers` | 20 / 2 s | `instId` or `quoteCcy` | — |
| Premium history | `GET /api/v5/public/premium-history` | 20 / 2 s | `instId`*, `after`, `before`, `limit` | max 100; 6 months |
| Server time | `GET /api/v5/public/time` | 10 / 2 s | — | — |

Source anchors: `#order-book-trading-market-data` (candles, books, trades, ticker), `#public-data-rest-api` (funding, open interest, mark price), `#trading-statistics-rest-api` (the `rubik` group). Examples: <https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks-history>, <https://www.okx.com/docs-v5/en/#public-data-rest-api-get-funding-rate-history>, <https://www.okx.com/docs-v5/en/#trading-statistics-rest-api-get-contract-open-interest-history>.

**Candle `bar` values:** `1m`, `3m`, `5m`, `15m`, `30m`, `1H`, `2H`, `4H`; candles opening on UTC+8: `6H`, `12H`, `1D`, `2D`, `3D`, `1W`, `1M`, `3M`; candles opening on UTC+0: `6Hutc`, `12Hutc`, `1Dutc`, `2Dutc`, `3Dutc`, `1Wutc`, `1Mutc`, `3Mutc`. `history-candles` additionally has `1s`. Default `1m`. The letters `H`, `D`, `W`, `M` are **uppercase**.

> Trap: OKX `1D` opens at 00:00 **UTC+8**, which does not line up with Binance `1d` candles (UTC). Use `1Dutc` to match.

**`period` values for the per-contract `rubik` group:** `5m`, `15m`, `30m`, `1H`, `2H`, `4H`, plus `6H`…`3M` and the `utc` variants as above, plus `5D`/`5Dutc`. Default `5m`.

**Candle structure:** `[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]`. `vol` is in contracts for derivatives, in base currency for Spot. `confirm` = `"0"` means the candle is not closed, `"1"` means closed. [docs][live]

**Pagination (the reverse of Binance):**
- Data is returned **newest first, oldest last**.
- `after=<ts>`: fetch records **older** than `ts`. `before=<ts>`: fetch records **newer** than `ts`.
- Downloading history: start from the end time, set `after` = the `ts` of the oldest record in the page just received, repeat until the page is empty or passes the start time.
- Sending a `limit` above the maximum does not error; it just returns the maximum number of records (tried `limit=301` on `history-candles`). [live]

**Liquidation:** the current docs **no longer have a REST section** for liquidation orders; there is only the WebSocket channel `liquidation-orders`. A test call to `GET /api/v5/public/liquidation-orders?instType=SWAP&instFamily=BTC-USDT&state=filled` still returns data [live], but since it is no longer in the docs, treat it as **[unverified]** and do not depend on it.

### 2.4 WebSocket

Source: <https://www.okx.com/docs-v5/en/#overview-websocket>

- **Pick the correct URL per channel**: public channels on `/ws/v5/public`; **candlesticks and all-trades on `/ws/v5/business`**; private channels on `/ws/v5/private` (login required).
- Subscribe:
  ```json
  {"id": "1512", "op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}]}
  ```
  Cancel with `"op": "unsubscribe"`. `id` is optional, up to 32 alphanumeric characters. Total length of channels in one request must not exceed 64 KB.
- **Ping/pong**: the connection drops automatically if there is no subscription or no pushed data for more than **30 seconds**. To keep it alive: set an N-second timer (N < 30) on every received message; when it fires, send the **text string `ping`** and wait for the string `pong`; if none arrives, reconnect. This is a text message, not a protocol ping frame.
- **Limits**:
  - New connections: **3 requests / second** per IP.
  - `subscribe` / `unsubscribe` / `login`: **480 total per hour** per connection.
  - Private channels (orders, account, positions...): max **30 connections per channel per sub-account**.
  - Total public connections per IP: **[unverified]** (not stated in the docs).
- A `{"event": "notice", "code": "64008", ...}` notice is sent 60 seconds before the server disconnects for an upgrade; open a new connection right away.

| Data | Channel | URL | Frequency |
|---|---|---|---|
| Ticker | `tickers` | public | at most once / 100 ms |
| Candles | `candle<bar>` e.g. `candle1m`, `candle1H` | **business** | at most once / second |
| Trades (aggregated) | `trades` | public | on every match; one message may aggregate several trades (field `count`) |
| Individual trades | `trades-all` | **business** | one trade per message |
| Order book | `books`, `books5`, `bbo-tbt`, `books50-l2-tbt`, `books-l2-tbt` | public | see below |
| Funding rate | `funding-rate` | public | 30–90 seconds |
| Open interest | `open-interest` | public | every 3 seconds when changed |
| Mark price | `mark-price` | public | 200 ms when changed, 10 seconds when unchanged |
| Index ticker | `index-tickers` | public | 100 ms when changed, otherwise 1 minute |
| Mark price / index candles | `mark-price-candle<bar>`, `index-candle<bar>` | **business** | at most once / second |
| Liquidation | `liquidation-orders` (parameter `instType`: `SWAP`, `FUTURES`, `MARGIN`, `OPTION`) | public | the docs explicitly say this data **does not represent all** liquidations on OKX |

**Order book channels:**

| Channel | Depth | Type | Frequency | Condition |
|---|---|---|---|---|
| `books` | 400 levels | initial snapshot + incremental | 100 ms | — |
| `books5` | 5 levels | snapshot every time | 100 ms | — |
| `bbo-tbt` | 1 level | snapshot every time | 10 ms | — |
| `books50-l2-tbt` | 50 levels | initial snapshot + incremental | 10 ms | **VIP4 and above** only; otherwise error `64003` |
| `books-l2-tbt` | 400 levels | initial snapshot + incremental | 10 ms | **VIP4 and above** only; otherwise error `64003` |

You cannot subscribe to `books-l2-tbt` and `books50-l2-tbt`/`books` at the same time for the same symbol.

**Building a local order book — OKX** (source: <https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-order-book-channel>):

1. Subscribe to `books` (or another incremental channel). The first message has `action: "snapshot"` and `prevSeqId = -1`: use it as the initial book. **No REST snapshot call needed**, unlike Binance.
2. Subsequent messages have `action: "update"`. Check that the new message's `prevSeqId` **equals** the previous message's `seqId`. If not: data was lost, discard the book and resubscribe.
3. Each element in `asks`/`bids` is `[price, quantity, (legacy field always "0"), order count]`; per the docs the third element is "part of a deprecated feature, always 0". [docs] The quantity is the absolute value for that price level; the rule **quantity "0" means remove the level** could not be re-read verbatim in the docs: **[unverified]**, check against real data when implementing.
4. Special cases per the docs:
   - About 60 seconds without changes: incremental channels send a message with `asks: []`, `bids: []` and `prevSeqId == seqId` (heartbeat, not an error).
   - After maintenance, the sequence may reset: you receive a message whose `seqId` is **smaller** than `prevSeqId`; subsequent messages follow the normal rule again. Docs example: snapshot (−1 → 10), update (10 → 15), unchanged (15 → 15), reset (15 → 3), update (3 → 5).
5. **`checksum` has been removed**: the field is still present in `books`, `books-l2-tbt`, `books50-l2-tbt` messages but is always 0; the docs require using `seqId`/`prevSeqId` to check continuity. Old code that checks CRC32 must be removed.

### 2.5 Rate limits and error codes

Sources: <https://www.okx.com/docs-v5/en/#overview-rate-limits>, <https://www.okx.com/docs-v5/en/#error-code>

- OKX **does not use weights**. Each endpoint has its own limit of the form "N requests / 2 seconds" stated in the endpoint description.
- Public REST: per **IP**. Private REST: per **User ID** (each sub-account has its own User ID). WebSocket login/subscribe: per connection.
- When limited you get error code **`50011`**. There is no header reporting usage (response headers showed no rate limit fields [live]); the client must count itself.
- Trading orders: limits are per instrument ID; REST and WebSocket share them; plus a cap of **1000 order requests / 2 seconds** per sub-account (error `50061`).
- A Binance-style 418 IP-ban penalty: not described in the OKX docs — **[unverified]**.

| Code | HTTP | Meaning |
|---|---|---|
| `0` | 200 | Success |
| `50001` | 503 | Service temporarily unavailable |
| `50004` | 400 | Endpoint timeout (does not tell whether the request succeeded or failed) |
| `50011` | 200 | Rate limit hit |
| `50013` | 429 | System busy, retry later |
| `50014` | 200 | Missing required parameter |
| `50026` | 500 | System error |
| `50061` | 200 | Account order rate limit exceeded |
| `50101` | 401 | API key does not match the environment (live / demo) |
| `50102` | 401 | Timestamp expired (more than 30 seconds off) |
| `50103` | 401 | Missing `OK-ACCESS-KEY` header |
| `50104`, `50105` | 401 | Missing / wrong `OK-ACCESS-PASSPHRASE` |
| `50110` | 401 | IP not in the API key's whitelist |
| `50111` | 401 | Invalid `OK-ACCESS-KEY` |
| `50113` | 401 | Invalid signature |
| `51000` | 200 | Parameter error |
| `51001` | 200 | Instrument ID does not exist |
| `60012` | WS | Invalid request |
| `60014` | WS | Requests too frequent |
| `60018` | WS | Wrong URL or channel does not exist (e.g. subscribing `candle1m` on `/public`) |
| `64003` | WS | Fee tier too low for this channel |
| `64008` | WS | Connection about to close for upgrade |

Note that `50011` and `51000` come with **HTTP 200**: check `code` in the body, not just the HTTP status.

### 2.6 Authentication, API key permissions, security

Sources: <https://www.okx.com/docs-v5/en/#overview-api-key-creation>, <https://www.okx.com/docs-v5/en/#overview-rest-authentication>

Creating an API key gives you three things: **API key**, **Secret key**, **Passphrase** (chosen by you; OKX stores only a salted hash, so if you lose it you must create a new key).

Required headers for private requests:

| Header | Content |
|---|---|
| `OK-ACCESS-KEY` | API key |
| `OK-ACCESS-SIGN` | Signature, Base64 |
| `OK-ACCESS-TIMESTAMP` | ISO 8601 UTC with milliseconds, e.g. `2020-12-08T09:08:57.715Z` |
| `OK-ACCESS-PASSPHRASE` | Passphrase |
| `x-simulated-trading: 1` | only for demo trading |

Signature: `Base64( HMAC_SHA256( secretKey, timestamp + METHOD + requestPath + body ) )`.
- `METHOD` uppercase (`GET`, `POST`).
- `requestPath` includes the query string for `GET` (e.g. `/api/v5/account/balance?ccy=BTC`).
- `body` is the request's JSON string, empty if none.
- The server rejects timestamps more than **30 seconds** off (error `50102`). Use UTC; sync with `GET /api/v5/public/time`.
- The request body must be `application/json`.

API key permissions: **Read** (view account, history), **Trade** (place/cancel orders, internal transfers, change settings), **Withdraw** (withdrawals).

Security per the docs:
- Each key can be bound to at most **20 IP addresses** (IPv4, IPv6, network ranges).
- Keys with `trade` or `withdraw` permission and **no bound IP expire after 14 days of inactivity** (demo keys do not expire).

Recommendations for the project: as in section 1.8 — no key needed for public data; a **Read**-only key when account reads are needed; **Trade** keys must be IP-bound; **do not enable Withdraw**; test on demo trading first.

Trading and account endpoint groups (listed only):

| Group | Prefix | Examples |
|---|---|---|
| Orders | `/api/v5/trade/` | `POST /api/v5/trade/order`, `GET /api/v5/trade/fills` |
| Trading account | `/api/v5/account/` | `GET /api/v5/account/balance`, `GET /api/v5/account/positions` |
| Funding account (deposits, withdrawals, transfers) | `/api/v5/asset/` | `GET /api/v5/asset/balances`, `POST /api/v5/asset/withdrawal` |
| Private WebSocket | `/ws/v5/private` | channels `account`, `positions`, `orders` |

### 2.7 Bulk historical data

- Download page: <https://www.okx.com/historical-data>. Per that page: trade history (from 2021-09), candlesticks (from 2023-07), funding rate (from 2022-03), L2 order book (from 2023-03), borrowing rate (from 2021-12). File format and download URL pattern: **[unverified]** (the page only has Download buttons).
- Endpoint that returns file links: `GET /api/v5/public/market-data-history` (5 requests / 2 seconds, per IP). [docs] <https://www.okx.com/docs-v5/en/#public-data-rest-api-get-historical-market-data>
  - `module`*: `1` tick-by-tick trades, `2` 1-minute candles, `3` funding rate, `4` 400-level order book, `5` 5000-level order book (from 2025-11-01), `6` 50-level order book (being phased out), `11` borrowing rate.
  - `instType`*: `SPOT`, `FUTURES`, `SWAP`, `OPTION`.
  - `instIdList` (for SPOT) or `instFamilyList` (for other types): max 10 entries, or `ANY` for some modules.
  - `dateAggrType`*: `daily` or `monthly`.
  - `begin`*, `end`*: Unix ms; max span 10 days for `daily`, 10 months for `monthly`.
  - The docs say historical data backfill is still ongoing; coverage varies by module and instrument.
  - A test call `module=3&instType=SWAP&instFamilyList=BTC-USDT&dateAggrType=monthly` returned a file list with `filename`, `sizeMB`, `url`, e.g. `BTC-USDT-SWAP-fundingrates-2026-10.zip` on host `static.okx.com`. [live] Contents and columns inside the zip: **[unverified]**.

### 2.8 Regional restrictions

Source [docs]: <https://www.okx.com/docs-v5/en/#overview>

- The docs have a "Regional API Domain Requirement" section: accounts registered in the **US and Australia** (via `app.okx.com`) must use the API domain **`us.okx.com`**; **EU** accounts (via `my.okx.com`) use **`eea.okx.com`**. The docs say `openapi.okx.com` will not work for these regions, and each region has its own API docs.
- Continued use of the API means accepting the "OKX API Agreement".
- The list of countries with restricted service is in OKX's "Risk and Compliance Disclosure", not yet read: **[unverified]**.

---

## 3. Python libraries

| Library | Install | Nature | Notes |
|---|---|---|---|
| `ccxt` | `pip install ccxt` | third party, unified API across many exchanges | version tested: **4.5.92**; exchange ids: `binance`, `binanceusdm`, `binancecoinm`, `okx` |
| `binance-connector-python` | `pip install binance-sdk-spot`, `pip install binance-sdk-derivatives-trading-usds-futures` | Binance's SDK, split into per-product packages | requires **Python 3.11+**; the old unified package has a migration guide `MIGRATION.md` |
| `python-binance` | `pip install python-binance` | **unofficial** | README shows v1.0.37; has `AsyncClient`, flags `testnet=True`, `demo=True` |
| `python-okx` | `pip install python-okx` | SDK referenced by OKX in its docs | Python ≥ 3.7; modules `okx.MarketData`, `okx.PublicData`, `okx.TradingData`; `flag="0"` is live, `"1"` is demo |

Sources: <https://github.com/ccxt/ccxt>, <https://github.com/binance/binance-connector-python>, <https://github.com/sammchardy/python-binance>, <https://github.com/okxapi/python-okx>.

- The `ccxt` docs could not be read in full (page too long); the behavior described in section 4.3 is based on **actually running** version 4.5.92.
- Latest versions of `python-okx`, `python-binance`, and whether these libraries have been updated for the 2026 URL changes (Binance `/market`, OKX `openapi.okx.com`): **[unverified]**. Check which URLs the library actually calls before trusting it.

---

## 4. Python examples

All four examples ran successfully on 2026-11-13 with Python 3.14, `requests` 2.34.2, `ccxt` 4.5.92, `websockets` 17.4. Install: `pip install requests ccxt websockets`.

### 4.1 Binance klines via plain REST

```python
import time
import requests

SPOT = "https://data-api.binance.vision"   # public market data only; or https://api.binance.com
FUT = "https://fapi.binance.com"


def binance_klines(symbol, interval, start_ms, end_ms, futures=False):
    """Download klines [start_ms, end_ms) by advancing startTime."""
    url = f"{FUT}/fapi/v1/klines" if futures else f"{SPOT}/api/v3/klines"
    limit = 1500 if futures else 1000
    out = []
    while start_ms < end_ms:
        r = requests.get(url, params={"symbol": symbol, "interval": interval,
                                      "startTime": start_ms, "endTime": end_ms - 1,
                                      "limit": limit}, timeout=10)
        if r.status_code in (418, 429):          # rate limited: must back off
            time.sleep(int(r.headers.get("Retry-After", "5")))
            continue
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        out += rows
        start_ms = rows[-1][0] + 1               # open time of the last candle + 1 ms
        print("used weight 1m:", r.headers.get("X-MBX-USED-WEIGHT-1M"))
    return out


if __name__ == "__main__":
    now = int(time.time() * 1000)
    k = binance_klines("BTCUSDT", "1m", now - 36 * 3600 * 1000, now)
    print(len(k), k[0][:6])                      # [openTime, open, high, low, close, volume]
    k = binance_klines("BTCUSDT", "1h", now - 48 * 3600 * 1000, now, futures=True)
    print(len(k), k[-1][:6])
```

Test run result: 2160 Spot 1-minute candles over 3 pages, 48 Futures 1-hour candles. The last candle may be **not yet closed**; filter by `closeTime < now` if you only want complete candles.

### 4.2 OKX candles via plain REST

```python
import time
import requests

OKX = "https://openapi.okx.com"


def okx_candles(inst_id, bar, start_ms, end_ms):
    """Download candles [start_ms, end_ms) — OKX returns NEW -> OLD, walk back with `after`."""
    out, after = [], end_ms
    while after > start_ms:
        r = requests.get(f"{OKX}/api/v5/market/history-candles",
                         params={"instId": inst_id, "bar": bar,
                                 "after": after, "limit": 300}, timeout=10)
        if r.status_code == 429:
            time.sleep(2)
            continue
        r.raise_for_status()
        body = r.json()
        if body["code"] != "0":                  # errors live in the body, e.g. 50011 = rate limit
            raise RuntimeError(f'{body["code"]}: {body["msg"]}')
        rows = body["data"]
        if not rows:
            break
        out += [x for x in rows if int(x[0]) >= start_ms]
        after = int(rows[-1][0])                 # ts of the oldest candle in the page
        time.sleep(0.11)                         # 20 req / 2 s per IP
    return out[::-1]                             # reverse to OLD -> NEW


if __name__ == "__main__":
    now = int(time.time() * 1000)
    c = okx_candles("BTC-USDT-SWAP", "1m", now - 12 * 3600 * 1000, now)
    print(len(c), c[0])   # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
```

Test run result: 720 candles. All values are **strings**; cast before computing. The last field `confirm == "0"` means the candle is not closed.

### 4.3 Both exchanges via ccxt

```python
import ccxt

binance = ccxt.binance({"enableRateLimit": True})
okx = ccxt.okx({"enableRateLimit": True})

since = binance.parse8601("2026-11-01T00:00:00Z")
for ex, symbol in [(binance, "BTC/USDT"),          # spot
                   (binance, "BTC/USDT:USDT"),     # USDⓈ-M perpetual
                   (okx, "BTC/USDT"),
                   (okx, "BTC/USDT:USDT")]:        # = BTC-USDT-SWAP
    rows, cursor = [], since
    while len(rows) < 2000:
        page = ex.fetch_ohlcv(symbol, "1h", since=cursor, limit=1000)
        if not page:
            break
        rows += page
        cursor = page[-1][0] + 1
    print(ex.id, symbol, ex.market(symbol)["id"], len(rows), rows[0])
    # each row: [timestamp_ms, open, high, low, close, volume]
```

Test run result: `BTC/USDT` → `BTCUSDT` / `BTC-USDT`; `BTC/USDT:USDT` → `BTCUSDT` (futures) / `BTC-USDT-SWAP`. ccxt returns data **old → new** as `float` for both exchanges and handles OKX's reverse pagination itself.

### 4.4 WebSocket

```python
import asyncio
import json
import websockets


async def binance_futures(n=3):
    # markPrice and aggTrade belong to the /market group; depth, bookTicker to /public
    url = "wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade/btcusdt@markPrice@1s"
    async with websockets.connect(url) as ws:     # the library answers ping frames with pong automatically
        for _ in range(n):
            msg = json.loads(await ws.recv())
            print("binance", msg["stream"], msg["data"]["E"])


async def okx_public(n=3):
    async with websockets.connect("wss://ws.okx.com/ws/v5/public", ping_interval=None) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [
            {"channel": "trades", "instId": "BTC-USDT-SWAP"},
            {"channel": "funding-rate", "instId": "BTC-USDT-SWAP"}]}))
        got = 0
        while got < n:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send("ping")             # OKX: string 'ping' -> receive 'pong'
                continue
            if raw == "pong":
                continue
            msg = json.loads(raw)
            if "data" in msg:
                got += 1
                print("okx", msg["arg"]["channel"], msg["data"][0].get("ts"))


async def main():
    await asyncio.gather(binance_futures(), okx_public())

asyncio.run(main())
```

Notes when running:
- On macOS with Python installed from python.org, `wss://` connections may report `CERTIFICATE_VERIFY_FAILED`. Fix used during testing: set the environment variable `SSL_CERT_FILE` to the `certifi` package's file (`python -c "import certifi; print(certifi.where())"`), or run the `Install Certificates.command` bundled with the Python installer.
- During testing, `requests` occasionally hit a transient `ConnectionError` to Binance hosts; rerunning succeeded. Production code needs retries with backoff.
- Production code also needs: automatic reconnect (Binance disconnects after 24 hours; OKX disconnects on upgrades), resubscribe after reconnect, and data-loss detection.

---

## 5. Binance vs OKX comparison

| Criterion | Binance | OKX |
|---|---|---|
| Version | Spot `/api/v3`; USDⓈ-M `/fapi/v1`; COIN-M `/dapi/v1` | `/api/v5` for all products |
| REST host | split by product: `api`, `fapi`, `dapi` | one host: `openapi.okx.com` |
| Spot symbol | `BTCUSDT` | `BTC-USDT` |
| USDT perpetual symbol | `BTCUSDT` (on `fapi`) | `BTC-USDT-SWAP` |
| Coin-margined perpetual symbol | `BTCUSD_PERP` (on `dapi`) | `BTC-USD-SWAP` |
| ccxt symbol | `BTC/USDT`, `BTC/USDT:USDT` | `BTC/USDT`, `BTC/USDT:USDT` |
| Symbol in WebSocket | lowercase in the stream name: `btcusdt@aggTrade` | `instId` as-is in `args` |
| Candle intervals | `1m`, `1h`, `1d`, `1w`, `1M` (lowercase except month) | `1m`, `1H`, `1D`, `1W`, `1M` (hour and above uppercase) |
| Daily candle open time | UTC (Spot can change via `timeZone`) | `1D` = UTC+8; `1Dutc` = UTC |
| Klines limit per call | Spot 1000; Futures 1500 | `candles` 300; `history-candles` 300 |
| Data order | old → new | new → old |
| Pagination | `startTime` / `endTime` / `fromId` | `after` (older) / `before` (newer) |
| Timestamp type | integer ms (Spot optionally µs) | string ms |
| Price / volume type | strings in the klines array | strings |
| Candle closed status | derived from `closeTime`; WebSocket has `k.x` | field `confirm` (`"0"` / `"1"`) |
| Max REST order book | Spot 5000; Futures 1000 | `books` 400; `books-full` 5000 |
| Local order book | diff stream + REST snapshot; `U`/`u` (Spot), plus `pu` (Futures) | snapshot arrives over WebSocket; `seqId`/`prevSeqId`; checksum removed |
| Funding rate history | `limit` max 1000 | `limit` max 400; 3 months only |
| Open interest history | `/futures/data/openInterestHist`, max 500, 1 month only | `rubik/.../open-interest-history`, max 100, latest 1440 records |
| Public liquidations | WebSocket `@forceOrder` only (1 latest order / 1000 ms) | WebSocket `liquidation-orders` only (incomplete) |
| Rate limit | weight-based: Spot 6000/min, Futures 2400/min, per IP | per endpoint, "N requests / 2 seconds", per IP |
| Reading usage | header `X-MBX-USED-WEIGHT-1M` | no header; count yourself |
| When exceeded | HTTP 429 → 418 (ban 2 minutes to 3 days), header `Retry-After` | code `50011` (HTTP 200) or HTTP 429 |
| Error reporting | HTTP 4XX + `{"code": -1121, "msg": ...}` | `{"code": "5xxxx", "msg": ...}`, many errors still HTTP 200 |
| Authentication | header `X-MBX-APIKEY` + `signature` (HMAC SHA256 hex, or Ed25519/RSA) in the query | 4 `OK-ACCESS-*` headers; HMAC SHA256 Base64 signature; has a **passphrase** |
| Auth timestamp | Unix ms, `recvWindow` default 5000 ms | ISO 8601 UTC, max 30 seconds skew |
| WebSocket ping | server sends ping frames (Spot 20 s; Futures 3 minutes), client replies pong | client sends the string `ping` within 30 seconds of silence |
| Connection lifetime | 24 hours | no fixed limit stated; disconnects on upgrade (60-second notice) |
| Test environment | testnet/demo on separate hosts | same REST host + header `x-simulated-trading: 1`; WebSocket `wspap.okx.com` |
| History dumps | `data.binance.vision` (daily/monthly zip files, with checksums) | historical-data page + `GET /api/v5/public/market-data-history` |

---

## 6. Unverified items

1. Weight and limits of `topLongShortAccountRatio`, `topLongShortPositionRatio`, `takerlongshortRatio`, `ticker/24hr`, `ticker/price`, `ticker/bookTicker` on USDⓈ-M, and `takerBuySellVol` on COIN-M (docs page truncated; endpoints are in the index and callable).
2. The full list of Futures kline intervals in the docs (hidden; checked with real calls).
3. Default frequency of the Futures depth stream (docs contradict themselves between 250 ms and the 100/500 ms enum).
4. Whether COIN-M WebSocket splits `/public`, `/market` like USDⓈ-M.
5. Restricted country/region lists for both Binance and OKX.
6. Full list of Binance API key permissions and maximum key count.
7. OKX REST `GET /api/v5/public/liquidation-orders`: still works but no longer in the docs.
8. The "quantity 0 means remove the level" rule in OKX's WebSocket order book (not re-read verbatim).
9. OKX's total public WebSocket connection limit; OKX's IP-ban penalty.
10. Format and columns of files downloaded from OKX historical data / `market-data-history`.
11. Futures path patterns on `data.binance.vision` (checked with HTTP HEAD, not in the README); column contents of `metrics` and `bookDepth`; why `bookTicker`, `liquidationSnapshot`, `cm/fundingRate` return 404.
12. `ccxt` docs (only confirmed by running version 4.5.92); latest versions and how up to date `python-okx`, `python-binance` are with the new URLs.
13. Out-of-scope products not researched: Binance Options, Portfolio Margin, Spot WebSocket API, SBE/FIX; OKX Options, spread trading, block trading.
