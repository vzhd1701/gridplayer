"""A video's address that opens it where it is playing now.

Only for the sites whose address says where to start, and in the words
each of them reads it in. Everything else about the address is kept just
as it was given, down to how it was escaped: it is the viewer's own.
"""

import re
from urllib.parse import urlsplit, urlunsplit

YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)
YOUTUBE_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
TWITCH_HOSTS = frozenset({"twitch.tv", "www.twitch.tv", "m.twitch.tv"})

TWITCH_VOD_PATH = re.compile(r"^/videos/\d+/?$")


def url_at_time(url: str, time_ms: int, youtube_id: str | None = None) -> str | None:
    """The address that starts at time_ms, or None for a site that has none.

    A YouTube short, embed or live address takes no time, so it is given
    as the watch page of the video it turned out to be, where that is
    known.
    """

    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None

    if parts.scheme not in {"http", "https"} or host is None:
        return None

    seconds = max(0, time_ms // 1000)

    if host in YOUTUBE_SHORT_HOSTS or (
        host in YOUTUBE_HOSTS and parts.path == "/watch"
    ):
        return _with_time(parts, f"{seconds}s", also_drop={"start"})

    if host in YOUTUBE_HOSTS:
        if youtube_id is None:
            return None

        return f"https://www.youtube.com/watch?v={youtube_id}&t={seconds}s"

    if host in TWITCH_HOSTS and TWITCH_VOD_PATH.match(parts.path):
        return _with_time(parts, _twitch_time(seconds))

    return None


def _twitch_time(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)

    return f"{hours:02d}h{minutes:02d}m{seconds:02d}s"


def _with_time(parts, time_txt: str, also_drop=frozenset()) -> str:
    dropped = {"t", *also_drop}

    query = [
        pair
        for pair in parts.query.split("&")
        if pair and pair.split("=", 1)[0] not in dropped
    ]
    query.append(f"t={time_txt}")

    # an old way of saying where to start, which would argue with the new one
    fragment = "" if parts.fragment.startswith("t=") else parts.fragment

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "&".join(query), fragment)
    )
