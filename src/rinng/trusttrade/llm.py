"""Claude client for the research runs: structured outputs, a disk cache and usage accounting.

The cache key covers model, effort, system prompt, user prompt, output schema and a sample index,
so (a) re-running an experiment costs nothing, and (b) ablation variants that read the same analyst
reports really read the *same* reports: the comparison isolates the aggregation step, not sampling
noise. Sample index k is what makes the N analysts independent draws of the same prompt.

The key is CLAUDE_API_KEY (environment or .env), the same one MakeMoney uses. The base URL is pinned
to the public API so an ANTHROPIC_BASE_URL set for some other tool does not redirect these calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from rinng.makemoney import env_api_key

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-haiku-5-5"
CACHE_VERSION = 1
# $ per million tokens (input, output), first-party list prices as of 2026-11; estimates only.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return (input_tokens * pin + output_tokens * pout) / 1e6


class LLM:
    def __init__(
        self,
        cache_dir: Path,
        *,
        concurrency: int = 8,
        api_key: str | None = None,
        cache_only: bool = False,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_only = cache_only
        self.sem = asyncio.Semaphore(concurrency)
        key = api_key or env_api_key()
        self.client = None
        if key:
            self.client = anthropic.AsyncAnthropic(api_key=key, base_url=API_URL, max_retries=4)
        self.usage: dict[str, dict] = defaultdict(
            lambda: {
                "calls": 0,
                "cache_hits": 0,
                "errors": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }
        )

    def _key(self, **parts) -> str:
        blob = json.dumps({"v": CACHE_VERSION, **parts}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    async def structured(
        self,
        *,
        role: str,
        model: str,
        system: str,
        prompt: str,
        schema: type[T],
        effort: str = "low",
        sample: int = 0,
        max_tokens: int = 8000,
    ) -> T:
        key = self._key(
            model=model,
            effort=effort,
            system=system,
            prompt=prompt,
            schema=schema.model_json_schema(),
            sample=sample,
        )
        path = self.cache_dir / key[:2] / f"{key}.json"
        u = self.usage[role]
        if path.exists():
            u["cache_hits"] += 1
            return schema.model_validate(json.loads(path.read_text())["output"])
        if self.cache_only:
            raise LLMError(f"{role}: not in cache (cache-only run)")
        if self.client is None:
            raise LLMError("no API key: set CLAUDE_API_KEY in the environment or .env")
        async with self.sem:
            try:
                r = await self.client.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    output_format=schema,
                    output_config={"effort": effort},
                )
            except anthropic.BadRequestError as e:
                u["errors"] += 1
                raise LLMError(f"{role}: bad request: {e.message}") from e
            except anthropic.RateLimitError as e:
                u["errors"] += 1
                raise LLMError(f"{role}: rate limited after retries") from e
            except anthropic.APIStatusError as e:
                u["errors"] += 1
                raise LLMError(f"{role}: API {e.status_code}: {e.message}") from e
            except anthropic.APIConnectionError as e:
                u["errors"] += 1
                raise LLMError(f"{role}: connection error") from e
        u["calls"] += 1
        u["input_tokens"] += r.usage.input_tokens
        u["output_tokens"] += r.usage.output_tokens
        u["cost_usd"] += cost(model, r.usage.input_tokens, r.usage.output_tokens)
        if r.stop_reason == "refusal":
            u["errors"] += 1
            raise LLMError(f"{role}: model declined")
        if r.stop_reason == "max_tokens" or r.parsed_output is None:
            u["errors"] += 1
            raise LLMError(f"{role}: no complete structured output (stop: {r.stop_reason})")
        out = r.parsed_output
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "role": role,
                    "model": model,
                    "effort": effort,
                    "sample": sample,
                    "usage": {"input": r.usage.input_tokens, "output": r.usage.output_tokens},
                    "output": out.model_dump(mode="json"),
                }
            )
        )
        return out

    def usage_summary(self) -> dict:
        total = {
            "calls": 0,
            "cache_hits": 0,
            "errors": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
        }
        for u in self.usage.values():
            for k in total:
                total[k] += u[k]
        total["cost_usd"] = round(total["cost_usd"], 4)
        by_role = {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in self.usage.items()}
        return {"total": total, "by_role": by_role}
