"""Danh mục hợp đồng perp USDT đang giao dịch trên Binance và OKX, để tìm một coin bất kỳ.

Instrument trong cấu hình (watchlist) luôn đứng trước và giữ nguyên tên. Coin khác được suy ra
từ danh mục: id chuẩn "{BASE}-USDT-PERP", tên trên Binance "{BASE}USDT", trên OKX
"{BASE}-USDT-SWAP". Binance gộp một số coin giá nhỏ thành "1000PEPE"...; khi đó base khác OKX
("PEPE") và hai bên là hai mục riêng. Danh mục được cache trong bộ nhớ một giờ.
"""

import re
import threading
import time
from collections.abc import Callable

from rinng.config import Instrument, Settings

TTL = 3600.0
_MULTIPLIER = re.compile(r"^(1000000|100000|10000|1000|1M)(?=[A-Z])")


def icon_symbol(base: str) -> str:
    """Mã dùng để tìm icon: bỏ hệ số nhân của Binance (1000PEPE → PEPE)."""
    return _MULTIPLIER.sub("", base)


def fetch_binance() -> dict[str, str]:
    """base → symbol trên Binance USDⓈ-M (perp USDT đang giao dịch)."""
    from rinng.exchanges.binance import Binance

    api = Binance()
    info = api._get("/fapi/v1/exchangeInfo", {}, api._weight)
    return {
        s["baseAsset"]: s["symbol"]
        for s in info.get("symbols", [])
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
    }


def fetch_okx() -> dict[str, str]:
    """base → instId trên OKX (swap USDT đang giao dịch). Một request công khai, gọi thẳng."""
    import certifi
    import httpx

    # IPv4: đường IPv6 tới www.okx.com có thể treo hàng chục giây trước khi rơi về IPv4.
    transport = httpx.HTTPTransport(local_address="0.0.0.0", verify=certifi.where())
    with httpx.Client(transport=transport, timeout=15) as client:
        r = client.get("https://www.okx.com/api/v5/public/instruments", params={"instType": "SWAP"})
    r.raise_for_status()
    out = {}
    for row in r.json().get("data", []):
        inst = row.get("instId", "")
        live = row.get("settleCcy") == "USDT" and row.get("state") == "live"
        if live and inst.endswith("-USDT-SWAP"):
            out[inst.split("-")[0]] = inst
    return out


class Catalog:
    def __init__(
        self,
        settings: Settings,
        fetchers: dict[str, Callable[[], dict[str, str]]] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.settings = settings
        self.fetchers = fetchers or {"binance": fetch_binance, "okx": fetch_okx}
        self._clock = clock
        self._lock = threading.Lock()
        self._at = -TTL
        self._items: dict[str, Instrument] = {}

    def _listed(self) -> dict[str, Instrument]:
        with self._lock:
            if self._clock() - self._at < TTL and self._items:
                return self._items
            venues: dict[str, dict[str, str]] = {}
            for ex, fetch in self.fetchers.items():
                try:
                    venues[ex] = fetch()
                except Exception:  # một sàn lỗi vẫn tìm được trên sàn kia
                    venues[ex] = {}
            items: dict[str, Instrument] = {}
            for base in sorted(set().union(*venues.values())):
                inst = Instrument(
                    id=f"{base}-USDT-PERP",
                    kind="perp",
                    base=base,
                    quote="USDT",
                    binance=venues.get("binance", {}).get(base),
                    okx=venues.get("okx", {}).get(base),
                )
                items[inst.id] = inst
            if items:
                self._items, self._at = items, self._clock()
            return self._items

    def configured(self) -> list[Instrument]:
        return list(self.settings.instruments)

    def is_configured(self, symbol: str) -> bool:
        return any(i.id == symbol for i in self.settings.instruments)

    def resolve(self, symbol: str) -> Instrument:
        """Instrument theo id chuẩn: cấu hình trước, rồi danh mục sàn. Không có thì KeyError."""
        for inst in self.settings.instruments:
            if inst.id == symbol:
                return inst
        inst = self._listed().get(symbol)
        if inst is None:
            raise KeyError(symbol)
        return inst

    def search(self, query: str, limit: int = 30) -> list[Instrument]:
        """Khớp base hoặc tên: trùng hẳn trước, rồi bắt đầu bằng, rồi chứa."""
        q = query.strip().upper().replace("/", "").removesuffix("USDT").removesuffix("-")
        pool: dict[str, Instrument] = {i.id: i for i in self._listed().values()}
        pool.update({i.id: i for i in self.settings.instruments})
        if not q:
            return self.configured()[:limit]

        def rank(i: Instrument) -> tuple[int, int, str]:
            base, name = (i.base or "").upper(), (i.name or "").upper()
            plain = icon_symbol(base)
            if q in (base, plain):
                tier = 0
            elif base.startswith(q) or plain.startswith(q) or name.startswith(q):
                tier = 1
            else:
                tier = 2
            return (tier, 0 if self.is_configured(i.id) else 1, base)

        hits = [
            i for i in pool.values() if q in (i.base or "").upper() or q in (i.name or "").upper()
        ]
        return sorted(hits, key=rank)[:limit]
