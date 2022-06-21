from enum import Enum, auto
from typing import NamedTuple

from gridplayer.params import env

PLAYER_ID_LENGTH = 8

PLAYER_INITIAL_SIZE = (640, 360)
PLAYER_MIN_VIDEO_SIZE = (100, 90)

OVERLAY_ACTIVITY_EVENT = 2000

if env.IS_MACOS:
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


class SeekSyncMode(AutoName):
    NONE = auto()
    PERCENT = auto()
    TIMECODE = auto()


class WindowState(NamedTuple):
    is_maximized: bool
    is_fullscreen: bool
    geometry: str


SUPPORTED_LANGUAGES = (
    "en_US",
    "hu_HU",
    "ru_RU",
)
