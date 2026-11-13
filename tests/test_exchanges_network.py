"""Test gọi sàn thật. Mặc định bị bỏ qua; chạy bằng: uv run pytest -m network"""

from datetime import UTC, datetime, timedelta

import pytest

from rinng.exchanges.base import timeframe_ms
from rinng.exchanges.binance import Binance
from rinng.exchanges.okx import Okx

pytestmark = pytest.mark.network

SYMBOLS = {"binance": "BTCUSDT", "okx": "BTC-USDT-SWAP"}


def _window(hours: int) -> tuple[datetime, datetime]:
    """Một khoảng gồm toàn nến 1h đã đóng, kết thúc ở đầu giờ hiện tại."""
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return end - timedelta(hours=hours), end


@pytest.fixture(scope="module", params=["binance", "okx"])
def api(request):
    return Binance() if request.param == "binance" else Okx()


def _rows(pages) -> list[dict]:
    return sorted((r for page in pages for r in page), key=lambda r: next(iter(r.values())))


def test_three_days_of_hourly_klines(api):
    start, end = _window(72)
    rows = _rows(api.klines(SYMBOLS[api.name], "1h", start, end))
    times = [r["open_time"] for r in rows]
    assert len(times) == 72
    assert len(set(times)) == 72
    assert times[0] == int(start.timestamp() * 1000)
    assert all(b - a == timeframe_ms("1h") for a, b in zip(times, times[1:], strict=False))
    assert all(r["is_closed"] for r in rows)
    assert all(
        r["low"] <= r["open"] <= r["high"] and r["low"] <= r["close"] <= r["high"] for r in rows
    )


def test_hourly_klines_span_multiple_pages(api):
    start, end = _window(2000)  # Binance 1500/trang, OKX 300/trang
    rows = _rows(api.klines(SYMBOLS[api.name], "1h", start, end))
    times = [r["open_time"] for r in rows]
    assert len(times) == 2000
    assert len(set(times)) == 2000


def test_mark_price_klines(api):
    start, end = _window(24)
    rows = _rows(api.mark_price_klines(SYMBOLS[api.name], "1h", start, end))
    assert len(rows) == 24


def test_funding_last_week(api):
    start, end = _window(24 * 7)
    rows = _rows(api.funding(SYMBOLS[api.name], start, end))
    assert len(rows) >= 14  # ít nhất hai lần mỗi ngày
    assert all(abs(r["rate"]) < 0.05 for r in rows)


@pytest.mark.parametrize("method", ["open_interest", "long_short", "taker_volume"])
def test_five_minute_stats_last_day(api, method):
    start, end = _window(24)
    rows = _rows(getattr(api, method)(SYMBOLS[api.name], "5m", start, end))
    times = [r["time"] for r in rows]
    assert len(set(times)) == len(times)
    assert 280 <= len(times) <= 288  # 288 điểm mỗi ngày; cho phép sàn thiếu vài điểm cuối
    assert all(int(start.timestamp() * 1000) <= t < int(end.timestamp() * 1000) for t in times)


def test_both_exchanges_agree_on_candle_times_and_prices():
    start, end = _window(48)
    binance = {r["open_time"]: r for r in _rows(Binance().klines("BTCUSDT", "1h", start, end))}
    okx = {r["open_time"]: r for r in _rows(Okx().klines("BTC-USDT-SWAP", "1h", start, end))}
    assert binance.keys() == okx.keys()
    for t, row in binance.items():
        assert abs(row["close"] / okx[t]["close"] - 1) < 0.005


def test_daily_candles_open_at_utc_midnight_on_both():
    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=5)
    for api, symbol in ((Binance(), "BTCUSDT"), (Okx(), "BTC-USDT-SWAP")):
        times = [r["open_time"] for r in _rows(api.klines(symbol, "1d", start, end))]
        assert len(times) == 5, api.name
        assert all(t % 86_400_000 == 0 for t in times), api.name
