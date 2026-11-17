"""Read-only relay to a Solana RPC for the wallet check (web/src/lib/multichain.ts).

Solana's public RPC refuses requests that carry a browser Origin, so the page cannot read it
directly. This relay forwards one JSON-RPC call at a time, and only the four read methods the
wallet check uses: nothing that sends, simulates or signs can pass. Set RINNG_SOLANA_RPC to use
your own RPC (Helius, Triton...) instead of the rate-limited public one.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
# A wallet's reads fit in a few MB; exchange hot wallets return hundreds of MB of token accounts.
MAX_BYTES = 16 * 1024 * 1024
ALLOWED = frozenset(
    {"getAccountInfo", "getTokenAccountsByOwner", "getSignaturesForAddress", "getTransaction"}
)


def upstream() -> str:
    return os.environ.get("RINNG_SOLANA_RPC") or PUBLIC_RPC


def check(body: Any) -> str | None:
    """Why `body` may not be relayed, or None when it may."""
    if not isinstance(body, dict):
        return "one JSON-RPC request object (no batches)"
    if body.get("method") not in ALLOWED:
        return f"method not allowed: {body.get('method')!r}"
    if not isinstance(body.get("params", []), list):
        return "params must be a list"
    return None


async def relay(body: dict) -> tuple[int, Any]:
    call = {"jsonrpc": "2.0", "id": body.get("id", 1), "method": body["method"]}
    call["params"] = body.get("params", [])
    # IPv4: the IPv6 route from this machine can hang (same as the OKX client).
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
    async with (
        httpx.AsyncClient(transport=transport, timeout=20) as client,
        client.stream("POST", upstream(), json=call) as r,
    ):
        body_bytes = bytearray()
        async for chunk in r.aiter_bytes():
            body_bytes += chunk
            if len(body_bytes) > MAX_BYTES:
                return 502, _error(
                    call["id"],
                    "this address holds too many token accounts for a public RPC "
                    "(an exchange or program wallet?); set RINNG_SOLANA_RPC to your own RPC",
                )
    try:
        return r.status_code, json.loads(body_bytes)
    except ValueError:
        return 502, _error(call["id"], body_bytes[:200].decode(errors="replace"))


def _error(id_: Any, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"message": message}}
