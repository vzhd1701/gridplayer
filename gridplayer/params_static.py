from enum import Enum, auto
from typing import NamedTuple


class AutoName(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()


class GridMode(AutoName):
    AUTO_ROWS = auto()
    AUTO_COLS = auto()


class VideoAspect(AutoName):
    FIT = auto()
    STRETCH = auto()
    NONE = auto()


class VideoDriver(AutoName):
    VLC_SW = auto()
    VLC_HW = auto()
    DUMMY = auto()


class WindowState(NamedTuple):
    is_maximized: bool
    is_fullscreen: bool
    geometry: str


SUPPORTED_VIDEO_EXT = {
    "3g2",
    "3gp",
    "3gp2",
    "3gpp",
    "amv",
    "asf",
    "avi",
    "bik",
    "dav",
    "divx",
    "drc",
    "dv",
    "dvr-ms",
    "evo",
    "f4v",
    "flv",
    "gvi",
    "gxf",
    "m1v",
    "m2t",
    "m2ts",
    "m2v",
    "m4v",
    "mkv",
    "mov",
    "mp2v",
    "mp4",
    "mp4v",
    "mpa",
    "mpe",
    "mpeg",
    "mpeg1",
    "mpeg2",
    "mpeg4",
    "mpg",
    "mpv2",
    "mts",
    "mtv",
    "mxf",
    "nsv",
    "nuv",
    "ogg",
    "ogm",
    "ogv",
    "ogx",
    "ps",
    "rec",
    "rm",
    "rmvb",
    "rpl",
    "thp",
    "tod",
    "tp",
    "ts",
    "tts",
    "vob",
    "vro",
    "webm",
    "wmv",
    "wtv",
    "xesc",
}
