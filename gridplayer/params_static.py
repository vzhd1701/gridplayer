import platform
from enum import Enum, auto
from typing import NamedTuple

PLAYER_ID_LENGTH = 8

PLAYER_INITIAL_SIZE = (640, 360)
PLAYER_MIN_VIDEO_SIZE = (100, 90)

if platform.system() == "Darwin":
    PLAYER_INFO_TEXT_SIZE = 24
else:
    PLAYER_INFO_TEXT_SIZE = 16


class AutoName(Enum):
    def _generate_next_value_(name, start, count, last_values):  # noqa: WPS120
        return name.lower()


class GridMode(AutoName):
    AUTO_ROWS = auto()
    AUTO_COLS = auto()


class VideoAspect(AutoName):
    FIT = auto()
    STRETCH = auto()
    NONE = auto()


class VideoRepeat(AutoName):
    SINGLE_FILE = auto()
    DIR = auto()
    DIR_SHUFFLE = auto()


class VideoDriver(AutoName):
    VLC_SW = auto()
    VLC_HW = auto()
    VLC_HW_SP = auto()
    DUMMY = auto()


class WindowState(NamedTuple):
    is_maximized: bool
    is_fullscreen: bool
    geometry: str


SUPPORTED_LANGUAGES = (
    "en_US",
    "ru_RU",
)


SUPPORTED_VIDEO_EXT = frozenset(
    (
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
    )
)
