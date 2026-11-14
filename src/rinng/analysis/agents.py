"""Rule-based analyst "agents" for the short-term desk (5m candles).

Each agent reads one family of analysis that already exists in rinng.analysis and returns a
`Vote`: a score in [-1, 1] (sell … buy), a confidence in [0, 1] and the reasons behind it.
`verdict` blends the votes; `scenarios` lays out one long and one short setup with an entry
zone, an invalidation and a target taken from the same levels the charts draw.

Everything is deterministic and reads closed candles only. The numbers describe how the
evidence leans right now; they are not a trading signal or a recommendation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from rinng.analysis import indicators, liquidity, orderflow, smc, volume_profile
from rinng.analysis.forecast import Forecast

WAIT_BAND = 0.2  # |score| below this is "wait"
LEAN_BAND = 0.2  # |blended score| below this is "no clear edge"
SWEEP_MEMORY = 24  # bars a liquidity sweep keeps influencing the liquidity agent
STOP_PAD = 0.3  # ATRs beyond the entry zone for the invalidation
MIN_REWARD = 1.2  # a target must pay at least this many times the risk
REACH = 3.0  # ATRs: how far from price an entry zone may sit


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(min(hi, max(lo, x)))


def fmt_price(v: float) -> str:
    if v >= 1000:
        return f"{v:,.1f}"
    return f"{v:,.2f}" if v >= 1 else f"{v:.5g}"


@dataclass(frozen=True)
class Vote:
    id: str
    name: str
    score: float
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def stance(self) -> str:
        if self.confidence <= 0 or abs(self.score) < WAIT_BAND:
            return "wait"
        return "buy" if self.score > 0 else "sell"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 3),
            "stance": self.stance,
            "reasons": self.reasons,
        }


@dataclass
class Snapshot:
    """Everything the agents read, computed once from closed candles."""

    close: float
    atr: float
    time: datetime
    bar: timedelta  # length of one candle
    events: pl.DataFrame  # smc.events on the desk timeframe
    htf_trend: int  # +1 / -1 / 0: direction of the last structure break on 1H
    pd: dict  # premium/discount row
    levels: pl.DataFrame  # untaken liquidity levels
    sweeps: pl.DataFrame
    feats: dict  # last indicator row
    macd_prev: float | None
    flow: dict
    day: dict | None  # today's volume profile (in progress)
    prev_day: dict | None  # yesterday's volume profile
    funding_pct: float | None = None
    oi_chg_24h: float | None = None
    price_chg_24h: float | None = None
    fc: Forecast | None = None
    stats: dict | None = None

    def zones(self, kinds: list[str]) -> list[dict]:
        """Untouched order blocks / fair value gaps of the given kinds."""
        z = self.events.filter(pl.col("kind").is_in(kinds) & pl.col("invalidated_at").is_null())
        return z.to_dicts()

    def pools(self, kind: str) -> list[float]:
        return self.levels.filter(pl.col("kind") == kind)["price_low"].to_list()


def _last_break(events: pl.DataFrame) -> dict | None:
    b = events.filter(pl.col("kind").str.contains("bos|choch")).sort("event_time").tail(1)
    return b.to_dicts()[0] if b.height else None


def _day_profile(o: pl.DataFrame, start: datetime) -> dict | None:
    part = o.filter(
        (pl.col("open_time") >= start) & (pl.col("open_time") < start + timedelta(days=1))
    )
    if part.height <= 2:
        return None
    prof = volume_profile.profile_from_ohlcv(part, n_bins=48)
    va = volume_profile.value_area(prof)
    return {
        "start": start,
        "shape": volume_profile.classify_shape(prof),
        "poc": float(va.poc),
        "vah": float(va.vah),
        "val": float(va.val),
        # No buy/sell split when the venue's candles carry no taker volume.
        "delta": float(prof["buy_volume"].sum() - prof["sell_volume"].sum())
        if "buy_volume" in prof.columns
        else 0.0,
    }


def snapshot(
    o: pl.DataFrame,
    h1: pl.DataFrame | None = None,
    *,
    derivs: dict | None = None,
    price_chg_24h: float | None = None,
    fc: Forecast | None = None,
    stats: dict | None = None,
) -> Snapshot:
    """`o`: closed candles of the desk timeframe (a few days); `h1`: 1H candles for context;
    `derivs`: the dashboard's derivatives block (funding / open interest), if any."""
    close = float(o["close"][-1])
    feats = indicators.compute(o)
    last = feats.tail(1).to_dicts()[0]
    hist = feats["macd_hist"].drop_nulls()
    atr = last.get("atr") or float((o["high"] - o["low"]).tail(14).mean())
    ev = smc.events(o)
    htf = 0
    if h1 is not None and h1.height >= 30:
        b = _last_break(smc.events(h1))
        htf = 0 if b is None else 1 if b["kind"].endswith("bull") else -1
    # Taker-side volume is missing on some venues (OKX candles): no delta, no CVD.
    flow: dict = {"delta_pct_1h": None}
    hour = o.tail(12)
    vol = float(hour["volume"].sum())
    if vol > 0 and hour["taker_buy_volume"].null_count() == 0:
        span = min(36, o.height - 1)
        cvd = orderflow.delta_features(o.tail(span + 1), cvd_reset=None)["cvd"]
        flow = {
            "delta_pct_1h": float((2 * hour["taker_buy_volume"] - hour["volume"]).sum() / vol),
            "price_chg": close / float(o["close"][-1 - span]) - 1,
            "cvd_chg": float((cvd[-1] or 0.0) - (cvd[0] or 0.0)),
            "volume": float(o.tail(span)["volume"].sum()),
        }
    end = o["open_time"][-1]
    today = end.replace(hour=0, minute=0, second=0, microsecond=0)
    funding = (derivs or {}).get("funding") or {}
    oi = (derivs or {}).get("oi") or {}
    return Snapshot(
        close=close,
        atr=float(atr),
        time=end,
        bar=end - o["open_time"][-2],
        events=ev,
        htf_trend=htf,
        pd=smc.premium_discount(o).tail(1).to_dicts()[0],
        levels=liquidity.liquidity_levels(o).filter(pl.col("invalidated_at").is_null()),
        sweeps=liquidity.sweeps(o).sort("event_time"),
        feats=last,
        macd_prev=float(hist[-2]) if hist.len() > 1 else None,
        flow=flow,
        day=_day_profile(o, today),
        prev_day=_day_profile(o, today - timedelta(days=1)),
        funding_pct=funding.get("rate_pct"),
        oi_chg_24h=oi.get("chg_24h"),
        price_chg_24h=price_chg_24h,
        fc=fc,
        stats=stats,
    )


# --------------------------------------------------------------------------- agents


def structure_agent(s: Snapshot) -> Vote:
    score, reasons = 0.0, []
    b = _last_break(s.events)
    d5 = 0
    if b:
        d5 = 1 if b["kind"].endswith("bull") else -1
        choch = b["kind"].startswith("choch")
        score += d5 * (0.45 if choch else 0.4)
        reasons.append(
            f"Last 5m break: {'CHoCH' if choch else 'BOS'} {'up' if d5 > 0 else 'down'} "
            f"through {fmt_price(b['price_low'])}"
        )
    if s.htf_trend:
        score += 0.3 * s.htf_trend
        reasons.append(f"1H structure is {'bullish' if s.htf_trend > 0 else 'bearish'}")
    eq = s.pd.get("pd_equilibrium")
    if eq is not None:
        cheap = s.close < eq
        score += 0.15 if cheap else -0.15
        reasons.append(
            f"Price is in the {'discount' if cheap else 'premium'} half of the 5m swing range"
        )
    for side, kinds in ((1, ["ob_bull", "fvg_bull"]), (-1, ["ob_bear", "fvg_bear"])):
        inside = [z for z in s.zones(kinds) if z["price_low"] <= s.close <= z["price_high"]]
        if inside:
            z = inside[-1]
            score += 0.2 * side
            what = "order block" if z["kind"].startswith("ob") else "fair value gap"
            reasons.append(
                f"Trading inside an untouched {'bullish' if side > 0 else 'bearish'} {what} "
                f"{fmt_price(z['price_low'])}–{fmt_price(z['price_high'])}"
            )
    agree = d5 and s.htf_trend and d5 == s.htf_trend
    clash = d5 and s.htf_trend and d5 != s.htf_trend
    conf = 0.45 + (0.3 if agree else -0.15 if clash else 0.0)
    if clash:
        reasons.append("5m and 1H structure disagree: lower confidence")
    return Vote("structure", "Structure (SMC)", _clip(score), conf if b else 0.2, reasons)


def liquidity_agent(s: Snapshot) -> Vote:
    score, reasons, recency = 0.0, [], 0.0
    if s.sweeps.height:
        sw = s.sweeps.tail(1).to_dicts()[0]
        age = (s.time - sw["event_time"]) / s.bar
        if age <= SWEEP_MEMORY:
            recency = 1 - age / SWEEP_MEMORY
            low = sw["kind"] == "sweep_ssl"
            score += (0.6 if low else -0.6) * recency
            reasons.append(
                f"{'Sell' if low else 'Buy'}-side liquidity was swept {int(age)} candles ago "
                f"and price closed back {'above' if low else 'below'} it"
            )
    above = [p for p in s.pools("liquidity_bsl") if p > s.close]
    below = [p for p in s.pools("liquidity_ssl") if p < s.close]
    if above and below:
        up, dn = min(above) - s.close, s.close - max(below)
        score += 0.25 * (dn - up) / (dn + up)
        near, far = (min(above), "BSL") if up < dn else (max(below), "SSL")
        reasons.append(
            f"Nearest resting liquidity is {far} {fmt_price(near)} "
            f"({abs(near / s.close - 1) * 100:.2f}% away): the closer pool is the likelier draw"
        )
    elif above or below:
        side = 1 if above else -1
        score += 0.2 * side
        reasons.append(
            f"Only {'buy' if above else 'sell'}-side liquidity is left nearby "
            f"({fmt_price(min(above) if above else max(below))})"
        )
    if not reasons:
        reasons.append("No recent sweep and no untaken liquidity pool nearby")
    return Vote("liquidity", "Liquidity", _clip(score), 0.3 + 0.4 * recency, reasons)


def profile_agent(s: Snapshot) -> Vote:
    ref = s.prev_day
    if ref is None:
        return Vote("profile", "Volume profile", 0.0, 0.0, ["Not enough candles for a profile"])
    score, reasons = 0.0, []
    outside = s.close > ref["vah"] or s.close < ref["val"]
    if s.close > ref["vah"]:
        score += 0.5
        reasons.append(f"Accepted above yesterday's value area high {fmt_price(ref['vah'])}")
    elif s.close < ref["val"]:
        score -= 0.5
        reasons.append(f"Accepted below yesterday's value area low {fmt_price(ref['val'])}")
    else:
        half = max(ref["vah"] - ref["val"], 1e-12) / 2
        pull = _clip((ref["poc"] - s.close) / half)
        score += 0.2 * pull
        reasons.append(
            f"Inside yesterday's value area: rotation towards POC {fmt_price(ref['poc'])} "
            "is the base case"
        )
    if s.day:
        if s.day["shape"] in ("P", "b"):
            up = s.day["shape"] == "P"
            score += 0.2 if up else -0.2
            reasons.append(
                f"Today's profile is {s.day['shape']}-shaped: volume built at "
                f"{'higher' if up else 'lower'} prices"
            )
        if abs(s.day["delta"]) > 0:
            buy = s.day["delta"] > 0
            score += 0.15 if buy else -0.15
            reasons.append(f"Today's taker delta is net {'buying' if buy else 'selling'}")
    return Vote("profile", "Volume profile", _clip(score), 0.5 if outside else 0.3, reasons)


def momentum_agent(s: Snapshot) -> Vote:
    f = s.feats
    score, reasons = 0.0, []
    e21, e50, e200 = f.get("ema_21"), f.get("ema_50"), f.get("ema_200")
    if e21 is not None and e50 is not None:
        if s.close > e21 > e50:
            score += 0.4
            reasons.append("Price > EMA 21 > EMA 50: short-term trend is up")
        elif s.close < e21 < e50:
            score -= 0.4
            reasons.append("Price < EMA 21 < EMA 50: short-term trend is down")
        else:
            reasons.append("EMA 21 and EMA 50 are tangled: no clean trend")
    if e200 is not None:
        score += 0.1 if s.close > e200 else -0.1
    hist = f.get("macd_hist")
    if hist is not None:
        score += 0.25 if hist > 0 else -0.25
        rising = s.macd_prev is not None and hist > s.macd_prev
        score += 0.1 if rising else -0.1
        reasons.append(
            f"MACD histogram is {'positive' if hist > 0 else 'negative'} and "
            f"{'rising' if rising else 'falling'}"
        )
    rsi = f.get("rsi")
    if rsi is not None:
        if rsi >= 70:
            score -= 0.25
            reasons.append(f"RSI {rsi:.0f}: stretched to the upside")
        elif rsi <= 30:
            score += 0.25
            reasons.append(f"RSI {rsi:.0f}: stretched to the downside")
        else:
            score += (rsi - 50) / 50 * 0.3
            reasons.append(f"RSI {rsi:.0f}")
    adx = f.get("adx") or 0.0
    conf = 0.35 + 0.4 * min(1.0, adx / 40)
    return Vote("momentum", "Momentum", _clip(score), conf if reasons else 0.0, reasons)


def flow_agent(s: Snapshot) -> Vote:
    score, reasons = 0.0, []
    pct = s.flow["delta_pct_1h"]
    if pct is None:
        reasons.append("No taker-side volume on this venue: reading derivatives only")
    else:
        score += _clip(pct / 0.15) * 0.45
        side = "bought" if pct >= 0 else "sold"
        reasons.append(f"Last hour: takers net {side} {abs(pct) * 100:.1f}% of volume")
        dp, dc = s.flow["price_chg"], s.flow["cvd_chg"]
        material = s.flow["volume"] > 0 and abs(dc) / s.flow["volume"] > 0.02
        if material and dp > 0 > dc:
            score -= 0.3
            reasons.append("Price rose while CVD fell: the move up lacked aggressive buying")
        elif material and dp < 0 < dc:
            score += 0.3
            reasons.append("Price fell while CVD rose: selling is being absorbed")
    have = s.funding_pct is not None or s.oi_chg_24h is not None
    if s.funding_pct is not None:
        if s.funding_pct > 0.03:
            score -= 0.15
            reasons.append(f"Funding {s.funding_pct:.4f}%: longs are crowded")
        elif s.funding_pct < -0.01:
            score += 0.15
            reasons.append(f"Funding {s.funding_pct:.4f}%: shorts are paying")
    if s.oi_chg_24h is not None and s.price_chg_24h is not None and s.oi_chg_24h > 0:
        up = s.price_chg_24h >= 0
        score += 0.15 if up else -0.15
        reasons.append(
            f"OI +{s.oi_chg_24h:.1f}% with price {'up' if up else 'down'} over 24h: "
            f"new {'longs' if up else 'shorts'} are opening"
        )
    conf = (0.4 if pct is not None else 0.1) + 0.2 * have
    return Vote("flow", "Order flow & derivatives", _clip(score), conf, reasons)


def projection_agent(s: Snapshot) -> Vote:
    fc = s.fc
    if fc is None:
        return Vote("projection", "Projection", 0.0, 0.0, ["Not enough history to project"])
    q = {k: float(fc.quantiles[i][-1]) for i, k in enumerate((5, 10, 25, 50, 75, 90, 95))}
    drift = float(fc.z_quantiles[3][-1]) / np.sqrt(fc.horizon)
    width = max(q[75] - q[25], 1e-12)
    skew = ((q[75] - fc.close) - (fc.close - q[25])) / width
    score = _clip(drift / 0.5) * 0.6 + _clip(skew) * 0.4
    reasons = [
        f"Median of {fc.analogs} similar past setups after {fc.horizon} candles: "
        f"{fmt_price(q[50])} ({(q[50] / fc.close - 1) * 100:+.2f}%)",
        f"Middle half of outcomes: {fmt_price(q[25])} – {fmt_price(q[75])}",
    ]
    hit = (s.stats or {}).get("direction_hit")
    conf = 0.2
    if hit is not None:
        conf = _clip(0.15 + 2 * (hit - 0.5), 0.15, 0.7)
        reasons.append(
            f"Backtest: the median called direction right {hit * 100:.0f}% of the time"
            + (" — treat this as a range, not a call" if hit < 0.55 else "")
        )
    return Vote("projection", "Projection", _clip(score), conf, reasons)


AGENTS = (
    structure_agent,
    liquidity_agent,
    profile_agent,
    momentum_agent,
    flow_agent,
    projection_agent,
)


def votes(s: Snapshot) -> list[Vote]:
    return [agent(s) for agent in AGENTS]


def verdict(vs: list[Vote]) -> dict:
    """Confidence-weighted blend of the votes."""
    weight = sum(v.confidence for v in vs)
    score = sum(v.score * v.confidence for v in vs) / weight if weight > 0 else 0.0
    count = {k: sum(v.stance == k for v in vs) for k in ("buy", "sell", "wait")}
    lean = "long" if score >= LEAN_BAND else "short" if score <= -LEAN_BAND else "none"
    return {"score": round(score, 3), "lean": lean, **count, "total": len(vs)}


# --------------------------------------------------------------------------- scenarios


def _entry_zone(s: Snapshot, side: int) -> tuple[float, float, str]:
    """Nearest area on the "right" side of price for a setup: (low, high, label)."""
    reach = REACH * s.atr
    kinds = ["ob_bull", "fvg_bull"] if side > 0 else ["ob_bear", "fvg_bear"]
    near = [
        z
        for z in s.zones(kinds)
        if (z["price_low"] <= s.close if side > 0 else z["price_high"] >= s.close)
        and abs((z["price_high"] if side > 0 else z["price_low"]) - s.close) <= reach
        and z["price_high"] > z["price_low"]
    ]
    if near:
        z = (
            max(near, key=lambda z: z["price_high"])
            if side > 0
            else min(near, key=lambda z: z["price_low"])
        )
        tag = "OB" if z["kind"].startswith("ob") else "FVG"
        return z["price_low"], z["price_high"], f"{'bullish' if side > 0 else 'bearish'} {tag}"
    pad = 0.15 * s.atr
    if s.prev_day:
        names = (
            (("pdVAL", "val"), ("pdPOC", "poc"))
            if side > 0
            else (("pdVAH", "vah"), ("pdPOC", "poc"))
        )
        for name, key in names:
            lv = s.prev_day[key]
            if 0 < (s.close - lv) * side <= reach:
                return lv - pad, lv + pad, name
    pools = s.pools("liquidity_ssl" if side > 0 else "liquidity_bsl")
    pools = [p for p in pools if 0 < (s.close - p) * side <= reach]
    if pools:
        p = max(pools) if side > 0 else min(pools)
        lo, hi = (p - 0.25 * s.atr, p) if side > 0 else (p, p + 0.25 * s.atr)
        return lo, hi, f"{'SSL' if side > 0 else 'BSL'} sweep"
    a, b = s.close - side * s.atr, s.close - side * 0.5 * s.atr
    return min(a, b), max(a, b), "0.5–1 ATR pullback" if side > 0 else "0.5–1 ATR bounce"


def _targets(s: Snapshot, side: int) -> list[tuple[float, str]]:
    out = [
        (p, "BSL" if side > 0 else "SSL")
        for p in s.pools("liquidity_bsl" if side > 0 else "liquidity_ssl")
    ]
    if s.prev_day:
        out += [(s.prev_day[k], f"pd{k.upper()}") for k in ("poc", "vah", "val")]
    if s.day:
        out.append((s.day["poc"], "dPOC"))
    for z in s.zones(["ob_bear", "fvg_bear"] if side > 0 else ["ob_bull", "fvg_bull"]):
        tag = "OB" if z["kind"].startswith("ob") else "FVG"
        out.append((z["price_low"] if side > 0 else z["price_high"], f"opposing {tag}"))
    if s.fc is not None:
        i = 4 if side > 0 else 2  # q75 / q25 at the end of the projection
        out.append(
            (float(s.fc.quantiles[i][-1]), "projection 75%" if side > 0 else "projection 25%")
        )
    return out


def scenario(s: Snapshot, side: int, vs: list[Vote], lean: str) -> dict:
    """One setup (side +1 long, -1 short): where it would make sense, where it is wrong and
    where it could go, with touch odds from the projection when there is one."""
    lo, hi, label = _entry_zone(s, side)
    edge, far = (hi, lo) if side > 0 else (lo, hi)
    entry = min(s.close, edge) if side > 0 else max(s.close, edge)
    stop = far - side * STOP_PAD * s.atr
    risk = abs(entry - stop)
    ok = sorted(
        (t for t in _targets(s, side) if (t[0] - entry) * side >= MIN_REWARD * risk),
        key=lambda t: abs(t[0] - entry),
    )
    target, target_label = ok[0] if ok else (entry + side * 2 * risk, "2R")
    inside = lo <= s.close <= hi
    word, back = ("long", "above") if side > 0 else ("short", "below")
    trigger = (
        f"Price is inside the {label} now: a 5m close back {back} {fmt_price(edge)} confirms"
        if inside
        else f"Wait for price to reach the {label} {fmt_price(lo)}–{fmt_price(hi)}, then a 5m "
        f"close back {back} {fmt_price(edge)}"
    )
    favor = sum(v.stance == ("buy" if side > 0 else "sell") for v in vs)
    fc = s.fc
    return {
        "side": word,
        "zone": [lo, hi],
        "zone_label": label,
        "entry": entry,
        "stop": stop,
        "target": target,
        "target_label": target_label,
        "rr": abs(target - entry) / risk if risk > 0 else None,
        "trigger": trigger,
        "favor": favor,
        "aligned": lean == word,
        "p_entry": None if fc is None or inside else fc.touch_probability(edge),
        "p_target": None if fc is None else fc.touch_probability(target),
        "p_stop": None if fc is None else fc.touch_probability(stop),
    }


def scenarios(s: Snapshot, vs: list[Vote], lean: str) -> list[dict]:
    return [scenario(s, 1, vs, lean), scenario(s, -1, vs, lean)]
