"""The short-term desk: one 5m chart carrying every overlay at once, plus the agents' read.

Same JSON contract as the lenses (see lenses.py), with two additions:
- every zone / level / marker / line / profile carries a `layer` so the UI can switch it off;
- `agents`, `verdict` and `scenarios` from rinng.analysis.agents.
"""

from datetime import datetime, timedelta

import polars as pl

from rinng.analysis import agents, forecast, indicators
from rinng.web import summary
from rinng.web.lenses import (
    BEAR,
    BLUE,
    BULL,
    GREY,
    HORIZON,
    POC,
    _attrs,
    _recent,
    _series,
    _zone,
    candles_json,
    forecast_json,
    lens_profile,
    ts,
)

TF = "5m"
SHOWN = 864  # 3 days of 5m candles: drawn and analysed
PROFILE_WIDTH = 4 * 3600  # seconds of chart width a day's volume histogram may take
LAYERS = ["structure", "liquidity", "profile", "ema", "projection", "setups"]


def _tag(items: list[dict], layer: str) -> list[dict]:
    return [{**i, "layer": layer} for i in items]


def _structure(s: agents.Snapshot) -> tuple[list[dict], list[dict]]:
    zones = []
    for e in _recent(s.events, ["ob_bull", "ob_bear"], 4, s.close, band=0.02):
        zones.append(_zone(e, BULL if e["kind"] == "ob_bull" else BEAR, "OB"))
    for e in _recent(s.events, ["fvg_bull", "fvg_bear"], 4, s.close, band=0.008):
        zones.append(_zone(e, BULL if e["kind"] == "fvg_bull" else BEAR, "FVG", "light"))
    levels = []
    breaks = s.events.filter(pl.col("kind").str.contains("bos|choch")).sort("event_time")
    for e in breaks.tail(6).to_dicts():
        a = _attrs(e["attrs"])
        choch = e["kind"].startswith("choch")
        levels.append(
            {
                "t0": ts(datetime.fromisoformat(a["swing_time"])) if a.get("swing_time") else None,
                "t1": ts(e["event_time"]),
                "price": e["price_low"],
                "color": BULL if e["kind"].endswith("bull") else BEAR,
                "label": "CHoCH" if choch else "BOS",
                "dash": choch,
            }
        )
    return zones, levels


def _liquidity(s: agents.Snapshot) -> tuple[list[dict], list[dict]]:
    lv = s.levels.sort("price_low")
    above = lv.filter((pl.col("kind") == "liquidity_bsl") & (pl.col("price_low") > s.close))
    below = lv.filter((pl.col("kind") == "liquidity_ssl") & (pl.col("price_low") < s.close))
    levels = [
        {
            "t0": ts(e["event_time"]),
            "t1": None,
            "price": e["price_low"],
            "color": BULL if e["kind"] == "liquidity_bsl" else BEAR,
            "label": "BSL" if e["kind"] == "liquidity_bsl" else "SSL",
            "dash": True,
        }
        for e in [*above.head(3).to_dicts(), *below.tail(3).to_dicts()]
    ]
    markers = [
        {
            "time": ts(e["event_time"]),
            "position": "aboveBar" if e["kind"] == "sweep_bsl" else "belowBar",
            "shape": "arrowDown" if e["kind"] == "sweep_bsl" else "arrowUp",
            "color": BEAR if e["kind"] == "sweep_bsl" else BULL,
            "text": "sweep",
        }
        for e in s.sweeps.tail(8).to_dicts()
    ]
    return levels, markers


def _profile(o: pl.DataFrame, s: agents.Snapshot) -> tuple[list[dict], list[dict]]:
    start = s.time.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    part = o.filter(pl.col("open_time") >= start)
    # The buy/sell histogram needs taker volume (missing on OKX candles): levels only there.
    split = part.height > 2 and part["taker_buy_volume"].null_count() == 0
    profiles = lens_profile(part, {"base": part, "period": "day"})["profiles"] if split else []
    # Compact histograms at the start of each day, so they do not sit under the running candle.
    for p in profiles:
        p["t1"] = p["t0"] + PROFILE_WIDTH
    levels = []
    if s.prev_day:
        t0 = ts(s.prev_day["start"] + timedelta(days=1))
        for key, name, color in (
            ("poc", "pdPOC", POC),
            ("vah", "pdVAH", GREY),
            ("val", "pdVAL", GREY),
        ):
            levels.append(
                {
                    "t0": t0,
                    "t1": None,
                    "price": s.prev_day[key],
                    "color": color,
                    "label": name,
                    "dash": key != "poc",
                }
            )
    return profiles, levels


def _setups(scenarios: list[dict], t0: int, t1: int) -> tuple[list[dict], list[dict]]:
    zones, levels = [], []
    for sc in scenarios:
        long = sc["side"] == "long"
        color = BULL if long else BEAR
        zones.append(
            {
                "t0": t0,
                "t1": t1,
                "p0": sc["zone"][0],
                "p1": sc["zone"][1],
                "color": color,
                "label": f"{sc['side']} zone",
                "style": "dash",
            }
        )
        for key, name, dash in (("stop", "stop", True), ("target", "target", False)):
            levels.append(
                {
                    "t0": t0,
                    "t1": t1,
                    "price": sc[key],
                    "color": color,
                    "label": f"{sc['side']} {name}",
                    "dash": dash,
                }
            )
    return zones, levels


def build(hist: pl.DataFrame, h1: pl.DataFrame | None, derivs: dict | None, source: str) -> dict:
    """`hist`: closed 5m candles, as long as available (the projection's pool of past paths);
    `h1`: 1H candles for higher-timeframe context; `derivs`: summary.derivatives_block."""
    o = hist.tail(SHOWN)
    horizon = HORIZON[TF]
    prepared = forecast.prepare(hist)
    fc = forecast.forecast_at(prepared, hist.height - 1, horizon)
    stats = forecast.walk_forward(hist, horizon, prepared=prepared) if fc is not None else None
    chg = summary.price_block(h1)["chg_24h"] if h1 is not None and h1.height > 24 else None
    s = agents.snapshot(o, h1, derivs=derivs, price_chg_24h=chg, fc=fc, stats=stats)
    vs = agents.votes(s)
    v = agents.verdict(vs)
    scs = agents.scenarios(s, vs, v["lean"])

    z_st, l_st = _structure(s)
    l_lq, markers = _liquidity(s)
    profiles, l_pr = _profile(o, s)
    f = indicators.compute(o)
    lines = [
        {"name": "EMA 21", "color": BLUE, "pane": 0, "data": _series(f, "ema_21")},
        {"name": "EMA 50", "color": POC, "pane": 0, "data": _series(f, "ema_50")},
    ]
    step = int(s.bar.total_seconds())
    t0 = ts(s.time)
    z_su, l_su = _setups(scs, t0, t0 + step * horizon)
    out: dict = {
        "candles": candles_json(o),
        "source": source,
        "tf": TF,
        "layers": LAYERS,
        "zones": _tag(z_st, "structure") + _tag(z_su, "setups"),
        "levels": _tag(l_st, "structure")
        + _tag(l_lq, "liquidity")
        + _tag(l_pr, "profile")
        + _tag(l_su, "setups"),
        "markers": _tag(markers, "liquidity"),
        "profiles": _tag(profiles, "profile"),
        "lines": _tag(lines, "ema"),
        "atr": s.atr,
        "agents": [x.to_json() for x in vs],
        "verdict": v,
        "scenarios": scs,
        "stats": stats,
    }
    if fc is not None:
        p = forecast_json(o, hist, fc, stats)
        out["forecast"] = p["forecast"]
        out["levels"] += _tag(p["levels"], "projection")
    return out
