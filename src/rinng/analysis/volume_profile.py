"""Volume profile: histogram volume theo mức giá, POC, value area, HVN/LVN, naked POC.

Lưới bin giá (chọn đúng một trong hai tham số):
- `bin_size`: kích thước bin tuyệt đối, lưới neo tại 0, bin k = [k*bin_size, (k+1)*bin_size).
  Mọi kỳ dùng chung lưới nên POC giữa các kỳ so sánh được.
- `n_bins`: số bin cố định, chia đều [low nhỏ nhất, high lớn nhất] của dữ liệu đưa vào.
  Mỗi kỳ có lưới riêng.

Hai cách dựng profile:
- `profile_from_ohlcv` (gần đúng): volume mỗi nến rải đều cho các bin mà [low, high] của nến
  chạm tới. Bin chứa low luôn được tính; high nằm đúng trên cạnh bin thì không tràn sang bin
  trên. `taker_buy_volume` (nếu có) được rải cùng cách thành `buy_volume`, phần còn lại là
  `sell_volume`. Profile tính trên đúng nến được đưa vào (1m hay khung lớn hơn); nến càng lớn
  thì càng thô (docs/04 mục 1.3).
- `profile_from_trades` (chính xác): cộng `qty` của từng trade vào bin chứa `price`.
  `is_buyer_maker=True` nghĩa là taker BÁN.
Cả hai trả bảng liền mạch (kể cả bin volume 0) tăng dần theo giá:
`price_low, price_high, volume[, buy_volume, sell_volume]`.

POC (VPOC): bin volume lớn nhất; hòa thì chọn bin gần giữa dải giá nhất, vẫn hòa thì bin thấp
hơn. Giá POC = giữa bin.

Value area (mặc định 70%): bắt đầu từ bin POC, mỗi bước so tổng HAI bin kế tiếp phía trên với
tổng HAI bin kế tiếp phía dưới, nhận cả hai bin của bên lớn hơn (kiểu CBOT cổ điển); bằng nhau
thì chọn phía trên; một phía chỉ còn một bin thì so một bin đó; hết một phía thì lấy phía kia.
Dừng khi volume cộng dồn >= pct * tổng, nên VA có thể vượt 70% đôi chút. VAL = cạnh dưới bin
thấp nhất, VAH = cạnh trên bin cao nhất. Chỗ có thể khác TradingView (mã nguồn đóng, biến thể
**chưa xác minh**): mở rộng từng bin một thay vì hai, cách phá hòa ở POC và ở mỗi bước, cách
rải volume nến (TradingView có thể dùng nến khung nhỏ hơn), và việc VAH/VAL là cạnh bin hay
giữa bin.

HVN/LVN: làm mượt volume bằng kernel Gauss `sigma_bins` (đệm 0 ngoài dải, vì ngoài dải không
có volume), rồi lấy cực đại (HVN) / cực tiểu (LVN) cục bộ ở bin bên trong (không lấy hai bin
biên). Cực trị dạng bậc thang lấy bin đầu tiên. Chỉ giữ cực trị có prominence (định nghĩa như
`scipy.signal.peak_prominences`) >= `min_prominence` * max(volume đã làm mượt).

Profile theo kỳ (`profile_events`): `period` là "day" (ngày UTC), "week" (thứ Hai 00:00 UTC),
"month" (tháng lịch UTC), hoặc danh sách khoảng neo [start, end). Nến thuộc kỳ chứa
`open_time` của nó. Kỳ chỉ được xuất khi đã đóng, tức dữ liệu đã có nến đóng lúc >= end.
- `event_time` = mở kỳ, `known_at` = max(đóng kỳ, lúc đóng nến cuối của kỳ).
- Kind: `vpoc` (price_low/high = cạnh bin POC), `value_area` (VAL, VAH), `hvn`, `lvn`
  (cạnh bin của nút), `naked_poc` (price_low = price_high = giá POC).
- `naked_poc.invalidated_at` = lúc ĐÓNG của nến đầu tiên mở từ `known_at` trở đi thỏa
  low <= POC <= high (đóng chứ không phải mở, vì chỉ khi nến đóng mới biết chắc nó đã chạm;
  điều này giữ `assert_no_lookahead`). Null nghĩa là POC vẫn "naked" đến cuối dữ liệu.
Kỳ đầu có thể thiếu nến (dữ liệu bắt đầu giữa kỳ); `attrs.n_bars` cho biết số nến đã dùng.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration, check_ohlcv, events_frame, params_hash

MODULE = "volume_profile"

PERIODS = {"day": "1d", "week": "1w", "month": "1mo"}

_EPS = 1e-7  # dung sai khi đổi giá ra chỉ số bin (giá nằm đúng cạnh bin)


# ---------------------------------------------------------------- lưới bin và dựng profile


def _grid(
    low_min: float, high_max: float, bin_size: float | None, n_bins: int | None
) -> tuple[float, float, int | None]:
    """Trả (origin, bin_size, n_bins hoặc None nếu lưới tuyệt đối)."""
    if (bin_size is None) == (n_bins is None):
        raise ValueError("cần đúng một trong hai tham số bin_size, n_bins")
    if bin_size is not None:
        if not bin_size > 0:
            raise ValueError("bin_size phải > 0")
        return 0.0, float(bin_size), None
    if n_bins is None or n_bins < 1:
        raise ValueError("n_bins phải >= 1")
    span = high_max - low_min
    if span <= 0:  # mọi giá như nhau: một bin duy nhất
        return low_min, 1.0, 1
    return low_min, span / n_bins, int(n_bins)


def _floor_index(price: np.ndarray, origin: float, size: float) -> np.ndarray:
    return np.floor((price - origin) / size + _EPS).astype(np.int64)


def _profile_frame(
    origin: float, size: float, k0: int, columns: dict[str, np.ndarray]
) -> pl.DataFrame:
    n = len(next(iter(columns.values())))
    idx = np.arange(n, dtype=np.float64) + k0
    return pl.DataFrame(
        {"price_low": origin + idx * size, "price_high": origin + (idx + 1) * size, **columns}
    )


def _has_buy(frame: pl.DataFrame, col: str) -> bool:
    return col in frame.columns and frame[col].null_count() == 0


def profile_from_ohlcv(
    ohlcv: pl.DataFrame, *, bin_size: float | None = None, n_bins: int | None = None
) -> pl.DataFrame:
    """Profile gần đúng từ nến: rải đều volume mỗi nến theo các bin trong [low, high]."""
    if ohlcv.is_empty():
        raise ValueError("frame nến rỗng")
    low = ohlcv["low"].to_numpy().astype(np.float64)
    high = ohlcv["high"].to_numpy().astype(np.float64)
    origin, size, fixed = _grid(float(low.min()), float(high.max()), bin_size, n_bins)
    k_lo = _floor_index(low, origin, size)
    k_hi = np.ceil((high - origin) / size - _EPS).astype(np.int64) - 1
    k_hi = np.maximum(k_hi, k_lo)
    if fixed is not None:
        k_lo = np.clip(k_lo, 0, fixed - 1)
        k_hi = np.clip(k_hi, 0, fixed - 1)
    k0 = 0 if fixed is not None else int(k_lo.min())
    lo, hi = k_lo - k0, k_hi - k0
    nb = fixed if fixed is not None else int(hi.max()) + 1
    count = (hi - lo + 1).astype(np.float64)
    # Mảng hiệu: cộng mật độ tại lo, trừ tại hi+1, rồi cộng dồn. O(số nến + số bin).
    cover = np.cumsum(np.bincount(lo, minlength=nb + 1) - np.bincount(hi + 1, minlength=nb + 1))
    empty = cover[:nb] == 0

    def spread(weights: np.ndarray) -> np.ndarray:
        d = weights / count
        x = np.cumsum(
            np.bincount(lo, weights=d, minlength=nb + 1)
            - np.bincount(hi + 1, weights=d, minlength=nb + 1)
        )[:nb]
        x[empty] = 0.0  # bin không nến nào phủ: đúng 0, không để sai số cộng dồn
        return x

    volume = ohlcv["volume"].to_numpy().astype(np.float64)
    columns = {"volume": spread(volume)}
    if _has_buy(ohlcv, "taker_buy_volume"):
        buy = ohlcv["taker_buy_volume"].to_numpy().astype(np.float64)
        columns["buy_volume"] = spread(buy)
        columns["sell_volume"] = spread(volume - buy)
    return _profile_frame(origin, size, k0, columns)


def profile_from_trades(
    trades: pl.DataFrame, *, bin_size: float | None = None, n_bins: int | None = None
) -> pl.DataFrame:
    """Profile chính xác từ trades: cộng qty vào bin chứa price. Có buy/sell theo taker."""
    if trades.is_empty():
        raise ValueError("frame trades rỗng")
    price = trades["price"].to_numpy().astype(np.float64)
    qty = trades["qty"].to_numpy().astype(np.float64)
    origin, size, fixed = _grid(float(price.min()), float(price.max()), bin_size, n_bins)
    k = _floor_index(price, origin, size)
    if fixed is not None:
        k = np.clip(k, 0, fixed - 1)
    k0 = 0 if fixed is not None else int(k.min())
    k = k - k0
    nb = fixed if fixed is not None else int(k.max()) + 1
    taker_buy = ~trades["is_buyer_maker"].to_numpy().astype(bool)
    buy = np.bincount(k, weights=np.where(taker_buy, qty, 0.0), minlength=nb)
    sell = np.bincount(k, weights=np.where(taker_buy, 0.0, qty), minlength=nb)
    return _profile_frame(
        origin, size, k0, {"volume": buy + sell, "buy_volume": buy, "sell_volume": sell}
    )


# ---------------------------------------------------------------- POC, value area, nút


@dataclass(frozen=True)
class ValueArea:
    poc: float  # giá giữa bin POC
    poc_low: float
    poc_high: float
    poc_volume: float
    val: float
    vah: float
    va_volume: float
    total_volume: float


def poc_index(volume: np.ndarray) -> int:
    """Chỉ số bin POC; hòa thì gần giữa dải nhất, vẫn hòa thì bin thấp hơn."""
    cands = np.flatnonzero(volume == volume.max())
    return int(cands[np.abs(cands - (len(volume) - 1) / 2).argmin()])


def value_area(profile: pl.DataFrame, pct: float = 0.70) -> ValueArea:
    """POC và value area theo biến thể hai bin mỗi bước (xem docstring module)."""
    if not 0 < pct <= 1:
        raise ValueError("pct phải trong (0, 1]")
    v = profile["volume"].to_numpy().astype(np.float64)
    total = float(v.sum())
    if len(v) == 0 or total <= 0:
        raise ValueError("profile rỗng hoặc tổng volume bằng 0")
    n = len(v)
    poc = poc_index(v)
    lo = hi = poc
    acc, target = float(v[poc]), pct * total * (1 - 1e-12)
    while acc < target and (lo > 0 or hi < n - 1):
        up = float(v[hi + 1 : hi + 3].sum()) if hi < n - 1 else -np.inf
        dn = float(v[max(lo - 2, 0) : lo].sum()) if lo > 0 else -np.inf
        if up >= dn:
            hi = min(hi + 2, n - 1)
            acc += up
        else:
            lo = max(lo - 2, 0)
            acc += dn
    p_low = profile["price_low"].to_numpy()
    p_high = profile["price_high"].to_numpy()
    return ValueArea(
        poc=float((p_low[poc] + p_high[poc]) / 2),
        poc_low=float(p_low[poc]),
        poc_high=float(p_high[poc]),
        poc_volume=float(v[poc]),
        val=float(p_low[lo]),
        vah=float(p_high[hi]),
        va_volume=acc,
        total_volume=total,
    )


def _smooth(v: np.ndarray, sigma_bins: float) -> np.ndarray:
    if sigma_bins <= 0:
        return v.copy()
    radius = max(1, int(np.ceil(3 * sigma_bins)))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (x / sigma_bins) ** 2)
    kernel /= kernel.sum()
    padded = np.concatenate([np.zeros(radius), v, np.zeros(radius)])
    return np.convolve(padded, kernel, mode="valid")


def _peaks(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cực đại cục bộ bên trong (trái nghiêm ngặt, phải không) và prominence kiểu scipy."""
    if len(x) < 3:
        return np.empty(0, np.int64), np.empty(0)
    mid = x[1:-1]
    idx = np.flatnonzero((mid > x[:-2]) & (mid >= x[2:])) + 1
    prom = np.empty(len(idx))
    for j, i in enumerate(idx):
        higher_left = np.flatnonzero(x[:i] > x[i])
        start = higher_left[-1] + 1 if len(higher_left) else 0
        higher_right = np.flatnonzero(x[i + 1 :] > x[i])
        stop = i + 1 + higher_right[0] if len(higher_right) else len(x)
        prom[j] = x[i] - max(x[start : i + 1].min(), x[i:stop].min())
    return idx, prom


def volume_nodes(
    profile: pl.DataFrame, *, sigma_bins: float = 2.0, min_prominence: float = 0.10
) -> pl.DataFrame:
    """HVN/LVN. Bảng: kind, price_low, price_high, volume, smoothed, prominence."""
    v = profile["volume"].to_numpy().astype(np.float64)
    sm = _smooth(v, sigma_bins)
    scale = float(sm.max()) if len(sm) else 0.0
    parts = []
    for kind, x in (("hvn", sm), ("lvn", -sm)):
        idx, prom = _peaks(x)
        keep = prom >= min_prominence * scale if scale > 0 else np.zeros(len(idx), bool)
        idx, prom = idx[keep], prom[keep]
        parts.append(
            pl.DataFrame(
                {
                    "kind": [kind] * len(idx),
                    "price_low": profile["price_low"].to_numpy()[idx],
                    "price_high": profile["price_high"].to_numpy()[idx],
                    "volume": v[idx],
                    "smoothed": sm[idx],
                    "prominence": prom,
                },
                schema={
                    "kind": pl.String(),
                    "price_low": pl.Float64(),
                    "price_high": pl.Float64(),
                    "volume": pl.Float64(),
                    "smoothed": pl.Float64(),
                    "prominence": pl.Float64(),
                },
            )
        )
    return pl.concat(parts).sort("price_low")


# ---------------------------------------------------------------- profile theo kỳ


def _epoch_ms(values: pl.Series) -> np.ndarray:
    return values.dt.cast_time_unit("ms").dt.epoch("ms").to_numpy()


def _period_bounds(
    ohlcv: pl.DataFrame, period: str | Sequence[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    if isinstance(period, str):
        if period not in PERIODS:
            raise ValueError(f"period phải là một trong {list(PERIODS)} hoặc danh sách khoảng")
        every = PERIODS[period]
        starts = ohlcv["open_time"].dt.truncate(every).unique().sort()
        ends = starts.dt.offset_by(every)
        return list(zip(starts.to_list(), ends.to_list(), strict=True))
    out = []
    for start, end in period:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("mốc khoảng neo phải có múi giờ (UTC)")
        if not start < end:
            raise ValueError(f"khoảng neo không hợp lệ: {start} -> {end}")
        out.append((start, end))
    return sorted(out)


def profile_events(
    ohlcv: pl.DataFrame,
    period: str | Sequence[tuple[datetime, datetime]] = "week",
    *,
    bin_size: float | None = None,
    n_bins: int | None = None,
    va_pct: float = 0.70,
    sigma_bins: float = 2.0,
    min_prominence: float = 0.10,
) -> pl.DataFrame:
    """Events vpoc, value_area, hvn, lvn, naked_poc cho mỗi kỳ ĐÃ ĐÓNG (xem docstring module).

    attrs chung: period_start, period_end, n_bars, bin_size; vpoc/value_area/naked_poc thêm
    poc, poc_volume, total_volume, va_volume, va_pct; hvn/lvn thêm volume, prominence.
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    _grid(0.0, 1.0, bin_size, n_bins)  # kiểm tham số sớm
    phash = params_hash(
        MODULE,
        {
            "period": period if isinstance(period, str) else [list(p) for p in period],
            "bin_size": bin_size,
            "n_bins": n_bins,
            "va_pct": va_pct,
            "sigma_bins": sigma_bins,
            "min_prominence": min_prominence,
        },
    )
    duration = bar_duration(timeframe)
    times = ohlcv["open_time"]
    open_ms = _epoch_ms(times)
    dur_ms = int(duration.total_seconds() * 1000)
    data_end_ms = int(open_ms[-1]) + dur_ms
    low = ohlcv["low"].to_numpy()
    high = ohlcv["high"].to_numpy()
    rows = []
    for start, end in _period_bounds(ohlcv, period):
        start_ms, end_ms = _epoch_ms(pl.Series([start, end]))
        if data_end_ms < end_ms:
            continue  # kỳ chưa đóng: không xuất
        i0, i1 = np.searchsorted(open_ms, [start_ms, end_ms], side="left")
        if i1 <= i0:
            continue
        bars = ohlcv.slice(int(i0), int(i1 - i0))
        if float(bars["volume"].sum()) <= 0:
            continue
        known_at = max(end, times[int(i1) - 1] + duration)
        prof = profile_from_ohlcv(bars, bin_size=bin_size, n_bins=n_bins)
        va = value_area(prof, va_pct)
        size = float(prof["price_high"][0] - prof["price_low"][0])
        base = {
            "period_start": start,
            "period_end": end,
            "n_bars": int(i1 - i0),
            "bin_size": size,
        }
        poc_attrs = {
            **base,
            "poc": va.poc,
            "poc_volume": va.poc_volume,
            "total_volume": va.total_volume,
            "va_volume": va.va_volume,
            "va_pct": va_pct,
        }
        # id chứa end để hai khoảng neo cùng start không trùng event_id
        common = {"event_time": start, "known_at": known_at, "id": str(end)}
        rows.append(
            {
                **common,
                "kind": "vpoc",
                "price_low": va.poc_low,
                "price_high": va.poc_high,
                "attrs": poc_attrs,
            }
        )
        rows.append(
            {
                **common,
                "kind": "value_area",
                "price_low": va.val,
                "price_high": va.vah,
                "attrs": poc_attrs,
            }
        )
        # naked POC: nến đầu tiên mở từ known_at trở đi chạm giá POC
        known_ms = int(_epoch_ms(pl.Series([known_at]))[0])
        j0 = int(np.searchsorted(open_ms, known_ms, side="left"))
        hit = np.flatnonzero((low[j0:] <= va.poc) & (high[j0:] >= va.poc))
        invalidated = times[j0 + int(hit[0])] + duration if len(hit) else None
        rows.append(
            {
                **common,
                "kind": "naked_poc",
                "price_low": va.poc,
                "price_high": va.poc,
                "invalidated_at": invalidated,
                "attrs": poc_attrs,
            }
        )
        nodes = volume_nodes(prof, sigma_bins=sigma_bins, min_prominence=min_prominence)
        for node in nodes.iter_rows(named=True):
            rows.append(
                {
                    **common,
                    "kind": node["kind"],
                    "price_low": node["price_low"],
                    "price_high": node["price_high"],
                    "id": f"{end}|{node['price_low']!r}",
                    "attrs": {
                        **base,
                        "volume": node["volume"],
                        "prominence": node["prominence"],
                    },
                }
            )
    return events_frame(rows, symbol=symbol, timeframe=timeframe, phash=phash)


# ---------------------------------------------------------------------------
# Hình dạng profile (anatomy): D, P, b, DD. Khớp với pine/rinng_overlay.pine.
#
# - Làm mượt volume bằng trung bình 5 bin (cửa sổ bị cắt ở hai đầu).
# - DD (double distribution): có đỉnh cục bộ thứ hai cách đỉnh lớn nhất >= 1/5 số bin, và đáy
#   thấp nhất giữa hai đỉnh <= `dd_valley` × đỉnh nhỏ hơn.
# - Nếu không phải DD, xét vị trí POC trong biên độ: >= 65% là P, <= 35% là b, còn lại D.
# Ngưỡng do dự án chọn, không phải chuẩn chung; cách đọc theo Market Profile chưa có kiểm định.
# ---------------------------------------------------------------------------

SHAPES = ("D", "P", "b", "DD")


def classify_shape(
    profile: pl.DataFrame, *, dd_valley: float = 0.30, p_level: float = 0.65, b_level: float = 0.35
) -> str:
    """Nhãn hình dạng của một profile (frame có cột volume, sắp từ giá thấp lên cao)."""
    v = profile["volume"].to_numpy().astype(np.float64)
    n = len(v)
    if n == 0 or v.sum() <= 0:
        raise ValueError("profile rỗng")
    csum = np.concatenate([[0.0], np.cumsum(v)])
    lo = np.maximum(np.arange(n) - 2, 0)
    hi = np.minimum(np.arange(n) + 2, n - 1)
    sm = (csum[hi + 1] - csum[lo]) / (hi - lo + 1)
    p1 = int(np.argmax(sm))
    p2, best = -1, 0.0
    for i in range(1, n - 1):
        if sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and abs(i - p1) >= n / 5 and sm[i] > best:
            best, p2 = float(sm[i]), i
    if p2 >= 0:
        a, b = sorted((p1, p2))
        if sm[a : b + 1].min() <= dd_valley * min(sm[p1], sm[p2]):
            return "DD"
    frac = (poc_index(v) + 0.5) / n
    return "P" if frac >= p_level else "b" if frac <= b_level else "D"
