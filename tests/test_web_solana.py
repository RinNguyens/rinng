from fastapi.testclient import TestClient

from rinng.config import load_settings
from rinng.web import solana
from rinng.web.app import create_app


def _client(tmp_path):
    settings = load_settings().model_copy(update={"data_dir": tmp_path})
    return TestClient(create_app(settings))


def test_relays_only_read_methods(tmp_path, monkeypatch):
    seen = []

    async def fake_relay(body):
        seen.append(body["method"])
        return 200, {"jsonrpc": "2.0", "id": 1, "result": {"value": None}}

    monkeypatch.setattr(solana, "relay", fake_relay)
    client = _client(tmp_path)
    ok = client.post("/api/solana", json={"method": "getAccountInfo", "params": ["x"]})
    assert ok.status_code == 200 and ok.json()["result"] == {"value": None}
    for method in ("sendTransaction", "simulateTransaction", "requestAirdrop", None):
        r = client.post("/api/solana", json={"method": method, "params": []})
        assert r.status_code == 400, method
    assert client.post("/api/solana", json=[{"method": "getAccountInfo"}]).status_code == 400
    assert seen == ["getAccountInfo"]


def test_upstream_override(monkeypatch):
    monkeypatch.delenv("RINNG_SOLANA_RPC", raising=False)
    assert solana.upstream() == solana.PUBLIC_RPC
    monkeypatch.setenv("RINNG_SOLANA_RPC", "https://rpc.example")
    assert solana.upstream() == "https://rpc.example"


def test_relay_caps_huge_responses(monkeypatch):
    import asyncio

    import httpx

    def handler(request):
        return httpx.Response(200, content=b"x" * (solana.MAX_BYTES + 10))

    real = httpx.AsyncClient
    monkeypatch.setattr(
        solana.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), timeout=kw.get("timeout")),
    )
    status, body = asyncio.run(solana.relay({"method": "getTokenAccountsByOwner", "params": []}))
    assert status == 502
    assert "too many token accounts" in body["error"]["message"]
