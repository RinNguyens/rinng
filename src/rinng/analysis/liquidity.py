"""Thanh khoản dạng Events (docs/03-pine-script-va-smc.md mục B6).

Ký hiệu như `smc`: swing từ `structure.swings(length=L)`, swing ở nến s được biết lúc đóng nến
s+L (known_index = s+L); `close_time(i)` = open_time[i] + độ dài nến. Mọi quét/so sánh chỉ xét
nến SAU known_index của mức giá, nên mức chỉ được dùng khi đã biết.

Vùng thanh khoản (`liquidity_levels`, `swing_length`=5):
- Mỗi swing high là một mức buy-side liquidity (kind liquidity_bsl) — vùng trên đỉnh cũ, nơi
  đặt buy stop; mỗi swing low là sell-side (liquidity_ssl). price_low = price_high = mức.
- event_time = nến swing, known_at = known_at của swing.
- invalidated_at = close_time của nến đầu tiên sau known_index có high > mức (BSL) hoặc
  low < mức (SSL), tức thanh khoản đã bị lấy bằng wick.

Equal highs / lows (`equal_levels`, `tolerance_atr`=0.1, `atr_length`=14, `max_lookback`=100):
- Khi swing high k được biết, gom các swing high p trước đó (cùng loại) thỏa:
  index_k - index_p <= max_lookback; |giá_p - giá_k| <= tolerance_atr × ATR[known_index_k];
  và không nến nào nằm giữa p và k có high > max(giá_p, giá_k) (mức chưa bị lấy). Cần ít nhất
  một p, tức cụm >= 2 swing. Equal lows đối xứng với low.
- kind eqh/eql, event_time = nến swing k, known_at = known_at của swing k, vùng =
  [min, max] giá các swing trong cụm.
- invalidated_at = close_time của nến đầu tiên sau known_index_k có high > đỉnh vùng (eqh)
  hoặc low < đáy vùng (eql).

Liquidity sweep (`sweeps`, `max_bars`=1):
- Với mỗi mức swing (BSL/SSL), nến i đầu tiên sau known_index có wick xuyên mức (high > mức
  với BSL, low < mức với SSL) là nến xuyên. Nếu trong max_bars nến tính từ i (i .. i+max_bars-1)
  có nến r đóng lại bên trong (close <= mức với BSL, close >= mức với SSL) thì là sweep; ngược
  lại là breakout, không sinh sự kiện. Mỗi mức chỉ xét lần xuyên đầu tiên.
- kind sweep_bsl/sweep_ssl, event_time = nến xuyên i, known_at = close_time(r). Vùng từ mức
  tới cực trị của các nến i..r. Sweep cụm equal highs/lows được bao hàm qua swing cao/thấp nhất
  trong cụm.
"""

from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.indicators import atr
from rinng.analysis.smc import _Bars, known_swings
from rinng.analysis.types import params_hash

MODULE = "liquidity"

_SIDE = {"swing_high": ("bsl", 1), "swing_low": ("ssl", -1)}


def _taken(bars: _Bars, start: int, level: float, side: int) -> int | None:
    """Nến đầu tiên >= start có wick vượt mức (side=1 phía trên, -1 phía dưới)."""
    for i in range(start, bars.n):
        if (side == 1 and bars.h[i] > level) or (side == -1 and bars.l[i] < level):
            return i
    return None


def liquidity_levels(ohlcv: pl.DataFrame, swing_length: int = 5) -> pl.DataFrame:
    """Events liquidity_bsl / liquidity_ssl. attrs: {"swing_index"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "levels", "swing_length": swing_length})
    rows = []
    for kind, idx, price, known in known_swings(ohlcv, swing_length):
        name, side = _SIDE[kind]
        hit = _taken(bars, known + 1, price, side)
        rows.append(
            {
                "kind": f"liquidity_{name}",
                "event_time": bars.times[idx],
                "known_at": bars.close_time(known),
                "price_low": price,
                "price_high": price,
                "invalidated_at": bars.close_time(hit) if hit is not None else None,
                "attrs": {"swing_index": idx},
            }
        )
    return bars.frame(rows, phash)


def equal_levels(
    ohlcv: pl.DataFrame,
    swing_length: int = 5,
    tolerance_atr: float = 0.1,
    atr_length: int = 14,
    max_lookback: int = 100,
) -> pl.DataFrame:
    """Events eqh / eql. attrs: {"count", "swing_indices", "tolerance"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE,
        {
            "fn": "equal",
            "swing_length": swing_length,
            "tolerance_atr": tolerance_atr,
            "atr_length": atr_length,
            "max_lookback": max_lookback,
        },
    )
    a = atr(ohlcv, atr_length)
    rows: list[dict[str, Any]] = []
    seen: dict[str, list[tuple[int, float]]] = {"swing_high": [], "swing_low": []}
    for kind, idx, price, known in known_swings(ohlcv, swing_length):
        _, side = _SIDE[kind]
        prior = seen[kind]
        tol = tolerance_atr * a[known]
        members = [(idx, price)]
        if not np.isnan(tol):
            for p_idx, p_price in prior:
                if idx - p_idx > max_lookback or abs(p_price - price) > tol:
                    continue
                between = slice(p_idx + 1, idx)
                if side == 1:
                    ok = bars.h[between].size == 0 or bars.h[between].max() <= max(p_price, price)
                else:
                    ok = bars.l[between].size == 0 or bars.l[between].min() >= min(p_price, price)
                if ok:
                    members.append((p_idx, p_price))
        prior.append((idx, price))
        if len(members) < 2:
            continue
        members.sort()
        low = min(m[1] for m in members)
        high = max(m[1] for m in members)
        hit = _taken(bars, known + 1, high if side == 1 else low, side)
        rows.append(
            {
                "kind": "eqh" if side == 1 else "eql",
                "event_time": bars.times[idx],
                "known_at": bars.close_time(known),
                "price_low": low,
                "price_high": high,
                "invalidated_at": bars.close_time(hit) if hit is not None else None,
                "attrs": {
                    "count": len(members),
                    "swing_indices": [m[0] for m in members],
                    "tolerance": float(tol),
                },
            }
        )
    return bars.frame(rows, phash)


def sweeps(ohlcv: pl.DataFrame, swing_length: int = 5, max_bars: int = 1) -> pl.DataFrame:
    """Events sweep_bsl / sweep_ssl.

    attrs: {"level", "level_index", "level_time", "bars", "penetration"}.
    """
    if max_bars < 1:
        raise ValueError("max_bars phải >= 1")
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE, {"fn": "sweeps", "swing_length": swing_length, "max_bars": max_bars}
    )
    rows = []
    for kind, idx, level, known in known_swings(ohlcv, swing_length):
        name, side = _SIDE[kind]
        i = _taken(bars, known + 1, level, side)
        if i is None:
            continue
        back = None
        for r in range(i, min(i + max_bars, bars.n)):
            if (side == 1 and bars.c[r] <= level) or (side == -1 and bars.c[r] >= level):
                back = r
                break
        if back is None:
            continue  # breakout: đóng ngoài mức suốt max_bars nến
        if side == 1:
            extreme = float(bars.h[i : back + 1].max())
            low, high, pen = level, extreme, extreme - level
        else:
            extreme = float(bars.l[i : back + 1].min())
            low, high, pen = extreme, level, level - extreme
        rows.append(
            {
                "kind": f"sweep_{name}",
                "id": idx,
                "event_time": bars.times[i],
                "known_at": bars.close_time(back),
                "price_low": low,
                "price_high": high,
                "attrs": {
                    "level": level,
                    "level_index": idx,
                    "level_time": bars.times[idx],
                    "bars": back - i + 1,
                    "penetration": pen,
                },
            }
        )
    return bars.frame(rows, phash)
