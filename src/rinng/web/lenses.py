"""Biến kết quả phân tích thành JSON cho chart web. Mỗi "lens" là một cách nhìn riêng.

Quy ước JSON chung (thời gian là giây UTC, đúng định dạng Lightweight Charts):
- markers: [{time, position: aboveBar|belowBar, shape, color, text}]
- zones:   [{t0, t1 (null = kéo tới phải), p0, p1, color, label, style}]
- levels:  [{t0, t1, price, color, label, dash}]
- lines:   [{name, color, pane, data: [{time, value}]}]  (pane 0 = cùng pane với nến)
- histos:  [{name, pane, data: [{time, value, color}]}]
- profiles:[{t0, t1, closed, shape, poc, val, vah, buy, sell, rows: [[lo, hi, buy, sell]]}]
- legend:  [[màu, mô tả]] để người xem biết mình đang nhìn gì.

Lens chỉ đọc nến đã đóng; mọi định nghĩa nằm trong rinng.analysis.
"""

import json
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from rinng.analysis import (
    derivatives,
    elliott,
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
    """Sự kiện còn hiệu lực ưu tiên trước, rồi tới sự kiện gần nhất.

    `near`: giá hiện tại; vùng còn hiệu lực nằm xa hơn `band` (tỉ lệ) bị bỏ để chart đỡ rối.
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
            [BULL, "HH/HL, BOS/CHoCH tăng, OB/FVG tăng"],
            [BEAR, "LH/LL, BOS/CHoCH giảm, OB/FVG giảm"],
            ["", "nét đứt = CHoCH (đổi xu hướng); vùng mờ = premium/discount"],
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
            [BULL, "BSL: thanh khoản phía trên (đỉnh cũ)"],
            [BEAR, "SSL: thanh khoản phía dưới (đáy cũ)"],
            [PURPLE, "EQH/EQL: đỉnh/đáy bằng nhau"],
            ["", "đường dừng = đã bị lấy; mũi tên = sweep (lấy rồi đóng lại bên trong)"],
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
            [BULL, "volume taker mua"],
            [BEAR, "volume taker bán"],
            [POC, "POC; đường chấm = naked POC chưa bị chạm"],
            ["", "nhãn D/P/b/DD = hình dạng profile; số dưới = delta (mua − bán)"],
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
            [PURPLE, "zigzag; số 1–5 = ứng viên sóng xung lực Elliott (có thể nhiều cách đếm)"],
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
        legend.append([BLUE, f"pane {pane}: open interest (BTC)"])
        pane += 1
    if ctx.get("ls") is not None and not ctx["ls"].is_empty():
        f = derivatives.long_short_features(o, ctx["ls"])
        lines.append({"name": "L/S", "color": POC, "pane": pane, "data": _series(f, "ls_ratio")})
        legend.append([POC, f"pane {pane}: tỷ lệ tài khoản long/short"])
        pane += 1
    d = orderflow.delta_features(o, cvd_reset=None)
    lines.append({"name": "CVD", "color": PURPLE, "pane": pane, "data": _series(d, "cvd")})
    legend.append([PURPLE, f"pane {pane}: CVD từ taker buy volume"])
    if len(legend) == 1:
        legend.insert(0, ["", "chưa có dữ liệu funding/OI/long-short cho khoảng này"])
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
            ["", "pane 2: MACD histogram; pane 3: delta mỗi nến"],
        ],
    }


LENSES = {
    "structure": ("Cấu trúc SMC", lens_structure),
    "liquidity": ("Thanh khoản", lens_liquidity),
    "profile": ("Volume profile", lens_profile),
    "wyckoff": ("Wyckoff / Elliott", lens_wyckoff),
    "derivatives": ("Phái sinh & CVD", lens_derivatives),
    "indicators": ("Indicator", lens_indicators),
}


def to_native(obj):
    """Đổi kiểu numpy sang kiểu Python để trả JSON."""
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [to_native(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, float) and (obj != obj):  # NaN
        return None
    return obj
