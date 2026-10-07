"""How far a press seeks or zooms, as the playlist has it set.

Read at the press rather than kept anywhere, so that a change in the
settings or a playlist with steps of its own counts from the next one on.
"""

import math

from gridplayer.params.static import MAX_SCALE, MIN_SCALE
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils.qt import translate

SEEK_STEP_KEYS = {
    "short": "playlist/seek_step_short",
    "medium": "playlist/seek_step_medium",
    "long": "playlist/seek_step_long",
}

# scales are kept to hundredths, which is as fine as the zoom shows them
_SCALE_DECIMALS = 2

# how far past a rung, in rungs, a scale has to be not to count as on it
_OFF_RUNG = 1e-6


def seek_step_ms(slot: str) -> int:
    """How far one of the seek steps goes, "short", "medium" or "long".

    Set in seconds, to the millisecond.
    """

    return round(PlaylistSettings().get(SEEK_STEP_KEYS[slot]) * 1000)


def seek_step_label(slot: str) -> str:
    """One of the seek steps as the menu names it: 5s, 1.5s, 1m 30s, 1h."""

    return seek_step_txt(seek_step_ms(slot))


def seek_step_txt(step_ms: int) -> str:
    # short of a second, a part of one reads better in milliseconds
    if 0 < step_ms < 1000:
        return translate("Actions", "{milliseconds}ms").format(milliseconds=step_ms)

    hours, rest_ms = divmod(step_ms, 3600 * 1000)
    minutes, rest_ms = divmod(rest_ms, 60 * 1000)
    seconds, ms = divmod(rest_ms, 1000)

    parts = []

    if hours:
        parts.append(translate("Actions", "{hours}h").format(hours=hours))

    if minutes:
        parts.append(translate("Actions", "{minutes}m").format(minutes=minutes))

    if seconds or ms or not parts:
        # as many places as there are milliseconds to show, and none for none
        seconds_txt = f"{seconds}.{ms:03d}".rstrip("0").rstrip(".")
        parts.append(translate("Actions", "{seconds}s").format(seconds=seconds_txt))

    return " ".join(parts)


def zoom_stepped(scale: float, direction: int) -> float:
    """The scale one press of zoom in (direction 1) or out (-1) takes a
    picture to from where it is.

    The steps are a share of the whole picture each, or, zooming in
    proportion, of what is on show, which feels the same at any zoom. Either
    way they go up from the whole picture in rungs, and a scale off them --
    zoomed to a selection, or set with other steps -- goes from the rung
    nearest to it, so zooming in and out again comes back to where it was.
    """

    percent = PlaylistSettings().get("playlist/zoom_step")

    if PlaylistSettings().get("playlist/zoom_proportional"):
        ratio = 1 + percent / 100
        rungs = math.log(scale) / math.log(ratio)

        def rung_scale(n):
            return ratio**n

    else:
        step = percent / 100
        rungs = scale / step

        def rung_scale(n):
            return n * step

    if direction < 0 and scale >= MAX_SCALE:
        # the top rung is only as far as the zoom goes, short of a whole
        # step, and out from it is the rung it was zoomed in from
        rung = math.floor(rungs - _OFF_RUNG)
    else:
        rung = round(rungs) + direction

    stepped = _clamped(rung_scale(rung))

    # a rung that close to the one it is on that the rounding puts it back
    # there is no press at all; on to the next one
    while stepped == scale and MIN_SCALE < stepped < MAX_SCALE:
        rung += direction
        stepped = _clamped(rung_scale(rung))

    return stepped


def _clamped(scale: float) -> float:
    return min(max(round(scale, _SCALE_DECIMALS), MIN_SCALE), MAX_SCALE)
