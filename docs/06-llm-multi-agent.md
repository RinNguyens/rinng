# 06 — The LLM multi-agent layer for quant trading / crypto / stock analysis

> Research date: **2026-11-13**. All "current" figures (model IDs, prices, GitHub stars, licenses) were read directly from sources on that day, with URLs.
> Convention: **[unverified]** = not read from the original source in this research session (taken from a secondary source or background knowledge); re-check before relying on it.
> This document is not investment advice. Section 2 (counter-evidence) should be read before deciding to invest effort in the LLM layer.

## Contents

1. [Overview of LLM systems for finance](#1-overview-of-llm-systems-for-finance)
2. [Counter-evidence and evaluation design](#2-counter-evidence-and-evaluation-design)
3. [Agent frameworks](#3-agent-frameworks)
4. [Techniques the project needs](#4-techniques-the-project-needs)
5. [Claude API specifics](#5-claude-api-specifics)
6. [Finance / crypto / TradingView MCP servers](#6-finance--crypto--tradingview-mcp-servers)
7. [Proposed architecture for the project](#7-proposed-architecture-for-the-project)
8. [Unverified items](#8-unverified-items)

---

## 1. Overview of LLM systems for finance

### 1.0 Summary table

Stars and last-push dates from the GitHub API on 2026-11-13.

| System | Type | Repo | License | Stars | Last push |
|---|---|---|---|---|---|
| QuantHarness | Multi-agent, OHLC only, with vision | [Y-Research-SBU/QuantHarness](https://github.com/Y-Research-SBU/QuantHarness) | MIT | 2.9k | 2026-08-18 |
| TradingAgents | Multi-agent simulating a trading firm | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Apache-2.0 | 122.4k | 2026-11-04 |
| FinMem | Single agent + layered memory | [pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading) | MIT | 973 | 2024-08-18 |
| FinCon | Multi-agent manager–analyst | [The-FinAI/FinCon](https://github.com/The-FinAI/FinCon) | MIT | 72 | 2026-10-08 |
| FinGPT | Open-source financial LLM (fine-tuning) | [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | MIT | 21.6k | 2026-10-25 |
| FinRobot | Financial analysis agent platform | [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | Apache-2.0 | 8.4k | 2026-10-24 |
| RD-Agent(Q) | Automated factor + model R&D agent | [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) | MIT | 15.4k | 2026-10-21 |
| FinAgent | Multimodal agent + tools + reflection | [DVampire/FinAgent](https://github.com/DVampire/FinAgent) | MIT | 78 | 2024-08-31 |
| StockAgent | Multi-agent market simulation | [MingyuJ666/Stockagent](https://github.com/MingyuJ666/Stockagent) | **none declared** | 719 | 2026-06-16 |
| AI Hedge Fund | Educational proof of concept | [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | MIT | 64.7k | 2026-11-09 |
| Trading-R1 | Financial research terminal | [TauricResearch/Trading-R1](https://github.com/TauricResearch/Trading-R1) | Apache-2.0 | 678 | 2026-11-09 |
| AI-Trader | Real-time trading agent benchmark | [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) | **none declared** | 23.3k | 2026-06-11 |

A repo with no declared license defaults to "all rights reserved": fine to read and learn from, but don't copy code into the project.

### 1.1 QuantHarness (the project's inspiration)

- **Paper**: "QuantHarness: Price-Driven Multi-Agent LLMs for High-Frequency Trading", Xiong, Zhang, Feng, Sun, You. arXiv [2509.09995](https://arxiv.org/abs/2509.09995), v1 on 2025-09-12, current version v4 on 2026-07-27. The repo was formerly named `QuantAgent`, now redirected to `QuantHarness`.
- **Idea**: drop news and social media entirely, use only price-derived (OHLC) signals for short 1h/4h timeframes.
- **Architecture** (read from the [v4 HTML version](https://arxiv.org/html/2509.09995v4)): built on **LangGraph**. The abstract lists four agents (Indicator, Pattern, Trend, Risk); section 3.4 of the paper adds a DecisionAgent as the final aggregation layer.
  - IndicatorAgent: calls tools `compute_rsi`, `compute_macd`, `compute_roc`, `compute_stoch`, `compute_willr`.
  - PatternAgent: tool `generate_kline_image` draws a simplified candlestick chart; a vision model compares it against a library of 16 classic patterns.
  - TrendAgent: tool `generate_trend_image` draws a chart with two OLS-fitted support/resistance lines, classifies the trend by slope.
  - RiskAgent: fixed stop-loss 0.0005, take-profit = r × stop-loss, the LLM only predicts r in [1.2, 1.8].
  - DecisionAgent: outputs LONG/SHORT, rationale, risk-reward ratio, forecast for the next 3 candles.
- **Input data**: OHLC; the README says it takes the 30 most recent candles from Yahoo Finance via `yfinance`, needs TA-Lib, and the model must accept images.
- **Reported results**: 1h directional accuracy, e.g. SPX 63.7% (random 47.3%), NQ 55.3% (random 43.7%), BTC 50.7% (random 45.0%). Baselines: random, linear regression (40-candle slope), XGBoost.
- **Limitations** (partly stated by the paper itself, partly read from the results tables):
  - Negative cumulative return on some tickers (AAPL −22.51%, VIX −38.70%), and linear regression often has higher returns. Higher-than-random accuracy does **not** translate into profit.
  - The paper does not name the LLM used ("zero-shot LLM ensemble"), so knowledge cutoff vs. test period cannot be checked (4h data spans 2015–2025, 1h mostly 2022–2025). The look-ahead risk in section 2.2 applies directly.
  - The number of assets is inconsistent between the abstract (nine), the body (eight) and the tables.
  - Not really real-time: each cycle involves one LLM call and many tool calls; the authors themselves say accuracy drops on 1–15 minute candles.
  - The paper does not describe transaction costs/slippage **[unverified]** (the last 13k characters of the HTML version were not read).
- **Default models in the README**: Anthropic `claude-haiku-4-5-20251001`; OpenAI `gpt-4o-mini`/`gpt-4o`; Qwen `qwen3-max`/`qwen3-vl-plus`; MiniMax `MiniMax-M3`.

### 1.2 TradingAgents (TauricResearch)

- **Paper**: arXiv [2412.20138](https://arxiv.org/abs/2412.20138).
- **Idea**: simulate a trading firm with specialized roles that debate each other.
- **Architecture** (read from the [README](https://github.com/TauricResearch/TradingAgents)): built with LangGraph. Analyst Team (Fundamentals, Sentiment, News, Technical) runs in parallel → Researcher Team (bull and bear debate) → Trader → Risk Management → Portfolio Manager approves or rejects.
- **Input data**: SEC EDGAR, Yahoo Finance, StockTwits, Reddit, FRED, Polymarket, Alpha Vantage (API key required).
- **LLMs**: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter, Mistral, Kimi, Groq, NVIDIA NIM, Ollama.
- **Version**: README states v0.7.1 (2026-10).
- **Reported results**: the paper reports beating baselines on cumulative return, Sharpe and max drawdown on a few US stocks over a few months in 2024 **[specific figures unverified]**.
- **Limitations**: the README itself says "designed for research purposes", not investment advice, and that results vary with model, temperature, and data quality. The backtest period is short and falls within the LLM's training data. Each decision costs many LLM calls. FINSABER (section 2.1) re-tested this group of systems over long horizons and found the edge disappears.

### 1.3 FinMem

- **Paper**: arXiv [2311.13743](https://arxiv.org/abs/2311.13743); published in IEEE Transactions on Big Data (2025) per secondary sources.
- **Idea**: one agent with three modules: profiling (personality/risk appetite), layered memory (shallow/intermediate/deep, each layer with a different decay rate) and decision.
- **Input data**: daily prices, news, 10-Q/10-K filings.
- **Reported results**: the authors report better cumulative return and Sharpe than algorithmic baselines on a few US stocks **[figures unverified]**.
- **Limitations**: repo inactive since 2024-08; evaluates single tickers individually over short periods; one of the systems FINSABER re-tested.

### 1.4 FinCon

- **Paper**: arXiv [2407.06567](https://arxiv.org/abs/2407.06567), NeurIPS 2024 **[venue unverified in this session]**.
- **Idea**: an investment-firm-style manager–analyst hierarchy; "conceptual verbal reinforcement": after each episode a risk-control module updates "investment beliefs" in words and propagates them back to the agents. Handles both single-stock trading and portfolio management.
- **Limitations**: small repo (72 stars); verbal "learning" on historical data further increases overfitting and leakage risk.

### 1.5 FinGPT

- **Paper**: arXiv [2306.06031](https://arxiv.org/abs/2306.06031).
- **Idea**: not a trading agent. It is an open-source toolkit and models for fine-tuning LLMs (LoRA) on financial tasks like sentiment, news classification, relation extraction, forecasting.
- **Relevance to the project**: useful if news sentiment is needed later. The project currently uses only OHLC, so not needed yet.
- **Limitations**: base models are much older than current commercial models; sentiment benchmarks do not translate into trading profit.

### 1.6 FinRobot

- **Paper**: arXiv [2405.14767](https://arxiv.org/abs/2405.14767).
- **Idea**: an agent platform for financial analysis (valuation reports, company analysis) with multiple layers: agents, LLM algorithms, LLMOps/DataOps, foundation models. A benchmark paper describes it as geared more toward market analysis than trading.
- **Underlying framework**: AutoGen **[unverified in this session]**. Note that AutoGen has entered maintenance mode (section 3.5).

### 1.7 Microsoft's RD-Agent(Q)

- **Paper**: "R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization", arXiv [2505.15155](https://arxiv.org/abs/2505.15155) (v2 on 2025-09-25).
- **Idea**: the LLM does not issue buy/sell orders. The LLM plays researcher: proposes factor hypotheses, writes code, runs backtests on Qlib, reads results, and iterates. Research and Development phases are linked by a Feedback phase; a multi-armed bandit scheduler chooses between factor and model optimization.
- **Reported results**: ARR roughly double that of classic factor libraries with 70% fewer factors, costing under 10 USD per run.
- **Why it matters**: the output is **deterministic factor code**, backtestable, auditable, runnable without an LLM. AlphaForgeBench (section 2.3) argues this is a more stable way to use LLMs than letting them decide directly.
- **Limitations**: a factor-search loop over historical data is data mining; a separate out-of-sample set and multiple-testing correction are needed. NeurIPS venue **[unverified]**.

### 1.8 FinAgent

- **Paper**: "A Multimodal Foundation Agent for Financial Trading: Tool-Augmented, Diversified, and Generalist", arXiv [2402.18485](https://arxiv.org/abs/2402.18485), KDD 2024 **[venue unverified]**.
- **Idea**: a multimodal agent (numbers, text, **chart images**) with a market intelligence module, dual-level reflection, diversified memory retrieval, and expert tools/strategies as references.
- **Reported results**: 6 datasets (stocks and crypto), beats 9 baselines; 92.27% return on one dataset.
- **Limitations**: repo stalled since 2024-08; very high returns on one ticker over a short period are a red flag per section 2.

### 1.9 StockAgent

- **Paper**: arXiv [2407.18957](https://arxiv.org/abs/2407.18957); the repo description says "[TIST]".
- **Idea**: simulate a **market** with many investor agents to study behavior under external events. Not aimed at producing profitable strategies.
- **Relevance to the project**: low. FinCon notes that multi-agent discussion increases communication cost and slows decisions.

### 1.10 AI Hedge Fund (virattt)

- **Read from the [README](https://github.com/virattt/ai-hedge-fund)**: a proof of concept for educational purposes; "the system does not actually make any trades"; has paper trading with simulated money and a backtester against a benchmark. Requires a Financial Datasets API key and a model API key. Supports Anthropic, OpenAI, DeepSeek, Google, xAI, Kimi.
- **Architecture**: several "investor agents" mimicking famous investors' styles plus valuation, sentiment, fundamentals, technicals, risk manager, and portfolio manager agents, orchestrated with LangGraph **[agent list and framework unverified in this session]**.
- **Limitations**: no verified published results; "famous investor" personas are role-play prompts, not quantitative methods.

### 1.11 Alpha Arena and live LLM trading benchmarks

The [nof1.ai](https://nof1.ai/) page links to alphaarena.ai, and alphaarena.ai returned HTTP 429 during research. So **all Alpha Arena figures below come from the press, [unverified] against the original source**.

- **Season 1** (about 2025-10-17 to 2025-11-03): six LLMs, 10,000 USD of real money each, trading crypto perpetuals on Hyperliquid with the same prompt and data. Qwen won with about +22.3%; only Qwen and DeepSeek were profitable; GPT-5 lost more than 62%. Sources: [Decrypt](https://decrypt.co/345006/ai-crypto-trading-showdown-deepseek-grok-winning-gemini-implodes), [iWeaver](https://iweaver.ai/blog/alpha-arena-ai-trading-season-1-results).
- **Season 1.5** (2025-11-19 to 2025-12-03): eight models, US stocks. A "Mystery Model" won with +12.11%, later said to be Grok 4.20. Sources: [GNcrypto](https://www.gncrypto.news/news/mystery-model-alpha-arena-season-1-5-winner/), [ForkLog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/amp).
- **Season 2**: no confirmed start date or results found.
- **How to read it**: each season is only 2–3 weeks, one run per model, high leverage. Rankings flip between seasons. This is anecdote, without the statistical power to conclude which model is "good at trading". Nof1's founder also said LLMs can't yet be trusted with money to trade on their own (per the press).

Academic benchmarks run live or after cutoff:

| Benchmark | Design | Main finding |
|---|---|---|
| StockBench, arXiv [2510.02209](https://arxiv.org/abs/2510.02209), repo [ChenYXxxx/stockbench](https://github.com/ChenYXxxx/stockbench) (Apache-2.0) | Data after the models' training cutoff; daily prices, fundamentals, news; about 82 sessions (2025-03 to 2025-06) **[window unverified]** | Most models fail to beat equal-weight buy-and-hold; being good at financial QA does not mean being good at trading |
| LiveTradeBench, arXiv [2511.03628](https://arxiv.org/abs/2511.03628) | 50 live days, 21 LLMs, US stocks and Polymarket | High LMArena scores do not lead to better trading results |
| AI-Trader, arXiv [2512.10971](https://arxiv.org/abs/2512.10971) | 6 LLMs, US stocks, A-shares, crypto, multiple frequencies | "General intelligence does not automatically translate to effective trading capability"; most agents have poor returns and weak risk management |
| Agent Market Arena ("When Agents Trade") | Live, multiple markets | More positive results: some agents beat buy-and-hold; agent architecture matters more than the base LLM **[unverified, only a secondary summary read]** |

### 1.12 Other new work 2025–2026

- **FINSABER**, arXiv [2505.07078](https://arxiv.org/abs/2505.07078), KDD 2026 Datasets & Benchmarks (Oral), repo [waylonli/FINSABER](https://github.com/waylonli/FINSABER) (Apache-2.0). See section 2.1.
- **Profit Mirage**, arXiv [2510.07920](https://arxiv.org/abs/2510.07920). See section 2.2.
- **AlphaForgeBench**, arXiv [2602.18481](https://arxiv.org/abs/2602.18481) (v2 on 2026-05-27). See section 2.3.
- **Trading-R1**: paper "Trading-R1: Financial trading with LLM reasoning via reinforcement learning" (Xiao et al., per the citation in the repo; arXiv ID 2509.11420 **[unverified]**). The repo is currently a financial research terminal app; the README states no results and does not explain how the software relates to the paper's method.
- **MemGuard-Alpha**, arXiv [2603.26797](https://arxiv.org/abs/2603.26797): filters LLM signals with membership inference to reduce the effect of memorization **[details unverified]**.
- **HKU live FX study** (2026-07): ten agents trading live for six weeks; the authors note six weeks is only a slice **[unverified, secondary source]**.

---

## 2. Counter-evidence and evaluation design

### 2.1 Performance does not hold out of sample

- **FINSABER** ([2505.07078](https://arxiv.org/abs/2505.07078)): two-decade backtest, over 100 tickers. The advantage of LLM strategies reported in earlier narrow evaluations "deteriorates significantly". LLMs are too conservative in bull markets, so they lose to passive benchmarks, and too aggressive in bear markets, so they lose heavily. The authors recommend prioritizing trend detection and regime-aware risk control over adding framework complexity.
- **StockBench**, **AI-Trader**, **LiveTradeBench** (section 1.11): when tested after cutoff or live, most agents fail to beat buy-and-hold, and a model's general capability does not predict trading results.
- **QuantHarness** itself: better-than-random accuracy but negative returns on some tickers and worse returns than linear regression (section 1.1).

Common denominator of papers reporting nice results: few tickers, few months, a single run, no fees, test period inside the LLM's training data.

### 2.2 Look-ahead from LLM training data

Traditional backtests only need features at time t not to use data after t. With LLMs there is another leakage channel: **the model weights have seen the future**. If the backtest period is before the knowledge cutoff, the model may "remember" that BTC crashed in May 2021 or that NVDA surged in 2023 without inferring anything from the chart.

- **Profit Mirage** ([2510.07920](https://arxiv.org/abs/2510.07920)): agent returns collapse when re-evaluated on post-cutoff data. The FinLake-Bench set contains 2,000 questions of the form "did the market go up or down on date X"; models like GPT-4o answer correctly more than 85% of the time **[figure from the abstract, full text not read]**.
- **The Memorization Problem** (Lopez-Lira, Tang, Zhu; arXiv [2504.14765](https://arxiv.org/abs/2504.14765)): LLMs can recall exact numeric values of economic data from their training period; LLM forecasts for that period cannot be trusted.
- **Detecting Lookahead Bias in LLM Forecasts** (Gao, Jiang, Yan; arXiv [2512.23847](https://arxiv.org/abs/2512.23847)): statistical tests show memorization significantly inflates apparent predictive power.
- **Glasserman & Lin** (arXiv [2309.17322](https://arxiv.org/abs/2309.17322)): within the training window, hiding company names from headlines actually gives higher returns. Besides look-ahead there is a "distraction" effect: general knowledge about the company skews judgment.
- **Sarkar & Vafa, "Lookahead Bias in Pretrained Language Models"** **[unverified, not found in this session]**.

Anonymization (removing tickers, dates, normalizing prices) reduces but does not eliminate leakage: the shape of a well-known asset's price series can still be recognizable.

**Direct consequence for this project.** Per [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview), all four current Claude models (Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5) have a "reliable knowledge cutoff" and "training data cutoff" of **June 2026**. As of today (2026-11-13):

- Every backtest with an LLM in the loop on data before July 2026 is contaminated.
- The clean window is only about 4.5 months (2026-07 to now), too short for statistical conclusions on 4h/1d timeframes.
- Every switch to a newer model shrinks the clean window again.
- The only approach with lasting value is **continuous forward testing / paper trading**, recording decisions before the outcome is known.

### 2.3 Non-determinism

- **AlphaForgeBench** ([2602.18481](https://arxiv.org/abs/2602.18481)): LLMs as trading agents show very high run-to-run variance, inconsistent action sequences **even with deterministic decoding**, and frequent irrational action flips between adjacent time steps. The authors attribute this to the stateless nature of LLMs and the sensitivity of mapping continuous to discrete. Proposal: have the LLM **generate executable alpha factors** instead of issuing orders directly.
- **Specifically for the Claude API**: you can no longer "fix the temperature". The [API versions](https://platform.claude.com/docs/en/api/versioning) page says for version `2026-10-21`: "The `temperature`, `top_p`, and `top_k` request parameters are removed. A request that sends any of them returns a 400 error on every model." A `seed` parameter for the Claude API: not seen in the pages read **[non-existence unverified]**.
- Beyond sampling there are other sources of non-determinism: provider infrastructure updates, model alias changes (Claude from generation 4.6 uses undated IDs, but they are fixed snapshots), prompt changes, tool result ordering.

Living with non-determinism:

1. Store **all** requests and responses; treat the record as the source of truth, replay from the record instead of calling the model again.
2. For each decision point in evaluation, run N times (e.g. 5) and report the distribution: direction agreement rate, standard deviation of confidence. Treat non-agreeing decisions as `neutral`.
3. Narrow the output space: enums instead of free text, numbers computed by code.
4. Pin the model ID, pin the SDK version, hash the system prompt and schema, write all of it to the log.

### 2.4 Cost and latency

- QuantHarness admits each cycle (one LLM call plus many tool calls) can be longer than a 1-minute opportunity window. The paper title says "High-Frequency" but in practice it's 1h/4h timeframes.
- TradingAgents-style systems call the LLM dozens of times per decision.
- Cost grows linearly with tickers × timeframes × frequency × agents × N repetitions. Estimates in section 5.6.
- LLM cost is a fixed cost deducted directly from profit; for small accounts it can exceed the expected edge.

### 2.5 Evaluation design checklist

| Principle | Concrete practice |
|---|---|
| Score only after the knowledge cutoff | Record `model_id` and its cutoff with each decision; exclude every sample with time ≤ cutoff from the main results table. For current Claude: count only from 2026-07 |
| Forward testing is the gold standard | Run paper trading; record decisions with timestamps before the next candle closes; append-only log |
| Compare with simple baselines | Buy-and-hold, random with the same frequency and long/short distribution, MA crossover, linear regression slope (the baseline QuantHarness loses to on returns), and **the project's own deterministic layer without the LLM** |
| Ablation | Run the pipeline with and without each agent; if removing the LLM leaves results unchanged, the LLM contributes nothing |
| Account for all friction | Fees, spread, slippage, funding rate (perps), latency from candle close to decision |
| Measure both profit and accuracy | Return, Sharpe, Sortino, max drawdown, turnover, along with directional accuracy and calibration of `confidence` (Brier score, reliability diagram) |
| Enough samples, multiple regimes | Many assets, including up, down, and sideways periods; report bootstrap confidence intervals |
| Control non-determinism | N runs per point, report variance; store and replay responses |
| Guard against self-deception | Pre-register hypotheses and metrics; count prompt variants tried (multiple testing); lock prompts before opening the test set |
| Full logging | See section 7.3 |

Set a stopping criterion in advance: if after K months of forward testing the LLM layer does not beat the deterministic layer with statistical significance, keep the LLM in the role of writing interpretive reports and drop its signal-generation role.

---

## 3. Agent frameworks

### 3.1 LangGraph

Sources: [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview), [persistence](https://docs.langchain.com/oss/python/langgraph/persistence). Repo [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph), MIT, 44.9k stars. Install: `pip install -U langgraph`.

LangGraph describes itself as a low-level orchestration framework for long-running stateful agents. It imposes no prompts or agent architecture, and lets you mix deterministic steps with LLM-driven steps in the same graph.

- **State**: a shared data structure (usually a `TypedDict` or Pydantic model) that every node reads and writes. Each key can have a **reducer** defining how updates are merged (overwrite, append to list...) **[reducer concept not re-read from the docs in this session]**.
- **Node**: a Python function that takes state and returns the part of state to update. A node can call an LLM, or be plain code.
- **Edge**: connects nodes. Edges are usually fixed; a **conditional edge** uses a routing function that reads state to choose the next node. There are two special nodes, `START` and `END`.
- **Checkpoint**: when a graph is compiled with a checkpointer, state is saved as checkpoints per `thread_id`. The docs list uses: per-thread short-term memory, human-in-the-loop, time travel, fault tolerance. Checkpointer libraries: `InMemorySaver` (lost on restart), `SqliteSaver` (local development), `PostgresSaver`/`AsyncPostgresSaver` (production, requires calling `setup()`).
- **Interrupt**: pause the graph, let a human view or edit state, then resume. This is the right mechanism for a "human approval" step.

Minimal example from the docs:

```python
from langgraph.graph import StateGraph, MessagesState, START, END

def mock_llm(state: MessagesState):
    return {"messages": [{"role": "ai", "content": "hello world"}]}

graph = StateGraph(MessagesState)
graph.add_node(mock_llm)
graph.add_edge(START, "mock_llm")
graph.add_edge("mock_llm", END)
graph = graph.compile()
```

Pros: explicit control flow, drawable, nodes testable individually; checkpoints and interrupts built in; QuantHarness and TradingAgents both use it, so easy to compare. Cons: adds a dependency and an abstraction layer; if `langchain-anthropic` is used as the model layer, new Claude API features (structured output, cache breakpoints, effort) may arrive late or be hidden. You can use LangGraph only for orchestration and call the `anthropic` SDK directly inside nodes.

### 3.2 Claude Agent SDK

Source: [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview). Repo [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python), MIT.

This is Claude Code packaged as a library (Python, TypeScript): it runs the Claude Code binary, with built-in tools for reading/writing/editing files, running commands, web search, plus hooks, subagents, MCP, permissions, sessions. The docs clearly distinguish it from the Client SDK: the Client SDK is direct Claude API access, where you write the tool loop yourself or use the tool runner.

- Good for: agents that need file and shell access, e.g. a research agent that writes and runs backtest notebooks itself.
- Not good for: analysis pipelines with a fixed structure, run thousands of times, needing per-token control. Giving an agent shell access in a money-related system expands the risk surface unnecessarily.
- Terms: SDK use is governed by Anthropic's Commercial Terms of Service; authenticate with an API key, do not use claude.ai login for third-party products.

### 3.3 OpenAI Agents SDK

Source: [docs](https://openai.github.io/openai-agents-python/). Repo [openai/openai-agents-python](https://github.com/openai/openai-agents-python), MIT, 30.6k stars. Install: `pip install openai-agents`.

Primitives: Agents, Handoffs / agents-as-tools, Guardrails (input and output checks), Sessions, built-in Tracing. Uses OpenAI's Responses API by default; has LiteLLM and Any-LLM adapters for other providers. A fit if the project picks OpenAI as its main provider. Using Claude through an adapter loses Claude API-specific features.

### 3.4 CrewAI

Source: [docs](https://docs.crewai.com/en/introduction). Repo [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI), MIT, 60.8k stars.

Two concepts: **Flows** (the backbone: steps, logic, state, conditions, loops) and **Crews** (groups of role-playing agents collaborating on tasks assigned by a Flow). The docs recommend starting with a Flow and calling a Crew inside a step when autonomy is needed. Fast to build, easy to read. Weakness for this project: the role-play model (role/goal/backstory) encourages LLMs to "discuss", whereas the project needs schema-bound output and a fixed flow.

### 3.5 AutoGen and Microsoft Agent Framework

The README of [microsoft/autogen](https://github.com/microsoft/autogen) says AutoGen is in **maintenance mode**; new users should start with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) (MIT, 14.7k stars). Agent Framework 1.0 went GA in April 2026 **[exact date unverified, sources differ between April 2–8]**. The community fork [ag2ai/ag2](https://github.com/ag2ai/ag2) (Apache-2.0) is still developed; the PyPI package `autogen` points to AG2 **[unverified]**. Don't start new projects on AutoGen.

### 3.6 PydanticAI

Source: [docs](https://pydantic.dev/docs/ai/overview/). Repo [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai), MIT, 21.2k stars.

Output validated by type (Pydantic models); dependency injection via `RunContext`; switch models with a string, Anthropic supported; Pydantic Graph for typed control flow; durable execution via Temporal/DBOS/Prefect; Pydantic Evals; MCP; OpenTelemetry. Human-in-the-loop via "deferred tools": a run can pause waiting for a human to approve a tool call. A very good fit for the project's "schema first" philosophy. Consideration: a multi-provider abstraction layer can lag the native SDK on new features.

### 3.7 Writing your own tool-use loop

The `anthropic` SDK offers two levels ([tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [tool runner](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner)):

**Tool runner** (a beta SDK helper that runs the loop for you):

```python
import anthropic
from anthropic import beta_tool

client = anthropic.Anthropic()

@beta_tool
def compute_rsi(symbol: str, timeframe: str, period: int = 14) -> str:
    """Compute RSI from stored OHLC data.

    Args:
        symbol: Ticker, e.g. BTCUSDT.
        timeframe: Candle timeframe, e.g. 1h or 4h.
        period: RSI period.
    """
    return indicators.rsi_json(symbol, timeframe, period)  # the project's deterministic function

runner = client.beta.messages.tool_runner(
    model="claude-opus-5-5",
    max_tokens=16000,
    tools=[compute_rsi],
    messages=[{"role": "user", "content": "Assess BTCUSDT momentum on the 4h timeframe."}],
)
for message in runner:
    log(message)
```

**Manual loop**: call `client.messages.create(...)`; if `stop_reason == "tool_use"`, run the requested tools, append `{"role": "assistant", "content": response.content}` and a `user` message containing **all** `tool_result`s (keyed by `tool_use_id`), then call again, until `stop_reason` is not `tool_use`. Set a cap on the number of iterations.

Pros: no framework dependency, every request is visible, easy logging, every API feature usable immediately. Cons: you handle checkpointing, retries, parallelism, interrupts yourself.

### 3.8 When to use which

| Situation | Choice |
|---|---|
| Fixed pipeline: compute → a few interpreting agents → aggregate → report | Plain Python calling the `anthropic` SDK, each agent one call with structured output. Sufficient for the early phase |
| Need conditional branches, parallelism, pausing for human approval, recovery after failure | LangGraph as the orchestration layer, nodes calling the `anthropic` SDK directly |
| Want strict typing and easy provider switching | PydanticAI |
| Research agent that writes code, runs backtests, reads files | Claude Agent SDK, run in a sandbox, separated from the signal system |
| OpenAI already chosen as main provider | OpenAI Agents SDK |
| Quick role-play prototype | CrewAI |
| New project | Don't use AutoGen |

Recommendation for the project: start with plain code using the `anthropic` SDK. Since QuantHarness has a nearly linear flow (three parallel agents → risk → decision), it does not need a framework yet. Move to LangGraph when checkpoints and interrupts are truly needed, and keep each agent's interface a `(state) -> dict` function so the switch requires no rewrite.

---

## 4. Techniques the project needs

### 4.1 Tool calling / function calling

The model does not run code. It returns a `tool_use` block with the tool name and arguments; the application runs the function and sends back a `tool_result`. Per the [tool use docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview):

- Client tools run in your application; server tools (web search, code execution) run on Anthropic's infrastructure.
- A tool definition has `name`, `description`, `input_schema`. Add `strict: true` so arguments always match the schema.
- `tool_choice` defaults to `{"type": "auto"}`. You can limit to one tool per turn with `disable_parallel_tool_use: true`.
- When `tools` is present, the API adds a tool-use system prompt: 286 tokens on Opus 5.5, Sonnet 5.5, Haiku 5.5.
- On Opus 5.5 and Sonnet 5.5, the docs' token table leaves the `any`/`tool` columns blank; forced tool calls (`tool_choice` of type `any` or `tool`) are not available on these models **[exact wording in the web docs not directly verified; taken from SDK reference docs]**. Use `auto` with instructions in the prompt, or structured output.

The tool description is the most important part: state clearly what the tool returns, units, and when to call it.

### 4.2 Structured output (JSON schema)

Source: [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

- Put the schema in `output_config.format` with `type: "json_schema"`; the response is schema-conforming JSON in a text block.
- The Python SDK has `client.messages.parse(..., output_format=PydanticModel)`, returning a validated `response.parsed_output`.
- **Schema limits** to know when designing:
  - Supported: object, array, string, integer, number, boolean, null; `enum`; `const`; `anyOf`; internal `$ref`; `required`; `additionalProperties: false`.
  - **Not supported**: `minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, recursive schemas, `additionalProperties` other than `false`. Using them returns a 400 error.
  - Consequence: `confidence` cannot be constrained to [0, 1] at the schema level. Validate in code.
  - A free-form `dict` field becomes an empty object; use nested models with fixed keys.
- Compiled grammars are cached for 24 hours; the first request with a new schema is slower. Changing `output_config.format` invalidates that conversation's prompt cache.
- Cannot be combined with citations.

Structured output guarantees **shape**, not **correct content**. Business checks are still needed: stop on the correct side of the entry price, sensible R:R, cited numbers matching input numbers.

### 4.3 Feeding chart images to a vision model

Source: [Vision](https://platform.claude.com/docs/en/build-with-claude/vision).

**Limits and cost:**

- Formats: JPEG, PNG, GIF, WebP.
- At most 8000×8000 px per image; 10 MB per image (base64) on the Claude API; at most 600 images per request (100 for 200k-context models). Above 20 images in one request, the per-image size limit is stricter.
- Cost: images are split into 28×28 px patches, each patch one visual token. Tokens = `⌈width/28⌉ × ⌈height/28⌉`.
- Resolution cap: Claude 4.7 and later models have a max long edge of 2,576 px and at most 4,784 visual tokens; older models 1,568 px and 1,568 tokens. Larger images are downscaled before processing.

| Size | Tokens (4.7+ models) | Notes |
|---|---|---|
| 1000×1000 | 1,296 | Not resized |
| 1092×1092 | 1,521 | Not resized |
| 1456×819 (16:9) | 1,560 | Self-computed: ⌈1456/28⌉ × ⌈819/28⌉ = 52 × 30 |
| 1920×1080 | 2,691 | |
| 3840×2160 | 4,784 | Downscaled to 2576×1449 |

- The docs advise: put images **before** text in the message; resize yourself before sending to control cost and latency; heavy lossy compression can make text hard to read.
- Limitations stated in the docs: coordinates and spatial localization are only approximate; counting many small objects is inaccurate; small images under 200 px are easily misread.

**Chart rendering recommendations** (design experience, no project-specific benchmark yet; A/B on forward tests):

- Default size **1456×819 PNG** (about 1,560 tokens): clear enough, fixed cost, same size for every call so results are comparable.
- 60–120 candles per image. More than that and candle bodies are only a few pixels, and the model counts small objects poorly.
- White or light background, contrasting candle colors, no gradients, no logos, no watermarks.
- Title containing symbol, timeframe and the last candle's time. During **evaluation**, hide symbol and dates (use candle indices) to reduce leakage per section 2.2.
- Price axis on the right with large enough labels; draw labeled horizontal lines for key levels (POC, VAH/VAL, order blocks, swing highs/lows). Don't make the model read prices from pixels.
- One purpose per image: one image for price + volume, a separate one for structure (trendlines, SMC zones). At most 2–3 overlays per image.
- Always send **JSON numbers** for everything drawn on the chart. The image is for the model to recognize shapes; the numbers are for it to cite.

With `mplfinance` (note: the [repo](https://github.com/matplotlib/mplfinance) last pushed 2024-08, so pin the version):

```python
import io
import mplfinance as mpf

def render_chart_png(df, levels: list[float], title: str) -> bytes:
    """df: DataFrame with a DatetimeIndex and columns Open, High, Low, Close, Volume."""
    buf = io.BytesIO()
    mpf.plot(
        df.tail(100),
        type="candle",
        style="yahoo",
        volume=True,
        mav=(20, 50),
        hlines=dict(hlines=levels, linestyle="--", linewidths=0.8),
        title=title,
        figsize=(14.56, 8.19),          # × dpi 100 = 1456×819 px
        savefig=dict(fname=buf, dpi=100, format="png"),
    )
    return buf.getvalue()
```

Don't use `bbox_inches="tight"` because it changes the pixel size between renders.

With `plotly` (static image export needs the `kaleido` package):

```python
import plotly.graph_objects as go

fig = go.Figure(go.Candlestick(
    x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"]))
fig.update_layout(template="plotly_white", xaxis_rangeslider_visible=False,
                  title=title, margin=dict(l=40, r=60, t=50, b=40))
for lv in levels:
    fig.add_hline(y=lv, line_dash="dash", annotation_text=f"{lv:g}")
png_bytes = fig.to_image(format="png", width=1456, height=819, scale=1)
```

### 4.4 Prompt caching

Source: [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

- The cache is **prefix matching**, in the order `tools` → `system` → `messages`. A change at one level invalidates the cache for that level and every level after it.
- Two ways to enable: automatic (a single top-level `cache_control: {"type": "ephemeral"}` field in the request) or explicit breakpoints on individual content blocks. At most 4 breakpoints.
- TTL: 5 minutes (default, write price 1.25× input) or 1 hour (`"ttl": "1h"`, write price 2× input). Cache reads cost 0.1× input; Opus 5.5 and Sonnet 5.5 are 0.05×, Fable 5.2 is 0.025×.
- Minimum cacheable length: **512 tokens** on Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5. Shorter prompts are not cached, with no error.
- Adding or removing **images** anywhere invalidates the messages-level cache (tools and system levels are kept). Changing tool definitions invalidates everything.
- Check with `usage.cache_read_input_tokens` and `usage.cache_creation_input_tokens`.

Applied to the project: the stable part (tool definitions, each agent's system prompt, chart-reading instructions, SMC/volume profile definitions) goes first and is cached; the parts that change each time (indicator dict, chart image, timestamp) go in the last message. Don't put timestamps or random IDs in the system prompt. Serialize JSON with `sort_keys=True`.

### 4.5 Batch API

Source: [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing).

- **50%** price reduction. At most 100,000 requests or 256 MB per batch. Most batches finish within 1 hour; they expire after 24 hours. Results are kept for 29 days.
- Supports vision, tool use, prompt caching (cache hits are best-effort; the docs recommend a 1-hour TTL). Does not support `stream`, `speed`, `fallbacks`, `max_tokens: 0`.
- Results come back unordered; match them by `custom_id`.
- Not eligible for zero data retention.

Applied: batch fits **bulk evaluation** (N runs × many tickers × many time points), end-of-day reports, and the 1d timeframe. Not suitable for 1h decisions that need results within minutes.

### 4.6 Controlling cost and latency

In recommended order:

1. **Call the LLM less.** The deterministic layer filters first: only call the LLM on events (price touching a zone, a new BOS/CHoCH, a candle close on the main timeframe). Most candles don't need the LLM.
2. **Don't use a tool loop when unnecessary.** If you know in advance which indicators are needed, precompute them and put them in the prompt in a single call. Tool loops multiply requests and latency. Only let the agent call tools on a "deep dive" branch.
3. **Run independent interpreting agents in parallel** (`asyncio` with `AsyncAnthropic`).
4. **Prompt caching** for the stable part.
5. **Choose models by role** (section 5.6) and set low `effort` for simple tasks. Measure on forward tests before lowering.
6. **Batch** everything non-urgent.
7. **Fixed image size** at just-enough resolution.
8. **Hard caps**: sensible `max_tokens`, iteration limits, a daily USD budget with a circuit breaker, a timeout per request.
9. **Measure**: record `usage` and duration of each request; compute cost per decision, not just per request.

### 4.7 Have agents call deterministic functions instead of computing numbers themselves

Principle: **the LLM is never the source of a number.** LLMs do mental arithmetic wrong, and it's not reproducible. Every number in a report must trace back to a versioned deterministic function.

Two ways to feed numbers in:

- **Precompute** (preferred): the pipeline calls `indicators.compute(df)`, `volume_profile.compute(df)`, `smc.detect(df)` and puts the JSON results into the prompt. One LLM call, deterministic inputs.
- **On-demand tools**: define tools for rarely used or expensive computations (changing timeframe, per-session profiles, a quick backtest of one condition). Use `strict: true`.

Tool and data design rules:

- Tools only accept **identifier parameters** (symbol, timeframe, period, number of candles). Tools do not accept price arrays typed by the model; price data always comes from the project's store by `data_snapshot_id`.
- Tools return compact JSON with units, an `as_of` (time of the last **closed** candle), and a `calc_version`.
- Round numbers to tick size before giving them to the model.
- Return **events already interpreted at the deterministic level** instead of raw number series: "RSI(14) = 71.3, above 70 since 3 candles ago", "bullish order block at 61,200–61,450, not yet mitigated", "price 2.1% above VAH". The model interprets combinations of events, rather than detecting them from number series.
- **Stop and take-profit**: let the deterministic layer generate candidate levels (ATR, nearest swing, order block edge, VAL/VAH). The LLM **chooses** from the candidate list, or code chooses and the LLM only explains. QuantHarness does something similar: fixed stop, the LLM only picks the r multiplier.
- Post-check: every number appearing in `rationale` must match a value in the input (tolerance-based matching); if it doesn't, flag and discard.

---

## 5. Claude API specifics

All information in this section was read from the official docs on 2026-11-13. Prices are in USD per million tokens (MTok).

### 5.1 Current models

Source: [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview).

| | Claude Fable 5.2 | Claude Opus 5.5 | Claude Sonnet 5.5 | Claude Haiku 5.5 |
|---|---|---|---|---|
| Claude API ID | `claude-fable-5-2` | `claude-opus-5-5` | `claude-sonnet-5-5` | `claude-haiku-5-5` |
| Anthropic's description | Hard reasoning, long-horizon agentic work | Long-running agentic coding and knowledge work | Balance of speed and intelligence | High volume, latency-sensitive: classification, extraction, routing |
| Relative latency | Moderate | Moderate | Fast | Fastest |
| Context window | 1M tokens | 1M tokens | 1M tokens | 1M tokens |
| Max output | 128K tokens | 128K tokens | 128K tokens | 128K tokens |
| Thinking | Adaptive (always on) | Adaptive (always on) | Adaptive | Adaptive |
| Default effort | `high` | `medium` | `high` | `medium` |
| Reliable knowledge cutoff | 2026-06 | 2026-06 | 2026-06 | 2026-06 |
| Training data cutoff | 2026-06 | 2026-06 | 2026-06 | 2026-06 |

- The docs advise: if unsure, start with Claude Opus 5.5 for most workloads.
- "All current models support text and image input, text output, multilingual capabilities, vision, and tool use."
- Every model ID is a fixed snapshot, including undated IDs from generation 4.6 onward.
- Older models still available (full list on the page above): Opus 5, Opus 4.8/4.7/4.6/4.5, Sonnet 5, Sonnet 4.6/4.5, Haiku 4.5, Fable 5.1/5. Claude Mythos is a restricted-access line.
- Capabilities and token limits can be queried via the [Models API](https://platform.claude.com/docs/en/api/models/list) (`max_input_tokens`, `max_tokens`, `capabilities`).

### 5.2 Pricing

Source: [Pricing](https://platform.claude.com/docs/en/about-claude/pricing).

| Model | Input | 5-min cache write | 1-hour cache write | Cache read | Output | Batch input | Batch output |
|---|---|---|---|---|---|---|---|
| Claude Fable 5.2 | $8 | $10 | $16 | $0.20 | $40 | **[unverified]** | **[unverified]** |
| Claude Opus 5.5 | $4 | $5 | $8 | $0.20 | $20 | $2 | $10 |
| Claude Sonnet 5.5 | $2 | $2.50 | $4 | $0.10 | $10 | $1 | $5 |
| Claude Haiku 5.5 (prompt ≤ 100,000 tokens) | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 | $0.05 | $0.25 |
| Claude Haiku 5.5 (prompt > 100,000 tokens) | $0.50 | $0.625 | $1 | $0.05 | $2.50 | $0.25 | $1.25 |
| Claude Haiku 4.5 | $1 | $1.25 | $2 | $0.10 | $5 | $0.50 | $2.50 |

Notes from the pricing page:

- Batch is 50% off (the Models overview page says "Batch API requests are 50% off"). The Fable 5.2 row in the batch table was cut off during research, so it is left blank.
- 1M-token context is billed at standard rates on 4.6+ models, except Haiku 5.5 which is priced by prompt length (100,000-token threshold, including cache read and write tokens).
- US-only inference (`inference_geo`) multiplies all token types by 1.1×.
- Cache multipliers stack with the batch discount.
- Claude 4.7 and later models use a new tokenizer that produces about 30% more tokens for the same text than older models.
- Thinking tokens are billed as output **[exact wording in the web docs unverified in this session]**; since thinking is always on for Opus 5.5 and Fable 5.2, actual output cost is higher than the visible JSON.

### 5.3 Feature support

| Feature | Status | Source |
|---|---|---|
| Vision | All current models; JPEG/PNG/GIF/WebP; base64, URL, or `file_id` sources | [Vision](https://platform.claude.com/docs/en/build-with-claude/vision) |
| Tool use | All current models; `strict: true` for strict schemas | [Tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) |
| Structured output | `output_config.format`; the page metadata lists `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` and other models | [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) |
| Prompt caching | All active models | [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) |
| Batch | All active models; on the Claude API | [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing) |

### 5.4 Common pitfalls

- **No temperature.** API version `2026-10-21` removes `temperature`, `top_p`, `top_k`; sending them returns a 400 error on every model ([API versions](https://platform.claude.com/docs/en/api/versioning)). Intermediary libraries (LangChain, LiteLLM) may still send these fields if configured to.
- **Thinking is always on** for Opus 5.5 and Fable 5.2; adjust depth with `output_config.effort` ([Effort](https://platform.claude.com/docs/en/build-with-claude/effort)).
- **`stop_reason`** must be checked before reading content: `max_tokens` means the JSON may be truncated; `refusal` means the model declined. There is a `fallbacks` parameter (beta) to automatically retry on another model after a refusal ([Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)) **[details unverified in this session]**; not usable with Batch.
- **Structured output does not support `minimum`/`maximum`**: validate value ranges in code.

### 5.5 Python example: an agent takes an indicator dict + chart image, returns JSON

Install: `pip install anthropic pydantic`. The SDK reads `ANTHROPIC_API_KEY` from the environment. The request shape (base64 `image` block, `output_config.format`, `cache_control` on the system block, the `usage` field) follows the docs pages cited above. This code was not run during this research session.

```python
"""Interpreting agent: indicator dict + chart image -> TradeView (schema-bound JSON)."""
import base64
import hashlib
import json
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
PROMPT_VERSION = "interpreter-v1"

SYSTEM_PROMPT = """You are the technical interpretation agent in a decision-support system.
You do NOT place orders. Your output is reviewed by a human before any action.

Rules:
- Only use numbers present in the <indicators> block. Do not compute or estimate new numbers.
- The chart image is for recognizing shapes and structure; do not read prices from the image.
- stop and take_profit must be chosen from the stop_candidates and tp_candidates lists.
- If signals conflict or are insufficient, return direction = "neutral", stop = null, take_profit = null.
- confidence is a subjective probability between 0 and 1 that direction is correct after 3 candles.
- rationale: at most 5 sentences, each claim citing a field name in <indicators>.
"""
# A real prompt should be longer (SMC and volume profile definitions, examples). Under 512 tokens,
# Opus 5.5 does not cache and raises no error.


class TradeView(BaseModel):
    direction: Literal["long", "short", "neutral"]
    confidence: float
    rationale: str
    stop: Optional[float]
    take_profit: Optional[float]


# Schema written by hand because structured output does not support minimum/maximum.
TRADE_VIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["long", "short", "neutral"]},
        "confidence": {"type": "number", "description": "From 0 to 1"},
        "rationale": {"type": "string"},
        "stop": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "take_profit": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": ["direction", "confidence", "rationale", "stop", "take_profit"],
    "additionalProperties": False,
}

client = anthropic.Anthropic()


def analyze(indicators: dict, chart_png: bytes) -> tuple[TradeView, dict]:
    """indicators must contain last_close, stop_candidates, tp_candidates."""
    indicators_json = json.dumps(indicators, sort_keys=True, ensure_ascii=False)
    image_b64 = base64.standard_b64encode(chart_png).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": TRADE_VIEW_SCHEMA},
        },
        messages=[{
            "role": "user",
            "content": [
                {   # image placed before text
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                },
                {
                    "type": "text",
                    "text": f"<indicators>\n{indicators_json}\n</indicators>\n"
                            "Give your assessment according to the schema.",
                },
            ],
        }],
    )

    audit = {
        "request_id": response.id,
        "model": response.model,
        "prompt_version": PROMPT_VERSION,
        "system_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "indicators_sha256": hashlib.sha256(indicators_json.encode()).hexdigest(),
        "chart_sha256": hashlib.sha256(chart_png).hexdigest(),
        "stop_reason": response.stop_reason,
        "usage": response.usage.model_dump(),
    }

    if response.stop_reason != "end_turn":
        # "max_tokens": JSON may be truncated; "refusal": the model declined.
        raise RuntimeError(f"No valid result: stop_reason={response.stop_reason}")

    text = next(b.text for b in response.content if b.type == "text")
    view = TradeView.model_validate_json(text)
    check_business_rules(view, indicators)
    return view, audit


def check_business_rules(view: TradeView, indicators: dict) -> None:
    """The schema guarantees shape; this function guarantees valid content."""
    if not 0.0 <= view.confidence <= 1.0:
        raise ValueError("confidence outside [0, 1]")
    if view.direction == "neutral":
        if view.stop is not None or view.take_profit is not None:
            raise ValueError("neutral must not have stop/take_profit")
        return
    if view.stop not in indicators["stop_candidates"]:
        raise ValueError("stop not in the candidate list")
    if view.take_profit not in indicators["tp_candidates"]:
        raise ValueError("take_profit not in the candidate list")
    last = indicators["last_close"]
    if view.direction == "long" and not view.stop < last < view.take_profit:
        raise ValueError("long: requires stop < last_close < take_profit")
    if view.direction == "short" and not view.take_profit < last < view.stop:
        raise ValueError("short: requires take_profit < last_close < stop")
```

Notes:

- The hand-written schema can be replaced with `client.messages.parse(..., output_format=TradeView)`; the SDK converts the Pydantic model into a schema and returns `response.parsed_output`.
- `audit`, together with verbatim copies of the request and response, is the input to the audit log in section 7.3.
- When a business rule is violated: do not fix the output by hand. Record the violation and treat the decision as `neutral`.

### 5.6 Cost estimate per call

Assumptions: one 1456×819 image (1,560 tokens), about 1,500 tokens of input text, about 600 tokens of JSON output. **Thinking tokens not included** (billed as output, depends on `effort`) and caching not included.

| Model | Input 3,060 tokens | Output 600 tokens | Total per call | With Batch (−50%) |
|---|---|---|---|---|
| Claude Opus 5.5 | $0.0122 | $0.0120 | about $0.024 | about $0.012 |
| Claude Sonnet 5.5 | $0.0061 | $0.0060 | about $0.012 | about $0.006 |
| Claude Haiku 5.5 | $0.0003 | $0.0003 | about $0.0006 | about $0.0003 |

Example: 10 tickers × 2 timeframes × 3 interpreting agents + 1 synthesis, on every 4h candle (6 times a day) is 10 × 2 × 4 × 6 = 480 calls per day, about 11.5 USD per day with Opus 5.5 before thinking. Multiply by N = 5 if repeating runs to measure non-determinism. Event filtering (section 4.6) is the biggest lever.

Suggested role split, to be validated by measurement on the project's own data: Haiku 5.5 or Sonnet 5.5 for individual interpreting agents; Opus 5.5 for the synthesis agent and report writing.

---

## 6. Finance / crypto / TradingView MCP servers

MCP (Model Context Protocol) lets a model call tools on an external server. The trust levels below are assessments for use within this project.

| Server | Source | Official? | Provides | Trust level |
|---|---|---|---|---|
| **TradingView MCP Server** (beta) | [tradingview.com/mcp/docs](https://www.tradingview.com/mcp/docs), URL `https://mcp.tradingview.com/mcp` | Yes, by TradingView | Historical OHLCV (up to 5,000 candles per call), indicator snapshots, screener, news, fundamentals, economic calendar, watchlists, simple price alerts. **No** chart screenshots, Pine Script, or order placement | High in provenance. In beta; OAuth 2.1 with a TradingView account; requires the Essential plan or higher; about 100 tool calls per minute. Data usage terms for automated systems **[unverified]** |
| **CoinGecko MCP** | [docs.coingecko.com/docs/mcp-server](https://docs.coingecko.com/docs/mcp-server); npm package `@coingecko/coingecko-mcp` | Yes, by CoinGecko | Current and historical price, market cap, volume; exchange data; on-chain DEX. Keyless endpoint at `https://mcp.api.coingecko.com/mcp` | High in provenance. The free tier shares a rate limit |
| **Alpaca MCP Server** | [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server), MIT, 1.1k stars, pushed 2026-11-12 | Yes, by Alpaca | Data and **trading** for stocks, ETFs, crypto, options | High in provenance. **Can place orders**: if used, only with a paper account and read-only keys |
| **Financial Datasets MCP** | [financial-datasets/mcp-server](https://github.com/financial-datasets/mcp-server), MIT, 2.3k stars | By the API provider | Financial statements, stock prices, news | Medium: last push 2025-06 |
| **tradingview-mcp** (atilaahmettaner) | [repo](https://github.com/atilaahmettaner/tradingview-mcp), MIT, 5.3k stars, pushed 2026-11-10 | No. The README says it is not affiliated with TradingView Inc. | 39 tools: screener, multi-timeframe analysis, candlestick patterns, backtesting, sentiment; built on the `tradingview_ta`, `tradingview-screener` libraries and Yahoo Finance | Low to medium: data via unofficial public endpoints, may be delayed or wrong. The README warns of fake copies with malicious npm packages |
| **tradingview-mcp** (tradesdontlie) | [repo](https://github.com/tradesdontlie/tradingview-mcp), 7.2k stars, pushed 2026-10-21 | No | Controls TradingView Desktop via the Chrome DevTools Protocol (port 9222): reads charts, Pine Script, replay, screenshots. No live order placement | Low: uses undocumented internal interfaces that can break at any time. The README itself notes it may conflict with TradingView's Terms of Use and forbids using extracted data for automated trading |
| CCXT-wrapping servers (e.g. [Nayshins/mcp-server-ccxt](https://github.com/Nayshins/mcp-server-ccxt)) | Community | No | Prices, order books, candles from many exchanges via CCXT | Low: small repos, license and maintenance status **[unverified]** (GitHub API rate-limited during lookup) |

No official Binance MCP server was found in this session **[unverified]**.

**Recommendations for the project:**

- The data and computation core should **not** go through MCP. Use Python libraries directly ([ccxt](https://github.com/ccxt/ccxt), MIT; exchange APIs; `yfinance`), storing versioned snapshots. MCP adds a non-deterministic, hard-to-reproduce layer.
- MCP is useful at the **interactive** layer: when the user asks free-form questions in Claude Code or Claude Desktop and needs a quick data lookup.
- If the project's indicator, volume profile, and SMC functions are packaged as its own MCP server, the same set of functions can serve both the pipeline and interactive sessions.
- Never give an agent an MCP server with tools for placing orders, withdrawing, or transferring funds. Read-only servers still require: pinning versions, reading the code before running it, issuing read-only API keys, and treating server-returned content (news, descriptions) as untrusted data that may contain prompt injection.

---

## 7. Proposed architecture for the project

### 7.1 Four layers

```
┌──────────────────────────────────────────────────────────────────────┐
│ L1  DETERMINISTIC COMPUTATION (no LLM)                               │
│     data snapshot (OHLCV, with id) → indicators, volume profile, SMC │
│     → detected events + candidate stop/TP levels + chart images      │
│     → event filter: is it worth calling the LLM?                     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ features (JSON) + chart (PNG) + hash
┌──────────────────────────────▼───────────────────────────────────────┐
│ L2  INTERPRETING AGENTS (parallel, one call each, schema-bound)      │
│     IndicatorAgent │ StructureAgent (SMC + volume profile, image)    │
│     │ TrendAgent (image)                                             │
│     Each agent sees only its own data; output is AgentView           │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ list of AgentView
┌──────────────────────────────▼───────────────────────────────────────┐
│ L3  SYNTHESIS AGENT                                                  │
│     Risk checks in code (R:R, stop distance, position limits)        │
│     → SynthesisAgent: merge, surface conflicts, final TradeView      │
│     → deterministic post-check (business rules, number matching)     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ checked TradeView
┌──────────────────────────────▼───────────────────────────────────────┐
│ L4  REPORT + HUMAN REVIEW                                            │
│     Markdown/HTML report: assessment, chart, tables, source per number│
│     → reviewer: accept / reject / note (logged)                      │
│     → NO path from here to an order-placement API                    │
└──────────────────────────────────────────────────────────────────────┘
```

Deliberate differences from QuantHarness:

- RiskAgent is replaced by **code**: candidate stop/TP levels and risk limits are deterministic; the LLM only chooses from the list and explains.
- Interpreting agents do not call tools in the main flow; numbers are precomputed. This cuts request count and makes inputs reproducible.
- There is a `neutral` state and a human review step. QuantHarness only outputs LONG/SHORT.
- Layer L1 is itself a complete signal system and the mandatory baseline for measuring the contribution of L2–L3.

### 7.2 State schema

Use Pydantic so one definition serves validation, logging, and (if later needed) LangGraph state.

```python
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel

Direction = Literal["long", "short", "neutral"]


class RunMeta(BaseModel):
    run_id: str                      # UUID generated in L1, not put into prompts
    symbol: str
    timeframe: str
    as_of: datetime                  # close time of the last candle, UTC
    data_snapshot_id: str            # identifier of the immutable OHLCV set
    calc_version: str                # L1 code version (git SHA)
    mode: Literal["live", "paper", "eval"]


class Features(BaseModel):
    indicators: dict[str, float]     # RSI, MACD, ATR... rounded to tick size
    events: list[str]                # deterministic events, short sentences with numbers
    volume_profile: dict[str, float] # poc, vah, val
    smc: list[dict]                  # order blocks, FVGs, BOS/CHoCH with price levels
    last_close: float
    stop_candidates: list[float]
    tp_candidates: list[float]
    features_sha256: str


class ChartRef(BaseModel):
    kind: Literal["price_volume", "structure", "trend"]
    path: str                        # path to the immutable PNG file
    width: int
    height: int
    sha256: str


class LLMCall(BaseModel):
    request_id: str
    model: str
    prompt_version: str
    system_sha256: str
    request_path: str                # verbatim copy of the request
    response_path: str               # verbatim copy of the response
    stop_reason: str
    usage: dict
    latency_ms: int
    cost_usd: float


class AgentView(BaseModel):
    agent: str
    direction: Direction
    confidence: float
    rationale: str
    cited_fields: list[str]          # Features field names the agent relied on
    call: LLMCall


class RiskCheck(BaseModel):
    passed: bool
    reward_risk: Optional[float]
    violations: list[str]


class TradeView(BaseModel):
    direction: Direction
    confidence: float
    rationale: str
    stop: Optional[float]
    take_profit: Optional[float]
    disagreements: list[str]         # conflicts between agents
    call: LLMCall


class HumanReview(BaseModel):
    reviewer: str
    decision: Literal["approved", "rejected", "needs_changes"]
    note: str
    reviewed_at: datetime


class PipelineState(BaseModel):
    meta: RunMeta
    features: Features
    charts: list[ChartRef]
    deterministic_signal: Direction  # L1 signal without the LLM (baseline)
    agent_views: list[AgentView] = []
    risk: Optional[RiskCheck] = None
    final: Optional[TradeView] = None
    validation_errors: list[str] = []
    review: Optional[HumanReview] = None
    outcome: Optional[dict] = None   # filled LATER by the evaluation job: price after k candles
```

If moving to LangGraph: `agent_views` and `validation_errors` are keys that need a list-append reducer because several parallel nodes write to them; the other keys are overwritten.

### 7.3 Logging for decision audits

Goal: for any past decision, be able to answer "what did the system see, what did it say, with which model and prompt, who reviewed it, and what was the outcome" without calling the model again.

- **Append-only.** Each run is one JSONL record (or a `runs/{date}/{run_id}/` directory). Never edit old records; `outcome` and `review` are appended records referencing `run_id`.
- **Store verbatim** the request and response of every LLM call, including images (by hash). This is required for replay and to prove the decision preceded the outcome.
- **Identify every input**: `data_snapshot_id`, `calc_version` (git SHA), `prompt_version`, system prompt hash, schema hash, model ID, SDK version.
- **Timing**: `as_of` (last closed candle), LLM call time, result time, review time. The gap between `as_of` and result time is the latency to include in backtests.
- **Hash chain**: each record contains the hash of the previous record, to detect later tampering. The chain head hash can be published daily to an independent location.
- **Cost and performance**: `usage` (including cache tokens), latency, USD cost per call and per decision.
- **Errors are data too**: abnormal `stop_reason`, business rule violations, timeouts, retries are all recorded; the corresponding decision is recorded as `neutral` with the reason.
- **Parallel baseline**: always record `deterministic_signal` next to `final` for comparison on the same sample.
- **Security**: never log API keys or account information; log the request before adding authentication headers.

### 7.4 Guardrails

**Agents never place orders themselves.** This must be guaranteed by structure, not by prompt:

1. **No capability.** The process running agents has no trading API key, does not import an order client, and has no tool that writes to the outside world. Agent tools only read data from the internal store.
2. **Read-only API keys** for every exchange connection used in the pipeline; trade and withdraw permissions off; IP restrictions.
3. **Process separation.** If an execution module is added later, it is a separate service that only accepts orders from human action (clicking approve in the UI), with order size limits and a kill switch independent of the LLM.
4. **Always a human reviewer.** `TradeView` is only a proposal. The default state is "pending review"; there is no auto-approval based on a confidence threshold.

Other guardrails:

- **Two-tier validation**: schema (structured output) and business rules (code). Failure at either tier leads to `neutral`, no auto-fixing.
- **Number checks**: every number in `rationale` must match the input.
- **Stale data**: refuse to run if `as_of` is too far from now or the last candle has not closed.
- **Prompt injection**: the project only uses OHLC, so the surface is small. If news or MCP data is added later, that content must sit in a separate data block, and an agent reading untrusted content must have no tools other than read tools.
- **Budget**: daily USD cap, cap on calls per run, timeouts; on exceeding a cap, stop and report.
- **Show uncertainty**: reports always state the agreement level between agents, the deterministic baseline's signal, and a reminder that this is not investment advice.
- **Periodic evaluation**: a weekly job fills `outcome`, computes accuracy, calibration, and compares with the baseline. If the LLM layer does not beat the baseline per the criteria predefined in section 2.5, demote it to interpretation only.

### 7.5 Suggested roadmap

1. Complete L1 and the LLM-free report; measure the baseline.
2. Add a single interpreting agent (the example in section 5.5) with full logging; run on paper, collect post-cutoff samples.
3. Add the remaining agents and the synthesis agent; run ablations.
4. Only bring in LangGraph when branching, complex parallelism, or pausing for review within the same flow is needed.
5. In parallel, try an RD-Agent(Q)-style approach: use the LLM to propose factors/conditions, feed them into L1 as code, and test them like any other factor.

---

## 8. Unverified items

1. All Alpha Arena figures (dates, returns, winning models) come from the press; the original alphaarena.ai page returned HTTP 429. No information on Season 2.
2. Specific result figures for TradingAgents, FinMem; the venues of FinCon (NeurIPS 2024), FinAgent (KDD 2024), RD-Agent(Q).
3. FinRobot being built on AutoGen; AI Hedge Fund's agent list and use of LangGraph.
4. StockBench's evaluation window; details of Agent Market Arena, MemGuard-Alpha, the HKU FX study; FinLake-Bench's 85% figure (full text not read).
5. The Sarkar & Vafa paper on lookahead bias was not found in this session.
6. QuantHarness: the end of the v4 HTML version was not read (transaction costs, specific LLM); the chart library actually used in the repo.
7. Claude API: whether a `seed` parameter exists; Fable 5.2 batch pricing; official wording that thinking tokens are billed as output; details of the `fallbacks` parameter; web docs wording on Opus 5.5 and Sonnet 5.5 rejecting `tool_choice` of type `any`/`tool`.
8. The exact GA date of Microsoft Agent Framework 1.0; the PyPI package `autogen` pointing to AG2.
9. LangGraph's reducer, conditional edge, and time travel concepts described from background knowledge, not re-read from the corresponding docs pages; the current LangGraph version.
10. MCP: license and maintenance status of CCXT-wrapping servers; whether an official Binance MCP exists; TradingView MCP data usage terms for automated systems.
11. The Python example code in this document has not been run (the research machine did not have the `anthropic` package installed).
12. Chart size and rendering recommendations are design experience, with no project-specific benchmark yet.
