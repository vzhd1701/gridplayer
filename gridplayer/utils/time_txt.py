import time
from typing import Optional

HOUR_SECONDS = 3600
DAY_SECONDS = HOUR_SECONDS * 24


def get_time_txt(
    seconds: int, max_seconds: Optional[int] = None, strip: bool = False
) -> str:
    if max_seconds and max_seconds < seconds:
        max_seconds = None

    seconds_cnt = max_seconds or seconds

    if seconds >= DAY_SECONDS:
        days, seconds_cnt = divmod(seconds, DAY_SECONDS)
    else:
        days = 0

    clock = _fmt_time(seconds, seconds_cnt)

    if strip and seconds_cnt >= 60:
        clock = clock.lstrip("0")

    if days:
        return f"{days}d {clock}"

    return clock


def _fmt_time(seconds, seconds_cnt):
    if seconds_cnt >= HOUR_SECONDS:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    elif seconds_cnt >= 60:
        return time.strftime("%M:%S", time.gmtime(seconds))

    return time.strftime("0:%S", time.gmtime(seconds))
