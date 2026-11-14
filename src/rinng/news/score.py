"""Keyword rules that tag a headline with sentiment, impact and the coins it mentions.

Heuristic only: a headline like "X denies hack" still scores as a hack. Each rule adds a
signed score (bullish > 0, bearish < 0) and an impact weight; the headline keeps the sum of
scores (clamped to -1..1) and the largest impact.
"""

import math
import re
from dataclasses import dataclass, field

# (pattern, score, impact 1=low 2=medium 3=high, tag)
RULES: list[tuple[str, float, int, str]] = [
    # Bearish
    (r"\b(hack(ed|s)?|exploit(ed|s)?|drain(ed)?|stolen|breach)\b", -0.9, 3, "hack"),
    (
        r"\b(insolven\w*|bankrupt\w*|halts? withdrawals?|suspends? withdrawals?)\b",
        -0.9,
        3,
        "insolvency",
    ),
    (r"\b(delist\w*|removal of|will remove|cease trading)\b", -0.7, 3, "delisting"),
    (r"\b(sues|sued|lawsuit|charged|indict\w*|fined|enforcement action)\b", -0.5, 3, "legal"),
    (r"\b(bans?|banned|crackdown|prohibit\w*)\b", -0.6, 3, "ban"),
    (r"\b(rate hikes?|hawkish|hotter[- ]than[- ]expected)\b", -0.5, 3, "macro"),
    (r"\b(outflows?)\b", -0.4, 2, "flows"),
    (
        r"\b(plunges?|crash(es|ed)?|tumbles?|slumps?|sell-?off|dumps?|sinks?|drops?|falls?)\b",
        -0.4,
        2,
        "price",
    ),
    (r"\b(\d+-(day|week|month|year) lows?|lowest (level|since)|new lows?)\b", -0.6, 2, "price"),
    (r"\b(liquidations?|liquidated)\b", -0.3, 2, "liquidations"),
    (r"\b(token unlocks?|unlock)\b", -0.3, 2, "unlock"),
    (r"\b(depeg\w*)\b", -0.7, 3, "depeg"),
    # Bullish
    (r"\b(etfs?)\b.*\b(approv\w*|launch\w*|debut\w*)\b", 0.7, 3, "etf"),
    (
        r"\b(will (list|launch)|new listing|lists|to list|launches? .*(spot|perpetual|futures))\b",
        0.6,
        3,
        "listing",
    ),
    (r"\b(rate cuts?|dovish|cooler[- ]than[- ]expected)\b", 0.5, 3, "macro"),
    (r"\b(strategic (bitcoin |crypto )?reserve|adopts?|legal tender)\b", 0.5, 3, "adoption"),
    (r"\b(inflows?)\b", 0.4, 2, "flows"),
    (r"\b(\d+-(day|week|month|year) highs?|highest (level|since)|new highs?)\b", 0.5, 2, "price"),
    (
        r"\b(surges?|soars?|rall(y|ies)|jumps?|climbs?|record high|all-time high|ath)\b",
        0.4,
        2,
        "price",
    ),
    (r"\b(approv(es|ed|al))\b", 0.4, 2, "approval"),
    (r"\b(buybacks?|burns?)\b", 0.3, 2, "supply"),
    (r"\b(acquires?|buys|bought|accumulat\w*)\b", 0.3, 2, "buying"),
    (r"\b(partner(s|ship)?|integrat\w*)\b", 0.2, 1, "partnership"),
    # Market-moving but direction-free: raises impact only
    (r"\b(fomc|fed|powell|cpi|ppi|nonfarm|payrolls|tariffs?|sec|treasury)\b", 0.0, 3, "macro"),
]
_RULES = [(re.compile(p, re.I), s, i, t) for p, s, i, t in RULES]

NAMES = {
    "bitcoin": "BTC",
    "ether": "ETH",
    "ethereum": "ETH",
    "solana": "SOL",
    "ripple": "XRP",
    "xrp": "XRP",
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "bnb": "BNB",
    "tron": "TRX",
    "avalanche": "AVAX",
    "chainlink": "LINK",
    "polkadot": "DOT",
    "litecoin": "LTC",
    "toncoin": "TON",
    "sui": "SUI",
    "aptos": "APT",
    "arbitrum": "ARB",
    "optimism": "OP",
    "pepe": "PEPE",
    "shiba": "SHIB",
    "hyperliquid": "HYPE",
    "near": "NEAR",
    "tether": "USDT",
    "usdc": "USDC",
}
# BTC, $BTC, (BTC), BTCUSDT, BTC/USDT
_TICKER = re.compile(
    r"\$([A-Z0-9]{2,10})\b|\(([A-Z0-9]{2,10})\)|\b([A-Z0-9]{2,10})(?:/|-)?USD[TC]?\b"
)
_WORD = re.compile(r"[a-z]+")
_STOP = {"USD", "USDT", "USDC", "ETF", "SEC", "CEO", "API", "NFT", "THE", "AND", "FOR"}


@dataclass
class Scored:
    score: float
    impact: int
    tags: list[str] = field(default_factory=list)
    coins: list[str] = field(default_factory=list)

    @property
    def sentiment(self) -> str:
        return "bullish" if self.score > 0.1 else "bearish" if self.score < -0.1 else "neutral"


def coins_in(title: str) -> list[str]:
    found: list[str] = []
    for m in _TICKER.finditer(title):
        sym = next(g for g in m.groups() if g)
        if sym not in _STOP and not sym.isdigit():
            found.append(sym)
    for w in _WORD.findall(title.lower()):
        if w in NAMES:
            found.append(NAMES[w])
    return list(dict.fromkeys(found))


def score_headline(title: str, source_kind: str = "media") -> Scored:
    total, impact, tags = 0.0, 1, []
    for rx, s, i, tag in _RULES:
        if rx.search(title):
            total += s
            impact = max(impact, i)
            if tag not in tags:
                tags.append(tag)
    if source_kind == "exchange" and {"listing", "delisting"} & set(tags):
        impact = 3
    return Scored(max(-1.0, min(1.0, total)), impact, tags, coins_in(title))


def outlook(
    items: list[dict], now_ms: int, base: str | None = None, half_life_h: float = 6.0
) -> dict:
    """Time-decayed average sentiment over the last 24h; `base` limits to items naming that coin."""
    num = den = 0.0
    used = 0
    for it in items:
        age_h = (now_ms - it["time"]) / 3_600_000
        if age_h > 24 or age_h < -1:
            continue
        if base and base not in it["coins"]:
            continue
        w = it["impact"] * math.exp(-max(age_h, 0) * math.log(2) / half_life_h)
        num += it["score"] * w
        den += w
        used += 1
    value = num / den if den else 0.0
    label = "bullish" if value > 0.15 else "bearish" if value < -0.15 else "neutral"
    return {"score": round(value, 3), "label": label, "count": used}
