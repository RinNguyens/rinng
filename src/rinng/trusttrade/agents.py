"""LLM roles: domain analysts, the trader, and short/long-term reflection agents.

All outputs are structured (Pydantic schemas → the API's JSON-schema output mode), so a malformed
reply is an error, never a silently mis-parsed trade.

Deviation from the paper: there is no Researcher (bull/bear debate) stage between the analysts and
the trader. The paper's own ablation (Fig. 1b-c) finds most of the benefit at the Analyst→Trader
step and drops its Risk Manager for the same reason; skipping the debate keeps each day at
N·domains + variants calls. The trader receives the evidence the variant allows.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, create_model

from rinng.trusttrade.consensus import Claim

Polarity = Literal["bullish", "bearish", "neutral"]

SUBJECTS: dict[str, tuple[str, ...]] = {
    "market": (
        "trend",
        "momentum",
        "moving_averages",
        "rsi",
        "macd",
        "stochastic",
        "adx",
        "volatility",
        "volume",
        "taker_flow",
        "support",
        "resistance",
        "bollinger_bands",
        "range_position",
        "price_action",
    ),
    "derivatives": (
        "funding",
        "open_interest",
        "oi_price_divergence",
        "long_short_ratio",
        "leverage",
        "positioning",
    ),
    "news": (
        "regulation",
        "exchange_listing",
        "etf_flows",
        "macro",
        "security_incident",
        "adoption",
        "project_update",
        "market_sentiment",
        "other",
    ),
}

DOMAIN_NOTES = {
    "market": "daily candles and technical indicators",
    "derivatives": "perpetual-futures funding, open interest and the long/short account ratio",
    "news": "recent headlines (titles only)",
}


def claim_model(domain: str) -> type[BaseModel]:
    subject = Literal[SUBJECTS[domain]]  # type: ignore[valid-type]
    return create_model(
        f"{domain.title()}Claim",
        subject=(subject, Field(description="what the claim is about")),
        predicate=(str, Field(description="the fact or inference, at most 15 words")),
        polarity=(Polarity, Field(description="implication for price over the next days")),
        value=(float | None, Field(description="main number in the claim, in the data's units")),
        unit=(str | None, Field(description="unit of value, e.g. % or x, or null")),
        date=(str | None, Field(description="YYYY-MM-DD if the claim is about a specific day")),
    )


def report_model(domain: str) -> type[BaseModel]:
    return create_model(
        f"{domain.title()}Report",
        summary=(str, Field(description="3-5 sentence assessment")),
        stance=(Polarity, ...),
        confidence=(int, Field(description="0-100")),
        claims=(list[claim_model(domain)], Field(description="3 to 8 atomic claims")),
    )


class Decision(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    pct: Literal[0, 25, 50, 75, 100] = Field(
        description="BUY: % of free cash to spend; SELL: % of the holding to sell; HOLD: 0"
    )
    confidence: int = Field(description="0-100")
    rationale: str = Field(description="2-4 sentences")
    key_evidence: list[str] = Field(description="the 1-4 items that drove the decision")


class Reflection(BaseModel):
    strengths: str
    weaknesses: str
    recommendation: str = Field(description="concrete guidance for the next decisions")
    risk_posture: Literal["more_aggressive", "keep", "more_conservative"]


# --------------------------------------------------------------------------- analysts

ANALYST_SYSTEM = """You are the {domain} analyst on a crypto trading desk. You see only {note}.
Assess what this data implies for the asset's price over the next few days.

Then break your assessment into 3-8 atomic claims. One claim = one fact read from the data or one
inference from it. For each claim:
- subject: pick the closest item from the allowed list;
- predicate: a short phrase, e.g. "close above the 50-day EMA" or "funding turned negative";
- polarity: bullish, bearish or neutral for price over the next days;
- value: the main number the claim rests on, copied from the data in its units (null if none);
- date: only when the claim is about one specific day shown in the data, else null.

Use only the data given. Do not bring in anything you may know about this asset's later price
history; the data ends at the decision time and nothing after it is known."""


def analyst_prompts(domain: str, label: str, when: str, data: dict) -> tuple[str, str]:
    system = ANALYST_SYSTEM.format(domain=domain, note=DOMAIN_NOTES[domain])
    user = (
        f"Asset: {label}. Decision time: {when} (start of the day, UTC).\n"
        f"{domain.title()} data (JSON):\n{json.dumps(data, separators=(',', ':'))}"
    )
    return system, user


def to_claims(report: BaseModel, agent: int, domain: str) -> list[Claim]:
    return [
        Claim(
            agent=agent,
            domain=domain,
            subject=c.subject,
            predicate=c.predicate,
            polarity=c.polarity,
            value=c.value,
            unit=c.unit,
            date=c.date,
        )
        for c in report.claims
    ]


def report_text(report: BaseModel) -> str:
    claims = "\n".join(
        f"  - {c.subject}: {c.predicate}"
        + ("" if c.value is None else f" [{c.value:g}{c.unit or ''}]")
        + f" ({c.polarity})"
        for c in report.claims
    )
    return (
        f"Stance: {report.stance} (confidence {report.confidence}/100)\n"
        f"Summary: {report.summary}\nClaims:\n{claims}"
    )


# --------------------------------------------------------------------------- trader

TRADER_SYSTEM = """You are the trader of a long-only spot crypto account (no leverage, no
shorting). Once a day you decide one action for one asset: BUY, SELL or HOLD. The order fills at
the day's open; a fee of {fee}% is paid on each fill. Your goal is good risk-adjusted return:
growth matters, and so does avoiding deep drawdowns. Holding cash is a valid position.

{sizing}

Base the decision only on the material provided. Do not use anything you may know about this
asset's price after the decision time."""

SIZING = {
    "partial": "Size: BUY p% spends p% of the free cash; SELL p% sells p% of the holding; "
    "p is 25, 50, 75 or 100. HOLD uses 0.",
    "full": "Size: every BUY spends all free cash and every SELL sells the whole holding; "
    "use pct 100 for BUY/SELL and 0 for HOLD.",
}


def trader_prompts(
    *,
    label: str,
    when: str,
    fee_pct: float,
    allocation: str,
    position: dict,
    sections: list[tuple[str, str]],
) -> tuple[str, str]:
    system = TRADER_SYSTEM.format(fee=fee_pct, sizing=SIZING[allocation])
    body = [
        f"Asset: {label}. Decision time: {when} (start of the day, UTC).",
        "Account: " + json.dumps(position),
    ]
    for title, text in sections:
        body.append(f"## {title}\n{text}")
    body.append("Decide today's action.")
    return system, "\n\n".join(body)


# --------------------------------------------------------------------------- reflection

REFLECT_SYSTEM = """You review a trading agent's recent decisions on one crypto asset at the
{span} horizon ({horizons} days). Each row is one day's decision; R columns are the realized PnL of
that day's trade over the horizon as % of portfolio value, SR columns the portfolio's annualized
Sharpe over the horizon. Empty cells are not known yet. Slopes > 0 mean performance is improving.

Say briefly what has worked, what has not, and what the trader should do differently in the next
decisions (sizing, when to act, when to stay out). Be concrete and short."""


def reflect_prompts(
    *, span: str, horizons: tuple[int, ...], label: str, when: str, table: str
) -> tuple[str, str]:
    system = REFLECT_SYSTEM.format(span=span, horizons=", ".join(map(str, horizons)))
    user = f"Asset: {label}. Now: {when}.\n\nDecision log:\n{table}"
    return system, user
