"""Shared timeframes for every layer (no dependency on other packages)."""

from datetime import timedelta

_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}


def timeframe_ms(timeframe: str) -> int:
    """Length of one timeframe, e.g. '15m', '4h', '1d', '1w'."""
    unit = timeframe[-1:]
    if unit not in _UNIT_MS or not timeframe[:-1].isdigit():
        raise ValueError(f"invalid timeframe: {timeframe!r}")
    return int(timeframe[:-1]) * _UNIT_MS[unit]


def bar_duration(timeframe: str) -> timedelta:
    return timedelta(milliseconds=timeframe_ms(timeframe))


_MONDAY_MS = 4 * 86_400_000  # 1970-01-05 00:00 UTC is a Monday


def bucket_start_ms(t_ms: int, timeframe: str) -> int:
    """Open time of the `timeframe` bar containing time t (ms, UTC).

    Matches resample: minutes/hours/days align to the epoch, weeks open Monday 00:00 UTC.
    """
    size = timeframe_ms(timeframe)
    offset = _MONDAY_MS if timeframe.endswith("w") else 0
    return t_ms - ((t_ms - offset) % size)
