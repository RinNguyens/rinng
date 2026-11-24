"""Deterministic selective consensus over atomic claims (paper: Methods, eq. 1-2, Fig. 7a).

Each analyst report is a list of claims in a fixed schema (domain, subject, predicate, polarity,
optional numeric value, optional date). For claims c, c' from *different* agents:

    s_sem(c, c') = 0.35·[same subject] + 0.65·cos(tfidf(predicate c), tfidf(predicate c'))
    s_num(c, c') = exp(−|x(c) − x(c')| / σ),  σ = sigma_rel · max(|x(c)|, |x(c')|)
    s(c, c')     = π · (λ·s_sem + (1 − λ)·s_num)  if both claims carry a number, else π · s_sem
    π            = 1 same polarity, 0.5 neutral vs directional, 0 bullish vs bearish

A shared subject alone (0.35) stays below τ, so two claims join only when their wording or their
numbers also match; a neutral reading and a directional one count as half an agreement.

Deviation from the paper: it embeds whole claims with a sentence-embedding model. The Claude API has
no embedding endpoint, so the subject comes from a fixed per-domain vocabulary (enforced by the
structured-output schema) and only the free-text predicate is compared lexically (TF-IDF). This
keeps the scorer deterministic and dependency-free.

Claims are nodes; an edge joins claims from different agents with s ≥ τ. Connected components are
consensus groups G_k with

    supp(G_k) = |agents with a claim in G_k| / N
    coh(G_k)  = mean pairwise s within G_k   (0 for a single claim)
    S(G_k)    = α·supp + (1 − α)·coh

Groups with S ≥ keep and at least `min_agents` distinct agents are high-consensus evidence; the
rest are low-consensus and dropped. A claim dated after the decision time is a leakage flag and is
removed before clustering.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import combinations

STOP = frozenset(
    "a an the is are was were be been being of to in on at for and or with by from as that this "
    "it its into over under than then there their which who whom has have had not no very more "
    "most less still remains remain currently now".split()
)
_TOKEN = re.compile(r"[a-z][a-z0-9]+|\d+(?:\.\d+)?")


@dataclass
class Params:
    lam: float = 0.6  # λ: weight of semantic vs numeric similarity
    sigma_rel: float = 0.15  # σ relative to the larger |value|
    tau: float = 0.4  # τ: edge threshold (Fig. 7 uses 0.4)
    alpha: float = 0.6  # α: support vs cohesion in the group score
    keep: float = 0.5  # S(G) threshold for high consensus
    min_agents: int = 2  # a group must be backed by at least this many agents


@dataclass
class Claim:
    agent: int
    domain: str
    subject: str
    predicate: str
    polarity: str  # bullish | bearish | neutral
    value: float | None = None
    unit: str | None = None
    date: str | None = None  # ISO date the fact refers to, if any

    def text(self) -> str:
        v = "" if self.value is None else f" [{self.value:g}{self.unit or ''}]"
        return f"{self.subject}: {self.predicate}{v} ({self.polarity})"


@dataclass
class Group:
    claims: list[Claim]
    support: float
    cohesion: float
    score: float
    agents: int
    polarity: str
    representative: Claim
    high: bool = False

    def to_dict(self) -> dict:
        return {
            "claim": self.representative.text(),
            "subject": self.representative.subject,
            "polarity": self.polarity,
            "agents": self.agents,
            "support": round(self.support, 3),
            "cohesion": round(self.cohesion, 3),
            "score": round(self.score, 3),
            "high": self.high,
            "members": [c.text() for c in self.claims],
        }


@dataclass
class Result:
    domain: str
    n_agents: int
    high: list[Group] = field(default_factory=list)
    low: list[Group] = field(default_factory=list)
    leaked: list[Claim] = field(default_factory=list)

    @property
    def kept_share(self) -> float:
        total = sum(len(g.claims) for g in self.high + self.low)
        return sum(len(g.claims) for g in self.high) / total if total else 0.0

    def evidence(self) -> str:
        """Text block for the trader: high-consensus claims only."""
        if not self.high:
            return f"(no claim in the {self.domain} domain reached consensus)"
        lines = [
            f"- {g.representative.subject}: {g.representative.predicate}"
            + (
                ""
                if g.representative.value is None
                else f" [{_median_value(g):g}{g.representative.unit or ''}]"
            )
            + f" — {g.polarity}, {g.agents}/{self.n_agents} analysts, score {g.score:.2f}"
            for g in self.high
        ]
        dropped = sum(len(g.claims) for g in self.low)
        tail = f"\n({dropped} low-consensus claims dropped"
        tail += f", {len(self.leaked)} leakage-flagged)" if self.leaked else ")"
        return "\n".join(lines) + tail

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "n_agents": self.n_agents,
            "kept_share": round(self.kept_share, 3),
            "high": [g.to_dict() for g in self.high],
            "low": [g.to_dict() for g in self.low],
            "leaked": [asdict(c) for c in self.leaked],
        }


def _median_value(g: Group) -> float:
    vals = sorted(c.value for c in g.claims if c.value is not None)
    if not vals:
        return float("nan")
    mid = len(vals) // 2
    v = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return round(v, 6)


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP]


def tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    """L2-normalised TF-IDF vectors (smoothed idf) for a small corpus."""
    n = len(docs)
    df = Counter(t for d in docs for t in set(d))
    out = []
    for d in docs:
        tf = Counter(d)
        v = {t: c * (math.log((1 + n) / (1 + df[t])) + 1) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        out.append({t: x / norm for t, x in v.items()})
    return out


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def similarity(c1: Claim, c2: Claim, v1: dict, v2: dict, p: Params) -> float:
    pols = {c1.polarity, c2.polarity}
    if pols == {"bullish", "bearish"}:
        return 0.0
    agree = 1.0 if len(pols) == 1 else 0.5
    sem = 0.35 * (c1.subject == c2.subject) + 0.65 * cosine(v1, v2)
    if c1.value is None or c2.value is None:
        return agree * sem
    scale = p.sigma_rel * max(abs(c1.value), abs(c2.value), 1e-9)
    num = math.exp(-abs(c1.value - c2.value) / scale)
    return agree * (p.lam * sem + (1 - p.lam) * num)


def leaked(c: Claim, as_of: str | None) -> bool:
    """A claim about a date after the decision time cannot be known yet."""
    return bool(as_of and c.date and c.date[:10] > as_of[:10])


def score(
    claims: list[Claim],
    n_agents: int,
    domain: str,
    *,
    as_of: str | None = None,
    params: Params | None = None,
) -> Result:
    p = params or Params()
    res = Result(domain=domain, n_agents=n_agents)
    clean = []
    for c in claims:
        (res.leaked if leaked(c, as_of) else clean).append(c)
    if not clean:
        return res

    vecs = tfidf([tokens(c.predicate) for c in clean])
    n = len(clean)
    sim = [[0.0] * n for _ in range(n)]
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in combinations(range(n), 2):
        s = similarity(clean[i], clean[j], vecs[i], vecs[j], p)
        sim[i][j] = sim[j][i] = s
        if s >= p.tau and clean[i].agent != clean[j].agent:
            parent[find(i)] = find(j)

    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)

    groups = []
    for idx in comps.values():
        agents = len({clean[i].agent for i in idx})
        pairs = list(combinations(idx, 2))
        coh = sum(sim[i][j] for i, j in pairs) / len(pairs) if pairs else 0.0
        supp = agents / n_agents
        s = p.alpha * supp + (1 - p.alpha) * coh
        pol = Counter(clean[i].polarity for i in idx).most_common()
        polarity = pol[0][0] if len(pol) == 1 or pol[0][1] > pol[1][1] else "mixed"
        medoid = max(idx, key=lambda i: sum(sim[i][j] for j in idx if j != i))
        g = Group(
            claims=[clean[i] for i in idx],
            support=supp,
            cohesion=coh,
            score=s,
            agents=agents,
            polarity=polarity,
            representative=clean[medoid],
            high=s >= p.keep and agents >= min(p.min_agents, n_agents),
        )
        groups.append(g)
    groups.sort(key=lambda g: g.score, reverse=True)
    res.high = [g for g in groups if g.high]
    res.low = [g for g in groups if not g.high]
    return res
