"""Turn analysis results into JSON for the web charts. Each "lens" is one way of looking.

Shared JSON contract (times are UTC seconds, as Lightweight Charts expects):
- markers: [{time, position: aboveBar|belowBar, shape, color, text}]
- zones:   [{t0, t1 (null = extends to the right), p0, p1, color, label, style}]
- levels:  [{t0, t1, price, color, label, dash}]
- lines:   [{name, color, pane, data: [{time, value}]}]  (pane 0 = the candle pane)
- histos:  [{name, pane, data: [{time, value, color}]}]
- profiles:[{t0, t1, closed, shape, poc, val, vah, buy, sell, rows: [[lo, hi, buy, sell]]}]
- legend:  [[color, text]] so the viewer knows what they are looking at.

Lenses read closed candles only; all definitions live in rinng.analysis.
"""

import json
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from rinng.analysis import (
    derivatives,
    elliott,
    forecast,
    indicators,
    liquidity,
    orderflow,
    smc,
    structure,
    volume_profile,
    wyckoff,
)
from rinng.analysis.structure import swing_table

BULL, BEAR, POC, GREY, PURPLE, BLUE = (
    "#26a69a",
    "#ef5350",
    "#ff9800",
    "#78909c",
    "#ab47bc",
    "#42a5f5",
)


def ts(value: datetime | None) -> int | None:
    return None if value is None else int(value.timestamp())


def candles_json(ohlcv: pl.DataFrame) -> list[dict]:
    o = ohlcv.select(
        "open_time", "open", "high", "low", "close", "volume", "taker_buy_volume"
    ).to_dicts()
    return [
        {
            "time": ts(r["open_time"]),
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"],
            "buy": r["taker_buy_volume"],
        }
        for r in o
    ]


def _attrs(value: str | None) -> dict:
    return json.loads(value) if value else {}


def _zone(e: dict, color: str, label: str, style: str = "solid") -> dict:
    return {
        "t0": ts(e["event_time"]),
        "t1": ts(e["invalidated_at"]),
        "p0": e["price_low"],
        "p1": e["price_high"],
        "color": color,
        "label": label,
        "style": style,
    }


def _recent(
    events: pl.DataFrame, kinds: list[str], keep: int, near: float | None = None, band: float = 0.12
) -> list[dict]:
    """Active events first, then the most recent ones.

    `near`: current price; active zones farther than `band` (fraction) are dropped.
    """
    sub = events.filter(pl.col("kind").is_in(kinds)).sort("event_time")
    active = sub.filter(pl.col("invalidated_at").is_null())
    if near is not None:
        active = active.filter(
            (pl.col("price_high") >= near * (1 - band)) & (pl.col("price_low") <= near * (1 + band))
        )
    done = sub.filter(pl.col("invalidated_at").is_not_null()).tail(max(0, keep - active.height))
    return pl.concat([done, active.tail(keep)]).to_dicts()


# --------------------------------------------------------------------------- lenses


def lens_structure(o: pl.DataFrame, ctx: dict) -> dict:
    sw = swing_table(structure.swings(o, 5))
    markers = [
        {
            "time": ts(r["event_time"]),
            "position": "aboveBar" if r["kind"] == "swing_high" else "belowBar",
            "shape": "circle",
            "color": BULL if r["kind"] == "swing_high" else BEAR,
            "text": r["label"] or "",
        }
        for r in sw.to_dicts()
    ]
    ev = smc.events(o)
    levels = []
    for e in ev.filter(pl.col("kind").str.contains("bos|choch")).to_dicts():
        a = _attrs(e["attrs"])
        bull = e["kind"].endswith("bull")
        levels.append(
            {
                "t0": ts(datetime.fromisoformat(a["swing_time"])) if a.get("swing_time") else None,
                "t1": ts(e["event_time"]),
                "price": e["price_low"],
                "color": BULL if bull else BEAR,
                "label": "CHoCH" if e["kind"].startswith("choch") else "BOS",
                "dash": e["kind"].startswith("choch"),
            }
        )
    zones = []
    price = float(o["close"][-1])
    for e in _recent(ev, ["ob_bull", "ob_bear"], 8, price):
        zones.append(_zone(e, BULL if e["kind"] == "ob_bull" else BEAR, "OB"))
    for e in _recent(ev, ["breaker_bull", "breaker_bear"], 4, price):
        zones.append(_zone(e, BULL if e["kind"] == "breaker_bull" else BEAR, "breaker", "dash"))
    for e in _recent(ev, ["fvg_bull", "fvg_bear"], 10, price, band=0.06):
        zones.append(_zone(e, BULL if e["kind"] == "fvg_bull" else BEAR, "FVG", "light"))
    pd_ = smc.premium_discount(o).tail(1).to_dicts()[0]
    if pd_.get("pd_range_high") is not None:
        zones.append(
            {
                "t0": ts(o["open_time"][-60 if o.height > 60 else 0]),
                "t1": None,
                "p0": pd_["pd_equilibrium"],
                "p1": pd_["pd_range_high"],
                "color": BEAR,
                "label": "premium",
                "style": "faint",
            }
        )
        zones.append(
            {
                "t0": ts(o["open_time"][-60 if o.height > 60 else 0]),
                "t1": None,
                "p0": pd_["pd_range_low"],
                "p1": pd_["pd_equilibrium"],
                "color": BULL,
                "label": "discount",
                "style": "faint",
            }
        )
    return {
        "markers": markers,
        "levels": levels[-40:],
        "zones": zones,
        "legend": [
            [BULL, "HH/HL, bullish BOS/CHoCH, bullish OB/FVG"],
            [BEAR, "LH/LL, bearish BOS/CHoCH, bearish OB/FVG"],
            ["", "dashed = CHoCH (trend change); faint zones = premium/discount"],
        ],
    }


def lens_liquidity(o: pl.DataFrame, ctx: dict) -> dict:
    lv = liquidity.liquidity_levels(o)
    levels = [
        {
            "t0": ts(e["event_time"]),
            "t1": ts(e["invalidated_at"]),
            "price": e["price_low"],
            "color": BULL if e["kind"] == "liquidity_bsl" else BEAR,
            "label": "BSL" if e["kind"] == "liquidity_bsl" else "SSL",
            "dash": True,
        }
        for e in _recent(lv, ["liquidity_bsl", "liquidity_ssl"], 40)
    ]
    eq = liquidity.equal_levels(o)
    for e in eq.sort("event_time").tail(10).to_dicts():
        levels.append(
            {
                "t0": ts(e["event_time"]),
                "t1": ts(e["invalidated_at"]),
                "price": e["price_high"],
                "color": PURPLE,
                "label": e["kind"].upper(),
                "dash": False,
            }
        )
    sw = liquidity.sweeps(o)
    markers = [
        {
            "time": ts(e["event_time"]),
            "position": "aboveBar" if e["kind"] == "sweep_bsl" else "belowBar",
            "shape": "arrowDown" if e["kind"] == "sweep_bsl" else "arrowUp",
            "color": BEAR if e["kind"] == "sweep_bsl" else BULL,
            "text": "sweep",
        }
        for e in sw.sort("event_time").tail(30).to_dicts()
    ]
    return {
        "levels": levels,
        "markers": markers,
        "legend": [
            [BULL, "BSL: buy-side liquidity above (old highs)"],
            [BEAR, "SSL: sell-side liquidity below (old lows)"],
            [PURPLE, "EQH/EQL: equal highs/lows"],
            ["", "line ends = taken; arrow = sweep (taken, then closed back inside)"],
        ],
    }


def lens_profile(o: pl.DataFrame, ctx: dict) -> dict:
    base: pl.DataFrame = ctx.get("base", o)
    period = ctx.get("period", "week")
    start = base["open_time"].min()
    if period == "day":
        first = start.replace(hour=0, minute=0, second=0)
        step = timedelta(days=1)
    else:
        first = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0)
        step = timedelta(days=7)
    last_close = base["open_time"].max() + (base["open_time"][1] - base["open_time"][0])
    profiles = []
    t = first
    while t <= base["open_time"].max():
        part = base.filter((pl.col("open_time") >= t) & (pl.col("open_time") < t + step))
        if part.height > 2:
            prof = volume_profile.profile_from_ohlcv(part, n_bins=48)
            va = volume_profile.value_area(prof)
            rows = prof.select("price_low", "price_high", "buy_volume", "sell_volume").rows()
            buy = float(prof["buy_volume"].sum())
            sell = float(prof["sell_volume"].sum())
            profiles.append(
                {
                    "t0": ts(t),
                    "t1": ts(t + step),
                    "closed": t >= start and t + step <= last_close,
                    "shape": volume_profile.classify_shape(prof),
                    "poc": va.poc,
                    "val": va.val,
                    "vah": va.vah,
                    "buy": buy,
                    "sell": sell,
                    "rows": [[r[0], r[1], r[2], r[3]] for r in rows],
                }
            )
        t += step
    naked = volume_profile.profile_events(base, period, n_bins=48)
    levels = [
        {
            "t0": ts(e["known_at"]),
            "t1": ts(e["invalidated_at"]),
            "price": e["price_low"],
            "color": POC,
            "label": "nPOC",
            "dash": True,
        }
        for e in naked.filter(pl.col("kind") == "naked_poc").to_dicts()
    ]
    return {
        "profiles": profiles,
        "levels": levels,
        "legend": [
            [BULL, "taker buy volume"],
            [BEAR, "taker sell volume"],
            [POC, "POC; dotted = naked POC not yet touched"],
            ["", "D/P/b/DD label = profile shape; number below = delta (buy − sell)"],
        ],
    }


def lens_wyckoff(o: pl.DataFrame, ctx: dict) -> dict:
    markers = []
    for e in wyckoff.climaxes(o).to_dicts():
        sc = e["kind"] == "selling_climax"
        markers.append(
            {
                "time": ts(e["event_time"]),
                "position": "belowBar" if sc else "aboveBar",
                "shape": "arrowUp" if sc else "arrowDown",
                "color": BULL if sc else BEAR,
                "text": "SC" if sc else "BC",
            }
        )
    zones = []
    for e in wyckoff.trading_ranges(o).to_dicts():
        if e["kind"] == "trading_range":
            zones.append(_zone(e, BLUE, "range", "light"))
        else:
            up = e["kind"] == "spring"
            markers.append(
                {
                    "time": ts(e["event_time"]),
                    "position": "belowBar" if up else "aboveBar",
                    "shape": "circle",
                    "color": BULL if up else BEAR,
                    "text": "spring" if up else "UT",
                }
            )
    zz = elliott.zigzag_table(elliott.zigzag(o, threshold=ctx.get("zigzag", 0.05)))
    line = [
        {"time": ts(r["event_time"]), "value": r["price"]} for r in zz.sort("event_time").to_dicts()
    ]
    for c in elliott.impulse_candidates(o, threshold=ctx.get("zigzag", 0.05)).to_dicts():
        a = _attrs(c["attrs"])
        idx = a.get("indices", [])
        times = o["open_time"].to_list()
        for n, i in enumerate(idx[1:], start=1):
            markers.append(
                {
                    "time": ts(times[i]),
                    "position": "aboveBar" if (n % 2) else "belowBar",
                    "shape": "square",
                    "color": PURPLE,
                    "text": str(n),
                }
            )
    markers.sort(key=lambda m: m["time"])
    return {
        "markers": markers,
        "zones": zones,
        "lines": [{"name": "zigzag", "color": PURPLE, "pane": 0, "data": line}],
        "legend": [
            [BULL, "SC: selling climax; spring"],
            [BEAR, "BC: buying climax; UT: upthrust"],
            [BLUE, "trading range (Wyckoff)"],
            [PURPLE, "zigzag; 1–5 = Elliott impulse candidates (several counts possible)"],
        ],
    }


def _series(frame: pl.DataFrame, col: str) -> list[dict]:
    f = frame.select("open_time", col).drop_nulls()
    return [{"time": ts(t), "value": float(v)} for t, v in f.iter_rows()]


def lens_derivatives(o: pl.DataFrame, ctx: dict) -> dict:
    lines, histos, legend = [], [], []
    pane = 1
    if ctx.get("funding") is not None and not ctx["funding"].is_empty():
        f = derivatives.funding_features(o, ctx["funding"])
        histos.append(
            {
                "name": "funding %",
                "precision": 4,
                "pane": pane,
                "data": [
                    {
                        "time": d["time"],
                        "value": d["value"] * 100,
                        "color": BULL if d["value"] >= 0 else BEAR,
                    }
                    for d in _series(f, "funding_rate")
                ],
            }
        )
        legend.append([BULL, f"pane {pane}: funding rate (%)"])
        pane += 1
    if ctx.get("oi") is not None and not ctx["oi"].is_empty():
        f = derivatives.open_interest_features(o, ctx["oi"])
        lines.append({"name": "OI", "color": BLUE, "pane": pane, "data": _series(f, "oi")})
        legend.append([BLUE, f"pane {pane}: open interest ({ctx.get('asset', 'base')})"])
        pane += 1
    if ctx.get("ls") is not None and not ctx["ls"].is_empty():
        f = derivatives.long_short_features(o, ctx["ls"])
        lines.append({"name": "L/S", "color": POC, "pane": pane, "data": _series(f, "ls_ratio")})
        legend.append([POC, f"pane {pane}: long/short account ratio"])
        pane += 1
    d = orderflow.delta_features(o, cvd_reset=None)
    lines.append({"name": "CVD", "color": PURPLE, "pane": pane, "data": _series(d, "cvd")})
    legend.append([PURPLE, f"pane {pane}: CVD from taker buy volume"])
    if len(legend) == 1:
        legend.insert(0, ["", "no funding/OI/long-short data for this range"])
    return {"lines": lines, "histos": histos, "legend": legend}


def lens_indicators(o: pl.DataFrame, ctx: dict) -> dict:
    f = indicators.compute(o)
    lines = [
        {"name": "EMA 21", "color": BLUE, "pane": 0, "data": _series(f, "ema_21")},
        {"name": "EMA 50", "color": POC, "pane": 0, "data": _series(f, "ema_50")},
        {"name": "EMA 200", "color": PURPLE, "pane": 0, "data": _series(f, "ema_200")},
        {"name": "RSI", "color": PURPLE, "pane": 1, "data": _series(f, "rsi")},
    ]
    hist = f.select("open_time", "macd_hist").drop_nulls()
    histos = [
        {
            "name": "MACD hist",
            "pane": 2,
            "data": [
                {"time": ts(t), "value": float(v), "color": BULL if v >= 0 else BEAR}
                for t, v in hist.iter_rows()
            ],
        }
    ]
    d = orderflow.delta_features(o)
    histos.append(
        {
            "name": "delta",
            "pane": 3,
            "data": [
                {"time": ts(t), "value": float(v), "color": BULL if v >= 0 else BEAR}
                for t, v in d.select("open_time", "delta").drop_nulls().iter_rows()
            ],
        }
    )
    return {
        "lines": lines,
        "histos": histos,
        "guides": [{"pane": 1, "values": [30, 70]}],
        "legend": [
            [BLUE, "EMA 21"],
            [POC, "EMA 50"],
            [PURPLE, "EMA 200; pane 1: RSI 14"],
            ["", "pane 2: MACD histogram; pane 3: delta per candle"],
        ],
    }


# Bars of lookahead per timeframe: 5m ≈ 4 hours, 15m/1h ≈ half a day/2 days, 4h ≈ 7 days,
# 1d ≈ 1 month.
HORIZON = {"5m": 48, "15m": 48, "1h": 48, "4h": 42, "1d": 30, "1w": 12}
CONE = "#42a5f5"


def _forecast_levels(o: pl.DataFrame, history: pl.DataFrame, fc) -> list[dict]:
    """Notable price levels near the current price, with touch probability within H bars."""
    close = fc.close
    cands: list[tuple[str, float, str]] = []
    lv = liquidity.liquidity_levels(o).filter(pl.col("invalidated_at").is_null())
    above = lv.filter((pl.col("kind") == "liquidity_bsl") & (pl.col("price_low") > close))
    below = lv.filter((pl.col("kind") == "liquidity_ssl") & (pl.col("price_low") < close))
    for price in above.sort("price_low")["price_low"].head(2).to_list():
        cands.append(("BSL", price, BULL))
    for price in below.sort("price_low", descending=True)["price_low"].head(2).to_list():
        cands.append(("SSL", price, BEAR))
    # Value area of the previous (closed) week from 1h history bars if any, else current bars.
    end = history["open_time"].max()
    week = (end - timedelta(days=end.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    prev = history.filter(
        (pl.col("open_time") >= week - timedelta(days=7)) & (pl.col("open_time") < week)
    )
    if prev.height > 2:
        prof = volume_profile.profile_from_ohlcv(prev, n_bins=48)
        va = volume_profile.value_area(prof)
        cands += [("wPOC", va.poc, POC), ("wVAH", va.vah, GREY), ("wVAL", va.val, GREY)]
    sigma_h = fc.sigma * np.sqrt(fc.horizon)
    out = []
    for label, price, color in cands:
        if price is None or price <= 0:
            continue
        # Drop levels too far away (beyond ~3.5 sigma of the horizon): probability ~0, just noise.
        if abs(np.log(price / close)) > 3.5 * sigma_h:
            continue
        out.append(
            {
                "label": label,
                "price": float(price),
                "color": color,
                "probability": fc.touch_probability(float(price)),
            }
        )
    return out


def forecast_json(o: pl.DataFrame, history: pl.DataFrame, fc, stats: dict | None) -> dict:
    """Projection payload (cone, touch levels, median line) for a forecast already computed."""
    horizon = fc.horizon
    t0 = history["open_time"][-1]
    step = history["open_time"][-1] - history["open_time"][-2]
    times = [ts(t0 + step * k) for k in range(horizon + 1)]
    bands = {
        f"q{int(q * 100):02d}": [fc.close] + [float(x) for x in fc.quantiles[i]]
        for i, q in enumerate(forecast.QUANTILES)
    }
    median = bands["q50"]
    levels = _forecast_levels(o, history, fc)
    end = {k: v[-1] for k, v in bands.items()}
    return {
        "forecast": {
            "times": times,
            "bands": bands,
            "horizon": horizon,
            "close": fc.close,
            "analogs": fc.analogs,
            "pool": fc.pool,
            "end": end,
            "levels": levels,
        },
        "stats": stats,
        "levels": [
            {
                "t0": times[0],
                "t1": times[-1],
                "price": lv["price"],
                "color": lv["color"],
                "label": f"{lv['label']} {lv['probability'] * 100:.0f}%",
                "dash": True,
            }
            for lv in levels
        ],
        "lines": [
            {
                "name": "median",
                "color": CONE,
                "pane": 0,
                "data": [{"time": t, "value": v} for t, v in zip(times, median, strict=True)],
            }
        ],
        "legend": [
            [
                CONE,
                f"projection for the next {horizon} candles: "
                "bands hold 50% / 80% / 90% of outcomes",
            ],
            [CONE, "solid line = median path (not a direction call)"],
            ["", "dashed levels: probability price touches them within the projection window"],
        ],
    }


def lens_forecast(o: pl.DataFrame, ctx: dict) -> dict:
    """Quantile cone for the next H bars + level-touch probabilities + backtest stats."""
    history: pl.DataFrame = ctx.get("history", o)
    tf = o["timeframe"][0] if "timeframe" in o.columns else ctx.get("tf", "4h")
    horizon = HORIZON.get(tf, 30)
    prepared = forecast.prepare(history)
    fc = forecast.forecast_at(prepared, history.height - 1, horizon)
    if fc is None:
        return {
            "legend": [
                [
                    "",
                    "need more history to project "
                    f"({forecast.WARMUP + forecast.MIN_POOL + horizon}+ candles)",
                ]
            ],
        }
    stats = forecast.walk_forward(history, horizon, prepared=prepared)
    return forecast_json(o, history, fc, stats)


LENSES = {
    "structure": ("SMC structure", lens_structure),
    "liquidity": ("Liquidity", lens_liquidity),
    "profile": ("Volume profile", lens_profile),
    "wyckoff": ("Wyckoff / Elliott", lens_wyckoff),
    "derivatives": ("Derivatives & CVD", lens_derivatives),
    "indicators": ("Indicators", lens_indicators),
    "forecast": ("Projection", lens_forecast),
}


def to_native(obj):
    """Convert numpy types to Python types for JSON."""
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [to_native(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, float) and (obj != obj):  # NaN
        return None
    return obj
