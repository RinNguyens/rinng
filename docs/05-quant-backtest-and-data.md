# 05 — Quant research, backtesting and data

> Research date: **2026-11-13**. Library versions come from the PyPI JSON API and the GitHub API on that day; prices and free-tier limits come from official pages when they could be opened, otherwise from secondary sources, noted as such.
>
> Conventions:
> - **[unverified]** = could not be checked against an official source in this research session. Open the original page before relying on it.
> - Formulas, concepts and the book/paper lists are background knowledge, independent of the research date. Paper URLs are written from memory, **links not individually checked**.
> - This document gives no buy/sell recommendations. All examples only illustrate methods.

## Contents

1. [Quant research workflow](#1-quant-research-workflow)
2. [Backtesting properly](#2-backtesting-properly)
3. [Metrics and annualization](#3-metrics-and-annualization)
4. [Risk management and position sizing](#4-risk-management-and-position-sizing)
5. [Strategy families](#5-strategy-families)
6. [Microstructure basics](#6-microstructure-basics)
7. [Python library comparison](#7-python-library-comparison)
8. [Data sources](#8-data-sources)
9. [Fundamental analysis for the stock analyzer](#9-fundamental-analysis-for-the-stock-analyzer)
10. [Proposed storage architecture and pipeline](#10-proposed-storage-architecture-and-pipeline)
11. [Foundational books and papers](#11-foundational-books-and-papers)
12. [List of unverified items](#12-list-of-unverified-items)

---

## 1. Quant research workflow

| Step | What to do | Output | Common mistakes |
|---|---|---|---|
| 1. Hypothesis | Write down *why* the edge exists (who is paying you: liquidity seekers, forced sellers, slow-reacting behavior…) and the conditions that would make it disappear | 1 paragraph + rejection criteria written **before** looking at the data | Mining the data first, then inventing a reason |
| 2. Data | Collect, clean, record the source and the time the data *became known* (point-in-time) | Immutable raw + normalized tables | Using restated data, missing delisted tickers |
| 3. Features | Transform into meaningful quantities, using only information available at time `t` | Timestamped feature store | Normalizing with full-sample mean/std (leak) |
| 4. Signal | Map features → desired position (direction + size) | A pure, reproducible `signal(t)` function | Too many free parameters |
| 5. Backtest | Simulate fills with fees, slippage, funding, latency | Equity curve, trade log | Fills at prices that could not have been filled |
| 6. Validation | Out-of-sample, walk-forward, CPCV, DSR, PBO, regime stress | Report including the **number of trials** | Picking the best version and reporting it as a single trial |
| 7. Paper trading | Run the real code on live data with fake money, long enough to see several regimes | Compare actual fills with backtest assumptions | Skipping this step because the backtest "looks good" |
| 8. Live | Small capital, scaling up gradually; kill-switch and loss limits | Trade log, daily reconciliation | Increasing size before having enough samples |

Cross-cutting principles:

- **Keep a research log**: for each backtest run record the parameters, data range, commit hash and result. The number of trials `N` is a required input of the deflated Sharpe ratio (section 2.4).
- **Split the data from the start**: keep a final hold-out segment, opened only once when the strategy is finalized.
- **Same code for backtest and live** (or at least the same signal function) to avoid behavioral drift.
- **Realistic expectations**: most ideas die at steps 5–6. A carefully documented negative result still has value.

---

## 2. Backtesting properly

### 2.1 Vectorized vs event-driven

| | Vectorized | Event-driven |
|---|---|---|
| How it runs | Computes over whole arrays (pandas/numpy/polars): `position.shift(1) * returns` | Event loop (bar, tick, fill), with order book and account state |
| Speed | Very fast, can sweep thousands of parameters | Many times slower |
| Realism | Low: hard to simulate limit orders, partial fills, margin, liquidation | High: can model order types, queue, latency, funding |
| Look-ahead risk | High (forget a `shift` and you're caught) | Lower, since it only sees data up to now |
| Use for | Screening ideas, factor research, low-frequency strategies | Confirmation before live, intraday strategies, leveraged strategies |
| Example libraries | vectorbt, hand-written polars | NautilusTrader, backtrader, LEAN, zipline-reloaded, freqtrade |

A sensible approach: use vectorized to eliminate bad ideas, then rewrite the surviving ideas in the event-driven engine you will use live. If the two results differ a lot, the difference is precisely the execution cost the vectorized version ignored.

### 2.2 Classic mistakes

| Mistake | Symptom | Prevention |
|---|---|---|
| **Look-ahead bias** | Using bar `t`'s close to enter at close `t`; using financial statements by quarter-end date instead of release date; `fillna(method="bfill")`; wrong resample labels (`label`/`closed`) | Signal computed at `t`, earliest fill at open `t+1`. Store `available_at` for all data. Test: truncate data at `t`; signals before `t` must not change |
| **Survivorship bias** | Universe contains only currently listed tickers or still-trading coins | Use point-in-time constituent lists, including delisted tickers. For crypto: include delisted coins |
| **Data snooping / multiple testing** | Try 500 variants, report the best one | Count trials, use DSR/PBO, keep a hold-out |
| **Overfitting** | Many parameters, results collapse when parameters change slightly | Few parameters, look for parameter "plateaus" instead of sharp peaks, walk-forward |
| **Ignoring costs** | Not counting maker/taker fees, spread, slippage, funding (perp), borrow fees (stock shorts), taxes | Model them all. Also run a ×2 cost scenario to see whether the strategy survives |
| **Unrealistic fills** | Limit orders fill as soon as price touches; filling size larger than the bar's volume; fills at the high/low | Limit orders only fill when price *trades through*. Cap participation rate (e.g. ≤ 1–5% of bar volume). Add latency |
| **Data errors** | Prices not adjusted for splits/dividends; mixed time zones; unclosed candles treated as closed | Normalize to UTC, store both raw and adjusted prices, drop the last unclosed bar |
| **Single regime** | Backtest only covers a bull market | Test per period, including bad periods |
| **Ignoring market constraints** | Daily price limits, T+ settlement (e.g. the Vietnamese market), no shorting, minimum lot size | Encode the constraints in the engine |

### 2.3 Time-based validation

**Walk-forward**: optimize on a train window, evaluate on the test window right after, slide forward and concatenate the test segments.

- *Rolling* (fixed-length train window) suits relationships that change over time; *anchored/expanding* (growing train window) suits cases needing many samples.
- Limitation: yields only **one** historical path; results depend on how the windows are split.

**Purged & embargoed K-fold** (López de Prado, *AFML* ch. 7): ordinary K-fold leaks information because train-sample labels overlap in time with test samples.

- *Purging*: remove from train any sample whose label interval `[t0, t1]` overlaps the test interval.
- *Embargo*: also remove a train segment right **after** the test (usually ~1% of samples) to block leakage via autocorrelation.

**Combinatorial purged CV (CPCV)** (*AFML* ch. 12): split into `N` groups, take `k` groups as test each time, with purge and embargo.

- Number of splits: `C(N, k)`.
- Number of reconstructable backtest paths: `φ = (k / N) · C(N, k)`. Example `N = 6, k = 2` → 15 splits, 5 paths.
- Benefit: yields a **distribution** of Sharpe instead of a single number.

### 2.4 Correcting for multiple testing

**Deflated Sharpe ratio (DSR)** — Bailey & López de Prado (2014). Idea: if you try `N` strategies, the largest Sharpe will be positive even if all are useless. DSR asks the probability that the true Sharpe > 0 after subtracting the expectation of "the max of N trials".

```
SR0 = sqrt(V[SR_n]) · [ (1 − γ) · Φ⁻¹(1 − 1/N) + γ · Φ⁻¹(1 − 1/(N·e)) ]

DSR = Φ( (SR − SR0) · sqrt(T − 1) / sqrt(1 − γ3·SR + ((γ4 − 1)/4)·SR²) )
```

- `SR`: **non-annualized** Sharpe (at the observation frequency); `T`: number of observations.
- `V[SR_n]`: variance of Sharpe across trials; `N`: number of *independent* trials (if variants are highly correlated, the effective number is smaller than the count).
- `γ ≈ 0.5772` (Euler–Mascheroni constant); `γ3`, `γ4`: skewness and kurtosis of returns.
- Reading the result: DSR > 0.95 is usually considered a credible threshold; below that, treat it as not proven.

**Probability of backtest overfitting (PBO)** — Bailey, Borwein, López de Prado & Zhu (2017), using CSCV (combinatorially symmetric cross-validation):

1. Build a `T × N` return matrix (N configurations), split into `S` time blocks.
2. For each choice of `S/2` blocks as in-sample: find the best configuration IS, check its OOS rank.
3. PBO = the fraction of times the IS winner falls **below the median** OOS.

PBO near 0.5 means selecting by backtest is no better than a coin flip.

**Statistical thresholds under many trials**: Harvey, Liu & Zhu (2016) argue a new factor should have t-stat > 3.0 rather than 2.0. Common corrections: Bonferroni (strict), Holm, Benjamini–Hochberg (controls the false discovery rate).

**Practical checks**, cheap and effective:

- Shuffle the signal or shift it randomly: Sharpe should go to near 0.
- Run on random data (random walk): if it is still "profitable", the engine has a bug.
- Perturb parameters by ±10–20%: results must not collapse.
- Switch to a similar exchange/market: does the edge repeat?

### 2.5 Triple-barrier labeling and meta-labeling

**Triple-barrier** (*AFML* ch. 3): instead of labeling by the return after a fixed `h` bars, set three barriers for each entry event:

- Upper barrier (profit-taking) and lower barrier (stop-loss), widths based on current volatility (e.g. a multiple of EWM std or ATR).
- Vertical barrier (holding time expires).

The label is the barrier touched first: `+1`, `−1`, or `0`/sign of the return if the vertical barrier is hit. Because labels overlap in time, you must use *uniqueness-based sample weights* and purged CV.

**Meta-labeling**: separate two decisions.

1. A primary model (a simple rule or a high-recall model) decides the **direction**.
2. A secondary model (classifier) predicts the probability that the primary signal is **correct**; this probability is used to filter trades and decide **size**.

Benefit: improves precision without breaking the original logic, and provides a principled sizing method. Risk: adds another layer to overfit, so it still has to go through CPCV/DSR.

---

## 3. Metrics and annualization

Notation: `r_t` is the per-period return, `P` the number of periods per year, `r_f` the per-period risk-free rate, `V_t` the account value.

| Metric | Formula | Notes |
|---|---|---|
| **CAGR** | `(V_end / V_start)^(1/years) − 1` | `years` measured in real calendar time (days / 365.25) |
| **Annual volatility** | `std(r) · sqrt(P)` | Assumes i.i.d. returns; wrong under autocorrelation |
| **Sharpe** | `mean(r − r_f) / std(r − r_f) · sqrt(P)` | State which `r_f` is used; for crypto many use 0, note it |
| **Sortino** | `mean(r − MAR) / DD · sqrt(P)`, `DD = sqrt(mean(min(r − MAR, 0)²))` | Downside deviation divides by **all** periods, not just negative ones |
| **Max drawdown** | `min_t (V_t / max_{s≤t} V_s − 1)` | Depends on sampling frequency: daily data hides intraday drawdowns |
| **Calmar** | `CAGR / |MaxDD|` | Usually computed over the last 36 months |
| **Win rate** | `winning trades / total trades` | Meaningless without the payoff ratio |
| **Profit factor** | `gross profit / |gross loss|` | > 1 is profitable; very high with few trades is usually overfit |
| **Expectancy** | `p · avg_win − (1 − p) · avg_loss` | Can be normalized by per-trade risk (R-multiple) |
| **Turnover** | `Σ |Δw_t| / 2` per period, then times `P` | Multiply by one-way cost to estimate cost drag |
| **Exposure** | Fraction of time in a position; gross = `Σ|w|`, net = `Σw` | A high Sharpe at 5% exposure is very different from at 100% |
| **Beta** | `cov(r, r_m) / var(r_m)` | `r_m` is an appropriate benchmark (index for stocks, BTC for altcoins) |
| **Alpha (Jensen)** | `mean(r − r_f) − β · mean(r_m − r_f)`, times `P` | Taken from the regression intercept; check the t-stat too |
| **Information ratio** | `mean(r − r_b) / std(r − r_b) · sqrt(P)` | The denominator is tracking error |

### Annualization factor `P`

| Frequency | US stocks | Crypto 24/7 |
|---|---|---|
| Daily | 252 | 365 |
| Weekly | 52 | 52 |
| 4h | ≈ 252 × 6.5 / 4 ≈ 410 (rarely used) | 365 × 6 = 2 190 |
| 1h | ≈ 252 × 6.5 = 1 638 | 365 × 24 = 8 760 |
| 1m | ≈ 252 × 390 = 98 280 | 525 600 |

Notes:

- Other markets have different session counts and trading hours (e.g. Vietnam has a lunch break and about 250 sessions/year). The safest approach: **count the actual bars per year in the data**.
- Comparing crypto and stock Sharpe requires the same convention. Using `sqrt(252)` on a daily crypto series lowers Sharpe by about 17% compared with `sqrt(365)`.
- Annualizing high-frequency data with `sqrt(P)` inflates Sharpe when returns are positively autocorrelated. Lo (2002) gives a correction factor; the simple approach is to compute Sharpe on aggregated daily returns.
- Intraday stock returns have an overnight gap; decide whether to include the overnight return and state it.
- The estimated Sharpe has a standard error of approximately `sqrt((1 + SR²/2) / T)` (in per-period units). With 1 year of daily data, the confidence interval is very wide.

---

## 4. Risk management and position sizing

### 4.1 Sizing methods

| Method | Formula | Pros | Cons |
|---|---|---|---|
| **Fixed fractional** | `qty = (equity · risk%) / |entry − stop|` | Simple, per-trade loss is capped | Ignores correlation between positions; gaps through the stop |
| **Volatility targeting** | `w_t = σ_target / σ̂_t` (capped at max leverage) | Stable risk across regimes | Depends on the `σ̂` estimate; increases size exactly when vol is low before a shock |
| **Kelly** | Discrete: `f* = p − (1 − p)/b`. Continuous: `f* = μ / σ²` | Maximizes long-run log growth | Extremely sensitive to estimation error in `μ`; very deep drawdowns |
| **Fractional Kelly** | `f = c · f*`, `c` usually 0.25–0.5 | Keeps most of the growth, sharply reduces volatility | Still needs an edge estimate |
| **ATR stop / ATR sizing** | `stop = entry − k · ATR(n)`; `qty = (equity · risk%) / (k · ATR)` | Stop adapts to volatility | `k`, `n` are parameters easy to overfit |

Note on Kelly: `b` is the average win/loss ratio, `p` the win probability. Half-Kelly keeps about 75% of the growth rate with half the volatility. Since `μ` estimated from a backtest is almost always inflated, full Kelly on backtest figures is almost certainly over-betting.

### 4.2 VaR and CVaR

- **VaR(α)**: the loss level not exceeded with probability `α` in one period. Three methods: historical (empirical quantile), parametric (`z_α · σ − μ`, assuming normality), Monte Carlo.
- **CVaR / Expected Shortfall**: the average loss *given that* VaR is exceeded: `E[L | L ≥ VaR_α]`. CVaR is a coherent (subadditive) measure while VaR is not, and it reflects the tail better.
- Crypto returns have fat tails: normal parametric VaR underestimates risk. Use historical, or a GARCH model with a Student-t distribution (the `arch` library).

### 4.3 Drawdown limits and operational controls

- Tiered limits: max loss per trade, per day, per week, and total drawdown (e.g. halve size when DD hits level A, stop completely at level B). The specific levels are a personal choice and must be written down **beforehand**.
- Concentration limits: caps per ticker, per sector, per exchange; caps on gross and net exposure.
- Kill-switch: stop when data is late, when actual positions deviate from desired positions, or on repeated API errors.
- Counterparty risk (especially crypto): don't keep all capital on one exchange; API keys must not have withdrawal permission.
- Recovery math: a 20% loss needs +25% to break even, a 50% loss needs +100%.

### 4.4 Leverage and liquidation in crypto futures

Concepts:

- **Initial margin** ≈ `notional / leverage`; **maintenance margin** = `notional × MMR` (MMR is tiered by position size; the larger the position, the higher the MMR).
- **Mark price** (not last price) is used to compute unrealized PnL and trigger liquidation.
- **Isolated** (separate margin per position) and **cross** (shared balance; one bad position drags down the whole account).

Approximate liquidation price for isolated margin, linear contracts, ignoring fees and funding:

```
Long : P_liq ≈ P_entry · (1 − 1/L + MMR)
Short: P_liq ≈ P_entry · (1 + 1/L − MMR)
```

Illustrative example with `MMR = 0.5%`: a 10x long is liquidated when price falls about 9.5%; a 20x long at about 4.5%. The exact formula differs by exchange and contract type (inverse/coin-margined has a nonlinear payoff); read the documentation of the exchange you use.

Commonly overlooked points:

- **Funding**: perps pay/receive funding periodically (usually 8h, some exchanges/symbols 1h or 4h). Funding of 0.01%/8h is about 11%/year on notional; at high leverage this cost is very large relative to capital.
- **Liquidation fees, insurance fund and ADL** (auto-deleveraging): profitable positions can be force-closed in extreme markets.
- **Effective leverage** = `total notional / equity`. This is the number to manage, not the number set on the exchange.
- Leveraged backtests must simulate liquidation on intrabar prices (high/low), otherwise they falsely survive wicks.

---

## 5. Strategy families

| Family | Idea | Data needed | Main risks |
|---|---|---|---|
| **Momentum / trend following** | Trends have inertia. *Time-series* (buy assets rising relative to themselves) or *cross-sectional* (buy the strongest group, sell the weakest) | Daily/4h OHLCV, a full point-in-time universe | Whipsaw in sideways markets; momentum crashes on fast reversals; low win rate, needs discipline |
| **Mean reversion** | Price deviates from a short-term equilibrium then returns (z-score, Bollinger, short RSI, overnight reversal) | Higher-frequency OHLCV, spread data | "Catching a falling knife" when the regime changes; small steady gains, rare big losses (negative skew); very cost-sensitive |
| **Pairs / stat-arb / cointegration** | A linear combination of assets is stationary; trade deviations of the spread | Time-synchronized prices; Engle–Granger/Johansen tests; half-life (OU) estimation | Relationship breaks permanently; hedge ratio drifts; borrow fees and shortability; crowded |
| **Market making** | Quote both sides, earn spread and rebates, manage inventory (Avellaneda–Stoikov) | L2/L3 order book, tick trades, real latency | Adverse selection; inventory when price runs one way; needs infrastructure and preferential fees |
| **Funding / basis arbitrage** | Long spot + short perp to collect positive funding; or cash-and-carry with dated futures | Funding rate history, basis, fees, margin interest | Funding flips sign; short leg liquidated on a strong rally; exchange risk; capital split across two venues |
| **Factor investing (stocks)** | Hold baskets of stocks by characteristics with long-run premia: value, quality, momentum, size, low-vol | Point-in-time financial statements, adjusted prices, market cap, delisting lists | Factors underperform for years; crowding; turnover; premia shrink after publication |
| **Machine learning** | Gradient boosting (XGBoost/LightGBM) predicting returns or triple-barrier labels from many features | Point-in-time features, non-overlapping labels or sample weights | Very low signal-to-noise; overfitting; non-stationarity; leakage via ordinary CV |

ML notes:

- Tree models on tabular data are usually a stronger baseline than deep learning when data is scarce and noisy.
- **Feature importance**: MDI (built into trees, biased toward high-cardinality features), MDA/permutation importance (measured OOS, diluted when features are correlated), SHAP (explains individual predictions). With correlated features, cluster them and measure importance per cluster (*clustered feature importance*).
- Evaluate with purged CV/CPCV, not with random `train_test_split`.
- Classification metrics (accuracy, AUC) are not PnL. Always re-check with a cost-aware backtest.
- Make series stationary while preserving memory: fractional differentiation (*AFML* ch. 5).

---

## 6. Microstructure basics

- **Order book**: the list of limit orders by price level. L1 = best bid/ask; L2 = aggregated size per price level; L3 = individual orders. Matching is price then time priority, so queue position has value.
- **Spread**: `ask − bid`. A market order pays half the spread relative to mid. *Effective spread* is measured on the actual fill price; *realized spread* subtracts the post-fill price move (the remainder is adverse selection).
- **Market impact**: large orders push price. The empirical *square-root* law: `impact ≈ Y · σ · sqrt(Q / V)` where `Q` is order size, `V` daily volume, `Y` a constant of order 1. Impact has temporary and permanent components (Almgren–Chriss).
- **Maker / taker fee**: makers add liquidity (low fee, sometimes a rebate), takers remove liquidity (higher fee). Fee schedules are tiered by volume and differ per exchange; always take them from the exchange's fee page. *Post-only* orders guarantee maker status but may not fill.
- **Latency**: from event to order in the book includes feed delay, processing, network, matching engine. HFT measures in microseconds and uses co-location; personal bots over REST/WebSocket are usually in the tens to hundreds of milliseconds.

### Why "real HFT" differs from predicting 1h/4h candles with an LLM

| | Real HFT / market making | Predicting 1h/4h candles (including with an LLM) |
|---|---|---|
| Source of edge | Speed, queue position, rebates, order-flow modeling | Forecasting price direction over a few hours |
| Data | Tick, L2/L3, large volumes | OHLCV, news, indicators |
| Holding time | Milliseconds to minutes | Hours to days |
| Infrastructure | Co-location, C++/Rust/FPGA, top fee tiers | One small server, public APIs |
| Inference latency | Must be under a millisecond | LLMs take seconds: **unusable** for HFT |
| Independent samples | Millions of orders, fast statistical testing | A few thousand bars per year, hard to tell edge from luck |
| Methodological risks | Adverse selection, system failures | Overfitting, leakage, and for LLMs **training-data leakage** |

Things to remember when using LLMs for prediction:

- The LLM has already "read" market history in its training data. Backtesting on periods before the model's knowledge cutoff is disguised look-ahead. Only results **after the cutoff** are meaningful.
- Output is non-deterministic and changes with model version: record the model ID, prompt, and store the raw output verbatim for reproducibility.
- LLMs are more useful in other roles: extracting structure from text (reports, news, filings), summarizing, generating hypotheses, writing and reviewing code. Numeric signals should still go through tested statistical models.
- At 1h/4h horizons, trading costs and validation quality matter more than speed. This is medium-frequency trading, not HFT.

---

## 7. Python library comparison

Versions and release dates from PyPI on 2026-11-13; last push date and license from the GitHub API on the same day.

### 7.1 Data, computation, indicators

| Library | Purpose | Pros | Cons | Maintenance (2026-11-13) | License |
|---|---|---|---|---|---|
| **pandas** | The ecosystem's standard DataFrame | Every quant library accepts pandas; strong time-series index | Slow and RAM-hungry on large data; 3.x has breaking changes (copy-on-write) | 3.1.1 (2026-11-04), active | BSD-3 |
| **polars** | Columnar, lazy, multithreaded DataFrame (Rust) | Much faster, streaming Parquet reads, clean API | Few quant libraries accept it directly, often need `.to_pandas()` | 2.1.0 (2026-10-25), active | MIT |
| **numpy** | Numeric arrays, linear algebra | Foundation of everything | No time labels | 2.5.4 (2026-10-10), active | BSD-3 |
| **TA-Lib** (python wrapper) | 150+ technical indicators, C core | Fast, the reference standard | Depends on a C library (recent releases ship prebuilt wheels) | 0.8.3 (2026-10-28), active | BSD-2 |
| **pandas-ta** | Indicators as a pandas extension | Convenient API, many indicators | Unclear status: the original GitHub repo returns 404, the docs domain did not resolve on the research day | 0.4.71b0 (2025-09-14, beta). **[unverified]** project future | **[unverified]** (license page could not be opened) |
| **pandas-ta-classic** | Community fork of pandas-ta | Maintained, same API style | Small fork, fewer users | 0.9.0 (2026-10-28), active | MIT |

### 7.2 Backtesting and trading

| Library | Purpose | Pros | Cons | Maintenance | License |
|---|---|---|---|---|---|
| **vectorbt** (open version) | Vectorized backtesting, parameter sweeps | Very fast (numba; plus a `vectorbt-rust` package), rich portfolio analytics | Steep learning curve; less detailed execution simulation than event-driven | 1.2.1 (2026-11-11), active | **Apache 2.0 + Commons Clause** ("fair code": you may not sell products/services whose value derives mainly from the software) |
| **VectorBT PRO** | Paid version with more features | Frequent updates, private repo, Discord | Paid, closed to the public | Install example on the site shows v2026.10.5 | Proprietary. Prices on the site: 25 USD/month, 225 USD/year, 500 USD lifetime |
| **backtrader** | Classic event-driven | Lots of docs and examples | Slow; **no longer substantively developed** | PyPI 1.9.78.123 (2023-04-19); last push 2024-08-19 | GPL-3.0 |
| **backtesting.py** | Lightweight single-asset backtesting | Minimal API, nice charts | No real multi-asset portfolio support; AGPL | 0.6.6 (2026-07-22); last push 2026-08-05 | AGPL-3.0 |
| **zipline-reloaded** | Quantopian-style event-driven, stocks | Pipeline API for factors, handles corporate actions | Cumbersome data loading (bundles); geared to daily US stocks | 3.2.1 (2026-10-25), active | Apache-2.0 |
| **NautilusTrader** | High-performance event-driven engine (Rust core), shared backtest and live code | Simulates order book, order types, latency; many crypto exchange adapters | Complex, API still changing | 1.231.0 on PyPI (2026-08-02); repo push 2026-11-13 | LGPL-3.0 |
| **freqtrade** | Complete crypto bot: backtest, hyperopt, dry-run, live | Ready to use, large community, includes FreqAI | Fixed strategy template; hyperopt easily leads to overfitting | 2026.10 (2026-10-30), active | GPL-3.0 |
| **hummingbot** | Crypto market making and arbitrage | Many CEX/DEX connectors, built-in MM strategies | Heavy; MM profit depends on fees and infrastructure | 20260922 (PyPI 2026-10-07), active | Apache-2.0 |
| **QuantConnect LEAN** | Multi-asset engine (C#, Python API), local or cloud | Integrated data and brokers, detailed execution model | Heavy (Docker); quality data lives on the paid cloud | `lean` CLI 1.0.233 (2026-10-27); repo push 2026-11-13 | Apache-2.0 |
| **ccxt** | Unified API for 100+ crypto exchanges (REST + WebSocket) | De facto standard, continuously updated | Exchange differences still leak through; rate limits must be handled yourself | 4.5.92 (2026-11-04), active | MIT |

### 7.3 Performance analysis, portfolio, statistics, ML

| Library | Purpose | Pros | Cons | Maintenance | License |
|---|---|---|---|---|---|
| **quantstats** | Tearsheets and performance metrics | One line to an HTML report | Defaults to 252 periods/year: pass `periods` for crypto; cross-check formulas | 0.0.86 (2026-09-27), active | Apache-2.0 |
| **pyfolio / empyrical** (original Quantopian) | Tearsheets / metrics | Once the standard | **Abandoned**: pyfolio 0.9.2 (2019), empyrical 0.5.5 (2020) | Do not use | Apache-2.0 |
| **pyfolio-reloaded / empyrical-reloaded** | Maintained forks | Compatible with new pandas/numpy | Few new features | 0.10.2 / 0.7.2 (both 2026-11-02), active | Apache-2.0 |
| **Riskfolio-Lib** | Portfolio optimization: mean-risk, CVaR, risk parity, HRC/NCO | Very many risk measures | Depends on solvers (cvxpy), broad API | 7.4.1 (2026-11-04), active | BSD-3 |
| **PyPortfolioOpt** | Mean-variance, Black-Litterman, HRP | Easy to learn | Fewer models than Riskfolio; infrequent releases | 1.6.0 (2026-02-26); repo `PyPortfolio/PyPortfolioOpt` push 2026-07-07 | MIT |
| **statsmodels** | Regression, time series (ARIMA, VAR), tests (ADF, cointegration) | Full inferential statistics | Inconsistent API | 0.15.0 (2026-08-30), active | BSD-3 |
| **arch** | ARCH/GARCH, bootstrap, unit root | Standard for volatility models | Narrow scope | 9.0.0 (2026-11-11), active | NCSA |
| **scikit-learn** | Classic ML, pipelines, CV | The standard | No built-in purged CV, write your own splitter | 1.9.1 (2026-09-10), active | BSD-3 |
| **xgboost** | Gradient boosting | Strong on tabular data, GPU support | Many hyperparameters | 3.4.1 (2026-08-15), active | Apache-2.0 |
| **lightgbm** | Gradient boosting | Fast, low RAM | Easy to overfit on small data | 4.7.0 (2026-07-18), active | MIT (per the repo; PyPI has no license field) |
| **mlfinlab** (Hudson & Thames) | Implementations of *AFML* techniques | Comprehensive, documented | **Closed source, paid**; not on PyPI; the public repo is only for issues (last push 2023-10-02) | Price **[unverified]** | Proprietary |
| **mlfinpy** | Open partial replacement for mlfinlab | MIT | Last release 0.1.2 (2024-10-09): nearly stalled | Low | MIT |

For López de Prado techniques (purged K-fold, CPCV, triple-barrier, DSR), the safest option for licensing and maintenance is to **implement them yourself** from the book; each technique is only a few dozen lines. `skfolio` (1.12.10, 2026-11-12, BSD-3) ships `CombinatorialPurgedCV` for portfolio problems. **[unverified]** current API details.

### 7.4 Storage

| Technology | Purpose | Pros | Cons | Maintenance | License |
|---|---|---|---|---|---|
| **Parquet** (via pyarrow) | Compressed columnar file format | Small, fast, readable by every tool; directory partitioning | No in-place updates, appending means writing new files | pyarrow 26.0.1 (2026-11-03) | Apache-2.0 |
| **DuckDB** | In-process embedded OLAP (like SQLite for analytics) | SQL directly on Parquet, `ASOF JOIN`, no server | One writer process at a time; not a DB serving many clients | 2.0.0 (2026-10-21), active | MIT |
| **TimescaleDB** (company renamed to Tiger Data on 2025-06-17) | Time-series extension for PostgreSQL | Full SQL, continuous aggregates, compression, many concurrent writers | You must operate Postgres | Repo push 2026-11-13 | Two editions: Apache-2.0 and Community (Tiger Data License, prohibits offering as DBaaS) |
| **QuestDB** | Columnar time-series DB, high-speed ingest | Very fast tick ingest, SQL with `ASOF JOIN`, `SAMPLE BY` | Smaller ecosystem than Postgres | Repo push 2026-11-13 | Apache-2.0 |

Sources for section 7: <https://pypi.org/> (per-package JSON API), <https://github.com/polakowo/vectorbt/blob/master/LICENSE.md>, <https://vectorbt.pro/>, <https://github.com/hudson-and-thames/mlfinlab>, <https://www.tigerdata.com/legal/licenses>, <https://www.tigerdata.com/docs/get-started/choose-your-path/timescaledb-editions>, <https://github.com/xgboosted/pandas-ta-classic>.

---

## 8. Data sources

Prices and limits change often. The "Limits" column follows the official page when it could be opened; figures from secondary sources are noted.

### 8.1 Stocks (US and international)

| Source | Data types | Free / paid | Limits | Access |
|---|---|---|---|---|
| **yfinance** (Yahoo Finance, unofficial) | OHLCV, dividends, splits, some financial statements | Free | No SLA, often breaks when Yahoo changes its pages. The README says Yahoo data is for **personal use** only; read Yahoo's terms | `pip install yfinance` (1.8.0, 2026-11-03) |
| **Alpha Vantage** | OHLCV, fundamentals, forex, crypto, indicators, economics | Free + paid | Free: **25 requests/day** (secondary source: plus 5/minute). Paid from 49.99 USD/month for 75 requests/minute, no daily limit | REST + API key. <https://www.alphavantage.co/premium/> |
| **Polygon.io → Massive** (renamed 2025-10-30, old keys and endpoints still work) | Tick trades/quotes, aggregates, options, forex, crypto | Free + paid | Free: 5 calls/minute, end-of-day data, about 2 years of history. Stocks Starter about 29 USD/month. **[unverified]** on the official page (figures from secondary sources, some conflicting) | REST, WebSocket, flat files. <https://massive.com/pricing> |
| **Tiingo** | EOD, IEX intraday, fundamentals, news, crypto, forex | Free + paid | Free: 50 requests/hour, 1 000/day, 1 GB bandwidth/month. Cap of 500 tickers/month **[unverified]**. Internal use only | REST + token. <https://api.tiingo.com/documentation> |
| **Finnhub** | Quotes, news, basic fundamentals, filings, WebSocket | Free + paid | Free: 60 calls/minute. Secondary source: stock candles are premium, WebSocket 50 symbols, personal use only | REST, WebSocket; `finnhub-python` 2.4.30. <https://finnhub.io/pricing> |
| **Financial Modeling Prep** | Financial statements, ratios, DCF, EOD prices | Free + paid | Free: 250 requests/day, EOD data. Starter about 22 USD/month (billed annually) | REST + API key. <https://site.financialmodelingprep.com/pricing-plans> |
| **SEC EDGAR** | Original filings (10-K, 10-Q, 8-K), XBRL company facts | Free, no key needed | Max **10 requests/second**; must declare a `User-Agent` | REST JSON at `data.sec.gov`, nightly bulk files. <https://www.sec.gov/os/accessing-edgar-data> |
| **Stooq** | EOD for many markets, indices, forex | Free | Since early 2026, scripted CSV access requires an API key obtained via CAPTCHA; the Stooq reader in `pandas-datareader` is broken. **[unverified]** by an official source | Manually download bulk packages at <https://stooq.com/db/h/>. See <https://github.com/pydata/pandas-datareader/issues/1012> |

Note on the SEC `User-Agent`: the SEC requires contact information. This is personal data sent externally, so consider using a dedicated email address for this purpose.

### 8.2 Vietnamese stocks

| Source | Data types | Free / paid | Limits | Access |
|---|---|---|---|---|
| **vnstock** (generation 6) | A connection and normalization layer for Vietnamese stock data; does **not** provide data itself | Community edition (personal, learning, research) + Bronze/Silver/Golden/Diamond plans | No longer on PyPI; prebuilt packages released via a private repository. Versions before generation 6 **stopped working on 2026-11-10**. Users pick the source and use keys issued by that source. Plan prices and the list of supported sources **[unverified]** | <https://vnstocks.com/onboard>, license: <https://vnstocks.com/onboard/giay-phep-su-dung>, historical repo: <https://github.com/thinh-vu/vnstock> |
| **SSI FastConnect Data** | Realtime and EOD for equities and derivatives | Requires an SSI trading account; fees **[unverified]** | Register at a branch, through a broker or by post; 1-year service term | REST + streaming. <https://guide.ssi.com.vn/ssi-products/tieng-viet/fastconnect-data> |
| **TCBS**, **DNSE** and other brokerages | Prices, company data | **[unverified]** | No current official information found on a public data API | Check the provider's site directly |

Important: the "public" endpoints of brokerage websites are not licensed APIs. The vnstock generation 6 docs also state clearly that they do not encourage scraping websites' public interfaces. The sustainable option is the official API of the brokerage where you hold an account.

### 8.3 Macro, rates, gold, forex

| Source | Data types | Free / paid | Limits | Access |
|---|---|---|---|---|
| **FRED** (St. Louis Fed) | 800 000+ US and international economic series | Free, API key required | About 120 requests/minute (secondary source, **[unverified]** on the official page) | REST; `fredapi` 0.5.2 (2024-05). <https://fred.stlouisfed.org/docs/api/fred/> |
| **ALFRED** | *Vintage* versions of FRED series (data as known at each point in time) | Free | Same as FRED | Parameters `realtime_start`/`realtime_end` |
| **Economic calendar** | Release times for CPI, NFP, FOMC… | Depends on source | Finnhub and FMP have economic calendar endpoints (which plans include them **[unverified]**). FRED has a "releases" API for series release dates | REST |
| **Gold / forex** | XAU/USD, currency pairs | Depends on source | Alpha Vantage, Tiingo, Massive, Finnhub all have forex. Quality spot gold is usually paid. Futures (`GC=F`) via yfinance can serve as a proxy | REST |

Commonly used FRED series (IDs from background knowledge, **[unverified]** on the day because the FRED site blocks automated queries):

| Series ID | Content |
|---|---|
| `FEDFUNDS` / `DFF` | Effective federal funds rate (monthly / daily) |
| `SOFR` | Secured Overnight Financing Rate |
| `DGS2`, `DGS10`, `DTB3` | 2-year, 10-year Treasury yields; 3-month T-bill |
| `T10Y2Y` | 10-year − 2-year spread |
| `DTWEXBGS` | Trade-weighted USD index (broad) |
| `CPIAUCSL` | US CPI |
| `VIXCLS` | VIX close |

On **DXY**: the DXY index is an ICE product and FRED does **not** publish it. `DTWEXBGS` is a USD index with a different basket, not a 1:1 substitute. For true DXY you need a source with ICE data (e.g. `DX` futures via a paid vendor, or `DX-Y.NYB` on Yahoo with yfinance's limitations).

On macro data in backtests: figures are **revised** after release. Using the current vintage is look-ahead; use ALFRED and align to release dates and times.

### 8.4 Crypto

OHLCV, trades, order book and funding data come directly from exchanges (Binance, Bybit, OKX…) via `ccxt` or the exchange API, free with their own rate limits. Some exchanges have downloadable historical data archives (e.g. <https://data.binance.vision/>, **[unverified]** on the day). The table below lists **non-exchange** sources.

| Source | Data types | Free / paid | Limits | Access |
|---|---|---|---|---|
| **CoinGecko** | Prices, market cap, aggregated volume, metadata, DEX (GeckoTerminal) | Free demo + paid | Demo: 10 000 calls/month, 100 calls/minute (per the official pricing page). Basic about 35 USD/month (secondary source) | REST + key. <https://www.coingecko.com/en/api/pricing> |
| **CoinMarketCap** | Prices, rankings, metadata | Free Basic + paid | Basic: 15 000 credits/month, 50 requests/minute, personal use. History on the free plan is very limited (sources conflict, **[unverified]**) | REST + key. <https://coinmarketcap.com/api/pricing> |
| **CoinGlass** | Derivatives: open interest, funding, liquidations, long/short ratio | Paid | Hobbyist 29 USD/month, 30 requests/minute, personal use; Startup 79 USD; Standard 299 USD | REST + key. <https://www.coinglass.com/pricing> |
| **Glassnode** | On-chain (BTC, ETH and other chains) | Paid for API | The API is an add-on to the Professional plan; add-on price not published (**[unverified]**) | REST. <https://studio.glassnode.com/pricing> |
| **CryptoQuant** | On-chain, exchange flows, miners | Free + paid | Every plan can create API keys; on-chain requires Professional or higher. Prices from secondary sources: about 29 / 99 / 799 USD/month (**[unverified]**) | REST. <https://cryptoquant.com/pricing> |
| **DefiLlama** | TVL, DEX volume, fees, stablecoins, yields | Free public API + Pro | Free needs no authentication (rate limit **[unverified]**). Pro: 1 000 requests/minute, 1 million calls/month; price 300 USD/month per most sources, some state otherwise (**[unverified]**) | REST. <https://api-docs.defillama.com/>, <https://defillama.com/pro-api> |
| **Kaiko** | Institutional-grade tick, order book, reference rates | Paid, sold via sales | No public pricing; secondary sources cite from about 1 000 USD/month (**[unverified]**). Beyond the reach of a personal project | REST, stream, files |
| **Tardis.dev** | Historical tick: trades, incremental L2, snapshots, funding, OI, liquidations; 50+ exchanges | Paid, with a trial | Free trial per the docs: days 1–10 of the previous month, 20 GB. Plan prices **[unverified]** (secondary sources conflict) | HTTP API, downloadable CSV, Python/Node clients. <https://docs.tardis.dev/faq/general> |

### 8.5 TradingView

TradingView **has no official public market data API**. What exists:

| Option | Use | Notes |
|---|---|---|
| **Webhook alerts** from Pine Script | Push signals from the chart to your own server | The official way to automate; requires a paid plan supporting webhooks (**[unverified]** which plan) |
| **Export chart data** (CSV) | Export the displayed data, manually | A paid-plan feature (**[unverified]**) |
| **Charting Library / Lightweight Charts** | Embed charts in an app, **feeding your own data** | Lightweight Charts is open source (Apache-2.0); the Charting Library requires a license application |
| **Broker Integration REST API** | For brokers connecting into TradingView | Not a data API |
| Unofficial libraries (`tvdatafeed`, `tradingview-ta`, scrapers) | Fetch data via internal endpoints | Likely **violates the terms of use** (restrictions on automated access and on using data beyond display to the viewer); risk of account bans; can break at any time |

Technical recommendation: use TradingView to **view and draw**; get backtest data from exchanges or vendors with clear terms. Read the current terms at <https://www.tradingview.com/policies/> (**[unverified]** verbatim in this session).

### 8.6 General notes on data terms

- "Free" usually comes with "personal use only, no redistribution". If the project later ships a public product, re-check each source's license.
- Do not commit API keys; keep them in environment variables or a `.gitignore`d `.env` file.
- Store the **raw response** with its download time for reproducibility and to detect when a vendor revises data.

---

## 9. Fundamental analysis for the stock analyzer

### 9.1 The three financial statements

| Statement | Question answered | Main items |
|---|---|---|
| **Income statement** | How much was earned this period | Revenue → gross profit → operating income (EBIT) → net income, EPS |
| **Balance sheet** | What is owned and owed at a point in time | Assets = Liabilities + Equity; cash, borrowings, working capital |
| **Cash flow statement** | Where the real cash went | CFO, CFI (including capex), CFF; `FCF = CFO − capex` |

Data notes: use TTM (trailing twelve months) figures for flow metrics; store the **filing date**, not just the period end date; distinguish *as reported* from *restated* figures.

### 9.2 Valuation metrics

| Metric | Formula | Use when | Traps |
|---|---|---|---|
| **P/E** | `Price / EPS` | Companies with stable profits | Meaningless when EPS is negative or distorted by one-offs; cyclicality |
| **EV/EBITDA** | `(Market cap + Debt − Cash) / EBITDA` | Comparing companies with different capital structures | EBITDA ignores capex; not for banks |
| **P/B** | `Price / Book value per share` | Banks, insurers, asset-heavy companies | Less meaningful for companies with many intangibles or heavy buybacks |
| **PEG** | `(P/E) / EPS growth (%)` | Growth companies | Very sensitive to growth forecasts |
| **FCF yield** | `FCF / Market cap` (or `/ EV`) | Assessing cash generation | FCF fluctuates with capex and working capital cycles |
| **EV/Sales**, **Dividend yield** | — | Unprofitable companies; income stocks | — |

### 9.3 Quality metrics

| Group | Metric | Formula |
|---|---|---|
| Profitability | **ROE** | `Net income / Average equity`. DuPont decomposition: `net margin × asset turnover × leverage` |
| | **ROIC** | `NOPAT / Invested capital`, `NOPAT = EBIT × (1 − tax rate)`, invested capital ≈ `Debt + Equity − Excess cash` |
| | **ROA** | `Net income / Total assets` |
| Margins | Gross, operating, net margin | Divided by revenue; look at multi-year trends |
| Debt | **Debt/Equity**, **Net debt/EBITDA** | Financial leverage |
| | **Interest coverage** | `EBIT / Interest expense` |
| | **Current ratio** | `Current assets / Current liabilities` |
| Earnings quality | **Accruals** | `(Net income − CFO) / Total assets`; high is a warning sign |
| | **Cash conversion** | `FCF / Net income` |
| Composite scores | Piotroski F-score (0–9), Altman Z-score | Screening financial health and bankruptcy risk |

High ROE from leverage differs from high ROE from margins; always look at ROIC as well and compare with the cost of capital.

### 9.4 DCF summary

1. Project FCFF for `N` years (usually 5–10): `FCFF = EBIT × (1 − t) + D&A − Capex − ΔNWC`.
2. Compute the discount rate: `WACC = E/V · Re + D/V · Rd · (1 − t)`, with `Re = r_f + β · ERP` (CAPM).
3. Terminal value: `TV = FCFF_{N+1} / (WACC − g)` (Gordon), `g` not exceeding the economy's long-run nominal growth.
4. `EV = Σ FCFF_t / (1 + WACC)^t + TV / (1 + WACC)^N`.
5. `Equity value = EV − Net debt − minority interests`; divide by diluted share count.

Practical reminders:

- Terminal value is often 60–80% of the value, so the result is very sensitive to `WACC` and `g`. Always present a **sensitivity table** instead of a single number.
- *Reverse DCF* (asking what growth the current price implies) is often more useful than a point estimate.
- DCF is a tool for organizing assumptions, not a machine that outputs the "right price".

### 9.5 Factors and screening

| Factor | Common definition | Intuition |
|---|---|---|
| **Value** | High B/M, E/P, FCF/P, EBIT/EV | Cheap relative to fundamentals |
| **Quality** | High ROE/ROIC, gross profitability, low accruals, low debt, stable earnings | Good businesses |
| **Momentum** | 12-month return, skipping the most recent month (12−1) | Winners keep winning |
| **Size** | Small market cap | Small-cap premium (weak and contested after publication) |
| **Low volatility** | Low volatility or beta | Low-risk stocks deliver higher risk-adjusted returns |

Screening and factor-building process:

1. Define the universe **point-in-time**, with a liquidity filter (minimum traded value) and including delisted tickers.
2. Compute metrics from point-in-time data (lagged to the release date).
3. Handle outliers (winsorize 1–99%), normalize via z-score or rank, optionally neutralize by sector.
4. Combine into a composite score; rank; split into quantile buckets.
5. Evaluate with returns by quantile, long-short spread, **IC** (rank correlation between score and next-period return), turnover and costs.
6. Rebalance monthly or quarterly; compare with an appropriate benchmark.

An end-user screener should show both raw data and data dates so viewers can judge for themselves. Screening results are a list for further research, not recommendations.

---

## 10. Proposed storage architecture and pipeline

### 10.1 Choice: Parquet + DuckDB, polars for processing

Reasons for a personal project:

- **No server to operate**: DuckDB runs in-process, data is files. Backup is copying a directory.
- **The workload is analytical**: scanning columns over time ranges across many tickers. Compressed columnar storage with predicate pushdown fits better than a row DB.
- **Parquet is a neutral format**: pandas, polars, DuckDB, Spark all read it, no lock-in to one tool.
- **Sufficient scale**: 1-minute OHLCV for a few hundred tickers over many years is only a few GB to a few tens of GB.
- DuckDB's **`ASOF JOIN`** neatly solves point-in-time joins (fundamentals, macro onto prices).
- **Reproducibility**: immutable files + a manifest let you know exactly which data a backtest ran on.

When you need something else:

| Situation | Choose |
|---|---|
| Many concurrent writer processes, need a dashboard or a continuously queried service | PostgreSQL + TimescaleDB |
| High-speed realtime tick/L2 collection from many exchanges | QuestDB, or write Parquet directly in batches |
| Live bot state (orders, positions, reconciliation) | SQLite or PostgreSQL (OLTP), **separate from** the research data store |

### 10.2 Directory layout

```
data/
  raw/                      # immutable: original responses, never edited
    binance/ohlcv/1m/symbol=BTCUSDT/date=2026-11-12.parquet
    edgar/companyfacts/cik=0000320193/fetched=2026-11-12.json
  curated/                  # cleaned, stable schema
    ohlcv/exchange=binance/timeframe=1h/symbol=BTCUSDT/year=2026/part-0.parquet
    funding/exchange=binance/symbol=BTCUSDT/year=2026/part-0.parquet
    fundamentals/ticker=AAPL/part-0.parquet       # has filed_at, period_end columns
    macro/series=DGS10/part-0.parquet             # has realtime_start column
  features/                 # computed, versioned features
    v3/…
  meta/
    manifest.parquet        # source, time range, row count, checksum, download time
    instruments.parquet     # ticker, exchange, tick size, listing/delisting dates
research.duckdb             # only VIEWs pointing at Parquet + backtest result tables
```

Schema rules:

- Timestamps in **UTC**, `TIMESTAMP` type with explicit resolution; the convention is that `ts` is the bar's **open** time, and this convention is documented.
- Every table has `ingested_at`; late-published data also has `available_at` (or `filed_at`, `realtime_start`).
- Stock prices: store **raw** prices and adjustment factors separately; compute adjusted prices at query time, since factors change over time.
- Moderate partitioning (by symbol and year); avoid tens of thousands of small files.

### 10.3 Pipeline

| Stage | Work | Suggested tools |
|---|---|---|
| **Ingest** | Incremental download by watermark, idempotent, with retries and respecting rate limits; write raw as-is | `ccxt`, `httpx`, each source's client |
| **Validate** | Check duplicates, missing bars, `high ≥ max(open, close)`, prices ≤ 0, abnormal jumps, time zone drift | polars + hand-written checks, or `pandera` |
| **Curate** | Normalize schema, deduplicate, write partitioned Parquet, update the manifest | polars, pyarrow |
| **Feature** | Compute features only from data with `available_at ≤ t`; store with version and commit hash | polars, DuckDB SQL |
| **Research / backtest** | Read via DuckDB views; write results, parameters, commit hash into a `runs` table | vectorbt or hand-written → NautilusTrader when realism is needed |
| **Scheduling** | Run periodically, alert when data is late | `cron`/`launchd` is enough; use Prefect/Dagster only when the pipeline is truly complex |

Example point-in-time join with DuckDB:

```sql
SELECT p.ts, p.ticker, p.close, f.eps_ttm
FROM read_parquet('data/curated/ohlcv/**/*.parquet', hive_partitioning = true) AS p
ASOF LEFT JOIN read_parquet('data/curated/fundamentals/**/*.parquet') AS f
  ON p.ticker = f.ticker AND p.ts >= f.filed_at;
```

Tests to have from the start:

- Anti-look-ahead test: compute features on data truncated at `t` and on the full data; values before `t` must be identical.
- Backtest engine test on a random price series: expected profit after fees must be negative by exactly the cost.
- Cross-check hand-written metrics against `quantstats`/`empyrical-reloaded` on the same return series.

---

## 11. Foundational books and papers

URLs written from memory, **links not individually checked** in this session.

### Books

| Author, title | Content | Level |
|---|---|---|
| Ernest Chan — *Quantitative Trading* (2nd ed.), *Algorithmic Trading: Winning Strategies and Their Rationale* | Practical introduction: mean reversion, momentum, cointegration, Kelly | Beginner |
| Marcos López de Prado — *Advances in Financial Machine Learning* (2018) | Triple-barrier, meta-labeling, purged CV, CPCV, fractional differentiation, DSR | Intermediate, core |
| Marcos López de Prado — *Machine Learning for Asset Managers* (2020) | Denoising, clustering, feature importance, false discovery | Intermediate |
| Robert Carver — *Systematic Trading*, *Advanced Futures Trading Strategies* | System design, volatility targeting, signal combination | Beginner to intermediate |
| Grinold & Kahn — *Active Portfolio Management* | Information ratio, fundamental law, portfolio construction | Advanced |
| Antti Ilmanen — *Expected Returns* | Overview of risk premia by asset class and factor | Intermediate |
| Lasse Pedersen — *Efficiently Inefficient* | Hedge fund strategies and their economic rationale | Intermediate |
| Larry Harris — *Trading and Exchanges* | Classic microstructure | Foundational |
| Bouchaud, Bonart, Donier, Gould — *Trades, Quotes and Prices* | Order books, quantitative market impact | Advanced |
| Stefan Jansen — *Machine Learning for Algorithmic Trading* (2nd ed.) | End-to-end Python practice | Intermediate |
| Ruey Tsay — *Analysis of Financial Time Series* | ARIMA, GARCH, multivariate models | Foundational |
| Aswath Damodaran — *Investment Valuation* (and free material on his personal site) | DCF and valuation | Foundational for the stock analyzer |
| Benjamin Graham — *The Intelligent Investor*; Joel Greenblatt — *The Little Book That Beats the Market* | Value mindset, a simple factor example | Beginner |

### Papers

| Paper | Topic | Link |
|---|---|---|
| Kelly (1956), *A New Interpretation of Information Rate* | Kelly criterion | — |
| Sharpe (1966, 1994), *The Sharpe Ratio* | Definition of Sharpe | — |
| Lo (2002), *The Statistics of Sharpe Ratios* | Sharpe error and annualization | — |
| Fama & French (1993), *Common Risk Factors in the Returns on Stocks and Bonds*; (2015) *A Five-Factor Asset Pricing Model* | Factor models | — |
| Jegadeesh & Titman (1993), *Returns to Buying Winners and Selling Losers* | Cross-sectional momentum | — |
| Carhart (1997), *On Persistence in Mutual Fund Performance* | Momentum factor | — |
| Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum* | Trend following | — |
| Asness, Moskowitz & Pedersen (2013), *Value and Momentum Everywhere* | Multi-asset factors | — |
| Novy-Marx (2013), *The Other Side of Value: The Gross Profitability Premium* | Quality | — |
| Frazzini & Pedersen (2014), *Betting Against Beta* | Low-beta | — |
| Piotroski (2000), *Value Investing: The Use of Historical Financial Statement Information* | F-score | — |
| Engle & Granger (1987), *Co-integration and Error Correction* | Cointegration | — |
| Gatev, Goetzmann & Rouwenhorst (2006), *Pairs Trading* | Pairs trading | — |
| Avellaneda & Lee (2010), *Statistical Arbitrage in the U.S. Equities Market* | Stat-arb | — |
| Avellaneda & Stoikov (2008), *High-frequency Trading in a Limit Order Book* | Market making | — |
| Almgren & Chriss (2000), *Optimal Execution of Portfolio Transactions* | Execution, market impact | — |
| Kyle (1985), *Continuous Auctions and Insider Trading* | Microstructure | — |
| Bailey & López de Prado (2014), *The Deflated Sharpe Ratio* | DSR | <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551> |
| Bailey, Borwein, López de Prado & Zhu (2017), *The Probability of Backtest Overfitting* | PBO, CSCV | <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253> |
| Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns* | Multiple testing in factors | <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2249314> |
| White (2000), *A Reality Check for Data Snooping* | Data snooping | — |
| McLean & Pontiff (2016), *Does Academic Research Destroy Stock Return Predictability?* | Premia shrink after publication | — |
| Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning* | ML for return prediction | — |
| Liu & Tsyvinski (2021), *Risks and Returns of Cryptocurrency* | Factors in crypto | — |

Suggested reading order: Chan → Carver → López de Prado (*AFML*) → Harris; Damodaran in parallel for the stock side. Three papers to read early: DSR, PBO, Harvey–Liu–Zhu.

---

## 12. List of unverified items

| # | Item | Why | Where to check |
|---|---|---|---|
| 1 | Status and license of the original `pandas-ta` | GitHub repo 404, docs domain does not resolve | <https://pypi.org/project/pandas-ta/> |
| 2 | Massive (Polygon) prices and free plan | Only secondary sources, some conflicting | <https://massive.com/pricing> |
| 3 | Tiingo free cap of 500 tickers/month | Only from a competitor's comparison page | <https://www.tiingo.com/about/pricing> |
| 4 | Finnhub free plan details (candles, WebSocket) | Secondary sources | <https://finnhub.io/pricing> |
| 5 | Stooq's API key/CAPTCHA mechanism | No official documentation | <https://stooq.com/> |
| 6 | vnstock plan prices, list of supported sources in generation 6 | The license page does not state them | <https://vnstocks.com/> |
| 7 | SSI FastConnect Data fees; TCBS, DNSE data APIs | No official information found | Each brokerage's site |
| 8 | FRED rate limit and current existence of each series ID | FRED site blocks automated queries | <https://fred.stlouisfed.org/docs/api/fred/> |
| 9 | History on CoinMarketCap's free plan | Sources conflict | <https://coinmarketcap.com/api/pricing> |
| 10 | Glassnode API add-on price; CryptoQuant plan prices | Not published or only secondary sources | Official pricing pages |
| 11 | DefiLlama Pro price (300 USD or otherwise), free rate limit | Sources conflict | <https://defillama.com/subscription> |
| 12 | Kaiko prices, Tardis.dev plan prices | Sold via sales / secondary sources conflict | Contact the vendor |
| 13 | Verbatim TradingView terms; which plans have webhooks and export | Policy page not opened | <https://www.tradingview.com/policies/> |
| 14 | mlfinlab price | Not published | <https://hudsonthames.org/mlfinlab/> |
| 15 | Current `skfolio` API for CPCV; the `data.binance.vision` archive | Not checked in the session | Each project's docs |
| 16 | All paper URLs in section 11 | Written from memory | SSRN / journal sites |
| 17 | Which Finnhub/FMP plans include the economic calendar | Not checked | Pricing pages |
