"""Công cụ kiểm thử dùng chung cho các module phân tích."""

from collections.abc import Callable
from datetime import datetime

import polars as pl


def _known_before(frame: pl.DataFrame, cutoff: datetime) -> pl.DataFrame:
    out = frame.filter(pl.col("known_at") <= cutoff)
    if "invalidated_at" in out.columns:
        # Sự kiện bị vô hiệu sau mốc cắt thì ở mốc cắt nó vẫn còn hiệu lực.
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
    """Chạy `compute` trên toàn bộ nến và trên nến bị cắt tại từng chỉ số trong `cut_indices`.

    Mọi dòng có `known_at` <= thời điểm đóng của nến cuối trong phần bị cắt phải giống hệt
    nhau giữa hai lần chạy (sau khi che `invalidated_at` xảy ra sau mốc cắt).
    """
    full = compute(ohlcv)
    for cut in cut_indices:
        if not 0 < cut < ohlcv.height:
            raise ValueError(f"chỉ số cắt {cut} phải nằm trong (0, {ohlcv.height})")
        # Mốc cắt = lúc đóng nến cuối của phần bị cắt = open_time của nến kế tiếp.
        cutoff = ohlcv["open_time"][cut]
        left = _known_before(full, cutoff)
        right = _known_before(compute(ohlcv.head(cut)), cutoff)
        if not left.equals(right, null_equal=True):
            diff = left.join(right, on=left.columns, how="anti", nulls_equal=True)
            raise AssertionError(
                f"nhìn trước tương lai tại nến {cut} (mốc {cutoff}):\n{diff.head(5)}\n"
                f"toàn bộ: {left.height} dòng, cắt: {right.height} dòng"
            )
