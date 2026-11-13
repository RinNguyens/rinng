import httpx

from rinng.exchanges.check import check_binance, check_okx


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_binance_reads_rate_limits():
    def handler(request):
        body = {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": 2400,
                }
            ]
        }
        return httpx.Response(200, json=body, headers={"x-mbx-used-weight-1m": "3"})

    result = check_binance(_client(handler), "b", "https://example.test/x")
    assert result.ok
    assert result.rate_limits == ["REQUEST_WEIGHT: 2400 / 1 MINUTE"]
    assert "3" in result.detail


def test_binance_blocked_status_is_failure():
    result = check_binance(
        _client(lambda r: httpx.Response(451, text="restricted location")), "b", "https://e.test"
    )
    assert not result.ok
    assert result.status == 451
    assert "restricted" in result.detail


def test_okx_error_code_with_http_200_is_failure():
    result = check_okx(
        _client(lambda r: httpx.Response(200, json={"code": "50011", "data": []})),
        "o",
        "https://e.test",
    )
    assert not result.ok
    assert "50011" in result.detail


def test_network_error_is_reported():
    def handler(request):
        raise httpx.ConnectError("no route")

    result = check_okx(_client(handler), "o", "https://e.test")
    assert not result.ok
    assert result.status is None
    assert "ConnectError" in result.detail
