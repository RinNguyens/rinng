"""Check connectivity to both exchanges' public APIs and read the rate limits in effect.

No API key needed. Use it to test a machine (especially a VPS) before running the collector there.
"""

import time
from dataclasses import dataclass, field

import httpx

BINANCE_TARGETS = {
    "binance-spot": "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT",
    "binance-usdm": "https://fapi.binance.com/fapi/v1/exchangeInfo",
}
OKX_TARGETS = {
    "okx": "https://openapi.okx.com/api/v5/public/time",
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    status: int | None = None
    latency_ms: float | None = None
    detail: str = ""
    rate_limits: list[str] = field(default_factory=list)


def _format_limit(limit: dict) -> str:
    return (
        f"{limit.get('rateLimitType')}: {limit.get('limit')} / "
        f"{limit.get('intervalNum')} {limit.get('interval')}"
    )


def _get(client: httpx.Client, name: str, url: str) -> tuple[CheckResult, httpx.Response | None]:
    started = time.perf_counter()
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return CheckResult(name, ok=False, detail=f"{type(exc).__name__}: {exc}"), None
    latency = (time.perf_counter() - started) * 1000
    result = CheckResult(name, ok=response.status_code == 200, status=response.status_code)
    result.latency_ms = round(latency, 1)
    return result, response


def check_binance(client: httpx.Client, name: str, url: str) -> CheckResult:
    result, response = _get(client, name, url)
    if response is None:
        return result
    if not result.ok:
        result.detail = response.text[:200]
        return result
    result.rate_limits = [_format_limit(x) for x in response.json().get("rateLimits", [])]
    used = response.headers.get("x-mbx-used-weight-1m")
    if used is not None:
        result.detail = f"weight used this minute: {used}"
    return result


def check_okx(client: httpx.Client, name: str, url: str) -> CheckResult:
    result, response = _get(client, name, url)
    if response is None:
        return result
    if not result.ok:
        result.detail = response.text[:200]
        return result
    # OKX returns HTTP 200 even on errors; the `code` in the body must be checked.
    code = response.json().get("code")
    if code != "0":
        result.ok = False
        result.detail = f"code={code}"
    return result


def run_checks(timeout: float = 10.0) -> list[CheckResult]:
    with httpx.Client(timeout=timeout) as client:
        results = [check_binance(client, n, u) for n, u in BINANCE_TARGETS.items()]
        results += [check_okx(client, n, u) for n, u in OKX_TARGETS.items()]
    return results
