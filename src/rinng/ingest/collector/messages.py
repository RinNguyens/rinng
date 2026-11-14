"""Convert each exchange's WebSocket messages into curated-schema rows. Pure functions, no I/O.

Each function returns a list of `Record(table, symbol, row)`; `symbol` is the canonical name.
Message formats checked against real data on 2026-11-13.
"""

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Record:
    table: str
    symbol: str
    row: dict[str, Any]
    timeframe: str | None = None  # only for candle tables


# --- Binance USDⓈ-M, URLs like /market/stream?streams=... ---


def binance_streams(venue_symbols: list[str]) -> list[str]:
    streams = []
    for s in venue_symbols:
        low = s.lower()
        streams += [
            f"{low}@aggTrade",
            f"{low}@markPrice@1s",
            f"{low}@forceOrder",
            f"{low}@kline_1m",
        ]
    return streams


def parse_binance(raw: str, symbols: dict[str, str]) -> list[Record]:
    """`symbols`: venue name (BTCUSDT) → canonical name (BTC-USDT-PERP)."""
    msg = json.loads(raw)
    data = msg.get("data")
    if not isinstance(data, dict):
        return []
    event = data.get("e")
    if event == "aggTrade":
        sym = symbols.get(data["s"])
        if sym is None:
            return []
        row = {
            "trade_id": int(data["a"]),
            "time": int(data["T"]),
            "price": float(data["p"]),
            "qty": float(data["q"]),
            "is_buyer_maker": bool(data["m"]),
        }
        return [Record("trades", sym, row)]
    if event == "markPriceUpdate":
        sym = symbols.get(data["s"])
        if sym is None:
            return []
        row = {
            "time": int(data["E"]),
            "mark_price": float(data["p"]),
            "index_price": float(data["i"]),
            "funding_rate": float(data["r"]) if data.get("r") not in (None, "") else None,
        }
        return [Record("mark_price", sym, row)]
    if event == "forceOrder":
        order = data["o"]
        sym = symbols.get(order["s"])
        if sym is None:
            return []
        row = {
            "time": int(order["T"]),
            "side": order[
                "S"
            ].lower(),  # side of the liquidation order: sell = a long was liquidated
            "price": float(order["ap"] or order["p"]),
            "qty": float(order["z"] or order["q"]),
        }
        return [Record("liquidations", sym, row)]
    if event == "kline":
        k = data["k"]
        sym = symbols.get(k["s"])
        if sym is None or k.get("i") != "1m":
            return []
        row = {
            "open_time": int(k["t"]),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "quote_volume": float(k["q"]),
            "trades": int(k["n"]),
            "taker_buy_volume": float(k["V"]),
            "is_closed": bool(k["x"]),  # running candles are sent too, x=true once closed
        }
        return [Record("ohlcv", sym, row, "1m")]
    return []


# --- OKX, URL /ws/v5/public ---


def okx_subscribe(venue_symbols: list[str]) -> str:
    args = [{"channel": "liquidation-orders", "instType": "SWAP"}]
    for s in venue_symbols:
        args += [{"channel": "trades", "instId": s}, {"channel": "mark-price", "instId": s}]
    return json.dumps({"op": "subscribe", "args": args})


def okx_candle_subscribe(venue_symbols: list[str]) -> str:
    """Candle channels live on the /ws/v5/business endpoint, not /public."""
    args = [{"channel": "candle1m", "instId": s} for s in venue_symbols]
    return json.dumps({"op": "subscribe", "args": args})


@dataclass(frozen=True)
class OkxControl:
    """OKX control message: error, upcoming disconnect notice (64008)..."""

    event: str
    code: str | None
    message: str


def parse_okx(
    raw: str, symbols: dict[str, str], contract_values: dict[str, float]
) -> list[Record] | OkxControl | None:
    """Return a list of Records for data messages, OkxControl for control messages, None for pong.

    `contract_values`: venue name → base units per contract. Missing ones drop the row,
    since the volume cannot be converted.
    """
    if raw == "pong":
        return None
    msg = json.loads(raw)
    if "event" in msg:
        return OkxControl(msg["event"], msg.get("code"), msg.get("msg", ""))
    channel = msg.get("arg", {}).get("channel")
    records: list[Record] = []
    if channel == "candle1m":
        sym = symbols.get(msg["arg"].get("instId"))
        if sym is None:
            return records
        for x in msg.get("data", []):
            records.append(
                Record(
                    "ohlcv",
                    sym,
                    {
                        "open_time": int(x[0]),
                        "open": float(x[1]),
                        "high": float(x[2]),
                        "low": float(x[3]),
                        "close": float(x[4]),
                        # x[5] is contracts; x[6] is volume in base currency.
                        "volume": float(x[6]),
                        "quote_volume": float(x[7]),
                        "trades": None,
                        "taker_buy_volume": None,
                        "is_closed": x[8] == "1",
                    },
                    "1m",
                )
            )
        return records
    for item in msg.get("data", []):
        inst = item.get("instId")
        sym = symbols.get(inst)
        if sym is None:
            continue
        if channel == "trades":
            ct = contract_values.get(inst)
            if ct is None:
                continue
            row = {
                "trade_id": int(item["tradeId"]),
                "time": int(item["ts"]),
                "price": float(item["px"]),
                "qty": float(item["sz"]) * ct,
                # side is the taker side; taker sell means the buyer is the maker.
                "is_buyer_maker": item["side"] == "sell",
            }
            records.append(Record("trades", sym, row))
        elif channel == "mark-price":
            row = {
                "time": int(item["ts"]),
                "mark_price": float(item["markPx"]),
                "index_price": None,
                "funding_rate": None,
            }
            records.append(Record("mark_price", sym, row))
        elif channel == "liquidation-orders":
            ct = contract_values.get(inst)
            if ct is None:
                continue
            for d in item.get("details", []):
                row = {
                    "time": int(d["ts"]),
                    "side": d["side"],
                    "price": float(d["bkPx"]),
                    "qty": float(d["sz"]) * ct,
                }
                records.append(Record("liquidations", sym, row))
    return records
