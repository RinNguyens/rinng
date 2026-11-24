"""TrustTrade research harness: a crypto re-implementation of arXiv 2603.22567.

"TrustTrade: Human-Inspired Selective Consensus Reduces Decision Uncertainty in LLM Trading
Agents" (Li, Gonsalves, Li, Yoon, Wang, 2026). The paper adds three parts to a TradingAgents-style
pipeline:

1. multi-agent selective consensus (`consensus`): N independent analysts per data domain, their
   reports split into atomic claims, claims clustered by similarity, only groups that several
   agents support are passed on;
2. deterministic temporal signals (`temporal`): price-only statistics and rule-based forecasts
   that anchor the LLM;
3. a memory bank with short/long-term reflection (`memory`): each decision is logged, its
   outcome back-filled only once it is observable, and LLM reflections are fed into later steps.

`run` drives an ablation over these parts (and rule baselines) on rinng's daily crypto data with
Claude Haiku, plus a forward "live" protocol that only ever sees data available at decision time.
See TrustTrade/README.md for the research design and the deviations from the paper.
"""
