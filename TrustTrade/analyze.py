"""Behaviour analysis of a TrustTrade run folder.

Usage: uv run python TrustTrade/analyze.py TrustTrade/runs/<name>
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

run = Path(sys.argv[1])
dec = [json.loads(x) for x in (run / "decisions.jsonl").read_text().splitlines()]
rep = [json.loads(x) for x in (run / "reports.jsonl").read_text().splitlines()]
LLM = ["single", "multi", "consensus", "consensus_temporal", "trusttrade"]

by = defaultdict(list)
for d in dec:
    by[(d["strategy"], d["symbol"])].append(d)

print("## Behaviour per LLM variant (all symbols pooled)")
print("| variant | BUY days | SELL days | HOLD % | flips/10d | avg conf | in-market days % |")
print("|---|---:|---:|---:|---:|---:|---:|")
for v in LLM:
    acts, confs, flips, inmkt, n = Counter(), [], 0, 0, 0
    for (s, _sym), rows in by.items():
        if s != v:
            continue
        rows.sort(key=lambda r: r["day"])
        prev = None
        for r in rows:
            acts[r["action"]] += 1
            confs.append(r.get("confidence", 0))
            if prev and r["action"] != "HOLD" and prev != "HOLD" and r["action"] != prev:
                flips += 1
            if r["action"] != "HOLD":
                prev = r["action"]
            inmkt += r["exposure"] > 0.01
            n += 1
    print(
        f"| {v} | {acts['BUY']} | {acts['SELL']} | {100 * acts['HOLD'] / n:.0f} | "
        f"{10 * flips / n:.2f} | {np.mean(confs):.0f} | {100 * inmkt / n:.0f} |"
    )

# pairwise agreement of daily actions between variants
print("\n## Same action on the same day (share of symbol-days)")
key = {(d["strategy"], d["symbol"], d["day"]): d["action"] for d in dec}
days = {(d["symbol"], d["day"]) for d in dec}
print("| | " + " | ".join(LLM) + " |")
print("|---|" + "---:|" * len(LLM))
for a in LLM:
    cells = []
    for b in LLM:
        same = np.mean([key[(a, s, d)] == key[(b, s, d)] for s, d in days])
        cells.append(f"{same:.2f}")
    print(f"| {a} | " + " | ".join(cells) + " |")

# analyst stance agreement
print("\n## Analyst stance agreement (3 Haiku samples)")
st = defaultdict(list)
for r in rep:
    st[(r["symbol"], r["day"], r["domain"])].append(r["stance"])
for dom in ("market", "derivatives"):
    groups = [v for k, v in st.items() if k[2] == dom and len(v) == 3]
    unanimous = np.mean([len(set(v)) == 1 for v in groups])
    split = np.mean([{"bullish", "bearish"} <= set(v) for v in groups])
    mix = Counter(x for v in groups for x in v)
    print(
        f"- {dom}: unanimous {unanimous:.0%}, bullish-vs-bearish split {split:.0%}, "
        f"stances {dict(mix)}"
    )

# trusttrade reflection posture
mem = [d for d in dec if d["strategy"] == "trusttrade"]
print(f"\ntrusttrade decisions: {len(mem)}")
