from datetime import UTC, datetime, timedelta

import httpx
import pytest

from rinng.exchanges.okx import CANDLES, Okx, okx_bar
from rinng.exchanges.ratelimit import ExchangeError, RateLimited

H = 3_600_000
T0 = datetime(2026, 11, 1, tzinfo=UTC)
T0_MS = int(T0.timestamp() * 1000)


def candle(ts: int, confirm: str = "1") -> list[str]:
    # [ts, o, h, l, c, vol (contracts), volCcy (base), volCcyQuote, confirm]
    return [str(ts), "100", "110", "90", "105", "1250", "12.5", "1300", confirm]


class FakeOkx:
    """Return 1h candles newest first, honouring `after` and `limit` like the real exchange."""

    def __init__(self, total_bars: int) -> None:
        self.total = total_bars
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        q = request.url.params
        after, limit = int(q["after"]), int(q["limit"])
        bars = [T0_MS + i * H for i in range(self.total)]
        selected = [b for b in reversed(bars) if b < after][:limit]
        return httpx.Response(200, json={"code": "0", "data": [candle(b) for b in selected]})


def make(handler, **kwargs) -> Okx:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://okx.test")
    kwargs.setdefault("sleep", lambda s: None)
    return Okx(client, **kwargs)


def collect(pages) -> list[dict]:
    return [row for page in pages for row in page]


def test_klines_paginates_backwards_without_gaps_or_duplicates():
    fake = FakeOkx(total_bars=1000)
    api = make(fake)
    pages = list(
        api.klines("BTC-USDT-SWAP", "1h", T0 + timedelta(hours=100), T0 + timedelta(hours=800))
    )
    for page in pages:
        times = [r["open_time"] for r in page]
        assert times == sorted(times)  # within a page: ascending
    all_times = sorted(r["open_time"] for page in pages for r in page)
    assert all_times == [T0_MS + i * H for i in range(100, 800)]
    assert len(fake.requests) == 3  # 300 + 300 + 100 (last page reaches the start)


def test_klines_stops_when_history_runs_out():
    fake = FakeOkx(total_bars=50)
    rows = collect(
        make(fake).klines("BTC-USDT-SWAP", "1h", T0 - timedelta(days=30), T0 + timedelta(days=30))
    )
    assert len(rows) == 50
    assert len(fake.requests) == 1


def test_kline_uses_base_volume_not_contracts():
    row = collect(make(FakeOkx(1)).klines("BTC-USDT-SWAP", "1h", T0, T0 + timedelta(hours=1)))[0]
    assert row == {
        "open_time": T0_MS,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 12.5,
        "quote_volume": 1300.0,
        "trades": None,
        "taker_buy_volume": None,
        "is_closed": True,
    }


def test_unconfirmed_candle_is_flagged():
    handler = lambda r: httpx.Response(200, json={"code": "0", "data": [candle(T0_MS, "0")]})  # noqa: E731
    row = collect(make(handler).klines("BTC-USDT-SWAP", "1h", T0, T0 + timedelta(hours=1)))[0]
    assert row["is_closed"] is False


def test_daily_and_weekly_use_utc_bars():
    assert okx_bar("1d") == "1Dutc"
    assert okx_bar("1w") == "1Wutc"
    assert okx_bar("1h") == "1H"
    with pytest.raises(ValueError):
        okx_bar("7m")


def test_daily_request_sends_utc_bar():
    fake = FakeOkx(0)
    collect(make(fake).klines("BTC-USDT-SWAP", "1d", T0, T0 + timedelta(days=2)))
    assert fake.requests[0].url.params["bar"] == "1Dutc"
    assert fake.requests[0].url.path == CANDLES


def test_rate_limit_code_with_http_200_retries():
    calls, slept = [], []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, json={"code": "50011", "msg": "Too Many Requests", "data": []}
            )
        return httpx.Response(200, json={"code": "0", "data": [candle(T0_MS)]})

    rows = collect(
        make(handler, sleep=slept.append).klines("BTC-USDT-SWAP", "1h", T0, T0 + timedelta(hours=1))
    )
    assert len(rows) == 1
    assert slept == [2.0]


def test_rate_limit_gives_up_after_max_retries():
    handler = lambda r: httpx.Response(200, json={"code": "50011", "data": []})  # noqa: E731
    with pytest.raises(RateLimited):
        collect(
            make(handler, max_retries=1).klines("BTC-USDT-SWAP", "1h", T0, T0 + timedelta(hours=1))
        )


def test_error_code_with_http_200_raises():
    handler = lambda r: httpx.Response(
        200, json={"code": "51001", "msg": "no instrument", "data": []}
    )  # noqa: E731
    with pytest.raises(ExchangeError) as info:
        collect(make(handler).klines("NOPE", "1h", T0, T0 + timedelta(hours=1)))
    assert info.value.code == "51001"


def test_funding_rows():
    def handler(request):
        data = [
            {"fundingTime": str(T0_MS + 8 * H), "fundingRate": "0.0003", "realizedRate": "0.0002"},
            {"fundingTime": str(T0_MS), "fundingRate": "-0.0001", "realizedRate": ""},
        ]
        return httpx.Response(200, json={"code": "0", "data": data})

    rows = collect(make(handler).funding("BTC-USDT-SWAP", T0, T0 + timedelta(days=1)))
    assert rows == [
        {"funding_time": T0_MS, "rate": -0.0001, "mark_price": None},
        {"funding_time": T0_MS + 8 * H, "rate": 0.0002, "mark_price": None},
    ]


def test_stats_rows_and_column_order():
    bodies = {
        "/api/v5/rubik/stat/contracts/open-interest-history": [
            [str(T0_MS), "3400000", "34000", "2300000000"]
        ],
        "/api/v5/rubik/stat/contracts/long-short-account-ratio-contract": [[str(T0_MS), "2.5"]],
        "/api/v5/rubik/stat/taker-volume-contract": [[str(T0_MS), "20", "10"]],  # [ts, sell, buy]
    }
    api = make(lambda r: httpx.Response(200, json={"code": "0", "data": bodies[r.url.path]}))
    end = T0 + timedelta(hours=1)
    assert collect(api.open_interest("BTC-USDT-SWAP", "5m", T0, end)) == [
        {"time": T0_MS, "oi_base": 34000.0, "oi_value": 2300000000.0}
    ]
    assert collect(api.long_short("BTC-USDT-SWAP", "5m", T0, end)) == [
        {"time": T0_MS, "ratio": 2.5, "long_pct": None, "short_pct": None}
    ]
    assert collect(api.taker_volume("BTC-USDT-SWAP", "5m", T0, end)) == [
        {"time": T0_MS, "buy_volume": 10.0, "sell_volume": 20.0}
    ]


def test_stats_paginate_backwards_with_end_cursor():
    step = 300_000
    points = [T0_MS + i * step for i in range(250)]
    requests = []

    def handler(request):
        requests.append(request)
        q = request.url.params
        begin, end, limit = int(q["begin"]), int(q["end"]), int(q["limit"])
        selected = [p for p in reversed(points) if begin <= p <= end][:limit]
        return httpx.Response(200, json={"code": "0", "data": [[str(p), "2.0"] for p in selected]})

    pages = make(handler).long_short("BTC-USDT-SWAP", "5m", T0, T0 + timedelta(minutes=5 * 250))
    times = sorted(r["time"] for page in pages for r in page)
    assert times == points
    assert len(requests) == 3


def test_transient_network_error_is_retried():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"code": "0", "data": [candle(T0_MS)]})

    rows = collect(make(handler).klines("BTC-USDT-SWAP", "1h", T0, T0 + timedelta(hours=1)))
    assert len(rows) == 1
