"""Kiểm chất lượng dữ liệu nến đã curated.

- Nến 1 phút: số nến thiếu và các khoảng thiếu, nến trùng, OHLC vô lý, volume âm.
- Khung lớn: so nến tự gộp với nến sàn trả về (cần mạng, `compare_with_exchange`).
- Hai sàn: độ lệch giá đóng giữa Binance và OKX ở cùng mốc.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import polars as pl

from rinng.exchanges.base import Exchange
from rinng.store.schemas import OHLCV, rows_to_frame


@dataclass
class CandleReport:
    rows: int
    first: datetime | None
    last: datetime | None
    missing: int
    duplicates: int
    invalid_ohlc: int
    negative_volume: int
    gaps: list[tuple[datetime, datetime]] = field(default_factory=list)  # [start, end)

    @property
    def ok(self) -> bool:
        return self.duplicates == 0 and self.invalid_ohlc == 0 and self.negative_volume == 0


def check_candles(ohlcv: pl.DataFrame, step: timedelta = timedelta(minutes=1)) -> CandleReport:
    if ohlcv.is_empty():
        return CandleReport(0, None, None, 0, 0, 0, 0)
    times = ohlcv["open_time"].sort()
    dup = len(times) - times.n_unique()
    uniq = times.unique().sort()
    diffs = uniq.diff().slice(1)
    gap_idx = (diffs > step).arg_true()
    gaps = [(uniq[i] + step, uniq[i + 1]) for i in gap_idx.to_list()]
    missing = sum(int((b - a) / step) for a, b in gaps)
    invalid = ohlcv.filter(
        (pl.col("low") > pl.min_horizontal("open", "close"))
        | (pl.col("high") < pl.max_horizontal("open", "close"))
        | (pl.col("low") > pl.col("high"))
    ).height
    return CandleReport(
        rows=ohlcv.height,
        first=uniq[0],
        last=uniq[-1],
        missing=missing,
        duplicates=dup,
        invalid_ohlc=invalid,
        negative_volume=ohlcv.filter(pl.col("volume") < 0).height,
        gaps=gaps,
    )


def compare_frames(ours: pl.DataFrame, theirs: pl.DataFrame, rel_tol: float = 1e-9) -> dict:
    """So từng nến cùng open_time. Trả số nến chung, số nến lệch và vài ví dụ."""
    cols = ["open", "high", "low", "close", "volume"]
    joined = ours.select("open_time", *cols).join(
        theirs.select("open_time", *cols), on="open_time", suffix="_x"
    )
    bad = joined.filter(
        pl.any_horizontal(
            [
                (pl.col(c) - pl.col(f"{c}_x")).abs() > rel_tol * pl.col(f"{c}_x").abs().clip(1.0)
                for c in cols
            ]
        )
    )
    return {
        "common": joined.height,
        "only_ours": ours.height - joined.height,
        "only_theirs": theirs.height - joined.height,
        "mismatched": bad.height,
        "examples": bad.head(3).to_dicts(),
    }


def compare_with_exchange(
    ours: pl.DataFrame,
    api: Exchange,
    venue_symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> dict:
    """So nến đã có với nến sàn trả về qua REST trong [start, end). Chỉ so nến đã đóng."""
    rows = [r for page in api.klines(venue_symbol, timeframe, start, end) for r in page]
    theirs = rows_to_frame(
        OHLCV, rows, exchange=api.name, symbol=ours["symbol"][0], timeframe=timeframe
    ).filter(pl.col("is_closed"))
    window = ours.filter(
        (pl.col("open_time") >= start) & (pl.col("open_time") < end) & pl.col("is_closed")
    )
    return compare_frames(window, theirs, rel_tol=1e-6)


def cross_exchange(a: pl.DataFrame, b: pl.DataFrame) -> dict:
    j = a.select("open_time", "close").join(b.select("open_time", "close"), on="open_time")
    if j.is_empty():
        return {"common": 0}
    rel = ((pl.col("close") - pl.col("close_right")).abs() / pl.col("close_right")).alias("rel")
    s = j.select(rel)["rel"]
    return {"common": j.height, "max_rel_diff": s.max(), "mean_rel_diff": s.mean()}
