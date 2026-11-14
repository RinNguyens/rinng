"""Volume profile: volume histogram by price level, POC, value area, HVN/LVN, naked POC.

Price bin grid (choose exactly one of the two parameters):
- `bin_size`: absolute bin size, grid anchored at 0, bin k = [k*bin_size, (k+1)*bin_size).
  All periods share the grid, so POCs are comparable across periods.
- `n_bins`: fixed number of bins, evenly splitting [min low, max high] of the input data.
  Each period has its own grid.

Two ways to build a profile:
- `profile_from_ohlcv` (approximate): each candle's volume is spread evenly over the bins its [low,
  high] touches. The bin containing low is always counted; a high exactly on a bin edge does not
  spill into the bin above. `taker_buy_volume` (if present) is spread the same way as `buy_volume`,
  the rest is `sell_volume`. The profile uses exactly the candles given (1m or a higher timeframe);
  larger candles give a coarser profile (docs/04 section 1.3).
- `profile_from_trades` (exact): add each trade's `qty` to the bin containing `price`.
  `is_buyer_maker=True` means the taker SOLD.
Both return a contiguous table (including zero-volume bins) ascending by price:
`price_low, price_high, volume[, buy_volume, sell_volume]`.

POC (VPOC): the bin with the largest volume; ties pick the bin nearest the middle of the price
range, then the lower bin. POC price = bin middle.

Value area (default 70%): start from the POC bin; each step compares the sum of the TWO next bins
above with the sum of the TWO next bins below and takes both bins of the larger side (classic CBOT
style); ties pick the upper side; if one side has a single bin left compare that bin; if a side is
exhausted take the other. Stop when cumulative volume >= pct * total, so VA may slightly exceed 70%.
VAL = lower edge of the lowest bin, VAH = upper edge of the highest bin. Possible differences from
TradingView (closed source, **unverified** variant): expanding one bin at a time instead of two,
tie-breaking at the POC and at each step, how candle volume is spread (TradingView may use
lower-timeframe candles), and whether VAH/VAL are bin edges or bin middles.

HVN/LVN: smooth volume with a Gaussian kernel `sigma_bins` (zero padding outside the range, since
there is no volume outside it), then take local maxima (HVN) / minima (LVN) at interior bins
(excluding the two edge bins). Plateau extrema take the first bin. Only extrema with prominence
(defined as `scipy.signal.peak_prominences`) >= `min_prominence` * max(smoothed volume) are kept.

Per-period profiles (`profile_events`): `period` is "day" (UTC day), "week" (Monday 00:00 UTC),
"month" (UTC calendar month), or a list of anchored ranges [start, end). A candle belongs to the
period containing its `open_time`. A period is only emitted once closed, i.e. the data has a candle
closing at >= end.
- `event_time` = period open, `known_at` = max(period close, close of the period's last candle).
- Kind: `vpoc` (price_low/high = POC bin edges), `value_area` (VAL, VAH), `hvn`, `lvn`
  (node bin edges), `naked_poc` (price_low = price_high = POC price).
- `naked_poc.invalidated_at` = CLOSE time of the first candle opening at or after `known_at` with
  low <= POC <= high (close rather than open, since a touch is only certain once the candle closes;
  this keeps `assert_no_lookahead`). Null means the POC is still "naked" at the end of the data.
The first period may be missing candles (data starts mid-period); `attrs.n_bars` gives the number of
candles used.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import polars as pl

from rinng.analysis.types import bar_duration, check_ohlcv, events_frame, params_hash

MODULE = "volume_profile"

PERIODS = {"day": "1d", "week": "1w", "month": "1mo"}

_EPS = 1e-7  # tolerance when converting a price to a bin index (price exactly on a bin edge)


# ---------------------------------------------------------------- bin grid and profile building


def _grid(
    low_min: float, high_max: float, bin_size: float | None, n_bins: int | None
) -> tuple[float, float, int | None]:
    """Return (origin, bin_size, n_bins or None for an absolute grid)."""
    if (bin_size is None) == (n_bins is None):
        raise ValueError("exactly one of bin_size, n_bins is required")
    if bin_size is not None:
        if not bin_size > 0:
            raise ValueError("bin_size must be > 0")
        return 0.0, float(bin_size), None
    if n_bins is None or n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    span = high_max - low_min
    if span <= 0:  # all prices equal: a single bin
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
    """Approximate profile from candles: spread each candle's volume evenly over the bins in [low,
    high]."""
    if ohlcv.is_empty():
        raise ValueError("empty candle frame")
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
    # Difference array: add density at lo, subtract at hi+1, then cumulative sum. O(candles + bins).
    cover = np.cumsum(np.bincount(lo, minlength=nb + 1) - np.bincount(hi + 1, minlength=nb + 1))
    empty = cover[:nb] == 0

    def spread(weights: np.ndarray) -> np.ndarray:
        d = weights / count
        x = np.cumsum(
            np.bincount(lo, weights=d, minlength=nb + 1)
            - np.bincount(hi + 1, weights=d, minlength=nb + 1)
        )[:nb]
        x[empty] = 0.0  # bins covered by no candle: exactly 0, no cumulative rounding error
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
    """Exact profile from trades: add qty to the bin containing price. Buy/sell split by taker
    side."""
    if trades.is_empty():
        raise ValueError("trades frame is empty")
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


# ---------------------------------------------------------------- POC, value area, nodes


@dataclass(frozen=True)
class ValueArea:
    poc: float  # middle price of the POC bin
    poc_low: float
    poc_high: float
    poc_volume: float
    val: float
    vah: float
    va_volume: float
    total_volume: float


def poc_index(volume: np.ndarray) -> int:
    """POC bin index; ties pick the one nearest the middle of the range, then the lower bin."""
    cands = np.flatnonzero(volume == volume.max())
    return int(cands[np.abs(cands - (len(volume) - 1) / 2).argmin()])


def value_area(profile: pl.DataFrame, pct: float = 0.70) -> ValueArea:
    """POC and value area using the two-bins-per-step variant (see module docstring)."""
    if not 0 < pct <= 1:
        raise ValueError("pct must be in (0, 1]")
    v = profile["volume"].to_numpy().astype(np.float64)
    total = float(v.sum())
    if len(v) == 0 or total <= 0:
        raise ValueError("empty profile or zero total volume")
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
    """Interior local maxima (strict on the left, non-strict on the right) and scipy-style
    prominence."""
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
    """HVN/LVN. Table: kind, price_low, price_high, volume, smoothed, prominence."""
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


# ---------------------------------------------------------------- period profiles


def _epoch_ms(values: pl.Series) -> np.ndarray:
    return values.dt.cast_time_unit("ms").dt.epoch("ms").to_numpy()


def _period_bounds(
    ohlcv: pl.DataFrame, period: str | Sequence[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    if isinstance(period, str):
        if period not in PERIODS:
            raise ValueError(f"period must be one of {list(PERIODS)} or a list of ranges")
        every = PERIODS[period]
        starts = ohlcv["open_time"].dt.truncate(every).unique().sort()
        ends = starts.dt.offset_by(every)
        return list(zip(starts.to_list(), ends.to_list(), strict=True))
    out = []
    for start, end in period:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("anchored range bounds must be timezone-aware (UTC)")
        if not start < end:
            raise ValueError(f"invalid anchored range: {start} -> {end}")
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
    """Events vpoc, value_area, hvn, lvn, naked_poc for each CLOSED period (see module docstring).

    Common attrs: period_start, period_end, n_bars, bin_size; vpoc/value_area/naked_poc add
    poc, poc_volume, total_volume, va_volume, va_pct; hvn/lvn add volume, prominence.
    """
    symbol, timeframe = check_ohlcv(ohlcv)
    _grid(0.0, 1.0, bin_size, n_bins)  # validate parameters early
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
            continue  # period not closed yet: do not emit
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
        # the id includes end so two anchored ranges with the same start do not share an event_id
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
        # naked POC: first candle opening at or after known_at that touches the POC price
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
# Profile shape (anatomy): D, P, b, DD. Matches pine/rinng_overlay.pine.
#
# - Smooth volume with a 5-bin moving average (window truncated at both ends).
# - DD (double distribution): a second local peak at least 1/5 of the bins away from the largest
#   peak, and the lowest valley between the two peaks <= `dd_valley` × the smaller peak.
# - If not DD, look at the POC position within the range: >= 65% is P, <= 35% is b, otherwise D.
# Thresholds chosen by the project, not a common standard; the Market Profile reading is untested.
# ---------------------------------------------------------------------------

SHAPES = ("D", "P", "b", "DD")


def classify_shape(
    profile: pl.DataFrame, *, dd_valley: float = 0.30, p_level: float = 0.65, b_level: float = 0.35
) -> str:
    """Shape label of a profile (frame with a volume column, sorted from low to high price)."""
    v = profile["volume"].to_numpy().astype(np.float64)
    n = len(v)
    if n == 0 or v.sum() <= 0:
        raise ValueError("profile is empty")
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
