"""Mô hình chi phí: phí sàn, slippage, funding của perpetual.

- Phí tính trên notional của từng lần khớp: `qty × giá khớp × fee`.
- Slippage luôn bất lợi: mua khớp ở `giá × (1 + bps/10_000)`, bán ở `giá × (1 − bps/10_000)`.
- Mặc định mọi lệnh (vào, thoát theo tín hiệu, stop, take-profit) là market: phí taker, có
  slippage. `take_profit_limit=True` coi take-profit là lệnh limit treo sẵn: phí maker, không
  slippage, khớp ở mức TP (hoặc giá mở nếu gap qua, giá đó tốt hơn mức TP).
- Funding: vị thế đang mở tại `funding_time` trả/nhận `notional × rate`, notional = qty × giá
  (mark price nếu bảng funding có, không thì giá mở của nến chứa funding_time).
  rate > 0: long trả, short nhận; rate < 0 thì ngược lại.
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CostModel:
    taker_fee: float = 0.0005
    maker_fee: float = 0.0002
    slippage_bps: float = 1.0
    take_profit_limit: bool = False

    def __post_init__(self) -> None:
        if min(self.taker_fee, self.maker_fee, self.slippage_bps) < 0:
            raise ValueError("phí và slippage không được âm")

    @property
    def slippage(self) -> float:
        return self.slippage_bps / 10_000

    def fill_price(self, price: float, buy: bool) -> float:
        """Giá khớp market sau slippage bất lợi."""
        return price * (1 + self.slippage) if buy else price * (1 - self.slippage)

    def fee(self, qty: float, price: float, maker: bool = False) -> float:
        return abs(qty) * price * (self.maker_fee if maker else self.taker_fee)

    @staticmethod
    def funding_flow(direction: int, qty: float, price: float, rate: float) -> float:
        """Dòng tiền funding cho tài khoản (âm = trả). direction: +1 long, −1 short."""
        return -direction * abs(qty) * price * rate

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
