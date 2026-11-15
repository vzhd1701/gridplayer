"""What of the player's asks this libmpv's FFmpeg was built with.

A build made small, as MPVKit's in the macOS package, leaves out filters and
demuxers: the filters most deinterlace modes are made of, and the readers of
most subtitle formats. What it hasn't got shows greyed out, rather than doing
nothing when picked. It has no zimg either, which Software MPV's frames are
made with: see SoftwareRender.

Asked once a run, of an mpv of its own made with the first video's (70 ms on a
Mac, a few here): the demuxers are a property, the filters what mpv lists for
`vf set lavfi=[help]`. Not known before then, or if mpv lists nothing, which is
taken as everything being there.
"""

import logging
import re
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

# printed after the list, so that the list is known to be over
_END_MARK = "gp-filters-end"

# "  yadif            Deinterlace the input image."
_LISTED_FILTER = re.compile(r"  (\S+)\s")

# A subtitle file by extension, and the demuxers that read it, any one of them
# doing. Formats FFmpeg has no demuxer for at all, or many (.txt), aren't here:
# those are left offered.
_SUBTITLE_DEMUXERS = {
    "aqt": ("aqtitle",),
    "ass": ("ass",),
    "ssa": ("ass",),
    "idx": ("vobsub",),
    "jss": ("jacosub",),
    "mks": ("matroska,webm",),
    "mpl2": ("mpl2",),
    "pjs": ("pjsub",),
    "rt": ("realtext",),
    "sami": ("sami",),
    "smi": ("sami",),
    "scc": ("scc",),
    "srt": ("srt",),
    "stl": ("stl",),
    "sub": ("microdvd", "subviewer", "subviewer1"),
    "vtt": ("webvtt",),
}


@dataclass(frozen=True)
class Abilities:
    filters: frozenset[str]
    demuxers: frozenset[str]
    has_zimg: bool = True

    def has_filters(self, names) -> bool:
        return not self.filters or set(names) <= self.filters

    def reads_subtitle_file(self, path: Path) -> bool:
        needed = _SUBTITLE_DEMUXERS.get(path.suffix[1:].casefold())

        if needed is None or not self.demuxers:
            return True

        return any(name in self.demuxers for name in needed)


_asking = threading.Lock()
_known: Abilities | None = None


def known() -> Abilities | None:
    """None until a libmpv has been asked."""

    return _known


def ask(mpv_module) -> Abilities:
    global _known

    with _asking:
        if _known is None:
            _known = _ask(mpv_module)

    return _known


def _ask(mpv_module) -> Abilities:
    listed: list[str] = []
    is_over = threading.Event()

    def on_log(_level, _component, message):
        if message.startswith(_END_MARK):
            is_over.set()
        else:
            listed.append(message)

    player = None

    try:
        player = mpv_module.MPV(
            vo="null",
            ao="null",
            idle=True,
            config=False,
            log_handler=on_log,
            loglevel="info",
        )

        demuxers = frozenset(player.demuxer_lavf_list or ())
        # its options are there only with it
        has_zimg = player.option_info("zimg-scaler") is not None

        # it lists them and says no, there being no filter called help
        with suppress(Exception):
            player.command("vf", "set", "lavfi=[help]")

        player.command("print-text", _END_MARK)

        if not is_over.wait(2):
            _log.warning("mpv didn't list its filters")
            listed.clear()
    except Exception:
        _log.warning("Couldn't ask mpv what it can do", exc_info=True)
        return Abilities(frozenset(), frozenset())
    finally:
        if player is not None:
            player.terminate()

    filters = frozenset(_filters_in(listed))

    _log.debug(
        f"libmpv has {len(filters)} filters, {len(demuxers)} demuxers,"
        f" {'' if has_zimg else 'no '}zimg"
    )

    return Abilities(filters, demuxers, has_zimg)


def _filters_in(lines: list[str]):
    """The names under "Available libavfilter filters:", up to the first line
    that isn't one: mpv's own lavfi options follow."""

    in_list = False

    for line in lines:
        if line.startswith("Available libavfilter filters"):
            in_list = True
            continue

        if not in_list:
            continue

        name = _LISTED_FILTER.match(line)

        if name is None:
            return

        yield name.group(1)
