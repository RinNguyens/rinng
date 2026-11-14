# 01 — QuantHarness: paper and repo summary, with a critical review

> Sources read:
> - **Paper**: "QuantHarness: Price-Driven Multi-Agent LLMs for High-Frequency Trading", arXiv 2509.09995**v4** (date stamp on the PDF: 27 Jul 2026), 32 pages, read in full including appendices A–H. Authors: Fei Xiong, Xiang Zhang (equal contribution), Aosong Feng, Siqi Sun, Chenyu You (Stony Brook, CMU, UBC, Yale, Fudan) — p.1.
> - **Repo**: https://github.com/Y-Research-SBU/QuantHarness, read at commit `2e64c7b` (2026-08-18, "Merge pull request #24 … upgrade-minimax-m3").
> - **Project page**: https://Y-Research-SBU.github.io/QuantHarness/ (text only; the tables on the page are images).
>
> Conventions: `[p.N]` = page N of the PDF; `[code: file]` = read directly from the repo; **unverified** = no evidence found in either the paper or the repo.
> This document is not investment advice.

---

## 0. TL;DR

1. The architectural idea (separate indicator / pattern / trend / decision, OHLC only, real computation tools instead of letting the LLM invent numbers) is sound and easy to reuse.
2. **The empirical evidence is weak.** In Table 1 (the only table with Sharpe / cumulative return), QuantHarness **does not top cumulative return on any asset (0/8)** and **does not top Sharpe on any asset (0/8)**. Linear Regression has higher cumulative return on **7/7** assets that have LR figures. Some bolded cells in Table 1 are not the best value in their column.
3. In Table 2 (4h), the system tops accuracy on 8/8 assets, but the margins are small (0.3 percentage points in one case), n = 100 segments/asset, no confidence intervals, no repeated seeds.
4. The paper does **not** account for trading fees, slippage, or spread; does **not** name the LLM used in the experiments; does **not** release evaluation/baseline code.
5. The repo is an analysis demo (Flask + LangGraph): **no** RiskAgent, **no** 0.0005 stop-loss, **no** backtest, **no** slope threshold τ from Algorithm 1.

---

## 1. Architecture

The paper describes "four specialized agents" Indicator, Pattern, Trend, Risk [p.1, p.3], plus a DecisionAgent at the final layer [p.5–6]. The system is built on LangGraph [p.3], uses only OHLC price data, no news/sentiment [p.3].

The actual flow in code is **sequential**: no debate, no parallel branches [code: `graph_setup.py`]:

```
START → Indicator Agent → Pattern Agent → Trend Agent → Decision Maker → END
```

The shared state is `IndicatorAgentState` (TypedDict) with `kline_data`, `time_frame`, `stock_name`, `indicator_report`, `pattern_report`, `trend_report`, `final_trade_decision`, base64 images… [code: `agent_state.py`].

### 1.1 IndicatorAgent

| Item | Paper | Code |
|---|---|---|
| Input | Latest OHLC + `time_frame` [p.18] | `state["kline_data"]` (dict of lists), dumped as JSON into the system prompt [code: `indicator_agent.py`] |
| Tools | `compute_rsi`, `compute_macd`, `compute_roc`, `compute_stoch`, `compute_willr` [p.18] | Same as paper, computed with TA-Lib [code: `graph_util.py`] |
| Output | Text report summarizing signals (e.g. "bullish but extended") [p.31] | `indicator_report` (free text) |
| LLM | not stated | `graph_llm` (default `gpt-4o`) [code: `graph_setup.py`, `default_config.py`] |

Indicator parameters:

| Indicator | Parameters | Source |
|---|---|---|
| MACD | fast EMA 12, slow EMA 26, signal 9; α = 2/(N+1) | Paper Appendix G [p.32] and code |
| RSI | period 14 | **Code only** (paper gives no period) |
| ROC | period 10 | Code only |
| Stochastic | `fastk_period=14, slowk_period=3, slowd_period=3` | Code only |
| Williams %R | period 14 | Code only |

Notable code details [code: `graph_util.py`]:
- Periods are tool defaults; the LLM may pass other periods when calling a tool (except Stochastic, which is hard-coded).
- Each tool returns only the **last 28 values**, rounded to 2 decimals (except `macd`, which returns the full series).
- NaN values in the warm-up period are replaced with **0** (`fillna(0)`). With the web demo's 45-candle window, the MACD signal needs about 33 warm-up candles, so most of the MACD series the LLM sees is fake zeros. This is a design bug to fix if reused.
- Tool loop is capped at 5 rounds [code: `indicator_agent.py`].

Prompt (Appendix C.1 [p.18], summarized): "You are a high-frequency trading (HFT) analyst assistant working under strict latency constraints…", lists 5 tools, says the OHLC data comes from the `{time_frame}` timeframe, inserts `{kline_data}`, ends with "Call necessary tools, and analyze the results." The prompt in code is nearly identical.

Interpretation thresholds in Figure 1 [p.2]: RSI > 70 bearish, RSI < 30 bullish, 30–70 neutral; Williams %R > −20 bearish, < −80 bullish; ROC > 0 bullish, < 0 bearish. These thresholds are illustrative only; they are not in the prompt or code — the LLM interprets on its own.

### 1.2 PatternAgent

| Item | Paper | Code |
|---|---|---|
| Input | OHLC → rendered as a candlestick image [p.4, p.19] | `kline_data`, or a prebuilt image in state |
| Tool | `generate_kline_image` [p.19] | mplfinance, **last 40 candles** (`df.tail(40)`), figsize 12×6, dpi 600 [code: `graph_util.py`] |
| Output | Pattern name + explanation by structure / trend / symmetry [p.7, p.19] | `pattern_report` (free text) |
| LLM | "multimodal" | Tool-calling step: `agent_llm` (`gpt-4o-mini`); image-reading step: `graph_llm` (`gpt-4o`) |

Library of 16 patterns in the prompt (Appendix C.2 [p.19], matches code `pattern_agent.py`):

1. Inverse Head and Shoulders — 2. Double Bottom — 3. Rounded Bottom — 4. Hidden Base — 5. Falling Wedge — 6. Rising Wedge — 7. Ascending Triangle — 8. Descending Triangle — 9. Bullish Flag — 10. Bearish Flag — 11. Rectangle — 12. Island Reversal — 13. V-shaped Reversal — 14. Rounded Top / Bottom — 15. Expanding Triangle — 16. Symmetrical Triangle.

Each pattern has a one-sentence description. Head and Shoulders (top), Double Top, Triple Top/Bottom are not in the list, even though Figure 1 [p.2] draws a "Double Top". Pattern recognition is done entirely by the LLM looking at the image; no geometric algorithm double-checks it. Appendix F [p.29–30] describes "extracts swing pivots… least-squares fit through those highs" but the PatternAgent code has no such step — **unverified** which code that description corresponds to.

### 1.3 TrendAgent

| Item | Paper | Code |
|---|---|---|
| Input | OHLC → candlestick image with trend channel [p.5, p.20] | `kline_data` or prebuilt image |
| Tool | `generate_trend_image` [p.20] | **Last 50 candles** (`data.iloc[-50:]`) [code: `graph_util.py`] |
| Output | Upward / downward / sideways prediction + "prediction, reasoning, signals" [p.20] | `trend_report` (free text) |

Prompt (Appendix C.3 [p.20], summarized): must call `generate_trend_image` first; only predict after the image exists; the image-reading prompt says the **blue line = support**, **red = resistance**, "both derived from recent closing prices".

Paper vs code discrepancies:
- The paper says resistance/support lines are fit through **highs/lows** [p.5, Algorithm 1 p.3]. The code computes both sets of lines (on close, and on high/low), but the high/low set is drawn **white on a white background**, so it is invisible; the LLM sees only the **close**-based lines [code: `graph_util.py`, `color_style.py`].
- The code's trend line is not pure OLS: it starts from OLS, finds the farthest pivot, then optimizes the slope so the line passes through the pivot without crossing price (function `optimize_slope`, taken from the `neurotrader888/TechnicalAnalysisAutomation` repo per the README).
- The code **does not have** the τ threshold classification step (section 2). Uptrend/downtrend/sideways classification is decided by the LLM looking at the image.

### 1.4 RiskAgent

According to the paper [p.5, Figure 2 p.4]:
- Does not generate signals; aggregates other agents' outputs into a risk–reward frame.
- Fixed stop-loss **ρ = 0.0005** (0.05%).
- Take-profit **R = r · ρ**, with **r ∈ [1.2, 1.8]** predicted by the LLM.
- Figure 2 shows a 6-axis radar: Momentum Strength, Trend Certainty, Pattern Reliability, Breakout Likelihood, S/R Strength, Volatility Risk.

In the repo: **no RiskAgent file/node at all**; no 0.0005 constant; no radar chart. The only remnant is the request for `risk_reward_ratio` 1.2–1.8 in the DecisionAgent prompt. The paper has no separate RiskAgent prompt in Appendix C. The project page also lists only Indicator / Pattern / Trend / Decision.

### 1.5 DecisionAgent

| Item | Content |
|---|---|
| Input | `indicator_report`, `pattern_report`, `trend_report`, `time_frame`, `stock_name` [p.21; code: `decision_agent.py`] |
| Tools | None |
| Output | JSON: `forecast_horizon`, `decision` (LONG/SHORT), `justification`, `risk_reward_ratio` (1.2–1.8) [p.21] |
| LLM | `graph_llm` (default `gpt-4o`), a single call |

Prompt rules (Appendix C.4 [p.21], summarized):
- "Issue an immediate execution order: LONG or SHORT. (HOLD is prohibited.)"
- Horizon: predict the **next 3 candles** (e.g. 15-min → 45 minutes; 4-hour → 12 hours).
- Indicators: prioritize strong signals (MACD cross, RSI divergence, extreme zones), down-weight neutral signals.
- Patterns: act only when the pattern is clearly formed and breakout is confirmed.
- Trend: rising support = buying pressure; falling resistance = selling pressure; do not infer breakout direction from geometry alone.
- When reports conflict: pick the side with stronger and more recent confirmation; when sideways: follow the dominant trendline slope.
- Propose risk-reward 1.2–1.8.

Notes:
- The prompt printed in the paper still contains chatbot replies: "Here is a LaTeX-style refactored version of your original decision guideline…" and "Let me know if you want this formatted directly in LaTeX code or exported to PDF." [p.21].
- The prompt in code contradicts itself on horizon: the body gives the example "N = 1 → Predict the next 4 hours", the output format says "Predicting next 3 candlestick" [code: `decision_agent.py`]. Figure 10 [p.25] also shows "Predicting next 1 candlestick (4 hours)".
- The code does not parse JSON in the graph; `final_trade_decision` is a raw string, `risk_reward_ratio` is a string.
- Because HOLD is banned, the system is always in the market. The prompt says "Only act on confirmed signals" while also forbidding inaction — the two requirements cannot both be satisfied.

### 1.6 Number of input candles — sources disagree

| Source | Candles |
|---|---|
| Benchmark, paper [p.6, p.28] | 100-candle segments, last 3 hidden → 97 input candles |
| Figure 9, paper [p.24] | "the most recent 40–50 price bars" |
| Repo README | "the most recent 30 candlesticks" |
| Web code [`web_interface.py`, line 317] | `df.tail(45)` |
| Pattern / trend tools [code] | last 40 / 50 candles |

---

## 2. Algorithm 1 — Slope-aware trend detection [p.3]

```
Input: P_{0:T-1} (candle series), N (window length), τ (slope threshold)
for t = N-1 to T-1:
    Fit OLS on highs / lows → m_r, m_s
    κ_t ← (m_r + m_s) / 2
    if   κ_t >  τ : Trend ← Uptrend
    elif κ_t < -τ : Trend ← Downtrend
    else          : Trend ← Sideways
Render chart K_t(P_t, κ_t, Trend)
```

Accompanying formulas [p.5]:
- Resistance: `R_t(x) = m_r·x + b_r` (through recent local highs).
- Support: `S_t(x) = m_s·x + b_s` (through recent local lows).
- Average slope: `κ_t = (m_r + m_s) / 2`.

What the paper does not say:
- **The values of N and τ are not given anywhere** in the 32 pages. → **unverified**.
- Whether τ is normalized by price (a slope in price units/candle is not comparable between BTC ~80,000 and VIX ~20) — not stated.
- The code does not implement this threshold step (section 1.3).

---

## 3. Evaluation metrics

### 3.1 Table 2 (defined on p.6–7)

- **Accuracy α = C / T**. For LONG, each of the next 3 candles whose close is **higher than the last seen close** scores 1 point (max 3); SHORT is the reverse. Each sample scores 0–3 points, averaged over samples. Note: all 3 candles are compared against the same reference, so the 3 points in one sample are strongly correlated; the number of independent observations is closer to 100 than 300.
- **Δα%**: relative improvement over the random baseline (rechecked: NQ 55.3 / 43.7 − 1 = +26.5%, matches Table 2).
- **R_cc, R_max, R_min**: Rate of Return estimates that "incorporate risk-constrained execution": exit at the first price within the next 3 candles that hits stop-loss or take-profit. Stop-loss ρ = 0.0005; profit threshold R = r·ρ, with r given by the LLM.
- **R_max**: best achievable return within 3 candles (highest high for LONG, lowest low for SHORT).
- **R_min**: most adverse move over the same span.

Unclear points:
- **The exact formula for R_cc is not written out** (what "cc" means, what the entry price is, where to exit if neither threshold is hit). → **unverified**.
- **The unit of R is not stated.** If it is %, then R_min ≈ −1.2 (BTC) or −3.1 (VIX) is tens of times larger than the 0.05% stop-loss — incompatible with "stop-loss applied". If a 0.05% stop were really applied on 4h candles, almost every trade would get stopped out. The paper does not explain. → **unverified**.

### 3.2 Table 1

Table 1 [p.8] uses Sharpe, Sortino, Cumulative Return, Max Drawdown. **The paper does not define how these metrics are computed** (return period, risk-free rate, annualized or not, timeframe, period, position size). The paper's text never even references Table 1 (section 5.1 discusses only Table 2). → **unverified** for the entire Table 1 setup.

### 3.3 MACD formula (Appendix G [p.32])

- `E_t = α·P_t + (1−α)·E_{t−1}`, `α = 2/(N+1)`
- `M_t = E_t^(f) − E_t^(s)` with N = 12 (fast), 26 (slow)
- `S_t = EMA_9(M_t)`; bullish when M_t crosses above S_t.

---

## 4. Experimental setup

| Item | Content | Source |
|---|---|---|
| Timeframes | 1h and 4h | p.6, p.28 |
| Data | 5,000 historical candles per asset, per timeframe | p.6, p.28 |
| Data source | "public TradingView data extraction tool API" [p.6]; Appendix says "YFinance and TradingView" [p.28] | |
| Sampling | Per asset, **100 random segments**, each of **100 consecutive candles**, last **3 candles hidden** for scoring | p.6, p.28 |
| Mode | Zero-shot, no fine-tuning, no examples | p.6 |
| LLM model | **Not stated in the paper.** Appendix H only says GPT-4o was used for copy-editing [p.32]. Code defaults to `gpt-4o` + `gpt-4o-mini`, temperature 0.1 | **unverified** experiment model |
| Case study | 1 SPX segment of 100 candles, 10 overlapping windows offset by 5 candles, 8/10 correct | p.10, Figure 6 |

4h assets (Table 3 [p.28]), 5,000 candles per row:

| Asset | Type | Start | End |
|---|---|---|---|
| BTC/USD | Cryptocurrency | 2023-04-01 | 2025-06-23 |
| CL | Commodity Futures | 2022-04-25 | 2025-06-19 |
| DJI | Equity Index (Spot) | 2015-08-26 | 2025-05-16 |
| ES | Equity Index Futures | 2022-04-19 | 2025-06-19 |
| NQ | Equity Index Futures | 2022-04-19 | 2025-06-19 |
| QQQ | Equity ETF | 2015-08-24 | 2025-05-16 |
| SPX | Equity Index (Spot) | 2015-08-25 | 2025-05-16 |
| VIX | Volatility Index (CBOE) | 2020-10-20 | 2025-08-27 |

1h assets (Table 4 [p.29]), 5,000 candles per row:

| Asset | Type | Start | End |
|---|---|---|---|
| BTC/USD | Cryptocurrency | 2025-02-21 | 2025-09-13 |
| CL | Commodity Futures | 2024-11-12 | 2025-09-10 |
| DJI | Equity Index (Spot) | 2022-11-14 | 2025-09-02 |
| ES | Equity Index Futures | 2024-11-11 | 2025-09-10 |
| NQ | Equity Index Futures | 2024-11-11 | 2025-09-10 |
| QQQ | Equity ETF | 2022-11-14 | 2025-09-02 |
| SPX | Equity Index (Spot) | 2022-11-14 | 2025-09-02 |
| DAX | Equity Index (Futures) | 2024-10-21 | 2025-09-22 |

Baselines [p.6]:
1. **Random**: random LONG/SHORT and risk-reward ∈ [1.2, 1.8].
2. **Linear Regression (LR)**: linear fit on the last **40 closes**; slope > 0 → LONG, otherwise SHORT.
3. **XGBoost**: TA-Lib features (RSI, MACD, SMA); trained on "hundreds of sliding-window samples" from 50 randomly chosen CSV files, tested on the other 50; majority vote outputs LONG/SHORT/HOLD, **HOLD decisions are excluded from the average**.
4. **QuantHarness**.

Table 1 also has a **TradingAgent** row, but the Baselines section does not describe how it was run. → **unverified**.

Asset counts are inconsistent: the abstract says "nine financial instruments" [p.1]; the project page says "ten"; Table 2 has 8; Tables 3 and 4 have 8 each (9 combined: plus DAX); Table 1 also has AAPL and AMZN, two tickers that **do not appear** in the benchmark description.

---

## 5. Results

### 5.1 Table 1 — Sharpe, Sortino, Cumulative Return, Max Drawdown [p.8]

Copied verbatim from the paper. The "Baseline" row in the paper is all "–", so it is omitted. "Our" = QuantHarness.

| Asset | Method | Sharpe | Sortino | CumReturn | MaxDrawdown |
|---|---|---|---|---|---|
| AAPL | LR | 0.044 | 0.068 | 10.21% | -29.59% |
| | XGBoost | -0.241 | -0.372 | -5.35% | -8.23% |
| | TradingAgent | -0.189 | -0.245 | -13.69% | 15.25% |
| | **Our** | -0.155 | -0.264 | -22.51% | -25.44% |
| AMZN | LR | 0.298 | 0.709 | 153.29% | -13.60% |
| | XGBoost | -0.248 | -0.324 | -6.82% | -10.31% |
| | TradingAgent | 0.199 | 0.482 | 20.53% | 4.85% |
| | **Our** | 0.236 | 0.502 | 44.85% | -17.31% |
| DJI | LR | 0.332 | 0.779 | 41.46% | -3.12% |
| | XGBoost | 0.320 | 0.751 | 3.87% | -2.61% |
| | TradingAgent | 0.194 | 0.332 | 5.82% | 2.34% |
| | **Our** | 0.271 | 0.590 | 15.50% | -3.12% |
| ES | LR | 0.430 | 0.953 | 74.50% | -5.90% |
| | XGBoost | 0.596 | 0.807 | 9.41% | -1.88% |
| | TradingAgent | 0.017 | 0.030 | 1.25% | 8.55% |
| | **Our** | 0.339 | 0.661 | 25.43% | -4.72% |
| QQQ | LR | 0.250 | 0.415 | 59.16% | -10.74% |
| | XGBoost | 0.684 | 1.604 | 15.54% | -2.01% |
| | TradingAgent | 0.067 | 0.112 | 3.82% | 3.66% |
| | **Our** | 0.516 | 0.000 | 1.44% | -0.27% |
| SPX | LR | 0.467 | 1.017 | 77.78% | -5.12% |
| | XGBoost | 1.266 | 6.048 | 15.34% | -0.37% |
| | TradingAgent | -0.158 | -0.226 | -6.11% | 7.68% |
| | **Our** | 0.179 | 0.301 | 12.52% | -8.24% |
| NQ | LR | 0.246 | 0.399 | 59.11% | -11.53% |
| | XGBoost | -0.072 | -0.108 | -2.00% | -5.10% |
| | TradingAgent | -0.092 | -0.114 | -5.04% | 9.26% |
| | **Our** | 0.190 | 0.289 | 19.76% | -5.46% |
| VIX | TradingAgent | -0.129 | -0.189 | -30.40% | 32.28% |
| | **Our** | -0.141 | -0.460 | -38.70% | -41.14% |

**Rechecking the claim "LR has higher cumulative return on most tickers": true, and even stronger than that.**

| Asset | CumReturn LR | CumReturn Our | Best method | Our rank |
|---|---|---|---|---|
| AAPL | 10.21% | -22.51% | LR | 4/4 (worst) |
| AMZN | 153.29% | 44.85% | LR | 2/4 |
| DJI | 41.46% | 15.50% | LR | 2/4 |
| ES | 74.50% | 25.43% | LR | 2/4 |
| QQQ | 59.16% | 1.44% | LR | 4/4 (loses even to XGBoost 15.54% and TradingAgent 3.82%) |
| SPX | 77.78% | 12.52% | LR | 3/4 (loses to XGBoost 15.34%) |
| NQ | 59.11% | 19.76% | LR | 2/4 |
| VIX | (none) | -38.70% | TradingAgent -30.40% | 2/2 (worst) |

- **Cumulative return**: LR beats QuantHarness on **7/7** assets with LR figures. QuantHarness is best on **0/8**.
- **Sharpe**: QuantHarness is best on **0/8** (LR best on AAPL, AMZN, DJI, NQ; XGBoost on ES, QQQ, SPX; TradingAgent on VIX).
- **Sortino**: QuantHarness is best on **0/8**.
- **Max drawdown**: if less negative is better, QuantHarness is best only on QQQ (-0.27%). The TradingAgent rows carry a **positive** sign (15.25%, 32.28%…) while other rows are negative — the sign convention is inconsistent, so they cannot be compared directly.

**Wrongly bolded cells in the paper** (bold usually means best in column):
- "Our" CumReturn is bolded for DJI (15.50%), ES (25.43%), QQQ (1.44%), SPX (12.52%), NQ (19.76%) even though LR is higher on all five.
- "Our" Sharpe/Sortino is bolded for AMZN (0.236 / 0.502) though LR is 0.298 / 0.709; for NQ (0.190 / 0.289) though LR is 0.246 / 0.399.
- Table 1 has no caption explaining the bolding rule.

Another anomaly: QQQ "Our" has Sharpe 0.516 but Sortino 0.000 and CumReturn only 1.44%, MaxDD -0.27% — this combination suggests almost no trades or a computation bug; the paper does not explain.

### 5.2 Table 2 — 4h timeframe [p.9]

Copied verbatim. Baseline = random.

| Asset | Method | Acc α | Δα% | R_cc | R_max | R_min |
|---|---|---|---|---|---|---|
| BTC | Baseline | 45.0 | – | -0.009 | 1.220 | -1.245 |
| | LR | 46.0 | +2.2% | -0.066 | 1.245 | -1.210 |
| | XGBoost | 45.3 | +0.7% | -0.050 | 1.218 | -1.331 |
| | **Our** | 50.7 | +12.7% | 0.089 | 1.232 | -1.212 |
| CL | Baseline | 41.0 | – | -0.373 | 0.970 | -1.348 |
| | LR | 54.3 | +32.4% | -0.114 | 1.178 | -1.141 |
| | XGBoost | 40.0 | -2.4% | -0.056 | 0.958 | -1.151 |
| | **Our** | 55.0 | +34.1% | -0.008 | 1.200 | -1.119 |
| DJI | Baseline | 47.0 | – | 0.048 | 0.755 | -0.793 |
| | LR | 52.0 | +10.6% | 0.149 | 0.790 | -0.725 |
| | XGBoost | 47.3 | +0.6% | -0.020 | 0.874 | -0.660 |
| | **Our** | 52.3 | +11.3% | 0.163 | 0.891 | -0.649 |
| ES | Baseline | 51.0 | – | -0.048 | 0.538 | -0.552 |
| | LR | 43.0 | -15.7% | 0.032 | 0.553 | -0.546 |
| | XGBoost | 52.0 | +2.0% | -0.182 | 0.440 | -0.644 |
| | **Our** | 55.0 | +7.8% | 0.179 | 0.613 | -0.485 |
| VIX | Baseline | 46.3 | – | 0.059 | 3.259 | -3.157 |
| | LR | 48.7 | +5.2% | -0.140 | 3.407 | -3.099 |
| | XGBoost | 53.3 | +15.1% | 0.161 | 3.325 | -3.110 |
| | **Our** | 54.7 | +18.1% | 0.458 | 3.872 | -2.851 |
| NQ | Baseline | 43.7 | – | -0.140 | 0.646 | -0.793 |
| | LR | 48.7 | +11.4% | 0.147 | 0.782 | -0.670 |
| | XGBoost | 47.3 | +8.2% | -0.007 | 0.706 | -0.753 |
| | **Our** | 55.3 | +26.5% | 0.216 | 0.814 | -0.639 |
| QQQ | Baseline | 47.3 | – | -0.048 | 0.930 | -1.017 |
| | LR | 56.0 | +18.4% | 0.175 | 1.113 | -0.849 |
| | XGBoost | 52.7 | +11.4% | 0.210 | 1.206 | -0.973 |
| | **Our** | 59.7 | +26.2% | 0.211 | 1.052 | -0.881 |
| SPX | Baseline | 47.3 | – | -0.162 | 0.719 | -0.862 |
| | LR | 59.7 | +26.2% | 0.377 | 0.960 | -0.648 |
| | XGBoost | 60.0 | +26.8% | 0.050 | 0.782 | -0.712 |
| | **Our** | 63.7 | +34.6% | 0.341 | 0.965 | -0.641 |

Checking the claims in the paper's section 5.1 [p.9–10]:

| Claim | Check result |
|---|---|
| Highest accuracy on all 8 markets | True per the table. But the gap to the runner-up is only 0.3 points on DJI (52.3 vs 52.0), 0.7 on CL (55.0 vs 54.3), 1.4 on VIX |
| Best R_cc on 7/8 | True (loses to LR on SPX: 0.341 vs 0.377). On CL, the "best" is still negative (-0.008); on QQQ it beats XGBoost by 0.001 |
| Highest R_max on 6/8 | True (loses to LR on BTC, to XGBoost on QQQ) |
| Good R_min | Best on 6/8; loses to LR on BTC and QQQ |

Observations:
- The random baseline scores 41.0–51.0% depending on the asset. An ideal random generator should sit around 50%; swinging by up to 10 points shows that **the sampling noise of the measurement itself is already around ±5 points**. Any difference below that (most of the table) cannot be considered meaningful.
- The Δα% column is measured against an unusually low random baseline (41.0 on CL, 43.7 on NQ), so figures like "+34.1%", "+26.5%" are inflated.
- LR (40 candles, one line of code) is very close: 59.7 vs 63.7 on SPX, 56.0 vs 59.7 on QQQ, 54.3 vs 55.0 on CL.
- On US equity indices over 2015–2025 (a long uptrend), any long-biased strategy has accuracy > 50%. The paper does not report the system's LONG/SHORT ratio or an "always LONG" baseline.

### 5.3 1h timeframe — Figure 5 [p.10]

1h results are only given as **line charts** for 8 assets (BTC, CL, DAX, DJI, ES, NQ, QQQ, SPX); **no numeric table**. The paper claims QuantHarness beats baselines "across most metrics and markets", most clearly on SPX, QQQ, BTC, but admits "less satisfactory R_min in some assets". Numbers could not be transcribed → specific values **unverified**.

### 5.4 Case study [p.10–11]

- SPX (2025), 10 overlapping windows: 8/10 correct = "80%". Wrong on windows 2 and 7 (the paper attributes this to relying on incomplete patterns and calling the rise too early).
- The "up to 80% directional accuracy" figure in the introduction [p.2] is exactly this 8/10: **one segment, ten overlapping samples**, not a statistical result.

### 5.5 Limitations the paper states itself [p.11]

- Accuracy drops sharply on very short candles (≈ 1–15 minutes) compared with 30 minutes–4 hours.
- Not truly real-time: each cycle involves LLM calls and multiple tools; latency can exceed a 1-minute opportunity window.

---

## 6. Critical review

### 6.1 What the paper does not account for / does not say

| Issue | Status |
|---|---|
| Trading fees, slippage, spread, funding | **Not mentioned anywhere** in the paper; searching the repo (`fee`, `commission`, `slippage`) finds nothing either. With a 0.05% stop and 0.06–0.09% take-profit, one typical crypto taker fee is already the same order as or larger than the entire target profit margin |
| HOLD | Banned in the prompt [p.6, p.21]. The system must enter a trade even when signals conflict. The XGBoost baseline may HOLD and HOLDs are excluded from the average [p.6] → not a like-for-like comparison |
| Experiment LLM model | Not stated. Not reproducible |
| Statistical significance | No confidence intervals, p-values, seed counts, repeated runs; the LLM runs at temperature 0.1 so it is not deterministic |
| Ablation | None. Unknown which agent contributes, or whether a single LLM call would do as well |
| Cost and latency | No figures on tokens, money, seconds/decision |
| Table 1 metric definitions | None (section 3.2) |
| N, τ of Algorithm 1 | None |
| Units and formula of R_cc | Unclear (section 3.1) |
| TradingAgent baseline | In Table 1, configuration not described |
| Position sizing, leverage, capital | Not stated |

### 6.2 Data leakage risks

- **Hiding the last 3 candles** is procedurally correct [p.6, p.28]. However the benchmark CSV files in the repo have a full **100 rows** (checked), i.e. they include the 3 answer candles; the cut must be done by the evaluation script, which **is not in the repo** → cannot be verified.
- **Segments overlap heavily.** 100 segments × 100 candles taken from 5,000 candles. Checking 4 folders directly in the repo (`benchmark/btc`, `benchmark/1h/btc`, `benchmark/spx`, `benchmark/vix`): after sorting by time, **86/99 adjacent segment pairs overlap**. Consequences: (a) samples are not independent, effective sample size is below 100; (b) XGBoost trained on 50 files and tested on the other 50 sees data overlapping in time with the test set.
- **The LLM may have "seen" the price history.** 4h data for DJI/QQQ/SPX goes back to 2015; the prompt contains the `Datetime` column and a time axis on the image, plus the asset name in DecisionAgent. An LLM trained through 2023–2024 may remember market moves on those dates. The paper does not discuss this and runs no date/name-masking experiment. This is a risk, impact **unverified**.
- There is no temporal train/test split because the system is zero-shot; but whether the prompt design (16 patterns, decision rules) was tuned on this same benchmark, the paper does not say.

### 6.3 Sample size

- 100 segments per asset, each scoring 3 correlated candles. The standard error of accuracy is about 3–5 percentage points. Only SPX (63.7) and QQQ (59.7) are far enough from 50%, and those two tickers have a long-term upward bias.
- The "80%" case study is based on 10 samples.

### 6.4 Wording

- "High-Frequency Trading" in the title does not match experiments on **1h and 4h** candles; the paper itself admits it does poorly at 1–15 minutes and is not real-time [p.11].
- "Consistently outperforms baseline methods" [p.1] does not hold up against Table 1.
- RiskAgent is presented as an agent but has no prompt and no code.

### 6.5 Genuine strengths

- Indicator values are computed by a tool (TA-Lib); the LLM only interprets → fewer fabricated numbers.
- Every decision comes with natural-language reasoning, traceable per agent.
- Public benchmark CSVs (16 folders × 100 files) and MIT code.
- The paper publishes Table 1 even though it is unfavorable, and has a Limitations section.

---

## 7. Repo: structure and how to run

### 7.1 Structure (commit `2e64c7b`)

```
QuantHarness/
├── trading_graph.py      # TradingGraph: init LLM per provider, build graph
├── graph_setup.py        # SetGraph: wire Indicator → Pattern → Trend → Decision
├── agent_state.py        # IndicatorAgentState (TypedDict)
├── indicator_agent.py    # Indicator node + prompt
├── pattern_agent.py      # Pattern node + 16-pattern library
├── trend_agent.py        # Trend node + prompt
├── decision_agent.py     # Decision node + prompt
├── graph_util.py         # TechnicalTools (@tool): 5 indicators, 2 plot functions, trendline fit
├── static_util.py        # non-@tool version of the 2 plot functions (web uses it to prebuild images)
├── color_style.py        # mplfinance style
├── default_config.py     # model, provider, temperature, API key
├── web_interface.py      # Flask app, fetches yfinance data, 1,175 lines
├── templates/            # demo.html, demo_new.html, output.html
├── tests/                # only tests the MiniMax provider
├── benchmark/            # CSV: {btc,cl,dji,es,nq,qqq,spx,vix}/ (4h) and 1h/{btc,cl,dax,dji,es,nq,qqq,spx}/
├── index.html, assets/   # project page (GitHub Pages)
├── requirements.txt
├── README.md, README_CN.md
└── LICENSE               # MIT
```

- Benchmark: 16 folders × 100 files × 100 rows; columns `Datetime,Close,High,Low,Open,Volume`. File names like `BTC_4h_1.csv`, `BTC_1h_1.csv`.
- **Missing**: evaluation script, baseline code (LR / XGBoost / random / TradingAgent), Sharpe/R_cc computation code, RiskAgent, backtest, exchange connection/order placement, pinned library versions.

### 7.2 Dependencies (`requirements.txt`, unpinned)

`flask, yfinance, pandas, numpy, matplotlib, mplfinance, scipy, TA-Lib, langchain, langchain-openai, langchain-anthropic, langchain-qwq, langchain-core, langgraph, openai, anthropic, ipython, Pillow, requests`

TA-Lib needs a C library; the README suggests `conda install -c conda-forge ta-lib` if `pip` fails.

### 7.3 How to run (per the README; **not test-run** in this review)

```bash
conda create -n quantharness python=3.11
conda activate quantharness
pip install -r requirements.txt

export OPENAI_API_KEY="..."        # or ANTHROPIC_API_KEY / DASHSCOPE_API_KEY / MINIMAX_API_KEY

python web_interface.py            # http://127.0.0.1:5000
```

Use from code:

```python
from trading_graph import TradingGraph

tg = TradingGraph()                       # or TradingGraph(config={...})
state = {
    "kline_data": df_dict,                # dict of lists: Datetime, Open, High, Low, Close
    "analysis_results": None,
    "messages": [],
    "time_frame": "4hour",
    "stock_name": "BTC",
}
out = tg.graph.invoke(state)
out["final_trade_decision"]; out["indicator_report"]; out["pattern_report"]; out["trend_report"]
```

Configuration [code: `default_config.py`]: `agent_llm_model="gpt-4o-mini"`, `graph_llm_model="gpt-4o"`, both temperatures = 0.1. Providers supported in code: `openai`, `anthropic`, `qwen`, `minimax`, `minimax_cn`, `gemini` (the README does not mention `gemini`). Default model when switching provider (per the README): Anthropic `claude-haiku-4-5-20251001`; Qwen `qwen3-max` / `qwen3-vl-plus`; MiniMax `MiniMax-M3`. **A vision-capable model is required.**

Notes when running:
- The web demo fetches data via yfinance (BTC → `BTC-USD`, NQ → `NQ=F`, SPX → `^GSPC`…), cuts `tail(45)`, prebuilds images, then calls the graph. 1h/4h timeframes are limited to 730 days; 30m to 60 days.
- Tools write files to the current directory: `kline_chart.png`, `trend_graph.png`, `record.csv` (dpi 600, large images → expensive vision tokens).
- `DEFAULT_CONFIG["api_key"] = "sk-"` is a non-empty string, so the code will not fall back to the environment variable when using the default config from Python; set the key in the config or via the web UI. (Inferred from reading `_get_api_key`, **not test-run**.)
- The web demo has static mock fields on the output page (e.g. `"forecast_horizon": "24-48 hours"`); Figure 12 in the paper [p.27] also shows ADX, "RSI Divergence", "Volume" — indicators that **are not** among the tools.

### 7.4 License

- Code: **MIT**, "Copyright (c) 2025 Y-Research @SBU" [`LICENSE`]. Free to use, modify, distribute, commercialize, as long as the copyright notice is kept.
- The project page footer says "© 2025 QuantHarness, All Rights Reserved" — this applies to the website content and does not change the code license.
- The README has a disclaimer: educational/research purposes only, not financial advice.
- The trendline fitting code comes from `neurotrader888/TechnicalAnalysisAutomation` (credited in the README); that original repo's license is **unverified**.
- Benchmark data comes from TradingView/yfinance; data redistribution terms are **unverified**.

---

## 8. Applying this to the project

### 8.1 Worth reusing

| Component | Reason |
|---|---|
| Role separation: indicator / pattern / trend / decision, shared state | Easy to swap parts, easy to log and debug |
| Indicator tools computed by a library, LLM only interprets | Prevents the LLM from fabricating numbers |
| Support/resistance trendline fitting (`fit_trendlines_single`, `optimize_slope`) | Deterministic algorithm, usable independently of the LLM (check the source license first) |
| Decision output schema (direction, justification, risk_reward) | Good starting point; needs tightening into structured output |
| Benchmark CSVs + the "hide the last k candles" protocol | Use as a quick smoke test |
| 40-candle LR baseline | Cheap and strong; **every version of the project must beat this baseline after fees** to be worth keeping |

### 8.2 What to change

1. **Write our own evaluation harness** (the repo has none): time-based walk-forward, non-overlapping segments, fees + slippage + funding, baselines always-long / buy-and-hold / random / LR / simple momentum, confidence intervals (bootstrap) and multiple seeds.
2. **Allow HOLD / no trade** and measure the participation rate too. Banning HOLD forces the system to trade even without an edge.
3. **Compute risk in code, do not let the LLM choose.** Replace the fixed 0.05% stop with a volatility-based stop (ATR or standard deviation per timeframe and asset); compute position sizing and daily loss limits in a deterministic layer.
4. **Actually implement Algorithm 1** with normalized slope (as % of price or in ATR) and τ calibrated on a validation set; feed the classification result to the LLM as numbers instead of only an image.
5. **Fix the indicator data bug**: drop `fillna(0)`, load enough warm-up candles (at least ~100 for MACD 12/26/9), return only the valid part.
6. **Verify patterns algorithmically** (pivots, convergence) before or alongside vision; measure pattern-recognition accuracy separately. Lower image dpi to save tokens.
7. **Guard against leakage from LLM memory**: try masking dates and asset names, normalizing prices; prefer evaluating on data after the model's cutoff date.
8. **Mandatory ablation**: single LLM call vs multi-agent; drop each agent; numbers only vs with images. Keep only what proves its contribution.
9. **Structured output + validation** for every agent (JSON schema), parse and range-check values; pin library versions; log full prompt/response/cost/latency.
10. **Do not call it HFT.** The realistic scope is decision support at 30-minute–4-hour timeframes and above. For equities, consider adding non-price data (which the paper deliberately excludes).
11. Real order execution is outside the scope of this repo; if the project needs it, it must be designed separately with risk controls independent of the LLM.

---

## 9. "Unverified" list

1. The LLM model used for the paper's experiments (code defaults to gpt-4o / gpt-4o-mini, the paper does not say).
2. The values of N and τ in Algorithm 1.
3. The exact formula and units of R_cc, R_max, R_min; how they are compatible with a 0.05% stop-loss.
4. The entire Table 1 setup: timeframe, period, how Sharpe/Sortino/CumReturn/MaxDD are computed, MaxDD sign convention, AAPL/AMZN data source, TradingAgent baseline configuration, why VIX lacks LR/XGBoost.
5. Specific 1h figures (chart only, Figure 5).
6. Whether the evaluation script really cuts the last 3 candles before feeding the LLM (script not published).
7. How much it matters that the LLM saw historical data during training.
8. Whether the prompt/benchmark was iteratively tuned on the same test set.
9. Whether RiskAgent exists as code in any other version (it is not in commit `2e64c7b`).
10. Which code the PatternAgent "extract swing pivots / least-squares fit" description in Appendix F corresponds to.
11. Whether the repo runs as-is (not installed and test-run); the `api_key="sk-"` behavior is inferred from reading code only.
12. The license of the original trendline code (`TechnicalAnalysisAutomation`) and the redistribution terms for TradingView/yfinance data.
13. Whether the asset count is "nine" (abstract) or "ten" (project page) — the tables match neither.
14. Benchmark segment overlap was checked on only 4/16 folders.
