# Project foundation documents

Compiled 2026-11-13. The six files below were written by six independent research threads; this file is the index and synthesis.

## Scope

The project covers crypto only. The stock-related parts of file 05 (stock data sources, fundamental analysis in section 9, factor investing) are out of scope and kept for reference only. The LLM multi-agent layer (files 01, 06) is on hold.

## Verification status

- Each file ends with an "unverified" section. About 120 spots are flagged in total. Read that section before relying on a number.
- Only the Python examples in file 02 have actually been run. Pine code, Python pseudocode (files 03, 04) and the Claude API examples (file 06) have not been run.
- Many paper citations in files 04 and 05 were written from memory, without opening the original.
- The synthesis has only cross-checked the structure and a few key passages of each file; the full 5,000 lines have not been reread.

## Contents

| File | Contents | Read when |
|---|---|---|
| [01-quantharness-paper.md](01-quantharness-paper.md) | The full 32-page QuantHarness paper, GitHub repo, every results table, critical review | Designing the agent layer |
| [02-exchange-apis.md](02-exchange-apis.md) | Binance and OKX: REST, WebSocket, rate limits, authentication, historical data, Python examples | Writing the data layer |
| [03-pine-script-and-smc.md](03-pine-script-and-smc.md) | Pine Script v6; SMC as algorithms; analysis of the "Dynamic SMC & Market Structure PRO" indicator | Writing an indicator or the SMC module |
| [04-analysis-methods.md](04-analysis-methods.md) | Volume profile, order flow, crypto derivatives, Wyckoff, Elliott, liquidity, classic indicators, macro, on-chain | Writing analysis modules |
| [05-quant-backtest-and-data.md](05-quant-backtest-and-data.md) | Research workflow, backtesting, metrics, risk management, Python libraries, data sources, stock fundamentals, storage architecture | Choosing tools, writing the backtest |
| [06-llm-multi-agent.md](06-llm-multi-agent.md) | LLM systems for finance, critical evidence, agent frameworks, Claude API, MCP, proposed architecture | Writing the LLM layer |
| [07-implementation-plan.md](07-implementation-plan.md) | Step-by-step plan, limits and blocking on both exchanges, data needed for each indicator | Before starting to code |
| [08-architecture.md](08-architecture.md) | Architecture: layers, processes, modules, data model, interfaces | Before building the skeleton |
| [09-phase-roadmap.md](09-phase-roadmap.md) | 12-phase roadmap: tasks, dependencies, done criteria, risks | When starting each phase |
| [12-cli-mcp-plan.md](12-cli-mcp-plan.md) | Plan to use rinng from the terminal and over MCP: service layer, commands, tools, packaging | Building the CLI/MCP front ends |
| [13-terminal-wallet-handoff.md](13-terminal-wallet-handoff.md) | Handoff spec: terminal sections (Market, Coin, Charts, Wallet) and the read-only Security Wallet (scan, revoke plan, watchlist, send check, lock) | Building the terminal UI |

## Cross-cutting conclusions

1. **The paper is a reference framework, not evidence.** In Table 1, linear regression has higher cumulative return than QuantHarness on 7/7 symbols with data. The paper ignores fees, does not allow HOLD and does not name the LLM model; the repo has no evaluation code. (File 01, sections 0 and 6.)
2. **Deterministic computation first, LLM second.** Indicators, volume profile, SMC and stop/TP levels are computed in code; the LLM only interprets. The deterministic layer itself is the baseline for measuring whether the LLM adds anything. (File 06, section 7.)
3. **Backtests with an LLM suffer look-ahead** if the data predates the model's knowledge cutoff. Only forward tests count. (File 06, section 2.)
4. **Evidence for SMC, Wyckoff, Elliott and volume profile is weak.** They can be partly programmed and must be validated by us. (File 03 part D; file 04 section 10.)
5. **Some data cannot be recovered later.** Open interest and long/short ratio via REST only keep about 30 days; liquidations are only available over WebSocket; futures aggTrades only 48 hours. The collector must start early. (File 02; file 04 section 3.)
6. **Storage:** Parquet + DuckDB, every feature has `event_time` and `known_at`. (File 05 section 10; file 04 section 10.2.)
7. **Licenses:** LuxAlgo's SMC forbids commercial use; vectorbt has the Commons Clause; the Dynamic SMC indicator is MPL 2.0. (File 03 part C; file 05 section 7.)

## What the documents do not cover yet

- Detailed design and source code of the project: not a single line of code written yet.
- Order execution, position management, reconciliation: only endpoint groups are listed.
- Tax and legal aspects of crypto/securities trading.
- Vietnamese stocks: only a short passage in file 05; the SSI/TCBS/DNSE APIs are unverified.
- Exchanges other than Binance and OKX (Bybit, Hyperliquid, DEXs).
- Options and implied volatility.

## Proposed roadmap

1. Data layer: download Binance/OKX bars into Parquet, plus a background collector for OI, funding and liquidations.
2. Deterministic modules: indicators, volume profile, swing/BOS/CHoCH/FVG, with unit tests.
3. Backtests with fees and slippage, compared against linear-regression and buy-and-hold baselines.
4. LLM layer for interpretation and reports, evaluated by forward testing.
5. Pine Script indicators for signals that passed validation.
