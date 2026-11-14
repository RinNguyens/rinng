"""Smart Money Concepts dạng Events/Features (docs/03-pine-script-va-smc.md phần B).

SMC không có định nghĩa chuẩn; module này chọn các định nghĩa dưới đây. Ký hiệu: nến i,
`close_time(i)` = open_time[i] + độ dài nến. Swing lấy từ `structure.swings(length=L)`, swing ở
nến s được biết lúc đóng nến s+L.

Quy tắc dùng swing: khi xét nến i để ra quyết định (phá cấu trúc), chỉ dùng swing có
known_at <= open_time[i], tức đã biết trước khi nến i mở. Features premium/discount ở dòng i
(known_at = close_time(i)) dùng swing có known_at <= close_time(i).

BOS / CHoCH (`structure_breaks`, tham số `swing_length`, `break_on` = "close" | "wick"):
- Mức trên = swing high đã biết gần nhất chưa bị phá; mức dưới tương tự với swing low. Swing
  mới được biết thay thế mức cũ cùng loại.
- Phá lên ở nến i: close[i] > mức trên (`break_on="close"`) hoặc high[i] > mức trên ("wick").
  Phá xuống đối xứng. Mỗi mức chỉ bị phá một lần.
- Nhãn theo xu hướng trước nến i: ngược chiều → CHoCH, cùng chiều hoặc chưa có xu hướng → BOS.
  Sau đó xu hướng = chiều phá. Nếu một nến phá cả hai mức (chỉ xảy ra với "wick"), ghi cả hai
  sự kiện, đều gán nhãn theo xu hướng trước nến; xu hướng sau = chiều thân nến (close >= open
  là tăng).
- kind: bos_bull, bos_bear, choch_bull, choch_bear. event_time = nến phá, known_at =
  close_time(nến phá), price_low = price_high = mức bị phá.

Displacement (`displacement`, `k`=1.5, `atr_length`=14):
- Nến i là displacement nếu |close - open| > k × ATR[i-1] (ATR của nến trước, để thân nến
  không tự làm tăng ngưỡng). Chiều theo thân. kind displacement_bull/bear, known_at =
  close_time(i), vùng = thân nến.

FVG (`fair_value_gaps`, `min_size_atr`=0, `atr_length`=14), mẫu 3 nến t-2, t-1, t:
- Bull: low[t] > high[t-2], vùng [high[t-2], low[t]]. Bear: high[t] < low[t-2], vùng
  [high[t], low[t-2]]. Kích thước vùng phải >= min_size_atr × ATR[t].
- event_time = nến giữa t-1, known_at = close_time(t).
- LẤP HOÀN TOÀN: nến j > t đầu tiên có low[j] <= đáy vùng (bull) hoặc high[j] >= đỉnh vùng
  (bear), tức wick đi xuyên hết vùng. invalidated_at = close_time(j).

Order block (`order_blocks`):
- Với mỗi BOS/CHoCH phá lên ở nến b: nến giảm (close < open) cuối cùng j trong
  [b - max_lookback, b-1]. Nếu `require_displacement`, phải có ít nhất một displacement tăng
  trong (j, b]; không có thì không sinh OB. Phá xuống đối xứng (nến tăng cuối cùng). Mỗi nến
  chỉ làm OB một lần mỗi chiều.
- Vùng = toàn bộ nến j [low, high]. kind ob_bull/ob_bear, event_time = nến j, known_at =
  close_time(b) (OB chỉ có ý nghĩa sau khi cấu trúc bị phá).
- Theo dõi từ nến b+1. Mitigation (chạm): nến đầu tiên có low <= đỉnh vùng (bull) hoặc
  high >= đáy vùng (bear), tính cả nến làm vô hiệu; ghi thành sự kiện riêng
  ob_bull_mitigated/ob_bear_mitigated tại nến đó (không ghi vào attrs của OB vì attrs không
  được chứa thông tin tương lai).
- Vô hiệu: close (hoặc wick nếu `invalidate_on="wick"`) xuyên qua mép bên kia: bull khi
  < đáy vùng, bear khi > đỉnh vùng. invalidated_at = close_time(nến đó).
- Breaker = OB bị vô hiệu, đổi vai trò: ob_bull bị phá sinh breaker_bear (và ngược lại) tại
  nến vô hiệu, cùng vùng. Breaker bị vô hiệu khi giá đóng (hoặc wick) xuyên ngược lại qua mép
  còn lại: breaker_bear khi > đỉnh vùng, breaker_bull khi < đáy vùng.

Premium / discount (`premium_discount`, Features): dải [L, H] = swing low và swing high đã
biết gần nhất. pd_position = (close - L) / (H - L), cắt vào [0, 1]; equilibrium = (H + L) / 2
(vị trí 0.5). pd_zone = "equilibrium" khi |pd_position - 0.5| <= `equilibrium_band` (mặc định 0,
cộng dung sai số thực 1e-9), còn lại "premium" (> 0.5) hoặc "discount" (< 0.5). Null khi
chưa có đủ hai swing hoặc H <= L. Không nới dải theo cực trị mới (khác LuxAlgo "trailing").
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import numpy as np
import polars as pl

from rinng.analysis.indicators import atr
from rinng.analysis.structure import swing_table, swings
from rinng.analysis.types import (
    bar_duration,
    check_ohlcv,
    empty_events,
    events_frame,
    features_frame,
    params_hash,
)

MODULE = "smc"
BREAK_SOURCES = ("close", "wick")


def known_swings(ohlcv: pl.DataFrame, length: int) -> list[tuple[str, int, float, int]]:
    """Danh sách (kind, index, price, known_index) sắp theo known_index rồi index.

    known_index = index + length: swing được biết lúc đóng nến known_index.
    """
    table = swing_table(swings(ohlcv, length))
    out = [
        (kind, int(idx), float(price), int(idx) + length)
        for kind, idx, price in zip(table["kind"], table["index"], table["price"], strict=True)
    ]
    return sorted(out, key=lambda r: (r[3], r[1]))


class _Bars:
    """Mảng numpy và thời gian của frame nến."""

    def __init__(self, ohlcv: pl.DataFrame):
        self.symbol, self.timeframe = check_ohlcv(ohlcv)
        self.n = ohlcv.height
        self.times: list[datetime] = ohlcv["open_time"].to_list()
        self.duration = bar_duration(self.timeframe)
        self.o, self.h, self.l, self.c = (
            ohlcv[col].cast(pl.Float64).to_numpy() for col in ("open", "high", "low", "close")
        )

    def close_time(self, i: int) -> datetime:
        return self.times[i] + self.duration

    def frame(self, rows: list[dict[str, Any]], phash: str) -> pl.DataFrame:
        return events_frame(rows, symbol=self.symbol, timeframe=self.timeframe, phash=phash)


def _check_source(name: str, value: str) -> None:
    if value not in BREAK_SOURCES:
        raise ValueError(f"{name} phải là một trong {BREAK_SOURCES}")


def _breaks(bars: _Bars, ohlcv: pl.DataFrame, swing_length: int, break_on: str) -> list[dict]:
    """Phá cấu trúc dạng dict nội bộ: i, side, kind, level, swing_index."""
    _check_source("break_on", break_on)
    up_src = bars.c if break_on == "close" else bars.h
    dn_src = bars.c if break_on == "close" else bars.l
    pending = known_swings(ohlcv, swing_length)
    ptr = 0
    hi: tuple[float, int] | None = None
    lo: tuple[float, int] | None = None
    trend = 0
    out = []
    for i in range(bars.n):
        # Chỉ nạp swing đã biết trước khi nến i mở (known_index < i).
        while ptr < len(pending) and pending[ptr][3] < i:
            kind, idx, price, _ = pending[ptr]
            if kind == "swing_high":
                hi = (price, idx)
            else:
                lo = (price, idx)
            ptr += 1
        before = trend
        hits = []
        if hi is not None and up_src[i] > hi[0]:
            hits.append((1, hi))
            hi = None
        if lo is not None and dn_src[i] < lo[0]:
            hits.append((-1, lo))
            lo = None
        for side, (level, idx) in hits:
            label = "choch" if before == -side else "bos"
            direction = "bull" if side == 1 else "bear"
            out.append(
                {"i": i, "side": side, "kind": f"{label}_{direction}", "level": level, "swing": idx}
            )
        if len(hits) == 1:
            trend = hits[0][0]
        elif len(hits) == 2:
            trend = 1 if bars.c[i] >= bars.o[i] else -1
    return out


def structure_breaks(
    ohlcv: pl.DataFrame, swing_length: int = 5, break_on: str = "close"
) -> pl.DataFrame:
    """Events BOS/CHoCH. attrs: {"swing_index", "swing_time", "break_index"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "breaks", "swing_length": swing_length, "on": break_on})
    rows = [
        {
            "kind": b["kind"],
            "event_time": bars.times[b["i"]],
            "known_at": bars.close_time(b["i"]),
            "price_low": b["level"],
            "price_high": b["level"],
            "attrs": {
                "swing_index": b["swing"],
                "swing_time": bars.times[b["swing"]],
                "break_index": b["i"],
            },
        }
        for b in _breaks(bars, ohlcv, swing_length, break_on)
    ]
    return bars.frame(rows, phash)


def _displacement_flags(bars: _Bars, ohlcv: pl.DataFrame, k: float, atr_length: int):
    """(+1/-1/0 mỗi nến, ATR của nến trước)."""
    a = atr(ohlcv, atr_length)
    prev = np.concatenate([[np.nan], a[:-1]])
    body = bars.c - bars.o
    with np.errstate(invalid="ignore"):
        big = np.abs(body) > k * prev
    flags = np.where(big & ~np.isnan(prev), np.sign(body), 0).astype(np.int64)
    return flags, prev


def displacement(ohlcv: pl.DataFrame, k: float = 1.5, atr_length: int = 14) -> pl.DataFrame:
    """Events displacement_bull/bear. attrs: {"body", "atr", "ratio"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "displacement", "k": k, "atr_length": atr_length})
    flags, prev = _displacement_flags(bars, ohlcv, k, atr_length)
    rows = []
    for i in np.flatnonzero(flags):
        i = int(i)
        body = abs(bars.c[i] - bars.o[i])
        rows.append(
            {
                "kind": "displacement_bull" if flags[i] > 0 else "displacement_bear",
                "event_time": bars.times[i],
                "known_at": bars.close_time(i),
                "price_low": float(min(bars.o[i], bars.c[i])),
                "price_high": float(max(bars.o[i], bars.c[i])),
                "attrs": {"body": body, "atr": float(prev[i]), "ratio": body / float(prev[i])},
            }
        )
    return bars.frame(rows, phash)


def fair_value_gaps(
    ohlcv: pl.DataFrame, min_size_atr: float = 0.0, atr_length: int = 14
) -> pl.DataFrame:
    """Events fvg_bull/fvg_bear, invalidated_at = lúc bị lấp hoàn toàn. attrs: {"size"}."""
    bars = _Bars(ohlcv)
    phash = params_hash(MODULE, {"fn": "fvg", "min_size_atr": min_size_atr, "atr": atr_length})
    a = atr(ohlcv, atr_length) if min_size_atr > 0 else None
    h, lo = bars.h, bars.l
    rows = []
    for t in range(2, bars.n):
        for side in (1, -1):
            if side == 1:
                bottom, top = h[t - 2], lo[t]
            else:
                bottom, top = h[t], lo[t - 2]
            size = top - bottom
            if size <= 0:
                continue
            if a is not None and not (size >= min_size_atr * a[t]):  # ATR NaN → bỏ
                continue
            filled = None
            for j in range(t + 1, bars.n):
                if (side == 1 and lo[j] <= bottom) or (side == -1 and h[j] >= top):
                    filled = bars.close_time(j)
                    break
            rows.append(
                {
                    "kind": "fvg_bull" if side == 1 else "fvg_bear",
                    "event_time": bars.times[t - 1],
                    "known_at": bars.close_time(t),
                    "price_low": float(bottom),
                    "price_high": float(top),
                    "invalidated_at": filled,
                    "attrs": {"size": float(size), "fill": "full"},
                }
            )
    return bars.frame(rows, phash)


def order_blocks(
    ohlcv: pl.DataFrame,
    swing_length: int = 5,
    break_on: str = "close",
    invalidate_on: str = "close",
    require_displacement: bool = True,
    displacement_k: float = 1.5,
    atr_length: int = 14,
    max_lookback: int = 50,
) -> pl.DataFrame:
    """Events ob_*, ob_*_mitigated, breaker_*.

    attrs của ob: {"break_index", "break_kind", "ob_index"}; của mitigated/breaker:
    {"ob_index", "ob_time"}.
    """
    _check_source("invalidate_on", invalidate_on)
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE,
        {
            "fn": "order_blocks",
            "swing_length": swing_length,
            "break_on": break_on,
            "invalidate_on": invalidate_on,
            "require_displacement": require_displacement,
            "displacement_k": displacement_k,
            "atr_length": atr_length,
            "max_lookback": max_lookback,
        },
    )
    flags, _ = _displacement_flags(bars, ohlcv, displacement_k, atr_length)
    o, h, lo, c = bars.o, bars.h, bars.l, bars.c
    low_src = c if invalidate_on == "close" else lo
    high_src = c if invalidate_on == "close" else h
    used: set[tuple[int, int]] = set()
    rows: list[dict[str, Any]] = []
    for brk in _breaks(bars, ohlcv, swing_length, break_on):
        b, side = brk["i"], brk["side"]
        j = None
        for k in range(b - 1, max(-1, b - 1 - max_lookback), -1):
            if (side == 1 and c[k] < o[k]) or (side == -1 and c[k] > o[k]):
                j = k
                break
        if j is None or (side, j) in used:
            continue
        if require_displacement and not np.any(flags[j + 1 : b + 1] == side):
            continue
        used.add((side, j))
        bottom, top = float(lo[j]), float(h[j])
        name = "bull" if side == 1 else "bear"
        opposite = "bear" if side == 1 else "bull"
        mitigated = invalid = None
        for m in range(b + 1, bars.n):
            if mitigated is None and (
                (side == 1 and lo[m] <= top) or (side == -1 and h[m] >= bottom)
            ):
                mitigated = m
            if (side == 1 and low_src[m] < bottom) or (side == -1 and high_src[m] > top):
                invalid = m
                break
        zone = {"price_low": bottom, "price_high": top}
        ref = {"ob_index": j, "ob_time": bars.times[j]}
        rows.append(
            {
                "kind": f"ob_{name}",
                "id": j,
                "event_time": bars.times[j],
                "known_at": bars.close_time(b),
                "invalidated_at": bars.close_time(invalid) if invalid is not None else None,
                "attrs": {"break_index": b, "break_kind": brk["kind"], "ob_index": j},
                **zone,
            }
        )
        if mitigated is not None:
            rows.append(
                {
                    "kind": f"ob_{name}_mitigated",
                    "id": j,
                    "event_time": bars.times[mitigated],
                    "known_at": bars.close_time(mitigated),
                    "attrs": ref,
                    **zone,
                }
            )
        if invalid is not None:
            # Breaker: bull OB bị phá thành kháng cự, vô hiệu khi giá xuyên ngược lên trên đỉnh.
            ended = None
            for w in range(invalid + 1, bars.n):
                if (side == 1 and high_src[w] > top) or (side == -1 and low_src[w] < bottom):
                    ended = bars.close_time(w)
                    break
            rows.append(
                {
                    "kind": f"breaker_{opposite}",
                    "id": j,
                    "event_time": bars.times[invalid],
                    "known_at": bars.close_time(invalid),
                    "invalidated_at": ended,
                    "attrs": ref,
                    **zone,
                }
            )
    return bars.frame(rows, phash)


def premium_discount(
    ohlcv: pl.DataFrame, swing_length: int = 5, equilibrium_band: float = 0.0
) -> pl.DataFrame:
    """Features pd_range_high, pd_range_low, pd_equilibrium, pd_position, pd_zone."""
    bars = _Bars(ohlcv)
    phash = params_hash(
        MODULE,
        {"fn": "premium_discount", "swing_length": swing_length, "band": equilibrium_band},
    )
    hi = np.full(bars.n, np.nan)
    lo = np.full(bars.n, np.nan)
    for kind, _, price, known in known_swings(ohlcv, swing_length):
        # Swing biết lúc đóng nến `known` → dùng được từ dòng `known` trở đi.
        target = hi if kind == "swing_high" else lo
        target[known:] = price
    valid = hi > lo
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = np.where(valid, np.clip((bars.c - lo) / (hi - lo), 0.0, 1.0), np.nan)
    eq = np.where(valid, (hi + lo) / 2, np.nan)
    band = equilibrium_band + 1e-9
    zone = [
        None
        if np.isnan(p)
        else "equilibrium"
        if abs(p - 0.5) <= band
        else "premium"
        if p > 0.5
        else "discount"
        for p in pos
    ]
    return features_frame(
        ohlcv,
        {
            "pd_range_high": pl.Series(np.where(valid, hi, np.nan)).fill_nan(None),
            "pd_range_low": pl.Series(np.where(valid, lo, np.nan)).fill_nan(None),
            "pd_equilibrium": pl.Series(eq).fill_nan(None),
            "pd_position": pl.Series(pos).fill_nan(None),
            "pd_zone": pl.Series(zone, dtype=pl.String()),
        },
        phash,
    )


def events(ohlcv: pl.DataFrame, params: Mapping[str, Any] | None = None) -> pl.DataFrame:
    """Gộp mọi Events SMC. `params` = {"breaks": {...}, "displacement": {...}, "fvg": {...},
    "order_blocks": {...}}, mỗi mục là kwargs cho hàm tương ứng."""
    p = dict(params or {})
    parts = [
        structure_breaks(ohlcv, **p.get("breaks", {})),
        displacement(ohlcv, **p.get("displacement", {})),
        fair_value_gaps(ohlcv, **p.get("fvg", {})),
        order_blocks(ohlcv, **p.get("order_blocks", {})),
    ]
    out = pl.concat([x for x in parts if not x.is_empty()] or [empty_events()])
    return out.sort(["event_time", "kind", "event_id"])
