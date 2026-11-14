"""Indicator so với cài đặt numpy độc lập và với giá trị tính tay."""

from datetime import timedelta

import numpy as np
import pytest

from rinng.analysis.indicators import anchored_vwap, atr, compute, vwap_daily
from rinng.analysis.testing import assert_no_lookahead
from tests.analysis.helpers import T0, make_ohlcv, random_walk

# ---------- cài đặt tham chiếu bằng numpy, viết từ công thức ----------


def ref_sma(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1 : i + 1].mean()
    return out


def ref_ema(x, n):
    """EMA seed bằng SMA của n giá trị hợp lệ đầu tiên (bỏ NaN ở đầu)."""
    out = np.full(len(x), np.nan)
    start = int(np.flatnonzero(~np.isnan(x))[0])
    seed = start + n - 1
    out[seed] = x[start : seed + 1].mean()
    alpha = 2 / (n + 1)
    for i in range(seed + 1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def ref_wilder(x, n, first):
    """Trung bình Wilder: seed = trung bình x[first-n+1 .. first]."""
    out = np.full(len(x), np.nan)
    out[first] = x[first - n + 1 : first + 1].mean()
    for i in range(first + 1, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def ref_rsi(c, n):
    d = np.diff(c, prepend=np.nan)
    gain = ref_wilder(np.where(d > 0, d, 0.0), n, n)
    loss = ref_wilder(np.where(d < 0, -d, 0.0), n, n)
    return 100 * gain / (gain + loss)


def true_range(h, lo, c):
    pc = np.concatenate([[np.nan], c[:-1]])
    return np.nanmax(np.vstack([h - lo, np.abs(h - pc), np.abs(lo - pc)]), axis=0)


def ref_atr(h, lo, c, n):
    return ref_wilder(true_range(h, lo, c), n, n)


def roll(x, n, fn):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = fn(x[i - n + 1 : i + 1])
    return out


def ref_adx(h, lo, c, n):
    up = np.diff(h, prepend=np.nan)
    dn = -np.diff(lo, prepend=np.nan)
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(h, lo, c)
    s_tr, s_p, s_m = (ref_wilder(x, n, n) for x in (tr, pdm, mdm))
    pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
    dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    return ref_wilder(dx, n, 2 * n - 1)


@pytest.fixture(scope="module")
def walk():
    o = random_walk(600, seed=11)
    arr = {k: o[k].to_numpy() for k in ("open", "high", "low", "close", "volume")}
    return o, compute(o), arr


def col(feat, name):
    return feat[name].fill_null(np.nan).to_numpy()


def close_valid(got, want, *, tail=None, rtol=1e-9):
    if tail is not None:
        got, want = got[-tail:], want[-tail:]
    assert np.array_equal(np.isnan(got), np.isnan(want))
    np.testing.assert_allclose(got[~np.isnan(got)], want[~np.isnan(want)], rtol=rtol, atol=1e-9)


def test_sma_ema(walk):
    _, f, a = walk
    for n in (20, 50, 200):
        close_valid(col(f, f"sma_{n}"), ref_sma(a["close"], n))
    for n in (9, 21, 50, 200):
        close_valid(col(f, f"ema_{n}"), ref_ema(a["close"], n))


def test_rsi_atr_adx(walk):
    _, f, a = walk
    close_valid(col(f, "rsi"), ref_rsi(a["close"], 14))
    close_valid(col(f, "atr"), ref_atr(a["high"], a["low"], a["close"], 14))
    # ADX: cách seed của TA-Lib có thể khác nhẹ; so phần đuôi sau khi đã hội tụ.
    close_valid(col(f, "adx"), ref_adx(a["high"], a["low"], a["close"], 14), tail=200, rtol=1e-6)
    assert np.isnan(col(f, "adx")[:27]).all()


def test_macd(walk):
    _, f, a = walk
    line = ref_ema(a["close"], 12) - ref_ema(a["close"], 26)
    signal = ref_ema(line, 9)
    close_valid(col(f, "macd"), line, tail=300, rtol=1e-7)
    close_valid(col(f, "macd_signal"), signal, tail=300, rtol=1e-7)
    close_valid(col(f, "macd_hist"), line - signal, tail=300, rtol=1e-6)


def test_roc_stoch_willr_bbands_obv(walk):
    _, f, a = walk
    c, h, lo = a["close"], a["high"], a["low"]
    roc = np.full(len(c), np.nan)
    roc[10:] = 100 * (c[10:] / c[:-10] - 1)
    close_valid(col(f, "roc"), roc)

    hh, ll = roll(h, 14, np.max), roll(lo, 14, np.min)
    raw_k = 100 * (c - ll) / (hh - ll)
    k = roll(raw_k, 3, np.mean)
    d = roll(k, 3, np.mean)
    k[np.isnan(d)] = np.nan  # TA-Lib: %K và %D cùng bắt đầu khi %D có giá trị
    close_valid(col(f, "stoch_k"), k)
    close_valid(col(f, "stoch_d"), d)
    close_valid(col(f, "willr"), -100 * (hh - c) / (hh - ll))

    mid = ref_sma(c, 20)
    sd = roll(c, 20, lambda w: w.std(ddof=0))
    close_valid(col(f, "bb_mid"), mid)
    close_valid(col(f, "bb_upper"), mid + 2 * sd, rtol=1e-7)
    close_valid(col(f, "bb_lower"), mid - 2 * sd, rtol=1e-7)

    sign = np.sign(np.diff(c, prepend=c[0]))
    obv = np.cumsum(sign * a["volume"])
    obv += a["volume"][0]  # TA-Lib: OBV[0] = volume[0]
    close_valid(col(f, "obv"), obv)


def test_small_hand_values():
    # ROC và Williams %R tính tay trên chuỗi ngắn.
    closes = [10.0, 11.0, 12.0, 11.0, 13.0]
    o = make_ohlcv(closes, highs=[10.5, 11.5, 12.5, 12.0, 13.5], lows=[9.5, 10.5, 11.5, 10.5, 12])
    f = compute(o, {"roc": 2, "willr": 3})
    assert f["roc"].to_list()[:2] == [None, None]
    assert f["roc"][2] == pytest.approx(20.0)  # 12/10 - 1
    assert f["roc"][4] == pytest.approx(100 * (13 / 12 - 1))
    # nến 3: HH = 12.5, LL = 10.5 → -100 × (12.5 - 11) / 2 = -75
    assert f["willr"][3] == pytest.approx(-75.0)
    assert f["willr"][1] is None
    # ATR(2) tay: TR từ nến 1 = [1.5, 1.5, 1.5, 2.5]; seed ở nến 2 = (1.5 + 1.5) / 2
    a = atr(o, 2)
    assert np.isnan(a[:2]).all()
    assert a[2] == pytest.approx(1.5)
    assert a[3] == pytest.approx((1.5 + 1.5) / 2)
    assert a[4] == pytest.approx((1.5 + 2.5) / 2)


def test_vwap_daily_resets_at_utc_midnight():
    # khung 12h: nến 0, 1 thuộc ngày 1; nến 2, 3 thuộc ngày 2.
    o = make_ohlcv(
        [10.0, 20.0, 30.0, 40.0],
        highs=[10.0, 20.0, 30.0, 40.0],
        lows=[10.0, 20.0, 30.0, 40.0],
        volumes=[1.0, 3.0, 2.0, 2.0],
        timeframe="12h",
    )
    v = vwap_daily(o).to_list()
    assert v[0] == pytest.approx(10.0)
    assert v[1] == pytest.approx((10 * 1 + 20 * 3) / 4)  # 17.5
    assert v[2] == pytest.approx(30.0)  # reset
    assert v[3] == pytest.approx(35.0)


def test_vwap_typical_price_and_zero_volume():
    o = make_ohlcv([10.0, 12.0], highs=[12.0, 15.0], lows=[9.0, 9.0], volumes=[0.0, 2.0])
    v = vwap_daily(o).to_list()
    assert v[0] is None  # tổng volume = 0
    assert v[1] == pytest.approx((15 + 9 + 12) / 3)


def test_anchored_vwap():
    o = make_ohlcv([10.0, 20.0, 30.0, 40.0], volumes=[5.0, 1.0, 1.0, 2.0])
    # typical = close vì high/low = max/min(open, close): nến 2 có open 20, close 30
    highs, lows, closes = (o[c].to_list() for c in ("high", "low", "close"))
    tp = [(h + lo + c) / 3 for h, lo, c in zip(highs, lows, closes, strict=True)]
    v = anchored_vwap(o, T0 + timedelta(hours=1, minutes=30)).to_list()
    assert v[:2] == [None, None]
    assert v[2] == pytest.approx(tp[2])
    assert v[3] == pytest.approx((tp[2] * 1 + tp[3] * 2) / 3)
    f = compute(o, {"avwap_anchor": T0 + timedelta(hours=2)})
    assert f["avwap"][2] == pytest.approx(tp[2])


def test_compute_rejects_unknown_param_and_keys():
    o = random_walk(50)
    with pytest.raises(ValueError):
        compute(o, {"rsi_len": 3})
    f = compute(o, {"ema": [5], "sma": [], "vwap": False})
    assert "ema_5" in f.columns and "sma_20" not in f.columns and "vwap" not in f.columns
    assert f["known_at"][0] == f["open_time"][1]
    assert f["params_hash"][0] != compute(o)["params_hash"][0]


def test_indicators_no_lookahead():
    o = random_walk(300)
    anchor = T0 + timedelta(hours=40)
    assert_no_lookahead(lambda x: compute(x, {"avwap_anchor": anchor}), o, [30, 120, 121, 250])
