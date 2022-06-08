import platform
from enum import Enum, auto
from types import MappingProxyType
from typing import NamedTuple

from PyQt5.QtCore import Qt

PLAYER_ID_LENGTH = 8

PLAYER_INITIAL_SIZE = (640, 360)
PLAYER_MIN_VIDEO_SIZE = (100, 90)

OVERLAY_ACTIVITY_EVENT = 2000

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
    "hu_HU",
    "ru_RU",
)

# https://github.com/videolan/vlc/blob/3.0.16/include/vlc_interface.h#L152
SUPPORTED_AUDIO_EXT = frozenset(
    (
        "3ga",
        "669",
        "a52",
        "aac",
        "ac3",
        "adt",
        "adts",
        "aif",
        "aifc",
        "aiff",
        "amb",
        "amr",
        "aob",
        "ape",
        "au",
        "awb",
        "caf",
        "dts",
        "flac",
        "it",
        "kar",
        "m4a",
        "m4b",
        "m4p",
        "m5p",
        "mka",
        "mlp",
        "mod",
        "mpa",
        "mp1",
        "mp2",
        "mp3",
        "mpc",
        "mpga",
        "mus",
        "oga",
        "ogg",
        "oma",
        "opus",
        "qcp",
        "ra",
        "rmi",
        "s3m",
        "sid",
        "spx",
        "tak",
        "thd",
        "tta",
        "voc",
        "vqf",
        "w64",
        "wav",
        "wma",
        "wv",
        "xa",
        "xm",
    )
)

# https://github.com/videolan/vlc/blob/3.0.16/include/vlc_interface.h#L158
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
        "crf",
        "divx",
        "drc",
        "dv",
        "dvr-ms",
        "evo",
        "f4v",
        "flv",
        "gvi",
        "gxf",
        "iso",
        "m1v",
        "m2v",
        "m2t",
        "m2ts",
        "m4v",
        "mkv",
        "mov",
        "mp2",
        "mp2v",
        "mp4",
        "mp4v",
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
        "mxg",
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
        "ts",
        "tts",
        "txd",
        "vob",
        "vro",
        "webm",
        "wm",
        "wmv",
        "wtv",
        "xesc",
    )
)

SUPPORTED_MEDIA_EXT = frozenset(SUPPORTED_AUDIO_EXT | SUPPORTED_VIDEO_EXT)

VLC_USER_AGENT_NAME = "Mozilla"
VLC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/99.0.7113.93 Safari/537.36"
)

QT_ASPECT_MAP = MappingProxyType(
    {
        VideoAspect.FIT: Qt.KeepAspectRatioByExpanding,
        VideoAspect.STRETCH: Qt.IgnoreAspectRatio,
        VideoAspect.NONE: Qt.KeepAspectRatio,
    }
)
