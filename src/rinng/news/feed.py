"""Fetch news from free sources and keep the latest items in memory.

Sources: OKX and Binance announcements (listings/delistings; the origin for exchange news),
and RSS from Cointelegraph, The Block and Decrypt (general market news, lags by tens of
seconds to minutes). Refreshed on demand at most every `ttl` seconds, shared by all clients.
"""

import asyncio
import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from rinng.news.score import score_headline

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (rinng news reader)"}

RSS = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "The Block": "https://www.theblock.co/rss.xml",
    "Decrypt": "https://decrypt.co/feed",
}
OKX_URL = "https://www.okx.com/api/v5/support/announcements"
BINANCE_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
BINANCE_CATALOGS = {48: "listing", 161: "delisting"}


def _item(source: str, kind: str, title: str, url: str, ts_ms: int) -> dict:
    s = score_headline(title, kind)
    return {
        "id": hashlib.sha1(f"{source}|{title}".encode()).hexdigest()[:16],
        "source": source,
        "kind": kind,
        "title": title.strip(),
        "url": url,
        "time": ts_ms,
        "score": round(s.score, 3),
        "sentiment": s.sentiment,
        "impact": s.impact,
        "tags": s.tags,
        "coins": s.coins,
    }


def parse_rss(source: str, xml_text: str) -> list[dict]:
    out = []
    for node in ET.fromstring(xml_text).iter("item"):
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        try:
            ts = int(parsedate_to_datetime(node.findtext("pubDate") or "").timestamp() * 1000)
        except (TypeError, ValueError):
            ts = int(time.time() * 1000)
        out.append(_item(source, "media", title, (node.findtext("link") or "").strip(), ts))
    return out


def parse_okx(payload: dict) -> list[dict]:
    out = []
    for page in payload.get("data") or []:
        for d in page.get("details") or []:
            out.append(_item("OKX", "exchange", d["title"], d.get("url", ""), int(d["pTime"])))
    return out


def parse_binance(payload: dict) -> list[dict]:
    out = []
    for cat in (payload.get("data") or {}).get("catalogs") or []:
        for a in cat.get("articles") or []:
            url = f"https://www.binance.com/en/support/announcement/{a['code']}"
            out.append(_item("Binance", "exchange", a["title"], url, int(a["releaseDate"])))
    return out


class NewsFeed:
    def __init__(self, ttl: float = 20.0, keep: int = 300):
        self.ttl, self.keep = ttl, keep
        self.items: dict[str, dict] = {}
        self.updated = 0.0
        self._lock = asyncio.Lock()

    async def _fetch(self, client: httpx.AsyncClient) -> list[dict]:
        async def rss(name: str, url: str):
            r = await client.get(url)
            r.raise_for_status()
            return parse_rss(name, r.text)

        async def okx():
            r = await client.get(OKX_URL)
            r.raise_for_status()
            return parse_okx(r.json())

        async def binance(cat: int):
            params = {"type": 1, "catalogId": cat, "pageNo": 1, "pageSize": 15}
            r = await client.get(BINANCE_URL, params=params)
            r.raise_for_status()
            return parse_binance(r.json())

        jobs = [rss(n, u) for n, u in RSS.items()] + [okx()]
        jobs += [binance(c) for c in BINANCE_CATALOGS]
        out: list[dict] = []
        for res in await asyncio.gather(*jobs, return_exceptions=True):
            if isinstance(res, BaseException):
                log.warning("news source failed: %r", res)
            else:
                out.extend(res)
        return out

    async def refresh(self, force: bool = False) -> None:
        async with self._lock:
            if not force and time.time() - self.updated < self.ttl:
                return
            async with httpx.AsyncClient(timeout=8, headers=UA, follow_redirects=True) as c:
                fresh = await self._fetch(c)
            for it in fresh:
                self.items.setdefault(it["id"], it)
            if len(self.items) > self.keep:
                newest = sorted(self.items.values(), key=lambda x: x["time"])[-self.keep :]
                self.items = {it["id"]: it for it in newest}
            self.updated = time.time()

    def latest(self, limit: int = 60) -> list[dict]:
        return sorted(self.items.values(), key=lambda x: x["time"], reverse=True)[:limit]
