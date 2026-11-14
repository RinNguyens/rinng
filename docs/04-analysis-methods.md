# 04 — Analysis methods: from chart to code

> Background document for the quant project (Python). Goal: turn the methods used on charts into programmable rules, with an honest assessment of the evidence.
> Updated: 2026-11-13.

## 0. How to read this document

**Scope.** This document describes methods and how to measure them. It contains no buy/sell recommendations; every numeric threshold in the pseudocode is a starting parameter to be tested, not a proven value.

**Verification level.** Sources were checked via web search in a single working session, mostly through snippets rather than full text. Three labels are used throughout:

| Label | Meaning |
|---|---|
| (verified) | Matches a snippet from a source with an attached URL, looked up in this session |
| (from memory) | Common knowledge or a well-known paper, not re-checked in this session; open the original source before relying on it |
| **unverified** | Searched but not confirmed, or the source is only a blog/vendor |

**Mapping the project owner's four charts to sections:**

| Chart | Related sections |
|---|---|
| (1) Weekly volume profile: VPOC, value area, thin zones, delta | §1, §2 |
| (2) BTC monthly, "liquidity zone" below old lows | §6, §3.4 |
| (3) Wyckoff accumulation + Elliott 1-5 / A-B-C | §4, §5 |
| (4) XAUUSD – FEDFUNDS – BTCUSDT | §8 |

**Four common traps, applying to every section:**

1. **Lookahead.** Swings, zigzags, the POC of the running week, and Wyckoff/Elliott labels are only "settled" after more data arrives. Every feature must be stamped with the time *it became known*, not the time it occurred.
2. **Data snooping.** Trying many parameters and picking the prettiest always yields pretty results. You need out-of-sample, walk-forward, and correction for the number of trials (Sullivan–Timmermann–White 1999; the deflated Sharpe ratio of Bailey & López de Prado — from memory).
3. **Costs.** Fees, spread, slippage, funding. Many technical results vanish after costs.
4. **Small samples.** BTC weekly/monthly charts have only a few hundred candles; the number of independent cycles is far smaller.

General academic context: the Park & Irwin (2007) survey notes that most technical-analysis studies have testing-procedure problems (data snooping, choosing rules after seeing results, estimation of risk and costs) (verified: https://econpapers.repec.org/RePEc:bla:jecsur:v:21:y:2007:i:4:p:786-826). Lo, Mamaysky & Wang (2000) show some patterns carry statistical information content but do not conclude they yield excess returns (verified via secondary source: https://www.cxoadvisory.com/technical-trading/classic-papers-returns-from-pattern-based-technical-analysis/).

---

## 1. Volume Profile and Market Profile (TPO)

### 1.1 Concepts

- **Volume Profile**: histogram of volume by *price level* (not by time) over a chosen period.
- **Market Profile / TPO** (Time Price Opportunity): histogram of the *time* price spent at each level; each time block (usually 30 minutes) stamps a letter on the levels it touched. Developed by J. Peter Steidlmayer at the CBOT in the 1980s (verified via secondary source: https://www.luxalgo.com/library/concept/tpo-profile/).
- **POC / VPOC**: the price level (bin) with the largest volume. For TPO, the level with the most TPOs.
- **Value Area (VA), VAH, VAL**: the contiguous price band around the POC containing 70% of total volume (or TPO). 70% is a convention approximating one standard deviation of a normal distribution (68.2%), not a parameter estimated from data; real profiles are rarely normal (verified: https://therighttrader.com/learn/volume-and-order-flow/value-area).
- **HVN / LVN**: local peaks and troughs of the histogram. The "thin volume zone" on chart (1) is an LVN.
- **Naked / virgin POC**: the POC of a closed period that price in later periods has not come back to touch.
- **Initial Balance**: the range of the first trading hour of the session (classic TPO). For 24/7 crypto you must define your own "session" (e.g. 00:00 UTC).

### 1.2 Profile types by range

| Type | Range | Programming notes |
|---|---|---|
| Session | One session/day | Crypto: cut by UTC; stocks: by exchange hours |
| Weekly / Monthly | ISO week / calendar month | Chart (1) uses this; `resample("W-MON")` or group by `isocalendar()` |
| Visible range | The range currently displayed | Pure UI, meaningless in a backtest; replace with a rolling window of N candles |
| Fixed range | Hand-picked t1 to t2 | Parameterize t1, t2 |
| Anchored | From an anchor to now | The anchor must be identifiable at that time (see lookahead trap) |

### 1.3 Algorithms

**From trades/aggTrades (exact):** sum `qty` per price bin.

```python
import numpy as np
import pandas as pd

def profile_from_trades(price: np.ndarray, qty: np.ndarray, bin_size: float) -> pd.Series:
    """Returns a Series: index = lower edge of the bin, value = volume."""
    b = np.floor(price / bin_size).astype(np.int64)
    s = pd.Series(qty).groupby(b).sum()
    full = np.arange(s.index.min(), s.index.max() + 1)
    s = s.reindex(full, fill_value=0.0)
    s.index = full * bin_size
    return s
```

**From OHLCV (approximate):** you don't know where in the candle the volume traded, so you must assume. The common approach spreads volume uniformly from low to high. The error shrinks with smaller candles: for a weekly profile, build it from 1-minute or 5-minute candles, not daily candles.

```python
def profile_from_ohlcv(df: pd.DataFrame, bin_size: float) -> pd.Series:
    lo = np.floor(df["low"].to_numpy() / bin_size).astype(np.int64)
    hi = np.floor(df["high"].to_numpy() / bin_size).astype(np.int64)
    base = lo.min()
    out = np.zeros(hi.max() - base + 1)
    for l, h, v in zip(lo - base, hi - base, df["volume"].to_numpy()):
        out[l:h + 1] += v / (h - l + 1)          # spread uniformly
    return pd.Series(out, index=(np.arange(len(out)) + base) * bin_size)
```

Variants: triangular spread around the typical price, or put everything at the close. Each assumption gives a different POC; record the assumption in metadata.

**POC and Value Area.** General procedure (verified: https://www.tradingview.com/wiki/Volume_Profile): compute total volume, multiply by the ratio (default 70%) to get the target volume, start at the POC and expand until the target is reached; the highest row is VAH, the lowest is VAL. The expansion step has several variants: compare the sum of the *two rows* above with the two rows below and take the larger side (classic CBOT style), or one row at a time, or alternating. The variant used by TradingView's built-in tool: **unverified** (closed source).

```python
def value_area(profile: pd.Series, pct: float = 0.70, step: int = 2):
    v = profile.to_numpy()
    n = len(v)
    # POC: on a tie, take the bin closest to the middle of the range
    cands = np.flatnonzero(v == v.max())
    poc = int(cands[np.abs(cands - (n - 1) / 2).argmin()])
    lo = hi = poc
    acc, target = v[poc], pct * v.sum()
    while acc < target and (lo > 0 or hi < n - 1):
        up = v[hi + 1: hi + 1 + step].sum() if hi < n - 1 else -1.0
        dn = v[max(lo - step, 0): lo].sum() if lo > 0 else -1.0
        if up >= dn:
            hi = min(hi + step, n - 1); acc += up
        else:
            lo = max(lo - step, 0); acc += dn
    bin_size = profile.index[1] - profile.index[0] if n > 1 else 0.0
    return {"poc": profile.index[poc] + bin_size / 2,
            "vah": profile.index[hi] + bin_size,
            "val": profile.index[lo]}
```

**HVN/LVN:** smooth the profile, then find extrema with sufficient prominence.

```python
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

def nodes(profile: pd.Series, sigma_bins: float = 2.0, prom_frac: float = 0.10):
    sm = gaussian_filter1d(profile.to_numpy(), sigma_bins)
    prom = prom_frac * sm.max()
    hvn, _ = find_peaks(sm, prominence=prom)
    lvn, _ = find_peaks(-sm, prominence=prom)
    return profile.index[hvn], profile.index[lvn]
```

**Naked POC:** for each closed period `k`, the POC is naked at time `t` if no candle in `(close of period k, t]` satisfies `low <= POC <= high`. Also store `touched_at` so the backtest does not look ahead.

### 1.4 Choosing the bin size

There is no "correct" value. Reasonable choices:

- A multiple of the tick size, fixed per asset (easy to compare across periods).
- Proportional to price: `bin = price * 0.0005`, or bins on log-price (needed for long series like BTC, since 100 USD in 2017 and in 2026 do not mean the same thing).
- By volatility: `bin = k * ATR` of the base timeframe.
- A fixed number of rows (24–100 rows per profile), like most charting platforms.

Bins too small make the profile jagged and the POC jumps around; too large and you lose LVNs. Run a sensitivity check: do POC/VAH/VAL stay stable when the bin changes by ±50%?

### 1.5 Data needed

- Best: aggTrades/tick. Binance publishes historical files at https://github.com/binance/binance-public-data/ (data.binance.vision).
- Minimum: 1-minute candles.
- Stocks: volume is fragmented across many venues and dark pools; a profile from one source does not represent the whole market.

### 1.6 Common traps

- The profile of the **running** week changes constantly; the "developing" POC differs from the week's final POC.
- Crypto: volume differs per exchange, some exchanges have wash trading; spot and perp give different profiles. Fix the source.
- Profiles built from higher-timeframe OHLCV are only rough estimates; don't compare them directly with TradingView's picture.
- Stock splits/price adjustments distort long-term profiles.

### 1.7 Empirical evidence

Weak. The ideas "price returns to high-volume zones" and "moves fast through thin-volume zones" make microstructural sense (where much trading happened is where many people hold positions), but no peer-reviewed study was found testing POC/VA/naked POC as a signal with an edge after costs: **unverified**. Treat these as *features describing structure* that need your own testing.

---

## 2. Order flow

### 2.1 Concepts

- **Aggressor / taker side**: the side sending an order that fills immediately (market or marketable limit). Taker buys fill against the ask; taker sells fill against the bid.
- **Delta** = taker buy volume − taker sell volume within a candle/bin. The "delta numbers" on chart (1) are delta accumulated over the weekly profile.
- **CVD** (cumulative volume delta) = the running sum of delta.
- **Footprint**: a matrix (candle × price level) holding bid/ask volume at each level.
- **Imbalance**: at a price level, volume on one side dominates the other by a threshold ratio.
- **Absorption**: takers hit one side hard but price does not move; implies passive limit orders absorbing the flow.
- **Order book heatmap**: snapshots of order book depth over time (price × time × resting size).

### 2.2 Deriving from Binance aggTrades

Field `m` in aggTrades is the boolean "buyer is maker". `m = true` means the buyer had the resting order, so **the taker is the seller**; `m = false` is a taker buy (verified: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List and https://dev.binance.vision/t/green-or-red-data/15736). Spot's `M` field is a different, unrelated flag.

```python
def add_delta(trades: pd.DataFrame) -> pd.DataFrame:
    """trades: columns ts (datetime, UTC), price, qty, is_buyer_maker (bool)."""
    t = trades.copy()
    t["signed"] = np.where(t["is_buyer_maker"], -t["qty"], t["qty"])
    return t

def bars_with_delta(t: pd.DataFrame, rule: str = "1min") -> pd.DataFrame:
    g = t.set_index("ts").resample(rule)
    out = g["price"].ohlc()
    out["volume"] = g["qty"].sum()
    out["delta"] = g["signed"].sum()
    out["cvd"] = out["delta"].cumsum()
    return out

def footprint(t: pd.DataFrame, rule: str, bin_size: float) -> pd.DataFrame:
    t = t.assign(bar=t["ts"].dt.floor(rule),
                 px=np.floor(t["price"] / bin_size) * bin_size,
                 side=np.where(t["is_buyer_maker"], "bid", "ask"))  # bid = taker sell filled against the bid
    return t.pivot_table(index=["bar", "px"], columns="side",
                         values="qty", aggfunc="sum", fill_value=0.0)
```

**No aggTrades?** Binance klines include a "taker buy base asset volume" column, so `delta = 2 * taker_buy_base − volume` (from memory of the kline structure; re-check in the API docs). With plain OHLCV only (stocks), you must estimate: tick rule, Lee–Ready (1991), or the bulk volume classification of Easley, López de Prado & O'Hara (from memory). These estimates have significant error.

**Diagonal imbalance** per footprint convention: compare ask volume at level `p` with bid volume at level `p − tick`.

```python
def diagonal_imbalance(fp_bar: pd.DataFrame, ratio: float = 3.0, min_vol: float = 0.0):
    """fp_bar: footprint of ONE candle, index = px ascending, columns bid/ask."""
    ask = fp_bar["ask"].to_numpy()[1:]
    bid = fp_bar["bid"].to_numpy()[:-1]
    buy_imb = (ask >= ratio * np.maximum(bid, 1e-12)) & (ask > min_vol)
    sell_imb = (bid >= ratio * np.maximum(ask, 1e-12)) & (bid > min_vol)
    return buy_imb, sell_imb     # 3 consecutive levels on the same side = "stacked imbalance"
```

The 3.0 (300%) threshold is a footprint-platform convention with no statistical basis: **unverified**.

**Absorption (heuristic):** unusually large delta without a corresponding price move.

```python
def absorption_score(bars: pd.DataFrame, win: int = 200) -> pd.Series:
    z_delta = (bars["delta"] - bars["delta"].rolling(win).mean()) / bars["delta"].rolling(win).std()
    ret = bars["close"].diff()
    z_ret = ret / ret.rolling(win).std()
    # strong positive delta but price not rising (or vice versa) -> high score
    return z_delta.abs() - (np.sign(z_delta) * z_ret).clip(lower=0)
```

**CVD divergence:** price makes a higher high while CVD makes a lower high (evaluated on the swings of §6.2, not candle by candle).

**Order book heatmap:** requires recording the depth stream (diff depth + snapshot) in real time; Binance does not provide full order book history for free, so you must collect it yourself or buy it (e.g. Tardis: https://docs.tardis.dev/historical-data-details/binance-futures). Store as an array `(time, price_bin) -> resting qty`.

### 2.3 Common traps

- **CVD is not comparable across exchanges or between spot and perp**; the absolute level depends on where accumulation starts. Use only changes or slope.
- Delta measures *who pays the spread*, not who is "smarter". Large institutions often use limit orders, so they show up on the passive side.
- aggTrades merges fills at the same price and side of one taker order; the "trade" count is not the order count.
- Order books have spoofing: large orders on the heatmap may be pulled before price arrives.
- Clock and latency: when joining trades with the order book, use the exchange timestamp.

### 2.4 Empirical evidence

Relatively good at **very short horizons**, weak at long horizons. Order flow imbalance explains most of the contemporaneous price change over seconds to minutes (Cont, Kukanov & Stoikov 2014, "The price impact of order book events" — from memory). A *contemporaneous* relationship does not mean *predictable*; predictive power decays very quickly and sits in HFT's competitive zone. Using weekly delta/CVD as on chart (1) to infer multi-week direction: **unverified**, no evidence found.

---

## 3. Crypto derivatives data

### 3.1 Funding rate

Periodic payment between longs and shorts on perpetuals to anchor the perp price to spot. Positive funding: longs pay shorts.

Binance formula (verified, announcement effective 2025-09-18: https://www.binance.com/en-AE/support/announcement/detail/c00588a7e8504b3eb28d02a2da00530b):

```
F = [ P_avg + clamp(I − P_avg, −0.05%, +0.05%) ] / (8 / N)
```

where `P_avg` is the average premium index, `I` = 0.01% per 8 hours (0% for some contracts), and `N` is the funding interval in hours. Consequence: when the average premium is between −0.04% and +0.06%, funding comes out at exactly 0.01%, so funding "sitting at 0.01%" is the default state, not a signal (verified via secondary source: https://coincub.com/blog/perpetual-futures-funding-rates-78-of-a-quarter-at-0-01/). Each exchange has its own formula and interval; don't naively pool across exchanges.

Suggested features: annualized funding = `F * (24/N) * 365`; rolling z-score; 7/30-day cumulative funding; funding spread between exchanges.

### 3.2 Open interest (OI)

Total number of open contracts. Every contract always has one long and one short, so **OI has no direction**.

- The historical endpoint `GET /futures/data/openInterestHist` only keeps roughly the last 30 days (verified for COIN-M: https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/Open-Interest-Statistics; USDⓈ-M page: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics — the 30-day limit on USDⓈ-M is **unverified** directly). Design consequence: a periodic collection job is needed from day one, or history is lost.
- Longer history may be available in the "metrics" file set on data.binance.vision: **unverified**.
- Distinguish OI in coin from OI in USD: USD OI rises when price rises even if the contract count is unchanged.

### 3.3 Long/short ratio

Binance has several different series that are easily confused (verified: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio and https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio):

- **Global account ratio**: ratio of the number of net-long *accounts* to net-short accounts.
- **Top trader account ratio**: as above but only the top 20% of accounts by margin, each account counted once.
- **Top trader position ratio**: by position size of the top group.
- **Taker buy/sell volume ratio**: actually order flow (§2), not positioning. Exact endpoint name: **unverified**.

Account-based ratios reflect the mass of small accounts; they do not contradict total longs equaling total shorts.

### 3.4 Liquidation and liquidation heatmap

- **Actual liquidations**: streams `<symbol>@forceOrder` and `!forceOrder@arr`. The stream only pushes *the latest liquidation order within each 1000 ms window* per symbol, so **data is missing** during liquidation cascades, exactly when it matters most (verified for COIN-M: https://developers.binance.com/docs/derivatives/coin-margined-futures/websocket-market-streams/Liquidation-Order-Streams; USDⓈ-M describes it as a "snapshot stream": https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams). Total liquidations computed from this stream are a lower bound.
- **Liquidation heatmap** (Coinglass and similar): **a model, not real position data**. Exchanges do not publish per-account liquidation prices; vendors estimate from OI, volume and an assumed leverage distribution, then project liquidation levels for each leverage tier (verified via secondary source: https://bitsgap.com/blog/crypto-liquidation-heatmap-explained; Coinglass API docs: https://docs.coinglass.com/v3.0/reference/liquidation-heatmap). Coinglass's detailed method: **unverified**.

Building your own estimate (approximate, ignoring fees and margin tiers):

```python
def est_liq_price(entry: float, lev: float, side: str, mmr: float = 0.005) -> float:
    # isolated margin, first-order approximation
    return entry * (1 - 1/lev + mmr) if side == "long" else entry * (1 + 1/lev - mmr)

def liq_map(bars: pd.DataFrame, bin_size: float,
            levs=(5, 10, 25, 50, 100), weights=(.3, .3, .2, .15, .05)) -> pd.Series:
    """bars needs columns close, d_oi (OI change, in coin). Only counts OI INCREASES."""
    acc: dict[float, float] = {}
    for px, d in zip(bars["close"], bars["d_oi"].clip(lower=0)):
        for L, w in zip(levs, weights):
            for side in ("long", "short"):
                lp = np.floor(est_liq_price(px, L, side) / bin_size) * bin_size
                acc[lp] = acc.get(lp, 0.0) + d * w
    return pd.Series(acc).sort_index()
```

This version ignores closed positions, the leverage distribution `weights` is an arbitrary assumption, and cross margin makes the liquidation price depend on the whole account. The "liquidity zone below old lows" on chart (2) has two programmable interpretations: a stop cluster below swing lows (§6) or an estimated liquidation cluster (this section). State which definition is in use.

### 3.5 Basis

- Dated futures: `basis = (F − S) / S`; annualized = `basis * 365 / days to expiry`.
- Perp: premium index `(mark − index) / index`, which is the input to funding.

### 3.6 Combined interpretation of price + OI + funding

| Price | OI | Common interpretation |
|---|---|---|
| Up | Up | New positions opening, buyers more aggressive |
| Up | Down | Shorts closing (short covering) |
| Down | Up | New positions opening, sellers more aggressive |
| Down | Down | Longs closing / being liquidated |

Adding funding: price up + OI up + abnormally high funding is usually read as crowded leveraged longs; price down + OI up + deeply negative funding is crowded shorts.

```python
def oi_regime(df: pd.DataFrame, n: int = 24) -> pd.Series:
    dp = np.sign(df["close"].pct_change(n))
    doi = np.sign(df["oi"].pct_change(n))
    lab = {(1, 1): "new_longs", (1, -1): "short_cover",
           (-1, 1): "new_shorts", (-1, -1): "long_unwind"}
    return pd.Series([lab.get((a, b), "flat") for a, b in zip(dp, doi)], index=df.index)
```

### 3.7 Traps and evidence

- The table above is **inference**: the "aggressive side" is guessed from price direction; OI by itself says nothing about direction. Labels can be wrong when hedgers (delta-neutral, basis trades) make up most of the OI.
- Extreme funding is widely seen as a reversal signal; the evidence is mostly from exchange reports and blogs. Peer-reviewed research confirming an edge after costs: **unverified**.
- Each exchange's data is only part of the market; aggregated data depends on how the vendor normalizes it.

---

## 4. Wyckoff

Main references: StockCharts ChartSchool (https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial) and the Wyckoff Analytics material built from it (https://www.wyckoffanalytics.com/wp-content/uploads/2021/05/Wyckoff-Method-Wyckoff-Analytics-English.pdf). The structure of the 5 phases A–E and the three laws were verified via snippets; the detailed definitions of each event below are written from memory of this material and should be re-read in the original when implementing.

### 4.1 Concepts

**Four stages of the price cycle:** Accumulation → Markup → Distribution → Markdown.

**Three laws:**

1. **Supply and Demand**: when demand exceeds supply price rises, and vice versa.
2. **Cause and Effect**: the time spent in accumulation/distribution (cause) determines the length of the subsequent trend (effect); traditionally measured with a horizontal count on Point & Figure.
3. **Effort versus Result**: volume (effort) should match the price move (result); a mismatch suggests the trend is about to change.

**Composite Man**: an imagined assumption that the market is run by one big player. It is a thinking tool, not an observable entity.

### 4.2 Events in the Accumulation schematic

| Symbol | Name | Description |
|---|---|---|
| PS | Preliminary Support | First significant buying after a long downtrend; volume and spread increase |
| SC | Selling Climax | Panic selling: very wide spread, extreme volume, often closes well off the low |
| AR | Automatic Rally | Strong bounce after the SC; the AR high defines the upper bound of the trading range (TR) |
| ST | Secondary Test | Return to the SC area with lower volume and spread |
| Spring / Shakeout | — | Break below the TR low then quickly return. Not mandatory: Schematic #2 has no spring (verified: https://www.tradingview.com/chart/BTCUSD/GV54T8ZJ-What-is-the-Wyckoff-Method/) |
| Test | — | Retest of the spring area on low volume |
| SOS | Sign of Strength | Rally with wide spread and high volume, often above the TR high |
| LPS | Last Point of Support | Pullback after the SOS on low volume, with a higher low |
| BU | Back-Up (also JAC/BUEC) | Return to test the just-broken TR high |

"UA" on the project owner's chart (3) is **Upthrust Action**: a push above the TR high in Phase B followed by a return into the range (from memory; re-check in ChartSchool).

### 4.3 Events in the Distribution schematic

| Symbol | Name | Description |
|---|---|---|
| PSY | Preliminary Supply | First significant selling after an uptrend |
| BC | Buying Climax | Climactic chase buying, wide spread, extreme volume |
| AR | Automatic Reaction | Sharp drop after the BC; the AR low defines the lower bound of the TR |
| ST | Secondary Test | Return to the BC area on lower volume |
| UT | Upthrust | Push above the TR high then return (mirror of the spring) |
| UTAD | Upthrust After Distribution | Late upthrust in Phase C |
| SOW | Sign of Weakness | Drop with wide spread, high volume, to near or below the TR low |
| LPSY | Last Point of Supply | Weak rally, low volume, lower high |

### 4.4 Phases A–E

| Phase | Accumulation | Distribution |
|---|---|---|
| A | Stopping the downtrend: PS, SC, AR, ST | Stopping the uptrend: PSY, BC, AR, ST |
| B | Building the "cause": oscillation in the TR, possibly UA and minor STs | Building the "cause": UT, minor SOW |
| C | The test: Spring/Shakeout and Test | The test: UTAD |
| D | Trend within the TR: SOS, LPS, BU | SOW, LPSY |
| E | Leaving the TR, markup | Leaving the TR, markdown |

### 4.5 Automated detection: heuristic approach

Idea: (i) find the prior trend, (ii) find the climax candle, (iii) build the TR, (iv) run a state machine over the events.

```python
def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()          # Wilder

def effort_result(df: pd.DataFrame, win: int = 50) -> pd.DataFrame:
    a = atr(df)
    spread = (df["high"] - df["low"]) / a
    vz = (df["volume"] - df["volume"].rolling(win).mean()) / df["volume"].rolling(win).std()
    clv = (df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0, np.nan)   # 0=closed at low, 1=at high
    return pd.DataFrame({"spread": spread, "vz": vz, "clv": clv,
                         "er_gap": vz - (spread - spread.rolling(win).mean()) / spread.rolling(win).std()})

def selling_climax(df, f, trend_n=60, min_drop_atr=6.0, vz_min=2.5, spread_min=1.8, clv_min=0.4):
    drop = (df["close"].shift(1) - df["close"].shift(trend_n)) / atr(df)
    return (drop < -min_drop_atr) & (f["vz"] > vz_min) & (f["spread"] > spread_min) \
           & (f["clv"] > clv_min) & (df["low"] == df["low"].rolling(trend_n).min())

def find_spring(df, tr_low: float, start, max_pen_atr=1.5, reclaim_bars=3):
    """Break the TR low by no more than max_pen_atr, then close back inside the TR within reclaim_bars candles."""
    a = atr(df)
    seg = df.loc[start:]
    broke = (seg["low"] < tr_low) & (seg["low"] > tr_low - max_pen_atr * a.loc[start:])
    reclaimed = seg["close"].rolling(reclaim_bars).max().shift(-(reclaim_bars - 1)) > tr_low  # LOOKAHEAD
    return seg.index[broke & reclaimed]
```

The line marked `LOOKAHEAD` is only for offline labeling. In live use, the spring is only confirmed after `reclaim_bars` candles; the signal timestamp must shift accordingly.

Minimal state machine for accumulation: `DOWNTREND → SC → AR (highest high within N candles after SC) → TR=[low(SC), high(AR)] → ST (touches the low area, vz lower than SC) → [SPRING → TEST] → SOS (close > TR high, high spread and vz) → LPS/BU (pulls back, holds above TR high or mid-TR, low vz) → MARKUP`. Each transition has a timeout; when it expires the hypothesis is dropped. If price closes below the TR low by more than `max_pen_atr` and does not reclaim, the accumulation hypothesis is rejected (it may be redistribution).

### 4.6 Automated detection: ML approach

- **Supervised**: hand-label TRs and events, train a CNN/LSTM on normalized price-volume windows. There is an arXiv preprint using LSTM/CNN to recognize accumulation (TR and ST) reporting positive results (https://arxiv.org/abs/2403.18839); it is a preprint by independent authors, method and data **unverified**.
- **Unsupervised / regime**: HMM or change-point detection to separate "range" from "trend", then apply heuristics only inside ranges.
- **Synthetic data**: generate idealized schematics with noise for pre-training. Risk: the model learns the textbook schematic, not the market.

### 4.7 Limits and evidence

- Wyckoff labels are **only clear in hindsight**. In real time, the same TR can be accumulation, redistribution, or just a range. Two experts labeling the same chart often disagree, so ML training labels are very noisy.
- Every threshold (`vz_min`, `max_pen_atr`...) is self-chosen; the more thresholds, the easier to overfit.
- Crypto volume depends on the exchange; stock volume has calendar effects (derivatives expiry, index rebalancing).
- Academic evidence of an edge for the Wyckoff method after costs: no sufficiently strong peer-reviewed study found: **unverified**. "Automatic Wyckoff" indicators on TradingView/LuxAlgo are commercial products based on heuristic scoring, not evidence.

Technical recommendation: export the *components* (climax score, effort-result gap, spring flag, position within the TR) as independent features and test each one, rather than testing the whole "schematic".

---

## 5. Elliott Wave

### 5.1 Concepts

Price moves in 5-step **motive** waves (1-2-3-4-5) in the direction of the larger trend and 3-step **corrective** waves (A-B-C) against it; the structure nests across multiple degrees. Standard source: Frost & Prechter, *Elliott Wave Principle* (from memory, not re-checked in this session).

### 5.2 Three hard rules (for impulses)

1. Wave 2 never retraces more than 100% of wave 1.
2. Wave 3 is never the shortest of waves 1, 3, 5.
3. Wave 4 never enters the price territory of wave 1 (exception: diagonals).

```python
def is_valid_impulse(p: list[float]) -> bool:
    """p = [P0..P5] are 6 alternating pivots. Handles both up and down by flipping the sign."""
    s = 1.0 if p[1] > p[0] else -1.0
    q = [s * x for x in p]
    w1, w3, w5 = q[1] - q[0], q[3] - q[2], q[5] - q[4]
    if min(w1, w3, w5) <= 0:
        return False
    return (q[2] > q[0]                       # rule 1
            and w3 >= min(w1, w5)             # rule 2: not the shortest
            and q[4] > q[1])                  # rule 3: no overlap
```

Details to decide when implementing: measure waves in absolute price or percent/log (for BTC use log), use high/low or close, and whether to allow equality (>=).

### 5.3 Guidelines (soft, used for scoring)

- **Alternation**: waves 2 and 4 differ in form (deep/shallow, sharp/sideways).
- **Extension**: usually one of the three motive waves extends, most commonly wave 3.
- **Equality**: the two non-extended motive waves tend to be equal.
- **Channeling**: connect the 2–4 lows and draw a parallel through the wave 3 high to estimate the wave 5 target.
- Wave 4 often ends in the area of the lower-degree wave 4 of wave 3.
- Volume is usually highest in wave 3.

### 5.4 Common Fibonacci ratios

| Relationship | Commonly cited ratios |
|---|---|
| Wave 2 retraces wave 1 | 50%, 61.8% |
| Wave 3 vs wave 1 | 1.618 (sometimes 2.618) |
| Wave 4 retraces wave 3 | 23.6%, 38.2% |
| Wave 5 | equal to wave 1, or 0.618 × (start of wave 1 to end of wave 3) |
| Zigzag: C vs A | 1.0 or 1.618 |
| Flat: B retraces A | ≥ 90%; expanded flat: B exceeds 100% (often cited 123.6–138.2%) |

These are guidelines, not rules. The numbers are practitioner conventions (from memory).

### 5.5 Corrective patterns

| Pattern | Substructure | Characteristics |
|---|---|---|
| Zigzag | 5-3-5 | Sharp; B retraces less than 61.8% of A; C goes beyond the end of A |
| Flat (regular / expanded / running) | 3-3-5 | Sideways; B retraces nearly all of A or beyond its start |
| Triangle (contracting / expanding) | 3-3-3-3-3 (A-B-C-D-E) | Usually in wave 4 or wave B |
| Combination (W-X-Y) | Several patterns joined | Main source of multiple valid counts |

### 5.6 Automated wave-counting algorithm

**Step 1 — pivots via zigzag.** Threshold in percent or as a multiple of ATR.

```python
def zigzag(high: np.ndarray, low: np.ndarray, thr: float):
    """Alternating pivots. thr = relative reversal threshold (e.g. 0.05).
    Returns a list of (idx_pivot, price, kind, idx_confirm). idx_confirm > idx_pivot: the pivot is only known at idx_confirm."""
    piv, trend = [], 0
    hi_i, lo_i = 0, 0
    for i in range(1, len(high)):
        if high[i] > high[hi_i]: hi_i = i
        if low[i] < low[lo_i]: lo_i = i
        if trend >= 0 and low[i] < high[hi_i] * (1 - thr) and hi_i < i:
            piv.append((hi_i, high[hi_i], "H", i)); trend = -1; lo_i = i
        elif trend <= 0 and high[i] > low[lo_i] * (1 + thr) and lo_i < i:
            piv.append((lo_i, low[lo_i], "L", i)); trend = 1; hi_i = i
        if trend == -1 and high[i] >= high[hi_i]: hi_i = i     # track the new extreme after the reversal
        if trend == 1 and low[i] <= low[lo_i]: lo_i = i
    return piv
```

This is illustrative pseudocode; a production version needs thorough tests of edge cases (a candle making both a high and a low, the first pivot of the series) and must reset the opposite extreme after each reversal.

**Step 2 — enumerate candidates.** Run zigzag at several thresholds (e.g. 2%, 5%, 10%, 20%) to get several wave degrees. For each degree, slide a window of 6 consecutive pivots (impulse) and 4 pivots (A-B-C); allow skipping small pivots to merge waves.

**Step 3 — filter by hard rules** (`is_valid_impulse`), with similar checks for zigzag/flat/triangle.

**Step 4 — score guidelines.**

```python
FIB = np.array([0.236, 0.382, 0.5, 0.618, 1.0, 1.618, 2.618])

def fib_closeness(ratio: float, tol: float = 0.08) -> float:
    return float(np.exp(-((np.abs(FIB - ratio).min()) / tol) ** 2))

def score_impulse(p: list[float]) -> float:
    w1, w2, w3, w4, w5 = [abs(p[i + 1] - p[i]) for i in range(5)]
    parts = [fib_closeness(w2 / w1), fib_closeness(w3 / w1), fib_closeness(w4 / w3),
             fib_closeness(w5 / w1), 1.0 if w3 == max(w1, w3, w5) else 0.5,
             1.0 if abs(w2 / w1 - w4 / w3) > 0.15 else 0.5]     # crude alternation
    return float(np.mean(parts))
```

**Step 5 — recursive check.** Waves 1, 3, 5 must themselves subdivide into 5 waves at a lower degree; waves 2, 4 into 3 waves. Each recursion level multiplies the number of candidates.

**Step 6 — keep the top-k** counts instead of a single answer; output each count's *invalidation* price level, because that is the only falsifiable part.

### 5.7 Multiple valid counts and subjectivity

- For the same pivot sequence there are usually several counts valid under the three hard rules. W-X-Y combinations and allowing "extension" and "truncation" make almost any price series countable.
- Results are very sensitive to the zigzag threshold and to log vs linear scale.
- When the primary count fails, analysts switch to an "alternate count", so the theory is hard to falsify. For testing, fix the algorithm and parameters *beforehand*, then measure.
- The last pivot is not yet confirmed: the "current" count always changes (repaint).
- The number of combinations grows exponentially; limit recursion depth and use beam search.

### 5.8 Empirical evidence

Weak. No solid peer-reviewed study was found showing automated wave counting has predictive power. A capstone on forex data concluded Elliott Wave has no statistically significant predictive power for daily exchange rates (https://nur.nu.edu.kz/handle/123456789/7226; weak evidence since it is a student project). Batchelor & Ramyar (2006, "Magic numbers in the Dow") is often cited as finding Fibonacci ratios appear no more often than chance in the Dow Jones: **unverified** (seen only via secondary sources, could not open the original). Accuracy claims by wave-counting software are marketing, with no independent verification.

Sensible use in this project: treat the wave counter as a *descriptive* tool that generates invalidation levels; to use it as a signal, test it like any other feature, with parameters fixed beforehand.

---

## 6. Support/resistance and liquidity

### 6.1 Concepts

- **Swing high/low**: a local extremum.
- **Equal highs/lows**: several swings at nearly the same level.
- **Stop cluster zone ("liquidity pool")**: the assumption that stop-loss orders pile up just beyond obvious swings and around round numbers.
- **Liquidity sweep / stop hunt**: price moves through that level then quickly returns. Wyckoff's spring and upthrust (§4) are the same phenomenon under a different name.

### 6.2 Swing detection

```python
def swings(df: pd.DataFrame, left: int = 5, right: int = 5) -> pd.DataFrame:
    """Fractal: the highest high in the window [i-left, i+right].
    A swing at i is only KNOWN at i+right -> known_at column."""
    w = left + right + 1
    is_h = df["high"] == df["high"].rolling(w, center=False).max().shift(-right)
    is_l = df["low"] == df["low"].rolling(w, center=False).min().shift(-right)
    out = pd.DataFrame({"swing_high": df["high"].where(is_h), "swing_low": df["low"].where(is_l)})
    out["known_at"] = df.index.to_series().shift(-right)
    return out
```

Alternatives: zigzag (§5.6) or `scipy.signal.find_peaks` with an ATR-based `prominence`.

### 6.3 Equal highs/lows clusters

```python
def cluster_levels(levels: pd.Series, tol: pd.Series, min_touches: int = 2) -> list[dict]:
    """levels: swing prices (time index, dropna'd). tol: tolerance at that time (e.g. 0.1*ATR)."""
    out, used = [], set()
    vals = levels.sort_values()
    for t0, p0 in vals.items():
        if t0 in used:
            continue
        grp = vals[(vals - p0).abs() <= tol.loc[t0]]
        if len(grp) >= min_touches:
            used.update(grp.index)
            out.append({"level": float(grp.mean()), "touches": len(grp),
                        "first": grp.index.min(), "last": grp.index.max()})
    return out
```

For the BTC monthly chart (chart 2), cluster on log-price with a percentage tolerance, since absolute ATR changes by orders of magnitude over time.

### 6.4 Liquidity sweep

```python
def sweeps_of_low(df: pd.DataFrame, level: float, valid_from, reclaim_bars: int = 1,
                  max_pen: float | None = None) -> pd.Index:
    seg = df.loc[valid_from:]
    pierced = seg["low"] < level
    if max_pen is not None:
        pierced &= seg["low"] > level - max_pen
    if reclaim_bars == 1:
        back = seg["close"] > level                      # same candle: known when the candle closes
    else:
        back = seg["close"].shift(-(reclaim_bars - 1)) > level   # lookahead, timestamp must be shifted
    return seg.index[pierced & back]
```

Additional features: penetration depth in ATR, volume and delta of the sweep candle (§2), number of times the level has been touched, age of the level, distance to a round number.

### 6.5 Data, traps, evidence

- Data: OHLCV is enough; add aggTrades to see delta at the moment of the sweep.
- Traps: swings are only confirmed after `right` candles; "nice" levels on a higher-timeframe chart are the result of visual selection; the same penetration can be a sweep or a real breakout, distinguishable only afterwards.
- Evidence: the **order clustering** part is well founded. Osler (2003, *Journal of Finance* 58(5), 1791–1819) used actual order data from a large FX bank and showed take-profit orders cluster at round numbers while stop-loss orders cluster just beyond them, and that trends accelerate after these levels break (verified: https://ideas.repec.org/a/bla/jfinan/v58y2003i5p1791-1819.html; NY Fed Staff Report 125 version: https://fraser.stlouisfed.org/files/docs/publications/frbnysr/frbny_sr125.pdf). Note this is the FX market, and the results support both *reversal at the level* and *acceleration after the break*, not specifically the sweep-then-reverse scenario. Edge from trading sweeps in crypto/stocks after costs: **unverified**.

---

## 7. Classic indicators

### 7.1 Formulas and default parameters

Notation: `C, H, L, V` are close, high, low, volume; `n` is the period.

| Indicator | Short formula | Common defaults |
|---|---|---|
| SMA | arithmetic mean of `n` prices | 20, 50, 200 |
| EMA | `EMA_t = α·C_t + (1−α)·EMA_{t−1}`, `α = 2/(n+1)` | 12, 26, 50, 200 |
| RSI (Wilder) | `RS = avg_gain / avg_loss` (Wilder smoothing, `α = 1/n`); `RSI = 100 − 100/(1+RS)` | n=14; thresholds 30/70 |
| MACD | `MACD = EMA12 − EMA26`; `signal = EMA9(MACD)`; `hist = MACD − signal` | 12, 26, 9 |
| ROC | `100·(C_t / C_{t−n} − 1)` | n=10 or 12 |
| Stochastic | `%K = 100·(C − LL_n)/(HH_n − LL_n)`; slow %K = SMA(%K, 3); `%D = SMA(slow %K, 3)` | 14, 3, 3 |
| Williams %R | `−100·(HH_n − C)/(HH_n − LL_n)` | n=14; thresholds −20/−80 |
| ATR | `TR = max(H−L, |H−C_{t−1}|, |L−C_{t−1}|)`; ATR = Wilder MA of TR | n=14 |
| Bollinger Bands | `mid = SMA_n`; `upper/lower = mid ± k·σ_n` | n=20, k=2 |
| VWAP | `Σ(TP·V) / ΣV`, `TP = (H+L+C)/3`, reset each session | daily reset |
| Anchored VWAP | VWAP accumulated from a chosen anchor | anchor: swing, event |
| ADX | `+DM/−DM` → Wilder → `+DI, −DI`; `DX = 100·|+DI − −DI|/(+DI + −DI)`; ADX = Wilder(DX) | n=14; threshold 20–25 |
| OBV | add `V` if `C_t > C_{t−1}`, subtract if lower | no parameters |

```python
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn)

def anchored_vwap(df: pd.DataFrame, anchor) -> pd.Series:
    seg = df.loc[anchor:]
    tp = (seg["high"] + seg["low"] + seg["close"]) / 3
    return (tp * seg["volume"]).cumsum() / seg["volume"].cumsum()

def session_vwap(df: pd.DataFrame) -> pd.Series:          # index is a UTC DatetimeIndex
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.floor("D")
    return (tp * df["volume"]).groupby(day).cumsum() / df["volume"].groupby(day).cumsum()
```

### 7.2 Libraries

- **TA-Lib** (C, Python wrapper): fast, the de facto reference. The wrapper ships binary wheels bundling the C library since 0.6.5, no manual build needed (verified: https://github.com/TA-Lib/ta-lib-python, https://pypi.org/project/TA-Lib).
- **pandas-ta**: the original announced it would be archived without more support before 2026-07-01; current status **unverified**. The community fork `pandas-ta-classic` is still releasing in 2026 (verified: https://pypi.org/project/pandas-ta-classic/, https://github.com/TheNeuroDeveloper/pandas-ta-classic). Pin the version and check maintenance status before choosing.
- Writing the core indicator set yourself in pandas/numpy is a reasonable choice: fewer dependencies, controlled warm-up.

### 7.3 Common traps

- **Library defaults differ from chart defaults.** From memory of TA-Lib: `BBANDS` defaults to `timeperiod=5` (not 20), `STOCH` defaults to `fastk_period=5` (not 14). Always pass parameters explicitly; re-check at https://ta-lib.org/functions/.
- **EMA/Wilder initialization differs** between TA-Lib (SMA seed), pandas `ewm(adjust=False)` and TradingView, causing different values at the start of the series. Use a long warm-up (at least several times `n`) and cross-check against a reference source.
- **VWAP** needs intraday data; VWAP from daily candles is meaningless. For crypto, the session reset point is a self-chosen convention.
- **Anchored VWAP** anchored to a swing: the swing must already be confirmed at the time of use.
- Most indicators are transformations of the same price series and highly correlated with each other; stacking many indicators adds no independent information.
- OBV and other volume indicators are affected by the exchange's volume quality.

### 7.4 Empirical evidence

Mixed. Brock, Lakonishok & LeBaron (1992) reported that MA and trading-range breakout rules had predictive power on the Dow Jones; Sullivan, Timmermann & White (1999) showed that after correcting for data snooping, the performance does not hold out of sample (both from memory). Park & Irwin (2007) summarize: positive results are concentrated in FX and commodities rather than stocks, and weaken over time (verified, URL in §0). For Bitcoin, some studies report MA rules have predictive power (Detzel et al. 2021; Hudson & Urquhart 2021 — from memory, **unverified** in this session). Trend/momentum indicators have better evidence than overbought/oversold oscillators.

---

## 8. Intermarket and macro analysis

### 8.1 Commonly cited relationships

| Variable | Common argument | Notes |
|---|---|---|
| Fed funds rate (FEDFUNDS) | Falling rates/easing support risk assets | A step-like policy variable that changes very rarely |
| DXY | Strong dollar goes with weak BTC | DXY is an ICE index; FRED has a broad dollar index (DTWEXBGS), which is a different series |
| Gold (XAUUSD) | "Digital gold", both benefit from currency debasement | BTC–gold correlation is low and unstable |
| Bond yields (10Y, real yield) | Rising real yields pressure assets that don't produce cash flow | FRED series: DGS10, DGS2, DFII10 |
| Global liquidity / M2 | BTC follows M2 with a lag of a few weeks to a few months | See warnings in §8.4 |
| Halving cycle | Tops/bottoms repeat on a ~4-year cycle | Only 4 halvings (2012, 2016, 2020, 2024) |

Evidence on the "safe haven" role: a Kansas City Fed study (2020) concluded Bitcoin never exhibited safe-haven behavior in their sample and often behaved like a risk asset (verified: https://www.kansascityfed.org/en/publications/research/eb/articles/2020/safe-haven-performance-age-of-bitcoin). Smales & Baur ("Bitcoin as a safe haven: Is it even worth considering?", *Finance Research Letters* 30) and Klein, Hien & Walther ("Bitcoin is not the New Gold", summarized at https://quantpedia.com/bitcoin-is-not-the-new-gold/) point the same way (verified via secondary source).

### 8.2 Data needed

- **FRED** (https://fred.stlouisfed.org): `FEDFUNDS` (monthly average), `DFF` (daily), `DGS10`, `DGS2`, `DFII10`, `DTWEXBGS`, `M2SL` (monthly), `WALCL` (Fed balance sheet, weekly). Series codes written from memory; check each on FRED.
- **Gold**: FRED used to have LBMA gold price series but removed them: **unverified**. Another source is needed (an FX/commodity data vendor, or GC futures).
- **Global M2**: no central bank publishes it; it is a self-assembled index from countries' M2 converted to USD, and everyone builds it differently (verified via secondary source: https://www.bit.com/knowledge-hub/global-m2-decoupling). Because it is converted to USD, the series already contains dollar moves.
- **Point-in-time**: macro data has publication lags and revisions. October `M2SL` is only available at the end of November. Use ALFRED (vintages) or shift series yourself according to the release calendar.

### 8.3 How to measure

**Rule number one: measure on returns (or differences), not on price levels.**

```python
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint

def rolling_corr(a: pd.Series, b: pd.Series, win: int = 90) -> pd.Series:
    ra, rb = np.log(a).diff(), np.log(b).diff()
    return ra.rolling(win).corr(rb)

def lead_lag(a: pd.Series, b: pd.Series, max_lag: int = 26) -> pd.Series:
    """corr(ret_a[t], ret_b[t-k]); k>0 means b leads a by k periods."""
    ra, rb = np.log(a).diff(), np.log(b).diff()
    return pd.Series({k: ra.corr(rb.shift(k)) for k in range(-max_lag, max_lag + 1)})

def engle_granger(a: pd.Series, b: pd.Series):
    la, lb = np.log(a).dropna().align(np.log(b).dropna(), join="inner")
    t, p, _ = coint(la, lb)                    # H0: not cointegrated
    return {"t": t, "p": p, "adf_a": adfuller(la)[1], "adf_b": adfuller(lb)[1]}

def rate_regime(ff: pd.Series, n: int = 3, eps: float = 0.10) -> pd.Series:
    """Monthly FEDFUNDS -> hiking / cutting / hold by n-month change."""
    d = ff.diff(n)
    return pd.Series(np.select([d > eps, d < -eps], ["hiking", "cutting"], "hold"), index=ff.index)
```

Additionally:

- **Regime**: compare the distribution of BTC and gold returns *conditional* on the rate regime (`rate_regime`) or on a Markov switching model (`statsmodels.tsa.regime_switching`, Hamilton 1989 — from memory).
- **Event study**: BTC's reaction around FOMC meetings, measured over short windows; less contaminated by the common trend than long-run correlation.
- **Time alignment**: BTC trades 24/7, gold and bonds have closing times and holidays. Sample BTC at the exact close of the other asset, or use weekly frequency to reduce timing noise.
- **Confidence intervals**: block bootstrap for rolling correlation; with overlapping samples, ordinary standard errors are underestimated.

Applied to chart (4): split into three separate measurements — (a) rolling correlation of weekly BTC–gold returns; (b) BTC and gold returns by FEDFUNDS regime; (c) event study around FOMC dates. Overlaying three lines on one chart is only an illustration, not a measurement.

### 8.4 Spurious correlation warnings

- **Two trending series will correlate highly in levels** even if unrelated (Granger & Newbold 1974, "spurious regression" — from memory). Concrete example: one analysis reports a BTC–global M2 level correlation of 0.86 to 0.94 but a contemporaneous monthly-change correlation of only about 0.04; the "best" lag drifts from 1–2 months to 2–3 months over time (https://www.bit.com/knowledge-hub/global-m2-decoupling — source is an exchange blog, figures **unverified** independently).
- **Choosing the lag after looking at the data** is data snooping: shift the M2 series by 70–110 days until it matches the chart and you will always find a matching lag.
- **The effective sample is very small.** Since BTC has had a liquid market, there have been only a few rate cycles and 4 halvings. Four observations are not enough to distinguish the "halving cycle" from a coincident global liquidity cycle.
- **Correlations are unstable.** BTC's correlation with stocks, gold, and the dollar flips sign across periods; BTC–gold correlation spiked during the 2020 COVID selloff and then fell back (https://vaneck.com/ch/en/blog/digital-assets/bitcoin-correlation-to-gold-jumps-in-2020 — practitioner source).
- **Common hidden variables**: global risk appetite and the dollar move many assets simultaneously; A and B moving together doesn't mean A leads B.
- **Cointegration** between BTC and macro variables: the test easily gives false positives on short samples with structural breaks; don't build mean-reversion strategies on it without out-of-sample testing.

### 8.5 Empirical evidence

Macro relationships with BTC are real at the descriptive level but unstable and based on small samples. Liu & Tsyvinski (2021, *Review of Financial Studies*) note that crypto returns have little exposure to macro factors and traditional equity factors, and are better explained by momentum and investor attention (from memory; their sample ends before 2020–2022, when correlation with stocks rose). Research on BTC's reaction to FOMC announcements and critiques of the small sample of halving cycles: **unverified** (search did not find specific sources).

---

## 9. On-chain for crypto

### 9.1 Definitions

| Metric | Definition |
|---|---|
| Realized Cap | Total value of supply, each coin valued at the time it last moved on-chain |
| Realized Price | `Realized Cap / circulating supply`; seen as the average "on-chain cost basis" |
| MVRV | `Market Cap / Realized Cap`; MVRV = 1 means price equals the average cost basis |
| MVRV Z-Score | `(Market Cap − Realized Cap) / std(Market Cap)` |
| SOPR | For outputs spent in the period: `value when spent / value when created`; > 1 is profit-taking, < 1 is loss-cutting |
| aSOPR | SOPR excluding outputs younger than 1 hour |
| NUPL | `(Market Cap − Realized Cap) / Market Cap = 1 − 1/MVRV` |
| Exchange flows | Inflow, outflow, netflow and balance on addresses labeled as exchanges |

The definitions of Realized Price, MVRV, SOPR/aSOPR, NUPL were verified against Glassnode (https://docs.glassnode.com/guides-and-tutorials/metric-guides, https://studio.glassnode.com/charts/realizedprice-mvrv?a=BTC, https://insights.glassnode.com/dissecting-bitcoins-unrealised-on-chain-profit-loss). The MVRV Z-Score formula is from memory. Since NUPL is a monotonic function of MVRV, the two carry the same information.

Cohort variants: STH/LTH (short/long-term holder, conventional threshold of 155 days — from memory) for MVRV, SOPR, and realized price per cohort.

### 9.2 Computation

```python
def onchain_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Daily df: columns price, supply, realized_cap (from a vendor)."""
    out = pd.DataFrame(index=df.index)
    mcap = df["price"] * df["supply"]
    out["realized_price"] = df["realized_cap"] / df["supply"]
    out["mvrv"] = mcap / df["realized_cap"]
    out["nupl"] = 1 - 1 / out["mvrv"]
    out["mvrv_z"] = (mcap - df["realized_cap"]) / mcap.expanding(min_periods=365).std()
    return out
```

`expanding()` keeps the Z-score free of lookahead; public charts usually use the full-sample std, which looks ahead.

Computing realized cap and SOPR from scratch requires a full node and traversing the entire UTXO set (per output: value, creation time, spend time, price at both times). Doable but laborious; start from vendor data.

### 9.3 Data sources

| Source | Notes |
|---|---|
| Glassnode (https://docs.glassnode.com/quickstart/rest-api) | Comprehensive; API and high resolution are paid |
| CryptoQuant | Strong on exchange flows; most data is paid (from memory) |
| Coin Metrics | Free community API with some metrics such as realized cap, MVRV (from memory; current free scope **unverified**) |
| Running your own node | Full control over definitions; no exchange address labels |

### 9.4 Common traps

- **Only directly applicable to UTXO-style chains** (BTC). For account-based chains (ETH) definitions must be approximated; stablecoins and multi-chain tokens are even more complex.
- **Exchange flows depend on address labeling** with each vendor's own heuristics; figures differ between sources and are retroactively revised when new wallets are discovered. Internal exchange wallet transfers can be counted as inflow/outflow.
- **Market structure has changed**: spot ETFs, centralized custody, wrapped BTC, and off-chain trading make "coins moving on-chain" less and less representative of real economic activity. Permanently lost coins distort realized cap.
- **Historical thresholds** (e.g. NUPL > 0.5 as "euphoria" per Glassnode; high MVRV-Z as "top") are drawn from 3–4 cycles and chosen after the fact. The peaks of these metrics decline across cycles, so fixed thresholds are unstable.
- **Lag and revisions**: daily data, usually settled in UTC; some metrics are recomputed. Store snapshots by fetch date if you want point-in-time backtests.

### 9.5 Empirical evidence

MVRV/NUPL/SOPR describe the market's unrealized profit/loss state well and have historically reached extremes near BTC cycle tops/bottoms. However, there are only about 3–4 independent cycles, thresholds are fitted in-sample, and the main sources are data vendors with commercial interests. Peer-reviewed research confirming out-of-sample predictive power: **unverified**. Suitable as a long-horizon regime feature (weekly/monthly), not as a short-term signal.

---

## 10. Summary for system design

### 10.1 Quick assessment table

| Method | Objectively programmable? | Evidence | Minimum data |
|---|---|---|---|
| Volume Profile (POC/VA/LVN) | Yes, once bin and range are fixed | Weak, no peer-reviewed tests | 1m candles; ideally aggTrades |
| Order flow (delta, CVD, imbalance) | Yes | Good at seconds–minutes; weak at long horizons | aggTrades |
| Funding / OI / liquidation | Yes | Mostly from industry sources | Exchange API, must be collected continuously |
| Liquidation heatmap | Only an estimation model | Not verifiable | OI + leverage assumptions |
| Wyckoff | Partly (components yes, schematics subjective) | Weak | OHLCV |
| Elliott Wave | Hard rules yes; counts have multiple solutions | Weak | OHLCV |
| Swing / equal lows / sweep | Yes | Stop clustering has evidence (FX); trading edge unclear | OHLCV |
| Classic indicators | Yes | Mixed; trend/momentum better | OHLCV |
| Intermarket / macro | Yes | Unstable relationships, small samples | FRED + prices |
| On-chain | Yes (from vendor data) | Good descriptively, prediction unverified | Vendor API |

### 10.2 Implementation principles

1. Every feature has two timestamps: `event_time` and `known_at`. Backtests use only `known_at`.
2. Start collecting unrecoverable data immediately: OI, long/short ratio, liquidation stream, order book.
3. Split subjective methods (Wyckoff, Elliott) into measurable components and test each separately.
4. Fix parameters before testing; record the number of configurations tried.
5. Measure every macro relationship on returns, with confidence intervals, and check stability across periods.
6. Record the source and assumptions of every data series (which exchange, spot or perp, volume-spreading method, "session" definition).

### 10.3 List of unverified items

1. The value-area expansion variant used by TradingView's built-in (two rows or one row).
2. Peer-reviewed evidence for POC/VA/naked POC, for the 300% imbalance threshold, and for weekly delta/CVD.
3. The 30-day limit of `openInterestHist` on USDⓈ-M (seen on COIN-M); the "metrics" file set on data.binance.vision; the taker buy/sell ratio endpoint name.
4. The 1000 ms snapshot rule of `forceOrder` on USDⓈ-M (seen on COIN-M).
5. Coinglass's detailed liquidation heatmap method.
6. Edge after costs of extreme funding, of sweeps, of Wyckoff.
7. Detailed definitions of each Wyckoff event and the UA symbol: written from memory of ChartSchool, original not re-read.
8. arXiv preprint 2403.18839 on Wyckoff recognition with LSTM: method and data not read.
9. Batchelor & Ramyar (2006) on Fibonacci; Detzel et al. (2021), Hudson & Urquhart (2021), Liu & Tsyvinski (2021), Cont–Kukanov–Stoikov (2014), Brock–Lakonishok–LeBaron (1992), Sullivan–Timmermann–White (1999): cited from memory, originals not opened.
10. TA-Lib defaults `BBANDS timeperiod=5`, `STOCH fastk_period=5`; the taker buy volume column in Binance klines.
11. Archive status of the original pandas-ta after 2026-07-01.
12. FRED series codes and whether FRED removed the LBMA gold price series; Coin Metrics' free scope.
13. BTC–global M2 correlation figures (0.86–0.94 and 0.04): from an exchange blog, not independently checked.
14. Research on BTC's reaction to FOMC and critiques of the small halving-cycle sample: no specific source found.
15. The MVRV Z-Score formula and the 155-day STH/LTH threshold: from memory.
16. None of the pseudocode in this document has been run; it needs unit tests before use.
