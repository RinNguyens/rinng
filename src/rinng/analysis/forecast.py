"""Probabilistic forecast of the price path: quantile cone + probability of touching a price level.

Does not draw a single "price will go like this" line. Short-term crypto prices are close to random,
so the output is a distribution, together with validation metrics showing whether that distribution
can be trusted.

Method (analog / k-nearest-neighbour on volatility-normalised trajectories):

1. Instantaneous volatility sigma_t: EWMA of log-returns (lambda 0.94, RiskMetrics). Only uses data
   up to candle t.
2. Each candle's state = a normalised feature vector: 1/5/20/60-candle returns divided by
   sigma, volatility regime (short sigma / long sigma), position within the 50-candle range, RSI,
   volume.
3. For the current candle, find the K past candles with the closest state (only candles whose next H
   candles occurred before now). Take the H-candle trajectory after each of them, divided by its own
   sigma.
4. Blend the conditional distribution (analogs, weighted by distance) with the unconditional
   distribution (all past trajectories) to avoid over-trusting a small group: weight = `blend`.
5. Multiply back by the current sigma → price quantiles for each step 1..H; probability of touching
   a price level = (weighted) share of trajectories whose high/low touches that level within H
   candles.

`walk_forward` reruns exactly this procedure over history (each origin only sees the past) to
measure: actual band coverage, pinball loss versus the unconditional distribution, directional hit
rate.
"""

from dataclasses import dataclass

import numpy as np
import polars as pl
import talib

QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
EWMA_LAMBDA = 0.94
WARMUP = 210  # enough for the 200-candle features
MIN_POOL = 300  # at least this many past trajectories are needed to forecast


# ---------------------------------------------------------------------------- base data


@dataclass(frozen=True)
class Prepared:
    """Arrays shared by the forecast; element i depends only on candles 0..i (except future
    trajectories)."""

    close: np.ndarray
    logc: np.ndarray
    sigma: np.ndarray  # EWMA sigma of 1-candle log-returns, known at the close of candle i
    features: np.ndarray  # (n, d), NaN while data is insufficient
    high: np.ndarray
    low: np.ndarray


def ewma_sigma(logc: np.ndarray, lam: float = EWMA_LAMBDA) -> np.ndarray:
    r = np.diff(logc, prepend=logc[0])
    var = np.empty_like(r)
    seed = np.var(r[1:51]) if len(r) > 51 else (np.var(r[1:]) if len(r) > 2 else 1e-8)
    v = max(seed, 1e-12)
    for i, x in enumerate(r):
        v = lam * v + (1 - lam) * x * x
        var[i] = v
    return np.sqrt(var)


def _rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    c1 = np.cumsum(np.insert(x, 0, 0.0))
    c2 = np.cumsum(np.insert(x * x, 0, 0.0))
    s1 = c1[n:] - c1[:-n]
    s2 = c2[n:] - c2[:-n]
    out[n - 1 :] = np.sqrt(np.maximum(s2 / n - (s1 / n) ** 2, 0.0))
    return out


def prepare(ohlcv: pl.DataFrame) -> Prepared:
    close = ohlcv["close"].to_numpy().astype(float)
    high = ohlcv["high"].to_numpy().astype(float)
    low = ohlcv["low"].to_numpy().astype(float)
    volume = ohlcv["volume"].to_numpy().astype(float)
    logc = np.log(close)
    sigma = ewma_sigma(logc)
    n = len(close)

    def lag_ret(k: int) -> np.ndarray:
        out = np.full(n, np.nan)
        if n > k:
            out[k:] = (logc[k:] - logc[:-k]) / (sigma[k:] * np.sqrt(k))
        return out

    r1 = np.diff(logc, prepend=logc[0])
    long_sd = _rolling_std(r1, 200)
    with np.errstate(divide="ignore", invalid="ignore"):
        vol_regime = np.log(sigma / long_sd)
        hh = pl.Series(high).rolling_max(50).to_numpy()
        ll = pl.Series(low).rolling_min(50).to_numpy()
        rng_pos = (close - ll) / (hh - ll) * 2 - 1
        vmean = pl.Series(volume).rolling_mean(50).to_numpy()
        vol_z = np.log(volume / vmean)
    rsi = talib.RSI(close, timeperiod=14) / 50 - 1
    feats = np.column_stack(
        [lag_ret(1), lag_ret(5), lag_ret(20), lag_ret(60), vol_regime, rng_pos, rsi, vol_z]
    )
    feats = np.clip(feats, -5, 5)
    feats[:WARMUP] = np.nan
    return Prepared(close, logc, sigma, feats, high, low)


def _paths(p: Prepared, idx: np.ndarray, horizon: int) -> tuple[np.ndarray, ...]:
    """Normalised trajectories after candles idx: close, max high, min low (in units of the origin
    candle's sigma)."""
    steps = np.arange(1, horizon + 1)
    j = idx[:, None] + steps[None, :]
    s = p.sigma[idx][:, None]
    base = p.logc[idx][:, None]
    z = (p.logc[j] - base) / s
    up = np.maximum.accumulate((np.log(p.high[j]) - base) / s, axis=1)
    down = np.minimum.accumulate((np.log(p.low[j]) - base) / s, axis=1)
    return z, up, down


def _wquantile(values: np.ndarray, weights: np.ndarray, qs) -> np.ndarray:
    """Weighted quantiles for each column of values (m, h); all columns share the weights."""
    wn = weights / weights.sum()
    order = np.argsort(values, axis=0)
    v = np.take_along_axis(values, order, axis=0)
    w = wn[order]
    cdf = np.cumsum(w, axis=0) - 0.5 * w  # midpoint of each step, like Hazen interpolation
    out = np.empty((len(qs), values.shape[1]))
    for col in range(values.shape[1]):
        out[:, col] = np.interp(qs, cdf[:, col], v[:, col])
    return out


# ---------------------------------------------------------------------------- forecast


@dataclass(frozen=True)
class Forecast:
    origin: int  # origin candle index
    horizon: int
    close: float
    sigma: float
    quantiles: np.ndarray  # (len(QUANTILES), horizon) prices
    z_quantiles: np.ndarray  # same shape, in sigma units
    analogs: int  # number of conditional trajectories used
    pool: int  # total number of past trajectories
    weights: np.ndarray  # final weights of every trajectory in the pool
    up: np.ndarray  # (pool,) normalised max high within H candles
    down: np.ndarray  # (pool,) normalised min low within H candles
    neighbours: np.ndarray  # indices of the analog candles (for plotting / explanation)

    def touch_probability(self, level: float) -> float:
        """Probability that price touches `level` within the next H candles (by high/low)."""
        z = np.log(level / self.close) / self.sigma
        hit = self.up >= z if z >= 0 else self.down <= z
        return float(np.sum(self.weights * hit) / np.sum(self.weights))

    def median_path(self) -> np.ndarray:
        return self.quantiles[QUANTILES.index(0.5)]


def analog_weights(
    p: Prepared, origin: int, pool_idx: np.ndarray, k: int, blend: float
) -> tuple[np.ndarray, np.ndarray]:
    """Weights for every trajectory in the pool: blend × analog (kernel over the K nearest) +
    (1 − blend) × uniform. Features are normalised by their standard deviation over the pool
    itself."""
    f = p.features[pool_idx]
    sd = np.nanstd(f, axis=0)
    sd[sd == 0] = 1.0
    d = np.sqrt(np.nansum(((f - p.features[origin]) / sd) ** 2, axis=1))
    k = min(k, len(pool_idx))
    near = np.argpartition(d, k - 1)[:k]
    h = np.median(d[near]) or 1.0
    w_an = np.zeros(len(pool_idx))
    w_an[near] = np.exp(-0.5 * (d[near] / h) ** 2)
    w_an /= w_an.sum()
    w = blend * w_an + (1 - blend) / len(pool_idx)
    return w, pool_idx[near]


@dataclass(frozen=True)
class Paths:
    """H-candle trajectories after every candle i >= WARMUP (row i - WARMUP). Only rows with i + H
    <= origin are used."""

    horizon: int
    z: np.ndarray
    up: np.ndarray
    down: np.ndarray


def all_paths(p: Prepared, horizon: int) -> Paths:
    idx = np.arange(WARMUP, max(WARMUP, len(p.close) - horizon))
    z, up, down = _paths(p, idx, horizon)
    return Paths(horizon, z, up[:, -1], down[:, -1])


def forecast_at(
    p: Prepared,
    origin: int,
    horizon: int,
    *,
    k: int | None = None,
    blend: float = 0.7,
    paths: Paths | None = None,
    last_only: bool = False,
) -> Forecast | None:
    """Forecast from candle `origin` using only data up to `origin`. None if history is
    insufficient.

    `paths`: precomputed trajectories (walk_forward reuses them for every origin); only rows ending
    before or at `origin` are read."""
    last_start = origin - horizon  # trajectory [i, i+H] must end before or at origin
    pool_idx = np.arange(WARMUP, last_start + 1)
    if len(pool_idx) < MIN_POOL or np.isnan(p.features[origin]).any():
        return None
    pool_idx = pool_idx[~np.isnan(p.features[pool_idx]).any(axis=1)]
    if len(pool_idx) < MIN_POOL:
        return None
    k = k or int(np.clip(len(pool_idx) // 15, 100, 600))
    w, near = analog_weights(p, origin, pool_idx, k, blend)
    if paths is not None and paths.horizon == horizon:
        rows = pool_idx - WARMUP
        z, up, down = paths.z[rows], paths.up[rows], paths.down[rows]
    else:
        z, up, down = _paths(p, pool_idx, horizon)
        up, down = up[:, -1], down[:, -1]
    # last_only: only the last-step quantiles are needed (walk_forward), much faster.
    zq = _wquantile(z[:, -1:] if last_only else z, w, QUANTILES)
    s, c = p.sigma[origin], p.close[origin]
    return Forecast(
        origin=origin,
        horizon=horizon,
        close=float(c),
        sigma=float(s),
        quantiles=c * np.exp(zq * s),
        z_quantiles=zq,
        analogs=len(near),
        pool=len(pool_idx),
        weights=w,
        up=up,
        down=down,
        neighbours=near,
    )


def forecast(ohlcv: pl.DataFrame, horizon: int, **kw) -> Forecast | None:
    """Forecast from the last (closed) candle of `ohlcv`."""
    return forecast_at(prepare(ohlcv), ohlcv.height - 1, horizon, **kw)


# ---------------------------------------------------------------------------- validation


def _pinball(zq: np.ndarray, actual: float) -> float:
    q = np.asarray(QUANTILES)
    diff = actual - zq
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def walk_forward(
    ohlcv: pl.DataFrame,
    horizon: int,
    *,
    max_origins: int = 250,
    blend: float = 0.7,
    prepared: Prepared | None = None,
) -> dict | None:
    """Re-forecast at many past origins (each only sees data before it) and compare
    with the actual price H candles later. Returns band coverage, skill versus the unconditional
    distribution, directional hit rate of the median, and Brier score of the ±1 sigma·sqrt(H) touch
    probabilities."""
    p = prepared or prepare(ohlcv)
    n = len(p.close)
    last = n - 1 - horizon  # an origin needs H candles after it to be scored
    first = WARMUP + MIN_POOL + horizon
    if last <= first:
        return None
    step = max(1, (last - first) // max_origins)
    origins = np.arange(last, first, -step)[:max_origins][::-1]
    inside = {50: 0, 80: 0, 90: 0}
    pin_c = pin_u = 0.0
    dir_hit = dir_n = 0
    brier_c = brier_u = 0.0
    count = 0
    lo = {50: 2, 80: 1, 90: 0}
    hi = {50: 4, 80: 5, 90: 6}
    paths = all_paths(p, horizon)
    for o in origins:
        fc = forecast_at(p, int(o), horizon, blend=blend, paths=paths, last_only=True)
        if fc is None:
            continue
        # Baseline: same trajectories, uniform weights (unconditional distribution).
        uniform = np.full(len(fc.weights), 1.0)
        rows = np.arange(fc.pool)
        uc_zq = _wquantile(paths.z[rows][:, -1:], uniform, QUANTILES)[:, -1]
        actual = (p.logc[o + horizon] - p.logc[o]) / p.sigma[o]
        zq = fc.z_quantiles[:, -1]
        for band in inside:
            inside[band] += int(zq[lo[band]] <= actual <= zq[hi[band]])
        pin_c += _pinball(zq, actual)
        pin_u += _pinball(uc_zq, actual)
        med = zq[3]
        if abs(med) > 1e-9 and actual != 0:
            dir_n += 1
            dir_hit += int(np.sign(med) == np.sign(actual))
        # Touch of ±1 sigma*sqrt(H) by high/low within H candles.
        thr = np.sqrt(horizon)
        j = np.arange(o + 1, o + horizon + 1)
        up_real = (np.log(p.high[j]).max() - p.logc[o]) / p.sigma[o] >= thr
        dn_real = (np.log(p.low[j]).min() - p.logc[o]) / p.sigma[o] <= -thr
        for w, acc in ((fc.weights, "c"), (uniform, "u")):
            pu = np.sum(w * (fc.up >= thr)) / np.sum(w)
            pd = np.sum(w * (fc.down <= -thr)) / np.sum(w)
            b = float((pu - up_real) ** 2 + (pd - dn_real) ** 2) / 2
            if acc == "c":
                brier_c += b
            else:
                brier_u += b
        count += 1
    if count == 0:
        return None
    return {
        "origins": count,
        "coverage": {band: inside[band] / count for band in inside},
        "pinball": pin_c / count,
        "pinball_baseline": pin_u / count,
        "skill": 1 - pin_c / pin_u if pin_u else 0.0,
        "direction_hit": dir_hit / dir_n if dir_n else None,
        "brier": brier_c / count,
        "brier_baseline": brier_u / count,
    }
