"""Shared testing helpers for the analysis modules."""

from collections.abc import Callable
from datetime import datetime

import polars as pl


def _known_before(frame: pl.DataFrame, cutoff: datetime) -> pl.DataFrame:
    out = frame.filter(pl.col("known_at") <= cutoff)
    if "invalidated_at" in out.columns:
        # An event invalidated after the cutoff is still valid at the cutoff.
        out = out.with_columns(
            pl.when(pl.col("invalidated_at") <= cutoff)
            .then(pl.col("invalidated_at"))
            .otherwise(None)
            .alias("invalidated_at")
        )
    sort_cols = ["event_id"] if "event_id" in out.columns else ["open_time"]
    return out.sort(sort_cols)


def assert_no_lookahead(
    compute: Callable[[pl.DataFrame], pl.DataFrame],
    ohlcv: pl.DataFrame,
    cut_indices: list[int],
) -> None:
    """Run `compute` on all candles and on candles truncated at each index in `cut_indices`.

    Every row with `known_at` <= the close time of the last candle in the truncated part must be
    identical between the two runs (after masking `invalidated_at` values that occur after the
    cutoff).
    """
    full = compute(ohlcv)
    for cut in cut_indices:
        if not 0 < cut < ohlcv.height:
            raise ValueError(f"cut index {cut} must be within (0, {ohlcv.height})")
        # Cutoff = close of the last truncated candle = open_time of the next candle.
        cutoff = ohlcv["open_time"][cut]
        left = _known_before(full, cutoff)
        right = _known_before(compute(ohlcv.head(cut)), cutoff)
        if not left.equals(right, null_equal=True):
            diff = left.join(right, on=left.columns, how="anti", nulls_equal=True)
            raise AssertionError(
                f"lookahead at candle {cut} (cutoff {cutoff}):\n{diff.head(5)}\n"
                f"full: {left.height} rows, truncated: {right.height} rows"
            )
