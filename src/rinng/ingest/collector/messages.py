"""Đổi message WebSocket của từng sàn thành dòng theo schema curated. Hàm thuần, không I/O.

Mỗi hàm trả về list các `Record(table, symbol, row)`; `symbol` là tên chuẩn của dự án.
Định dạng message đã đối chiếu với dữ liệu thật ngày 2026-11-13.
"""

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Record:
    table: str
    symbol: str
    row: dict[str, Any]
    timeframe: str | None = None  # chỉ bảng nến cần


# --- Binance USDⓈ-M, URL dạng /market/stream?streams=... ---


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
    """`symbols`: tên trên sàn (BTCUSDT) → tên chuẩn (BTC-USDT-PERP)."""
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
            "side": order["S"].lower(),  # bên của lệnh thanh lý: sell = vị thế long bị thanh lý
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
            "is_closed": bool(k["x"]),  # nến đang chạy cũng được gửi, x=true khi đã đóng
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
    """Kênh nến nằm ở endpoint /ws/v5/business, không phải /public."""
    args = [{"channel": "candle1m", "instId": s} for s in venue_symbols]
    return json.dumps({"op": "subscribe", "args": args})


@dataclass(frozen=True)
class OkxControl:
    """Message điều khiển của OKX: lỗi, thông báo sắp ngắt kết nối (64008)..."""

    event: str
    code: str | None
    message: str


def parse_okx(
    raw: str, symbols: dict[str, str], contract_values: dict[str, float]
) -> list[Record] | OkxControl | None:
    """Trả list Record cho message dữ liệu, OkxControl cho message điều khiển, None cho pong.

    `contract_values`: tên trên sàn → số đồng base mỗi hợp đồng. Thiếu thì bỏ dòng,
    vì không đổi được khối lượng.
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
                        # x[5] là số hợp đồng; x[6] là khối lượng tính bằng đồng base.
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
                # side là bên taker; taker bán nghĩa là bên mua là maker.
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
