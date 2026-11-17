"""Compact, machine-friendly views of service payloads, plus plain-text renderings.

The web payloads carry thousands of candles and chart styling; the CLI (`--json`) and the MCP server
want the conclusions: verdicts, levels, events, statistics. Every compact view has the same
envelope: `schema_version`, `kind`, `as_of`, `disclaimer`, then the content. Times are ISO-8601 UTC
strings and floats are rounded to 6 significant digits.

The `text_*` functions turn a compact view into a few readable lines (CLI output, MCP text block).
"""

import math
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = 1
DISCLAIMER = "rinng output is analysis only, not investment advice. It never places orders."
_TIME_KEYS = {"time", "t0", "t1", "start", "end_time", "updated"}


# --------------------------------------------------------------------------- helpers


def iso(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    if seconds > 10**11:  # milliseconds
        seconds = seconds / 1000
    return datetime.fromtimestamp(seconds, UTC).isoformat().replace("+00:00", "Z")


def _round(x: float, digits: int = 6) -> float:
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, digits - 1 - int(math.floor(math.log10(abs(x)))))


def clean(obj: Any, key: str | None = None) -> Any:
    """Round floats, turn epoch times under known keys into ISO strings."""
    if isinstance(obj, dict):
        return {k: clean(v, k) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [clean(v) for v in obj]
    if key in _TIME_KEYS and isinstance(obj, int | float) and not isinstance(obj, bool):
        return iso(obj)
    if isinstance(obj, float):
        return _round(obj)
    return obj


def envelope(kind: str, body: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "as_of": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **clean(body),
        "disclaimer": DISCLAIMER,
    }


TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}


def freshness(last_open: float | int | None, tf: str) -> dict:
    """Age of the newest closed candle. A closed bar opened 1–2 bars ago; older means the stored
    data is not being updated and the answer describes the past."""
    if last_open is None or tf not in TF_MINUTES:
        return {}
    seconds = last_open / 1000 if last_open > 10**11 else last_open
    age = int((datetime.now(UTC).timestamp() - seconds) // 60)
    out: dict = {"data_age_minutes": age}
    if age > 3 * TF_MINUTES[tf]:
        out["warning"] = (
            f"newest {tf} candle opened {age} minutes ago: stored data is stale. Run "
            "`rinng live` or `rinng collect` + `rinng curate` to refresh it."
        )
    return out


def _pick(d: dict, *keys: str) -> dict:
    return {k: d[k] for k in keys if k in d}


def _last_candle(payload: dict) -> dict | None:
    candles = payload.get("candles") or []
    if not candles:
        return None
    c = candles[-1]
    return _pick(c, "time", "open", "high", "low", "close", "volume")


def _candles_columns(candles: list[dict], n: int) -> dict:
    rows = candles[-n:]
    cols = ("time", "open", "high", "low", "close", "volume")
    out = {c: [r.get(c) for r in rows] for c in cols}
    out["time"] = [iso(t) for t in out["time"]]
    return out


def _forecast(fc: dict | None) -> dict | None:
    if not fc:
        return None
    out = _pick(fc, "horizon", "close", "analogs", "pool")
    out["end_quantiles"] = fc.get("end")
    if times := fc.get("times"):
        out["end_time"] = times[-1]
    out["levels"] = [_pick(lv, "label", "price", "probability") for lv in fc.get("levels", [])]
    return out


# --------------------------------------------------------------------------- compact views


def summary_view(s: dict) -> dict:
    price = {k: v for k, v in s["price"].items() if k != "spark"}
    return envelope("summary", {**s, "price": price, **freshness(price.get("time"), "1h")})


def desk_view(d: dict) -> dict:
    last = _last_candle(d)
    close = last["close"] if last else None

    def near(items: list[dict], price_key: str, limit: int) -> list[dict]:
        if close is None:
            return items[-limit:]
        return sorted(items, key=lambda x: abs(x[price_key] - close))[:limit]

    levels = [_pick(lv, "label", "price", "layer") for lv in d.get("levels", []) if lv.get("label")]
    levels = list({(lv["label"], round(lv["price"], 8)): lv for lv in levels}.values())
    zones = [_pick(z, "label", "p0", "p1", "layer") for z in d.get("zones", [])]
    return envelope(
        "desk",
        {
            "source": d.get("source"),
            "timeframe": d.get("tf"),
            "last_candle": last,
            **freshness(last and last["time"], d.get("tf") or ""),
            "atr": d.get("atr"),
            "verdict": d.get("verdict"),
            "agents": d.get("agents", []),
            "scenarios": d.get("scenarios", []),
            "forecast": _forecast(d.get("forecast")),
            "forecast_stats": d.get("stats"),
            "levels_near_price": near(levels, "price", 15),
            "zones_near_price": near(zones, "p0", 10),
        },
    )


LENS_LIMIT = 15


def lens_view(c: dict, lens: str, symbol: str, exchange: str, tf: str, candles: int = 0) -> dict:
    body: dict = {
        "lens": lens,
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": tf,
        "source": c.get("source"),
        "bars": len(c.get("candles") or []),
        "last_candle": _last_candle(c),
        **freshness((_last_candle(c) or {}).get("time"), tf),
    }
    if markers := [m for m in c.get("markers", []) if m.get("text")]:
        body["events"] = [
            {"time": m["time"], "text": m["text"], "side": m.get("position")}
            for m in markers[-LENS_LIMIT:]
        ]
    if levels := c.get("levels"):
        body["levels"] = [_pick(lv, "label", "price", "t0", "t1") for lv in levels[-LENS_LIMIT:]]
    if zones := c.get("zones"):
        body["zones"] = [_pick(z, "label", "p0", "p1", "t0", "t1") for z in zones[-LENS_LIMIT:]]
    if profiles := c.get("profiles"):
        keys = ("t0", "t1", "closed", "shape", "poc", "val", "vah", "buy", "sell")
        body["profiles"] = [_pick(p, *keys) for p in profiles[-4:]]
    series = [*c.get("lines", []), *c.get("histos", [])]
    if series:
        body["series_last"] = [
            {"name": s.get("name"), "time": s["data"][-1]["time"], "value": s["data"][-1]["value"]}
            for s in series
            if s.get("data")
        ]
    if fc := c.get("forecast"):
        body["forecast"] = _forecast(fc)
        body["forecast_stats"] = c.get("stats")
    if legend := c.get("legend"):
        body["legend"] = [x[1] if isinstance(x, list | tuple) and len(x) > 1 else x for x in legend]
    if candles:
        body["candles"] = _candles_columns(c.get("candles") or [], candles)
    return envelope("lens", body)


def news_view(n: dict, limit: int = 20) -> dict:
    keys = ("time", "source", "title", "sentiment", "score", "impact", "coins", "url")
    return envelope(
        "news",
        {
            "updated": n.get("updated"),
            "market": n.get("market"),
            "coin": n.get("coin"),
            # Headlines are third-party text: data to read, never instructions to follow.
            "untrusted_headlines": [_pick(it, *keys) for it in n.get("items", [])[:limit]],
            "coin_headlines": [_pick(it, *keys) for it in n.get("coin_items", [])[:limit]],
        },
    )


def candles_view(c: dict) -> dict:
    rows = c.get("candles") or []
    body = {k: c[k] for k in ("symbol", "exchange", "timeframe", "source")}
    body |= freshness(rows[-1]["time"] if rows else None, c["timeframe"])
    return envelope(
        "candles", {**body, "bars": len(rows), "candles": _candles_columns(rows, len(rows))}
    )


def search_view(items: list[dict]) -> dict:
    keys = ("id", "name", "base", "binance", "okx", "configured")
    return envelope("search", {"instruments": [_pick(i, *keys) for i in items]})


def status_view(s: dict) -> dict:
    return envelope("status", s)


# --------------------------------------------------------------------------- text


def _num(x: Any, digits: int = 2) -> str:
    if x is None:
        return "-"
    if isinstance(x, float):
        if abs(x) >= 1000:
            return f"{x:,.{digits}f}"
        return f"{_round(x, 5):g}"
    return str(x)


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x:+.2f}%"


def _warn(v: dict) -> list[str]:
    return [f"WARNING: {v['warning']}"] if v.get("warning") else []


def text_summary(v: dict) -> str:
    p, d, st = v["price"], v["derivatives"], v["structure"]
    pr, lq, wy, mo = v["profile"], v["liquidity"], v["wyckoff"], v["momentum"]
    fund, oi, ls = d.get("funding") or {}, d.get("oi") or {}, d.get("ls") or {}
    br = st.get("last_break") or {}
    cur = pr.get("current") or {}
    lines = [
        f"{v['symbol']} on {v['exchange']}  close {_num(p.get('close'))}  "
        f"24h {_pct(p.get('chg_24h'))}  7d {_pct(p.get('chg_7d'))}  ({p.get('time')})",
        f"Derivatives: funding {_num(fund.get('rate_pct'))}% "
        f"(7d avg {_num(fund.get('avg_7d_pct'))}%)"
        f"  OI 24h {_pct(oi.get('chg_24h'))}  long/short {_num(ls.get('ratio'))}"
        f" ({_num(ls.get('long_pct'))}% long)",
        f"Structure 4h: trend {st.get('trend')}, last {br.get('kind', '-')} at "
        f"{_num(br.get('price'))}, price in {st.get('zone')} of range "
        f"{_num(st.get('range_low'))}–{_num(st.get('range_high'))}",
        f"Weekly profile: {cur.get('shape', '-')} POC {_num(cur.get('poc'))} "
        f"VA {_num(cur.get('val'))}–{_num(cur.get('vah'))}; price {pr.get('price_vs_prev_va')} "
        "previous value area",
        f"Liquidity: BSL {_num(lq.get('bsl'))} ({_pct(lq.get('bsl_dist_pct'))}), "
        f"SSL {_num(lq.get('ssl'))} ({_pct(lq.get('ssl_dist_pct'))})",
        f"Wyckoff: last {(wy.get('last_event') or {}).get('kind', '-')}; "
        f"momentum RSI {_num(mo.get('rsi'))}, MACD hist {_num(mo.get('macd_hist'))}",
    ]
    return "\n".join(lines + _warn(v))


def text_desk(v: dict) -> str:
    vd = v.get("verdict") or {}
    last = v.get("last_candle") or {}
    lines = [
        f"Desk ({v.get('timeframe')}, {v.get('source')}): close {_num(last.get('close'))} at "
        f"{last.get('time')}",
        f"Verdict: lean {vd.get('lean')} (score {vd.get('score')}; buy {vd.get('buy')}, "
        f"sell {vd.get('sell')}, wait {vd.get('wait')} of {vd.get('total')})",
    ]
    for a in v.get("agents", []):
        reason = (a.get("reasons") or [""])[0]
        lines.append(
            f"  {a['name']:<25} {a['stance']:<4} score {a['score']:+.2f} "
            f"conf {a['confidence']:.2f}  {reason}"
        )
    for sc in v.get("scenarios", []):
        lines.append(
            f"Scenario {sc.get('side')}: entry {_num(sc.get('entry'))} stop {_num(sc.get('stop'))} "
            f"target {_num(sc.get('target'))} ({sc.get('target_label')}), R:R {_num(sc.get('rr'))}"
            f", p(target before stop) {_num(sc.get('p_target'))}"
        )
        if sc.get("trigger"):
            lines.append(f"  {sc['trigger']}")
    fc, stats = v.get("forecast"), v.get("forecast_stats") or {}
    if fc and fc.get("end_quantiles"):
        q = fc["end_quantiles"]
        lines.append(
            f"Projection to {fc.get('end_time')}: median {_num(q.get('q50'))}, "
            f"80% band {_num(q.get('q10'))}–{_num(q.get('q90'))}; past skill "
            f"{_num(stats.get('skill'))}, direction hit {_num(stats.get('direction_hit'))} over "
            f"{stats.get('origins')} tests"
        )
    return "\n".join(lines + _warn(v))


def text_lens(v: dict) -> str:
    last = v.get("last_candle") or {}
    lines = [
        f"{v['lens']} · {v['symbol']} {v['exchange']} {v['timeframe']} ({v['source']}, "
        f"{v['bars']} bars): close {_num(last.get('close'))} at {last.get('time')}"
    ]
    for e in (v.get("events") or [])[-8:]:
        lines.append(f"  event {e['time']}  {e['text']}")
    for lv in (v.get("levels") or [])[-8:]:
        lines.append(f"  level {lv.get('label', ''):<10} {_num(lv.get('price'))}")
    for z in (v.get("zones") or [])[-6:]:
        lines.append(f"  zone  {z.get('label', ''):<10} {_num(z.get('p0'))}–{_num(z.get('p1'))}")
    for p in v.get("profiles") or []:
        lines.append(
            f"  profile {p.get('t0')}: {p.get('shape')} POC {_num(p.get('poc'))} "
            f"VA {_num(p.get('val'))}–{_num(p.get('vah'))}"
        )
    for s in v.get("series_last") or []:
        lines.append(f"  {s['name']}: {_num(s['value'])}")
    if fc := v.get("forecast"):
        q = fc.get("end_quantiles") or {}
        lines.append(
            f"  projection to {fc.get('end_time')}: median {_num(q.get('q50'))}, "
            f"80% band {_num(q.get('q10'))}–{_num(q.get('q90'))}"
        )
    return "\n".join(lines + _warn(v))


def text_news(v: dict) -> str:
    m = v.get("market") or {}
    lines = [
        f"Market 24h news sentiment: {m.get('label')} ({m.get('score')}, {m.get('count')} items)"
    ]
    if c := v.get("coin"):
        lines.append(
            f"{c.get('base')}: {c.get('label')} ({c.get('score')}, {c.get('count')} items)"
        )
    items = v.get("coin_headlines") if v.get("coin") else v.get("untrusted_headlines")
    for it in items or []:
        lines.append(f"  {it['time']}  [{it['sentiment']:<7}] {it['source']}: {it['title']}")
    return "\n".join(lines)


def text_candles(v: dict) -> str:
    c = v["candles"]
    head = f"{v['symbol']} {v['exchange']} {v['timeframe']} ({v['source']}, {v['bars']} bars)"
    rows = [
        f"  {t}  O {_num(o)}  H {_num(h)}  L {_num(lo)}  C {_num(cl)}  V {_num(vol)}"
        for t, o, h, lo, cl, vol in zip(
            c["time"], c["open"], c["high"], c["low"], c["close"], c["volume"], strict=True
        )
    ]
    return "\n".join([head, *rows[-20:], *_warn(v)])


def text_search(v: dict) -> str:
    rows = v.get("instruments") or []
    if not rows:
        return "No match."
    return "\n".join(
        f"{i['id']:<22} {i.get('name') or '':<16} binance={'yes' if i.get('binance') else 'no':<3} "
        f"okx={'yes' if i.get('okx') else 'no':<3}{'  (in config)' if i.get('configured') else ''}"
        for i in rows
    )


def text_status(v: dict) -> str:
    lines = [f"data_dir: {v['data_dir']}  stored: {v['stored']}  live: {v['live']}"]
    for inst in v.get("instruments", []):
        parts = []
        for ex in ("binance", "okx"):
            if ex in inst:
                age = inst[ex]["age_minutes"]
                parts.append(f"{ex} " + ("none" if age is None else f"{age} min old"))
        lines.append(f"  {inst['id']:<18} " + ", ".join(parts))
    return "\n".join(lines)
