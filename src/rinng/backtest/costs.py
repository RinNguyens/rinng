"""Cost model: exchange fees, slippage, perpetual funding.

- Fees are charged on the notional of each fill: `qty × fill price × fee`.
- Slippage is always adverse: buys fill at `price × (1 + bps/10_000)`, sells at `price × (1 −
  bps/10_000)`.
- By default every order (entry, signal exit, stop, take-profit) is a market order: taker fee,
  slippage. `take_profit_limit=True` treats take-profit as a resting limit order: maker fee, no
  slippage, fills at the TP level (or at the open if it gaps through, which beats the TP level).
- Funding: a position open at `funding_time` pays/receives `notional × rate`, notional = qty × price
  (mark price if the funding table has it, otherwise the open of the candle containing
  funding_time).
  rate > 0: longs pay, shorts receive; rate < 0 the reverse.
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
            raise ValueError("fees and slippage must not be negative")

    @property
    def slippage(self) -> float:
        return self.slippage_bps / 10_000

    def fill_price(self, price: float, buy: bool) -> float:
        """Market fill price after adverse slippage."""
        return price * (1 + self.slippage) if buy else price * (1 - self.slippage)

    def fee(self, qty: float, price: float, maker: bool = False) -> float:
        return abs(qty) * price * (self.maker_fee if maker else self.taker_fee)

    @staticmethod
    def funding_flow(direction: int, qty: float, price: float, rate: float) -> float:
        """Funding cash flow to the account (negative = paid). direction: +1 long, −1 short."""
        return -direction * abs(qty) * price * rate

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
