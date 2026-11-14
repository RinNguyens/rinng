"""Chạy các module phân tích trên dữ liệu curated và ghi vào features/ hoặc events/.

Mỗi module trong `MODULES` nhận một `Inputs` (nến của một symbol, một khung, cùng dữ liệu
phái sinh nếu cần) và trả về (features | None, events | None). Đầu ra là dữ liệu dẫn xuất,
tính lại được bất cứ lúc nào, nên được ghi đè cả file:
data/{features|events}/{module}/v{VERSION}/symbol=…/timeframe=…/data.parquet

Đổi định nghĩa của một module thì tăng VERSION của nó, để kết quả cũ không bị trộn.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import polars as pl

from rinng.analysis import (
    derivatives,
    elliott,
    indicators,
    liquidity,
    orderflow,
    smc,
    structure,
    volume_profile,
    wyckoff,
)
from rinng.analysis.types import empty_events
from rinng.store import catalog
from rinng.store.paths import DataPaths
from rinng.store.reader import read_curated
from rinng.store.schemas import FUNDING, LONG_SHORT, MARK_PRICE, OHLCV, OPEN_INTEREST, table
from rinng.store.writer import PART_FILE, _commit, _tmp_path

Result = tuple[pl.DataFrame | None, pl.DataFrame | None]


@dataclass
class Inputs:
    paths: DataPaths
    exchange: str
    symbol: str
    timeframe: str
    ohlcv: pl.DataFrame
    start: datetime | None = None
    end: datetime | None = None

    def table(self, name: str, **filters) -> pl.DataFrame:
        frame = read_curated(
            self.paths, table(name), exchange=self.exchange, symbol=self.symbol, end=self.end
        )
        for col, value in filters.items():
            frame = frame.filter(pl.col(col) == value)
        return frame

    def gaps(self) -> pl.DataFrame:
        g = catalog.read_meta(self.paths, "gaps")
        return g.filter((pl.col("exchange") == self.exchange) & (pl.col("symbol") == self.symbol))


def _concat(*frames: pl.DataFrame) -> pl.DataFrame:
    parts = [f for f in frames if f is not None and not f.is_empty()]
    return pl.concat(parts).sort(["event_time", "kind", "event_id"]) if parts else empty_events()


def _join_features(*frames: pl.DataFrame) -> pl.DataFrame:
    keys = ["symbol", "timeframe", "open_time", "known_at"]
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f.drop("params_hash"), on=keys, how="left")
    return out


def _derivatives(i: Inputs) -> Result:
    o, gaps = i.ohlcv, i.gaps()
    parts = []
    funding = i.table(FUNDING.name)
    if not funding.is_empty():
        parts.append(derivatives.funding_features(o, funding, gaps=gaps))
    oi = i.table(OPEN_INTEREST.name)
    if not oi.is_empty():
        source = "api" if oi.filter(pl.col("source") == "api").height else None
        parts.append(derivatives.open_interest_features(o, oi, source=source, gaps=gaps))
    ls = i.table(LONG_SHORT.name, kind="global_account")
    if not ls.is_empty():
        parts.append(derivatives.long_short_features(o, ls, gaps=gaps))
    mark = i.table(MARK_PRICE.name)
    if not mark.is_empty() and mark["index_price"].null_count() < mark.height:
        parts.append(derivatives.basis_features(o, mark, gaps=gaps))
    liq = i.table("liquidations")
    events = None
    if not liq.is_empty():
        parts.append(derivatives.liquidation_features(o, liq, gaps=gaps))
        events = derivatives.liquidation_clusters(o, liq, gaps=gaps)
    return (_join_features(*parts) if parts else None), events


MODULES: dict[str, tuple[int, Callable[[Inputs], Result]]] = {
    "indicators": (1, lambda i: (indicators.compute(i.ohlcv), None)),
    "structure": (1, lambda i: (None, structure.swings(i.ohlcv, 5))),
    "smc": (1, lambda i: (smc.premium_discount(i.ohlcv), smc.events(i.ohlcv))),
    "liquidity": (
        1,
        lambda i: (
            None,
            _concat(
                liquidity.liquidity_levels(i.ohlcv),
                liquidity.equal_levels(i.ohlcv),
                liquidity.sweeps(i.ohlcv),
            ),
        ),
    ),
    "volume_profile": (
        1,
        lambda i: (None, volume_profile.profile_events(i.ohlcv, "week", n_bins=100)),
    ),
    "orderflow": (
        1,
        lambda i: (
            orderflow.delta_features(i.ohlcv, cvd_reset="week"),
            orderflow.absorption(i.ohlcv),
        ),
    ),
    "wyckoff": (
        1,
        lambda i: (
            wyckoff.effort_result(i.ohlcv),
            _concat(wyckoff.climaxes(i.ohlcv), wyckoff.trading_ranges(i.ohlcv)),
        ),
    ),
    "elliott": (
        1,
        lambda i: (
            None,
            _concat(elliott.zigzag(i.ohlcv), elliott.impulse_candidates(i.ohlcv)),
        ),
    ),
    "derivatives": (1, _derivatives),
}


def _write(paths: DataPaths, zone: str, module: str, version: int, frame: pl.DataFrame) -> None:
    symbol, tf = frame["symbol"][0], frame["timeframe"][0]
    target = paths.derived(zone, module, version, symbol, tf) / PART_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(target)
    frame.write_parquet(tmp)
    _commit(tmp, target, overwrite=True)


def load_ohlcv(
    paths: DataPaths,
    exchange: str,
    symbol: str,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pl.DataFrame:
    """Nến đã đóng, đúng định dạng đầu vào của lớp phân tích."""
    o = read_curated(
        paths, OHLCV, exchange=exchange, symbol=symbol, timeframe=timeframe, start=start, end=end
    )
    return o.filter(pl.col("is_closed")).sort("open_time")


def analyze(
    paths: DataPaths,
    exchange: str,
    symbol: str,
    timeframe: str,
    modules: list[str] | None = None,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    write: bool = True,
) -> dict[str, Result]:
    ohlcv = load_ohlcv(paths, exchange, symbol, timeframe, start, end)
    if ohlcv.is_empty():
        raise ValueError(f"không có nến {exchange} {symbol} {timeframe}")
    inputs = Inputs(paths, exchange, symbol, timeframe, ohlcv, start, end)
    out: dict[str, Result] = {}
    for name in modules or list(MODULES):
        version, fn = MODULES[name]
        features, events = fn(inputs)
        out[name] = (features, events)
        if write:
            if features is not None and not features.is_empty():
                _write(paths, "features", name, version, features)
            if events is not None and not events.is_empty():
                _write(paths, "events", name, version, events)
    return out


def read_derived(
    paths: DataPaths, zone: str, module: str, symbol: str, timeframe: str
) -> pl.DataFrame | None:
    version = MODULES[module][0]
    target = paths.derived(zone, module, version, symbol, timeframe) / PART_FILE
    return pl.read_parquet(target) if target.exists() else None
