from enum import Enum, auto
from typing import NamedTuple

from gridplayer.params import env

PLAYER_ID_LENGTH = 8

PLAYER_INITIAL_SIZE = (640, 360)
PLAYER_MIN_SIZE = (200, 150)
CHROME_MIN_SIZE = (150, 100)
INFO_LABEL_MIN_SIZE = (250, 250)

OVERLAY_ACTIVITY_EVENT = 2000

FONT_SIZE_MAIN = 12 if env.IS_MACOS else 9
FONT_SIZE_BIG_INFO = 22 if env.IS_MACOS else 16

MIN_SCALE = 1.0
MAX_SCALE = 10.0
MIN_RATE = 0.2
MAX_RATE = 12

# How far the sound can be moved against the picture, and by how much at a
# time. The step is the one VLC moves it by on its own keys, small enough to
# tune by ear and large enough to get somewhere.
MIN_AUDIO_DELAY_MS = -60000
MAX_AUDIO_DELAY_MS = 60000
AUDIO_DELAY_STEP_MS = 50

# The same for the subtitles, over a wider range and in coarser steps. A
# subtitle file cut for another release of the same film can be out by whole
# minutes, where sound that far out would not be worth listening to, and the
# eye is a poorer judge of a few tens of milliseconds than the ear.
MIN_SUBTITLE_DELAY_MS = -300000
MAX_SUBTITLE_DELAY_MS = 300000
SUBTITLE_DELAY_STEP_MS = 100


class AutoName(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()


class GridMode(AutoName):
    AUTO_ROWS = auto()
    AUTO_COLS = auto()
    FIXED = auto()


class DropAction(AutoName):
    INSERT = auto()
    REPLACE = auto()


class DropModifier(AutoName):
    SHIFT = auto()
    CTRL = auto()
    ALT = auto()
    NONE = auto()


class VideoAspect(AutoName):
    FIT = auto()
    STRETCH = auto()
    NONE = auto()


class VideoCrop(NamedTuple):
    Left: int
    Top: int
    Right: int
    Bottom: int


class VideoTransform(AutoName):
    ROTATE_90 = auto()
    ROTATE_180 = auto()
    ROTATE_270 = auto()
    HFLIP = auto()
    VFLIP = auto()
    TRANSPOSE = auto()
    ANTITRANSPOSE = auto()
    NONE = auto()


class VideoEndAction(AutoName):
    LOOP_FILE = auto()
    NEXT_FILE = auto()
    PREVIOUS_FILE = auto()
    SHUFFLE_FILE = auto()
    PAUSE = auto()
    STOP = auto()
    CLOSE = auto()


class VideoInitialState(AutoName):
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()


class VideoDriver(AutoName):
    VLC_SW = auto()
    VLC_SW_SP = auto()
    VLC_HW = auto()
    VLC_HW_SP = auto()
    DUMMY = auto()


class HWCropBorderOffset(AutoName):
    AUTO = auto()
    DISABLED = auto()
    PX2 = auto()
    PX4 = auto()
    PX6 = auto()
    PX8 = auto()
    PX10 = auto()
    PX12 = auto()


class SeekSyncMode(AutoName):
    DISABLED = auto()
    PERCENT = auto()
    TIMECODE = auto()


class UnsavedChangesMode(AutoName):
    ASK = auto()
    DISCARD = auto()
    AUTO_SAVE_DISCARD = auto()
    AUTO_SAVE_ASK = auto()


class URLResolver(AutoName):
    STREAMLINK = auto()
    YT_DLP = auto()
    DIRECT = auto()


class ProxyMode(AutoName):
    """Where the proxy to reach the outside world with comes from."""

    # whatever the machine is already set up with, which is what every
    # HTTP client in here does when it is told nothing
    SYSTEM = auto()
    # straight out, ignoring what the machine is set up with
    NONE = auto()
    CUSTOM = auto()


class NetworkRetryMode(AutoName):
    """What to do when a network video fails to load or dies mid-playback."""

    OFF = auto()
    TIMES = auto()
    INFINITE = auto()


class AudioTrackMode(AutoName):
    """Which audio track a video starts with, before anyone picks one by hand."""

    # whichever one the file itself marks as the default, which is what a
    # player that was told nothing would play
    DEFAULT = auto()
    PREFERRED = auto()
    DISABLED = auto()


class SubtitleTrackMode(AutoName):
    """Which subtitle a video starts with, before anyone picks one by hand."""

    # none, which is where a video starts unless it is told otherwise. Not
    # the same as having none to show: the tracks are still there to pick.
    DISABLED = auto()
    PREFERRED = auto()
    # whichever one the container marks default or forced, which is what a
    # player that was told nothing would show
    DEFAULT = auto()


class ColorScheme(AutoName):
    SYSTEM = auto()
    LIGHT = auto()
    DARK = auto()


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
