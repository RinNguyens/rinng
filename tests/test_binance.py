from datetime import UTC, datetime, timedelta

import httpx
import pytest

from rinng.exchanges.binance import Binance
from rinng.exchanges.ratelimit import ExchangeError, IpBanned, RateLimited

H = 3_600_000
T0 = datetime(2026, 11, 1, tzinfo=UTC)
T0_MS = int(T0.timestamp() * 1000)


def kline(open_ms: int, interval: int = H) -> list:
    return [
        open_ms,
        "100",
        "110",
        "90",
        "105",
        "12.5",
        open_ms + interval - 1,
        "1300",
        42,
        "7",
        "0",
        "0",
    ]


class FakeBinance:
    """Return 1h candles from T0 on, honouring startTime/endTime/limit like the real exchange."""

    def __init__(self, total_bars: int) -> None:
        self.total = total_bars
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        q = request.url.params
        start, end, limit = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
        bars = [T0_MS + i * H for i in range(self.total)]
        selected = [b for b in bars if start <= b <= end][:limit]
        return httpx.Response(
            200, json=[kline(b) for b in selected], headers={"x-mbx-used-weight-1m": "10"}
        )


def make(handler, **kwargs) -> Binance:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://fapi.test")
    kwargs.setdefault("sleep", lambda s: None)
    return Binance(client, **kwargs)


def collect(pages) -> list[dict]:
    return [row for page in pages for row in page]


def test_klines_paginates_without_gaps_or_duplicates():
    fake = FakeBinance(total_bars=4000)
    rows = collect(make(fake).klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=3200)))
    times = [r["open_time"] for r in rows]
    assert times == [T0_MS + i * H for i in range(3200)]
    assert len(fake.requests) == 3  # 1500 + 1500 + 200


def test_klines_end_is_exclusive():
    rows = collect(make(FakeBinance(100)).klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=3)))
    assert [r["open_time"] for r in rows] == [T0_MS, T0_MS + H, T0_MS + 2 * H]


def test_klines_empty_range_makes_no_rows():
    assert collect(make(FakeBinance(0)).klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=5))) == []


def test_kline_fields_and_types():
    row = collect(make(FakeBinance(1)).klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=1)))[0]
    assert row == {
        "open_time": T0_MS,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 12.5,
        "quote_volume": 1300.0,
        "trades": 42,
        "taker_buy_volume": 7.0,
        "is_closed": True,
    }


def test_unclosed_candle_is_flagged():
    now = T0_MS + H + 60_000  # in the first minute of the second candle
    api = make(FakeBinance(2), now_ms=lambda: now)
    rows = collect(api.klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=2)))
    assert [r["is_closed"] for r in rows] == [True, False]


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        collect(make(FakeBinance(1)).klines("BTCUSDT", "1h", datetime(2026, 11, 1), T0))


def test_429_sleeps_retry_after_then_succeeds():
    calls, slept = [], []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "7"}, json={"code": -1003})
        return httpx.Response(200, json=[kline(T0_MS)])

    api = make(handler, sleep=slept.append)
    rows = collect(api.klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=1)))
    assert len(rows) == 1
    assert slept == [7.0]


def test_429_gives_up_after_max_retries():
    slept = []
    api = make(lambda r: httpx.Response(429, json={}), sleep=slept.append, max_retries=2)
    with pytest.raises(RateLimited):
        collect(api.klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=1)))
    assert slept == [60.0, 60.0]


def test_418_raises_immediately_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(418, headers={"retry-after": "120"}, json={})

    with pytest.raises(IpBanned) as info:
        collect(make(handler).klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=1)))
    assert len(calls) == 1
    assert info.value.retry_after == 120.0


def test_error_body_becomes_exchange_error():
    handler = lambda r: httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})  # noqa: E731
    with pytest.raises(ExchangeError) as info:
        collect(make(handler).klines("NOPE", "1h", T0, T0 + timedelta(hours=1)))
    assert info.value.code == "-1121"
    assert info.value.status == 400


def test_weight_header_feeds_limiter():
    api = make(FakeBinance(1))
    collect(api.klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=1)))
    assert api._weight.used == 10


def test_funding_rows():
    def handler(request):
        assert request.url.path == "/fapi/v1/fundingRate"
        return httpx.Response(
            200,
            json=[
                {
                    "symbol": "BTCUSDT",
                    "fundingTime": T0_MS + 2,
                    "fundingRate": "0.0001",
                    "markPrice": "70000.5",
                },
                {
                    "symbol": "BTCUSDT",
                    "fundingTime": T0_MS + 8 * H,
                    "fundingRate": "-0.0002",
                    "markPrice": "",
                },
            ],
        )

    rows = collect(make(handler).funding("BTCUSDT", T0, T0 + timedelta(days=1)))
    assert rows == [
        {"funding_time": T0_MS + 2, "rate": 0.0001, "mark_price": 70000.5},
        {"funding_time": T0_MS + 8 * H, "rate": -0.0002, "mark_price": None},
    ]


def test_stats_endpoints_rows():
    bodies = {
        "/futures/data/openInterestHist": [
            {"sumOpenInterest": "100.5", "sumOpenInterestValue": "7000000", "timestamp": T0_MS}
        ],
        "/futures/data/globalLongShortAccountRatio": [
            {
                "longAccount": "0.75",
                "longShortRatio": "3.0",
                "shortAccount": "0.25",
                "timestamp": T0_MS,
            }
        ],
        "/futures/data/takerlongshortRatio": [
            {"buySellRatio": "0.5", "sellVol": "20", "buyVol": "10", "timestamp": T0_MS}
        ],
    }
    api = make(lambda r: httpx.Response(200, json=bodies[r.url.path]))
    end = T0 + timedelta(hours=1)
    assert collect(api.open_interest("BTCUSDT", "5m", T0, end)) == [
        {"time": T0_MS, "oi_base": 100.5, "oi_value": 7000000.0}
    ]
    assert collect(api.long_short("BTCUSDT", "5m", T0, end)) == [
        {"time": T0_MS, "ratio": 3.0, "long_pct": 0.75, "short_pct": 0.25}
    ]
    assert collect(api.taker_volume("BTCUSDT", "5m", T0, end)) == [
        {"time": T0_MS, "buy_volume": 10.0, "sell_volume": 20.0}
    ]


def test_invalid_period_rejected_before_any_request():
    api = make(lambda r: pytest.fail("must not hit the network"))
    with pytest.raises(ValueError):
        collect(api.open_interest("BTCUSDT", "7m", T0, T0 + timedelta(hours=1)))


def test_sync_limits_reads_exchange_info():
    body = {
        "rateLimits": [
            {
                "rateLimitType": "REQUEST_WEIGHT",
                "interval": "MINUTE",
                "intervalNum": 1,
                "limit": 1000,
            },
            {"rateLimitType": "ORDERS", "interval": "MINUTE", "intervalNum": 1, "limit": 1200},
        ]
    }
    api = make(lambda r: httpx.Response(200, json=body))
    api.sync_limits()
    assert api._weight.budget == 500


def test_stats_paginate_backwards_because_binance_returns_newest():
    """The exchange returns the latest `limit` points in the range, ascending."""
    step = 300_000
    points = [T0_MS + i * step for i in range(1200)]
    requests = []

    def handler(request):
        requests.append(request)
        q = request.url.params
        start, end, limit = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
        inside = [p for p in points if start <= p <= end][-limit:]
        body = [
            {"sumOpenInterest": "1", "sumOpenInterestValue": "2", "timestamp": p} for p in inside
        ]
        return httpx.Response(200, json=body)

    pages = make(handler).open_interest("BTCUSDT", "5m", T0, T0 + timedelta(minutes=5 * 1200))
    times = sorted(r["time"] for page in pages for r in page)
    assert times == points
    assert len(requests) == 3  # 500 + 500 + 200


def test_transient_network_error_is_retried():
    calls, slept = [], []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("Connection reset by peer")
        return httpx.Response(200, json=[kline(T0_MS)])

    rows = collect(
        make(handler, sleep=slept.append).klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=1))
    )
    assert len(rows) == 1
    assert slept == [2.0]


def test_persistent_network_error_raises():
    def handler(request):
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        collect(make(handler, max_retries=1).klines("BTCUSDT", "1h", T0, T0 + timedelta(hours=1)))


# --------------------------------------------------------------------------- bulk market data


def test_tickers_24h_parses_all_symbols():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "symbol": "SPXUSDT",
                    "priceChange": "0.0132000",
                    "priceChangePercent": "4.450",
                    "lastPrice": "0.3145000",
                    "volume": "12365700",
                    "quoteVolume": "3888972.0801000",
                },
                {
                    "symbol": "BTCUSDT",
                    "priceChangePercent": "-1.20",
                    "lastPrice": "91204.10",
                    "quoteVolume": "12400000000.5",
                },
            ],
            headers={"x-mbx-used-weight-1m": "40"},
        )

    rows = make(handler).tickers_24h()
    assert len(seen) == 1
    assert seen[0].url.path == "/fapi/v1/ticker/24hr"
    assert "symbol" not in seen[0].url.params  # all symbols in one call
    assert rows == [
        {"symbol": "SPXUSDT", "price": 0.3145, "chg_24h": 4.45, "volume_24h": 3888972.0801},
        {"symbol": "BTCUSDT", "price": 91204.10, "chg_24h": -1.2, "volume_24h": 12400000000.5},
    ]


def test_premium_index_parses_rate_and_next_funding():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "91200.1",
                    "lastFundingRate": "0.00010000",
                    "nextFundingTime": 1763391600000,
                    "time": 1763380800000,
                },
                {
                    "symbol": "SPXUSDT",
                    "lastFundingRate": "-0.00005250",
                    "nextFundingTime": "1763385600000",
                },
            ],
        )

    rows = make(handler).premium_index()
    assert len(seen) == 1
    assert seen[0].url.path == "/fapi/v1/premiumIndex"
    assert "symbol" not in seen[0].url.params
    assert rows == [
        {"symbol": "BTCUSDT", "funding_rate": 0.0001, "next_funding": 1763391600},
        {"symbol": "SPXUSDT", "funding_rate": -0.0000525, "next_funding": 1763385600},
    ]


def test_bulk_endpoints_raise_on_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "1"})

    api = make(handler, max_retries=0)
    with pytest.raises(RateLimited):
        api.tickers_24h()
    with pytest.raises(RateLimited):
        api.premium_index()
