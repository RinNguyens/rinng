"""Summary figures for the dashboard page: each item is a number or a short reading, taken
from the same analysis functions the charts use, so the dashboard and charts never disagree.

Describes market state only; not a trading signal or recommendation.
"""

from datetime import timedelta

import polars as pl

from rinng.analysis import indicators, liquidity, smc, volume_profile, wyckoff
from rinng.web.lenses import ts


def _pct(now: float, before: float | None) -> float | None:
    return None if not before else (now / before - 1) * 100


def _at_or_before(frame: pl.DataFrame, col: str, value: str, when) -> float | None:
    f = frame.filter(pl.col(col) <= when)
    return None if f.is_empty() else float(f[value][-1])


def price_block(h1: pl.DataFrame) -> dict:
    last = h1.tail(1).to_dicts()[0]
    end = last["open_time"]
    close = float(last["close"])
    day = h1.filter(pl.col("open_time") > end - timedelta(hours=24))
    week = h1.filter(pl.col("open_time") > end - timedelta(days=7))
    return {
        "close": close,
        "time": ts(end),
        "chg_24h": _pct(close, _at_or_before(h1, "open_time", "close", end - timedelta(hours=24))),
        "chg_7d": _pct(close, _at_or_before(h1, "open_time", "close", end - timedelta(days=7))),
        "high_24h": float(day["high"].max()),
        "low_24h": float(day["low"].min()),
        "spark": [float(v) for v in week["close"].to_list()],
        "delta_24h": float((2 * day["taker_buy_volume"] - day["volume"]).sum()),
        "volume_24h": float(day["volume"].sum()),
    }


def derivatives_block(funding: pl.DataFrame, oi: pl.DataFrame, ls: pl.DataFrame) -> dict:
    out: dict = {"funding": None, "oi": None, "ls": None}
    if not funding.is_empty():
        f = funding.sort("funding_time")
        rate = float(f["rate"][-1])
        out["funding"] = {
            "rate_pct": rate * 100,
            # 3 funding periods per day (8h) on Binance/OKX for BTC/ETH perps.
            "annual_pct": rate * 3 * 365 * 100,
            "avg_7d_pct": float(f.tail(21)["rate"].mean()) * 100,
            "time": ts(f["funding_time"][-1]),
        }
    if not oi.is_empty():
        f = oi.sort("time")
        end, now = f["time"][-1], float(f["oi_base"][-1])
        out["oi"] = {
            "base": now,
            "value": float(f["oi_value"][-1]) if f["oi_value"][-1] is not None else None,
            "chg_24h": _pct(now, _at_or_before(f, "time", "oi_base", end - timedelta(hours=24))),
            "chg_7d": _pct(now, _at_or_before(f, "time", "oi_base", end - timedelta(days=7))),
            "time": ts(end),
        }
    if not ls.is_empty():
        f = ls.sort("time")
        ratio = float(f["ratio"][-1])
        # OKX gives the ratio only: long share = ratio / (1 + ratio).
        long_pct = f["long_pct"][-1]
        out["ls"] = {
            "ratio": ratio,
            "long_pct": (float(long_pct) if long_pct is not None else ratio / (1 + ratio)) * 100,
            "time": ts(f["time"][-1]),
        }
    return out


def structure_block(h4: pl.DataFrame) -> dict:
    ev = smc.events(h4)
    breaks = ev.filter(pl.col("kind").str.contains("bos|choch")).sort("event_time")
    last = breaks.tail(1).to_dicts()
    trend, last_break = None, None
    if last:
        e = last[0]
        trend = "up" if e["kind"].endswith("bull") else "down"
        last_break = {
            "kind": "CHoCH" if e["kind"].startswith("choch") else "BOS",
            "price": e["price_low"],
            "time": ts(e["event_time"]),
        }
    pd_ = smc.premium_discount(h4).tail(1).to_dicts()[0]
    close = float(h4["close"][-1])
    zone = None
    if pd_.get("pd_equilibrium") is not None:
        zone = "premium" if close > pd_["pd_equilibrium"] else "discount"
    open_ = pl.col("invalidated_at").is_null()
    ob = ev.filter(pl.col("kind").is_in(["ob_bull", "ob_bear"]) & open_)
    return {
        "trend": trend,
        "last_break": last_break,
        "zone": zone,
        "range_high": pd_.get("pd_range_high"),
        "range_low": pd_.get("pd_range_low"),
        "equilibrium": pd_.get("pd_equilibrium"),
        "active_ob": {
            "bull": int((ob["kind"] == "ob_bull").sum()),
            "bear": int((ob["kind"] == "ob_bear").sum()),
        },
    }


def _week_profile(base: pl.DataFrame, start) -> dict | None:
    part = base.filter(
        (pl.col("open_time") >= start) & (pl.col("open_time") < start + timedelta(days=7))
    )
    if part.height <= 2:
        return None
    prof = volume_profile.profile_from_ohlcv(part, n_bins=48)
    va = volume_profile.value_area(prof)
    # OKX candles carry no taker volume: the profile has no buy/sell split, delta is 0.
    split = "buy_volume" in prof.columns
    buy = float(prof["buy_volume"].sum()) if split else 0.0
    sell = float(prof["sell_volume"].sum()) if split else 0.0
    return {
        "start": ts(start),
        "shape": volume_profile.classify_shape(prof),
        "poc": va.poc,
        "vah": va.vah,
        "val": va.val,
        "delta": buy - sell,
    }


def profile_block(base: pl.DataFrame) -> dict:
    end = base["open_time"].max()
    week = (end - timedelta(days=end.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    now = _week_profile(base, week)
    prev = _week_profile(base, week - timedelta(days=7))
    close = float(base["close"][-1])
    where = None
    ref = prev or now
    if ref:
        where = "above" if close > ref["vah"] else "below" if close < ref["val"] else "inside"
    return {"current": now, "previous": prev, "price_vs_prev_va": where}


def liquidity_block(h1: pl.DataFrame) -> dict:
    close = float(h1["close"][-1])
    lv = liquidity.liquidity_levels(h1).filter(pl.col("invalidated_at").is_null())
    above = lv.filter((pl.col("kind") == "liquidity_bsl") & (pl.col("price_low") > close))
    below = lv.filter((pl.col("kind") == "liquidity_ssl") & (pl.col("price_low") < close))
    bsl = float(above["price_low"].min()) if not above.is_empty() else None
    ssl = float(below["price_low"].max()) if not below.is_empty() else None
    sw = liquidity.sweeps(h1).sort("event_time").tail(1).to_dicts()
    return {
        "bsl": bsl,
        "bsl_dist_pct": _pct(bsl, close) if bsl else None,
        "ssl": ssl,
        "ssl_dist_pct": _pct(ssl, close) if ssl else None,
        "last_sweep": (
            {
                "kind": "BSL" if sw[0]["kind"] == "sweep_bsl" else "SSL",
                "time": ts(sw[0]["event_time"]),
            }
            if sw
            else None
        ),
    }


def wyckoff_block(d1: pl.DataFrame) -> dict:
    names = {
        "selling_climax": "SC",
        "buying_climax": "BC",
        "spring": "Spring",
        "upthrust": "UT",
        "trading_range": "Trading range",
    }
    ev = pl.concat([wyckoff.climaxes(d1), wyckoff.trading_ranges(d1)], how="diagonal_relaxed").sort(
        "event_time"
    )
    last = ev.tail(1).to_dicts()
    tr = ev.filter((pl.col("kind") == "trading_range") & pl.col("invalidated_at").is_null())
    rng = tr.tail(1).to_dicts()
    return {
        "last_event": (
            {"kind": names.get(last[0]["kind"], last[0]["kind"]), "time": ts(last[0]["event_time"])}
            if last
            else None
        ),
        "in_range": (
            {
                "high": rng[0]["price_high"],
                "low": rng[0]["price_low"],
                "since": ts(rng[0]["event_time"]),
            }
            if rng
            else None
        ),
    }


def momentum_block(h4: pl.DataFrame) -> dict:
    f = indicators.compute(h4).tail(1).to_dicts()[0]
    close = float(h4["close"][-1])
    emas = {k: f.get(f"ema_{k}") for k in (21, 50, 200)}
    above = [k for k, v in emas.items() if v is not None and close > v]
    return {
        "rsi": f.get("rsi"),
        "macd_hist": f.get("macd_hist"),
        "above_ema": above,
        "ema": emas,
    }
