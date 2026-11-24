# TrustTrade research workspace

Re-implementation and test of **"TrustTrade: Human-Inspired Selective Consensus Reduces Decision
Uncertainty in LLM Trading Agents"** (Li, Gonsalves, Li, Yoon, Wang; arXiv
[2603.22567](https://arxiv.org/abs/2603.22567), 2026-03) on rinng's crypto data with Claude Haiku.

Code: `src/rinng/trusttrade/` · CLI: `rinng trusttrade …` · Tests: `tests/trusttrade/`.
Outputs in this folder (`runs/`, `live/`, `cache/`) are gitignored.

Not investment advice. Everything here is simulated: no exchange account, no orders.

## What the paper claims

LLM trading agents trust every retrieved input equally ("uniform trust"), which makes them unstable
and pushes them into extreme risk/return regimes. Three additions move them toward the
mid-risk/mid-return behaviour of human traders:

1. **Selective consensus**: N independent analysts per domain → atomic claims → similarity graph →
   keep only groups that several analysts support.
2. **Deterministic temporal signals**: price-only statistics and rule forecasts as an anchor.
3. **Memory bank + reflection**: log every decision, back-fill outcomes when they become known,
   let short/long-term reflection agents feed lessons into later decisions.

Evidence in the paper: 3 stocks (AAPL, GOOG, NVDA), 2024-Q1 backtest plus a 2026-01-01 → 02-18
real-time run, 19 human annotators. No transaction costs, no significance tests.

## How this implementation maps to the paper

| Paper | Here | File |
|---|---|---|
| Domains: fundamentals, market, news, sentiment | `market` (daily candles + indicators), `derivatives` (funding, OI, long/short ratio as positioning/sentiment), `news` (live only) | `data.py` |
| N heterogeneous LLM agents (GPT + Gemini) | N samples of Haiku by default; `--analyst-models` cycles several models over the agents | `agents.py`, `llm.py` |
| Claim schema (domain, subject, predicate, polarity, value, timestamp) | Same; subject is an enum per domain, enforced by structured outputs | `agents.py` |
| Hybrid similarity `λ·s_sem + (1−λ)·s_num`, graph at τ, `S = α·supp + (1−α)·coh` | Same formulas; `s_sem` = shared subject + TF-IDF cosine of the predicate (no embedding API); polarity gate (opposite claims never join, neutral vs directional counts half) | `consensus.py` |
| Data-leakage audit | Claims dated after the decision day are flagged and removed | `consensus.py` |
| Temporal module (H = 1…360 days, trend label, MA rules, bounded forecast, confidence, BUY/SELL/HOLD %) | Same structure; trend label normalised by volatility so thresholds work across coins | `temporal.py` |
| Memory record, back-filled R and Sharpe, rolling slopes, short {1,7,14} / long {28,90,180,360} reflection | Same; √365 annualisation (crypto trades daily) | `memory.py` |
| Researcher (bull/bear debate) | **Omitted**: analysts → trader. The paper's own ablation puts most of the gain at Analyst→Trader | `agents.py` |
| Baselines: Buy&Hold, MACD, KDJ+RSI, ZMR, SMA | Same, plus `temporal_rule` (the temporal module alone) | `sim.py` |
| Partial allocation 25/50/75/100% | `--allocation partial` (default) or `full` | `sim.py` |
| Real-time 2026 protocol | `rinng trusttrade live`, once a day | `run.py` |
| Human-aligned preference ellipse | Not reproduced (no human annotators) | |

Added for research hygiene (not in the paper): fees (10 bps per fill by default), `--blind` mode
(ticker, dates and price levels hidden, so the model cannot recall the period), and a disk cache so
every variant reads the *same* analyst reports.

## Variants

Cumulative ablation, same analyst calls underneath:

| name | analysts | aggregation | temporal | memory |
|---|---|---|---|---|
| `single` | 1 per domain | full report | – | – |
| `multi` | N per domain | all N reports (uniform trust) | – | – |
| `consensus` | N | high-consensus claims only | – | – |
| `consensus_temporal` | N | high-consensus claims | ✓ | – |
| `trusttrade` | N | high-consensus claims | ✓ | ✓ |

## Running

```bash
# prints the call count and a cost estimate, asks before calling the API
uv run rinng trusttrade backtest --start 2026-09-01 --end 2026-10-31 --symbols BTC,ETH,SOL
```

```bash
# same window, anonymised (leakage check)
uv run rinng trusttrade backtest --start 2026-09-01 --end 2026-10-31 --symbols BTC,ETH,SOL --blind --name sep-oct-blind
```

```bash
# rebuild a report from the cache only, no API calls
uv run rinng trusttrade backtest --start 2026-09-01 --end 2026-10-31 --symbols BTC,ETH,SOL --cache-only --name replay
```

```bash
# forward test: run once a day after 00:00 UTC (state persists in TrustTrade/live/)
uv run rinng trusttrade live --symbols BTC,ETH,SOL
```

The API key is `CLAUDE_API_KEY` from the environment or `.env` (the same key MakeMoney uses).
Each run folder holds `config.json`, `report.md`, `metrics.json`, `equity_<symbol>.csv` and the raw
logs: `reports.jsonl` (analyst outputs), `consensus.jsonl` (kept and dropped claim groups),
`decisions.jsonl` (every strategy's action and rationale), `errors.jsonl`.

The cost estimate is conservative: real runs cost about half of it per call.

`uv run python TrustTrade/analyze.py TrustTrade/runs/<name>` prints behaviour tables for a run:
action counts, how often each variant agrees with the others, and how unanimous the analysts were.

Daily bars missing from the local store are fetched from the exchange's public API for the run
(logged, never written back).

### Viewing runs in the web UI

Run `uv run rinng web` and the web UI (`pnpm --dir web dev`), then open `/trusttrade`. The page
reads every finished run in `TrustTrade/runs/` (read-only, no model or exchange calls) and shows:

- every run side by side;
- per-strategy metrics and equity curves (equal-weight average or one coin);
- trader behaviour and how often the analysts agree;
- each decision on a price chart. Clicking a day shows the trader's reasoning, the claims the
  consensus filter kept or dropped, and every analyst's report.

The API lives in `src/rinng/web/trusttrade.py`.

## Research plan

| # | Question | Run |
|---|---|---|
| E1 | Does each component help on crypto? | 5 coins (BTC, ETH, SOL, BNB, LINK) × 60–90 days, all variants + baselines. ≈ 5.9k calls / ≤ $5 for 90 days |
| E2 | Are results inflated by the model remembering the period? | E1 window with `--blind`; compare variant by variant |
| E3 | Does consensus need *different* models? | `--analyst-models claude-haiku-5-5,claude-sonnet-5-5`; watch the kept share and whether `consensus` separates from `multi` |
| E4 | Is the risk profile driven by sizing? | `--allocation full` vs `partial` (paper Fig. 1d-e) |
| E5 | Out-of-sample, no leakage possible | `live` every day for 6–8 weeks (the paper's 2026-Q1 protocol) |

Metrics: CR, MDD, Sharpe, exposure, number of trades, consensus kept share. With a handful of coins
and weeks, report everything but read differences as anecdotes unless they hold across E1/E2/E5.

## Log

- **2026-11-23 smoke run** (BTC, 2026-11-18 → 11-19, 3 Haiku analysts): 24 calls, 0 errors,
  ≈ $0.011. All LLM variants held cash in a falling market, buy-and-hold lost 4.7%. Same-model
  analysts agree a lot: 74–90% of claims reached consensus, so on Haiku-only runs `consensus` and
  `multi` differ mostly in how compact the evidence is. That makes E3 the interesting experiment.
- **2026-11-23 live check** (ETH, all three domains including news): 11 calls, ≈ $0.007; the news
  domain produced consensus groups such as an ETF-flow and a security-incident claim.
- **2026-11-23 E1** (`runs/e1-sep-nov`): BTC, ETH, SOL, BNB, LINK, 2026-09-22 → 11-20 (60 days),
  3 Haiku analysts, partial allocation, 10 bps fees. 3,878 calls, 0 errors, ≈ $1.98 in total.
  The store was missing the 2026-11-13 daily bar for SOL, BNB and LINK; the run fetched it.

  | strategy | CR % | MDD % | Sharpe | exposure % | trades |
  |---|---:|---:|---:|---:|---:|
  | single | −4.54 | 4.89 | −3.66 | 12 | 6 |
  | multi | −1.58 | 1.75 | −2.99 | 5 | 4 |
  | consensus | −1.37 | 2.23 | −2.04 | 6 | 6 |
  | consensus_temporal | −2.15 | 3.95 | −2.23 | 11 | 11 |
  | trusttrade | **−1.11** | 2.07 | −2.05 | 5 | 5 |
  | buy_hold | −36.70 | 38.88 | −5.43 | 100 | 1 |
  | macd (best rule) | −4.11 | 8.43 | −1.81 | 17 | 3 |
  | temporal_rule | −8.22 | 11.65 | −2.51 | 33 | 33 |

  Reading:
  1. A one-way bear market (buy-and-hold −37%). Every LLM variant sat mostly in cash (HOLD on
     82–94% of days), so all of them beat every rule baseline. That shows a cautious prior; it
     does not show any skill at picking entries.
  2. Ordering matches the paper's direction: `single` is worst on return and drawdown on all
     five coins, and `trusttrade` has the best average return. But `multi`, `consensus` and
     `trusttrade` are within 0.5 pp of each other, with per-coin rankings that swap. Treat that
     gap as noise.
  3. Temporal signals made the trader more active (11 trades vs 6) and worse in this regime: the
     rule itself lost 8%. Adding memory/reflection pulled it back to 5 trades, which matches the
     paper's "more conservative" claim.
  4. Same-model analysts barely disagree: stance unanimous on 87% (market) and 79%
     (derivatives) of days, a bullish-vs-bearish split on ≤ 1%, and 82–83% of claims kept. On
     Haiku-only runs the consensus filter has little noise to remove, so E3 (mixed models) is
     the real test of the mechanism.
  5. Variants took the same action on 75–88% of symbol-days.

  Next: the same five coins over an up-trend (2026-08-02 → 09-30, the five-coin average was
  +52%) to check whether the cautious variants just miss rallies; E2 (blind) to rule out recall.
- **2026-11-23 E1b, up-trend** (`runs/e1b-aug-sep-up`): same setup, 2026-08-02 → 09-30. 3,602
  calls (288 from E1's cache), 0 errors, ≈ $1.86.

  | strategy | down CR (E1) | up CR (E1b) | avg CR | avg MDD | CR / MDD | exposure down / up % |
  |---|---:|---:|---:|---:|---:|---:|
  | single | −4.54 | +4.56 | +0.01 | 3.46 | 0.00 | 12 / 14 |
  | multi | −1.58 | +1.42 | −0.08 | 1.45 | −0.06 | 5 / 5 |
  | consensus | −1.37 | +4.17 | +1.40 | 1.68 | 0.84 | 6 / 9 |
  | consensus_temporal | −2.15 | **+11.24** | **+4.55** | 4.09 | 1.11 | 11 / 29 |
  | trusttrade | **−1.11** | +7.82 | +3.36 | 2.87 | **1.17** | 5 / 24 |
  | buy_hold | −36.70 | +50.78 | +7.04 | 24.29 | 0.29 | 100 / 100 |
  | sma_cross | −7.54 | +29.89 | +11.18 | 11.11 | 1.01 | 37 / 83 |
  | macd | −4.11 | +19.36 | +7.62 | 9.37 | 0.81 | 17 / 54 |
  | temporal_rule | −8.22 | +29.82 | +10.80 | 10.40 | 1.04 | 33 / 76 |
  | kdj_rsi | −33.18 | +14.96 | −9.11 | 18.33 | −0.50 | 67 / 19 |
  | zmr | −29.11 | +12.87 | −8.12 | 16.76 | −0.48 | 70 / 16 |

  Reading (two 60-day windows, five coins; still anecdotes):
  1. Haiku as a trader is strongly risk-averse. In a +51% market the LLM variants captured 1–11%
     and held the coin on at most 29% of days. This matches the paper's own finding that small
     models (Claude Haiku 4.5, Gemini 2.5 lite) end up low-risk/low-return.
  2. Temporal signals are the component that moves results: +7 pp in the up window, −0.8 pp in
     the down window, and exposure 9% → 29%. They are the only thing that gets the trader to act
     on a trend.
  3. Memory/reflection makes the trader more conservative in both regimes: less return in the
     rally (11.2 → 7.8), less loss in the decline (−2.15 → −1.11), the best CR/MDD ratio
     overall. This matches the paper's description.
  4. `consensus` beats `multi` in both windows, but not by removing noise. Analysts agree most
     of the time (unanimous stance 66–87%, a bullish-vs-bearish split ≤ 1%). With six full
     reports to read, the trader hedges and holds (exposure 5%, the lowest of all); the
     condensed claim list lets it act. Compression explains the gain better than filtering.
  5. A domain bias: the derivatives analysts were bearish on 71% of stances during the +51%
     rally (crowded longs and positive funding read as risk). That pull towards cash is shared by
     every variant.
  6. On CR/MDD, `trusttrade` (1.17) and `consensus_temporal` (1.11) sit with the best rules
     (`sma_cross` 1.01, `temporal_rule` 1.04), well above buy-and-hold (0.29), and at a much
     lower risk level: the "mid-risk" place the paper aims for, reached here from the low-risk
     side rather than from the high-risk one.

  Open questions: is the caution a prior or recall of these months (E2, blind)? Does a
  heterogeneous analyst pool disagree enough for the filter to matter (E3)? Does a sizing nudge
  (`--allocation full`, E4) close the gap to the rule baselines?
- **2026-11-24 E2, blind** (`runs/e2-sep-nov-blind`, `runs/e2-aug-sep-blind`): both windows
  again with ticker, dates and price levels hidden. 7,773 calls, 0 errors, ≈ $3.92.

  | variant | down: normal → blind | up: normal → blind | mean CR of 4 runs | mean MDD of 4 runs |
  |---|---:|---:|---:|---:|
  | single | −4.54 → −3.97 | +4.56 → +5.09 | +0.29 | 3.30 |
  | multi | −1.58 → −2.11 | +1.42 → +3.00 | +0.18 | 1.78 |
  | consensus | −1.37 → −3.02 | +4.17 → +4.19 | +0.99 | 1.84 |
  | consensus_temporal | −2.15 → −2.65 | +11.24 → +9.40 | **+3.96** | 4.12 |
  | trusttrade | −1.11 → −1.61 | +7.82 → +7.75 | +3.21 | 2.99 |

  Reading:
  1. **No sign of recall.** Hiding the asset and the calendar moved the five-coin averages by
     0.78 pp on average (at most 1.83 pp), and the mean shift is −0.24 pp. Exposure stayed the
     same (5–14% in the decline, 6–26% in the rally). The caution is the model's prior, not
     knowledge of these months.
  2. **This gives a noise floor.** The blind and normal runs use different samples of the same
     model on the same information, so the gap between them measures run-to-run noise: median
     1.85 pp per coin (up to 9.5 pp), ≈ 0.8 pp on a five-coin average. Any claim must clear
     that bar.
  3. **Robust, well above the noise:**
     - temporal signals raise returns in the rally (+5 to +7 pp, exposure ~9% → ~26%);
     - memory/reflection lowers exposure and drawdown in the rally (MDD 4.2 → 3.7 normal,
       3.6 → 2.7 blind) and cuts losses in the decline (−2.15 → −1.11, −2.65 → −1.61).
  4. **Not robust (within noise or flips sign):**
     - "single is worst": true in the decline, but in the blind rally `single` beat `multi`
       and `consensus`;
     - "consensus beats multi": +1.4 pp in E1/E1b, but −0.9 pp in the blind decline and equal
       in the blind rally.

     With Haiku-only analysts (kept share 81–86% again), this setup cannot show a benefit of
     selective consensus itself.
  5. Bottom line so far: on crypto with Haiku, the paper's results are partly reproduced.
     - Reproduced: the deterministic temporal anchor and the memory/reflection effects, and the
       move to a mid-risk profile (`trusttrade`: about +3% average return per 60 days at ≈ 3%
       MDD, vs buy-and-hold +7% at 24% MDD).
     - Not reproduced: the consensus filter's contribution. The analysts never disagreed enough
       for filtering to matter. E3 (heterogeneous analysts) is the remaining test.
