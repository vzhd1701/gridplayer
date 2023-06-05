from enum import Enum, auto
from typing import NamedTuple

from gridplayer.params import env

PLAYER_ID_LENGTH = 8

PLAYER_INITIAL_SIZE = (640, 360)
PLAYER_MIN_VIDEO_SIZE = (100, 90)

OVERLAY_ACTIVITY_EVENT = 2000

FONT_SIZE_MAIN = 12 if env.IS_MACOS else 9  # noqa: WPS432
FONT_SIZE_BIG_INFO = 22 if env.IS_MACOS else 16  # noqa: WPS432

VIDEO_END_LOOP_MARGIN_MS = 500


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


class VideoTransform(AutoName):
    ROTATE_90 = auto()
    ROTATE_180 = auto()
    ROTATE_270 = auto()
    HFLIP = auto()
    VFLIP = auto()
    TRANSPOSE = auto()
    ANTITRANSPOSE = auto()
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
    DISABLED = auto()
    PERCENT = auto()
    TIMECODE = auto()


class URLResolver(AutoName):
    STREAMLINK = auto()
    YT_DLP = auto()
    DIRECT = auto()


class AudioChannelMode(AutoName):
    UNSET = auto()
    STEREO = auto()
    RSTEREO = auto()
    LEFT = auto()
    RIGHT = auto()
    DOLBYS = auto()
    HEADPHONES = auto()
    MONO = auto()


class WindowState(NamedTuple):
    is_maximized: bool
    is_fullscreen: bool
    geometry: str
