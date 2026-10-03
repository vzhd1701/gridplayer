import re
import time

HOUR_SECONDS = 3600
DAY_SECONDS = HOUR_SECONDS * 24


def get_time_txt(
    seconds: int, max_seconds: int | None = None, strip: bool = False
) -> str:
    seconds = max(0, seconds)

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


def timed_title(name: str, start_ms: int, length_ms: int) -> str:
    """A chapter's or a bookmark's name, with where it is where a shortcut
    would go.

    Past the tab is the shortcut column, which lines the times up down the
    right of the menu. An ampersand is doubled so it shows as one instead
    of underlining the letter after it.
    """

    start_txt = get_time_txt(start_ms // 1000, length_ms // 1000)

    return "{}\t{}".format(name.replace("&", "&&"), start_txt)


def ms_time_txt(time_ms: int, length_ms: int | None = None, strip: bool = False) -> str:
    """A time to the millisecond, laid out as get_time_txt lays out the
    seconds: 03:27.412, or 3:27.412 stripped."""

    time_ms = max(0, time_ms)
    length_s = None if length_ms is None else length_ms // 1000

    whole_txt = get_time_txt(time_ms // 1000, length_s, strip=strip)

    return f"{whole_txt}.{time_ms % 1000:03d}"


def parse_time_txt(text: str) -> int | None:
    """A time typed the way the times are shown, in ms: 1:02:03, 03:27.4,
    or plain seconds, 45; None for anything else.

    A minute or a second past a larger unit is under 60 of it, as on a
    clock; seconds alone can run on.
    """

    match = re.fullmatch(r"\s*(?:(\d+):)?(?:(\d+):)?(\d+)(?:[.,](\d+))?\s*", text)

    if match is None:
        return None

    *larger, seconds_txt, fraction_txt = match.groups()
    units = [int(unit) for unit in larger if unit is not None]
    units.append(int(seconds_txt))

    if any(unit >= 60 for unit in units[1:]):
        return None

    seconds = 0
    for unit in units:
        seconds = seconds * 60 + unit

    fraction_ms = int((fraction_txt or "0").ljust(3, "0")[:3])

    return seconds * 1000 + fraction_ms


def timestamp_txt(time_ms: int, length_ms: int, is_precise: bool = False) -> str:
    """A time the way a video's description lists one: 3:27, or 1:02:03 in
    a video an hour long, in whole seconds; or precisely, to the
    millisecond, 3:27.400, for nothing to be lost on the way."""

    hours, seconds = divmod(time_ms // 1000, HOUR_SECONDS)
    minutes, seconds = divmod(seconds, 60)

    if hours or length_ms >= HOUR_SECONDS * 1000:
        time_txt = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        time_txt = f"{minutes}:{seconds:02d}"

    if is_precise:
        return f"{time_txt}.{time_ms % 1000:03d}"

    return time_txt


def _fmt_time(seconds, seconds_cnt):
    if seconds_cnt >= HOUR_SECONDS:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    elif seconds_cnt >= 60:
        return time.strftime("%M:%S", time.gmtime(seconds))

    return time.strftime("0:%S", time.gmtime(seconds))
