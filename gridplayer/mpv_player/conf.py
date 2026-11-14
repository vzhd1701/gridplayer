"""mpv.conf: mpv options of the user's own, in a file beside settings.ini, for
every video MPV plays while "Use mpv.conf" is on.

Read as each video opens, in mpv's own format: `name=value` a line, a name alone
for yes, `no-name` for no, `#` for a comment. What the app can't play without
having its own way is skipped, as is a name this libmpv doesn't know: given at
the start that would stop mpv starting (see "libmpv versions" in AGENTS.md).
Applied after the app's own options as a video opens, so they win there, and
then left alone by the app, but for the decoder.
"""

import logging
from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path
from typing import NamedTuple

from gridplayer.utils.app_dir import get_app_data_dir

_log = logging.getLogger(__name__)

FILE_NAME = "mpv.conf"

TEMPLATE = """\
# mpv options for GridPlayer, used while "Use mpv.conf" is on in
# Settings > Advanced > Video Decoder. As in mpv's own mpv.conf: one option
# a line, name=value, a name alone for yes, # for a comment.
#
# Read as each video opens: reload a video for a change to reach it.
# Skipped: names mpv doesn't know, values it won't take, and what GridPlayer
# sets itself (its window and output, audio device, view, tracks, playback).
# "Check" beside the setting lists what's skipped, and why.
#
# deband=yes
# hwdec=nvdec
"""


class Skip(Enum):
    NOT_AN_OPTION = auto()
    UNKNOWN = auto()
    BAD_VALUE = auto()
    APP_OWN = auto()
    DIRECT_ONLY = auto()
    PROFILE = auto()


class ConfLine(NamedTuple):
    number: int
    text: str
    name: str
    value: str


class Skipped(NamedTuple):
    number: int
    text: str
    why: Skip


# What the app needs its own way of: its window and output, sound device, the
# view (zoom, crop, turns, placement), tracks and playback, and no scripts or
# other files read
_APP_OWN = frozenset(
    (
        "wid",
        "gpu-context",
        "ao",
        "audio-device",
        "config",
        "config-dir",
        "include",
        "profile",
        "idle",
        "keep-open",
        "keep-open-pause",
        "loop-file",
        "loop-playlist",
        "pause",
        "mute",
        "volume",
        "speed",
        "start",
        "end",
        "ab-loop-a",
        "ab-loop-b",
        "vid",
        "aid",
        "sid",
        "audio-files",
        "sub-files",
        "ytdl",
        "keepaspect",
        "vf",
        "deinterlace",
        "video-zoom",
        "video-pan-x",
        "video-pan-y",
        "video-align-x",
        "video-align-y",
        "video-rotate",
        "video-crop",
        "video-aspect-override",
        "video-unscaled",
        "video-scale-x",
        "video-scale-y",
        "panscan",
        "osc",
        "osd-level",
        "fullscreen",
        "geometry",
        "autofit",
    )
)
_APP_OWN_PREFIXES = ("input-", "load-", "script", "video-margin-ratio-")
# mpv's own output on Direct only: Copy and Shared draw through the render API
_DIRECT_ONLY = frozenset(("vo", "gpu-api"))
# Direct's subtitle layout, see MpvPlayer._own_window_options
_DIRECT_OWN = frozenset(("sub-use-margins", "sub-scale-with-window"))


def conf_path() -> Path:
    return get_app_data_dir() / FILE_NAME


def read_conf(path: Path | None = None) -> str:
    """The file's text, or none if there's no file or it can't be read."""

    try:
        return (path or conf_path()).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    except OSError:
        _log.warning("Could not read mpv.conf", exc_info=True)
        return ""


def conf_lines() -> list[ConfLine]:
    """The file's options, as a video opens."""

    lines, skipped = parse_conf(read_conf())
    log_skipped(skipped)

    return lines


def parse_conf(text: str) -> tuple[list[ConfLine], list[Skipped]]:
    lines, skipped = [], []
    in_profile = False

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        # options in a profile apply only once it's picked, which the app never does
        if line.startswith("["):
            in_profile = True

        if in_profile:
            skipped.append(Skipped(number, line, Skip.PROFILE))
            continue

        name, has_value, value = line.partition("=")
        name = name.strip().removeprefix("--")
        value = _unquoted(value.strip()) if has_value else "yes"

        if not name or " " in name:
            skipped.append(Skipped(number, line, Skip.NOT_AN_OPTION))
            continue

        lines.append(ConfLine(number, line, name, value))

    return lines, skipped


def resolve(
    lines: list[ConfLine],
    option_info: Callable[[str], dict | None],
    is_direct: bool,
) -> tuple[list[ConfLine], list[Skipped]]:
    """Those this libmpv has and the app leaves to them, `no-name` made
    `name=no`."""

    kept, skipped = [], []

    for line in lines:
        line = _flag_turned_off(line, option_info)

        why = _refused(line.name, is_direct)
        if why is None and not option_info(line.name):
            why = Skip.UNKNOWN

        if why is None:
            kept.append(line)
        else:
            skipped.append(Skipped(line.number, line.text, why))

    return kept, skipped


def check_conf(mpv_module, is_direct: bool) -> tuple[int, list[Skipped]] | None:
    """How many of the file's options a video opening now would take, and the
    lines it would skip, from an mpv started to ask. None if it won't start."""

    lines, skipped = parse_conf(read_conf())

    try:
        mpv = mpv_module.MPV(vo="null", ao="null", load_scripts=False, ytdl=False)
    # what a libmpv that won't take what it's asked can raise
    except Exception:
        _log.exception("Could not start mpv to check mpv.conf")
        return None

    try:
        kept, refused = resolve(lines, mpv.option_info, is_direct)
        skipped += refused

        taken = 0
        for line in kept:
            if is_taken(mpv, line):
                taken += 1
            else:
                skipped.append(Skipped(line.number, line.text, Skip.BAD_VALUE))
    finally:
        mpv.terminate()

    return taken, sorted(skipped)


def is_taken(mpv, line: ConfLine) -> bool:
    """Set, if mpv takes the value."""

    try:
        mpv.command("set", line.name, line.value)
    # what mpv says of a value it won't take
    except Exception:
        return False

    return True


def log_skipped(skipped: list[Skipped]) -> None:
    for line in skipped:
        _log.warning(
            f"mpv.conf line {line.number} skipped, {line.why.name}: {line.text}"
        )


def _unquoted(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]

    return value


def _flag_turned_off(
    line: ConfLine, option_info: Callable[[str], dict | None]
) -> ConfLine:
    if line.name.startswith("no-") and line.value == "yes":
        flag = line.name[3:]

        if not option_info(line.name) and option_info(flag):
            return line._replace(name=flag, value="no")

    return line


def _refused(name: str, is_direct: bool) -> Skip | None:
    if name in _APP_OWN or name.startswith(_APP_OWN_PREFIXES):
        return Skip.APP_OWN

    if is_direct and name in _DIRECT_OWN:
        return Skip.APP_OWN

    if not is_direct and name in _DIRECT_ONLY:
        return Skip.DIRECT_ONLY

    return None
