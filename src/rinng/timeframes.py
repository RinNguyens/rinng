"""Khung thời gian dùng chung cho mọi lớp (không phụ thuộc gói nào khác)."""

from datetime import timedelta

_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}


def timeframe_ms(timeframe: str) -> int:
    """Độ dài một khung thời gian, ví dụ '15m', '4h', '1d', '1w'."""
    unit = timeframe[-1:]
    if unit not in _UNIT_MS or not timeframe[:-1].isdigit():
        raise ValueError(f"khung thời gian không hợp lệ: {timeframe!r}")
    return int(timeframe[:-1]) * _UNIT_MS[unit]


def bar_duration(timeframe: str) -> timedelta:
    return timedelta(milliseconds=timeframe_ms(timeframe))
