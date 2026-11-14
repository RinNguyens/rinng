"""Sample SMC strategy: follow structure breaks, stop at the known opposite swing.

It illustrates how to wire Events into a backtest; it is NOT a strategy proven
to have an edge.

- Go long on `choch_bull` or `bos_bull` (per `kinds`), short on the bear variants.
- Signal time = the event's known_at (close of the breaking candle), so the engine fills on the
  next candle.
- Stop: the latest swing low known before the signal (long) / swing high (short).
- Take-profit: estimated entry (close of the breaking candle) ± `rr` × distance to the stop.
- Drop the signal if there is no valid opposite swing.
"""

from dataclasses import dataclass, field

import polars as pl

from rinng.strategy.base import signals_frame


@dataclass
class StructureBreak:
    kinds: tuple[str, ...] = ("choch",)
    rr: float = 2.0
    name: str = "smc_structure_break"
    params: dict = field(init=False)

    def __post_init__(self) -> None:
        self.params = {"kinds": list(self.kinds), "rr": self.rr}

    def signals(
        self, ohlcv: pl.DataFrame, features: pl.DataFrame | None, events: pl.DataFrame
    ) -> pl.DataFrame:
        wanted = [f"{k}_{d}" for k in self.kinds for d in ("bull", "bear")]
        breaks = events.filter(pl.col("kind").is_in(wanted)).sort("known_at")
        swings = events.filter(pl.col("kind").is_in(["swing_high", "swing_low"])).sort("known_at")
        closes = dict(zip(ohlcv["open_time"].to_list(), ohlcv["close"].to_list(), strict=True))
        rows = []
        for b in breaks.iter_rows(named=True):
            long = b["kind"].endswith("bull")
            known = swings.filter(
                (pl.col("known_at") <= b["known_at"])
                & (pl.col("kind") == ("swing_low" if long else "swing_high"))
            )
            if known.is_empty():
                continue
            stop = known["price_low"][-1]
            entry = closes.get(b["event_time"])
            if entry is None or (long and stop >= entry) or (not long and stop <= entry):
                continue
            risk = abs(entry - stop)
            rows.append(
                {
                    "time": b["known_at"],
                    "side": "long" if long else "short",
                    "stop": stop,
                    "take_profit": entry + self.rr * risk if long else entry - self.rr * risk,
                    "size": 1.0,
                    "reason": b["kind"],
                }
            )
        return signals_frame(rows)
