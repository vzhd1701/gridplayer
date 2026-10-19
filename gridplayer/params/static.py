from enum import Enum, auto
from typing import NamedTuple

from gridplayer.params import env

PLAYER_ID_LENGTH = 8

# adding more cells than this at once warns first: every cell plays at the
# same time, and so many can freeze the player
MANY_CELLS = 20

PLAYER_INITIAL_SIZE = (640, 360)
PLAYER_MIN_SIZE = (200, 150)
CHROME_MIN_SIZE = (150, 100)
INFO_LABEL_MIN_SIZE = (250, 250)

OVERLAY_ACTIVITY_EVENT = 2000

FONT_SIZE_MAIN = 12 if env.IS_MACOS else 9
FONT_SIZE_BIG_INFO = 22 if env.IS_MACOS else 16

MIN_SCALE = 1.0
MAX_SCALE = 10.0

# What a seek step can be set to: to the millisecond, and up to an hour;
# past that a timecode or a share of the video gets there in one go anyway.
MIN_SEEK_STEP_SECONDS = 0.001
MAX_SEEK_STEP_SECONDS = 3600

# How far one move takes the picture: this much of the part on show, so a
# press goes as far on screen whatever the video's size or the zoom.
SHIFT_STEP = 0.05
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


class VideoCellViewMode(AutoName):
    """How a picture is fitted into its cell: covering it, cut at the sides
    or the top and bottom (FILL); whole, with bars (FIT); or pulled to its
    shape (STRETCH)."""

    FILL = auto()
    FIT = auto()
    STRETCH = auto()


# The view mode was saved as the "aspect" once, under other names: its
# "fit" covered the cell, which is FILL now, and "none" showed the whole
# picture, which is FIT
LEGACY_VIEW_MODES = {
    "fit": VideoCellViewMode.FILL,
    "none": VideoCellViewMode.FIT,
    "stretch": VideoCellViewMode.STRETCH,
}


class VideoCrop(NamedTuple):
    Left: int
    Top: int
    Right: int
    Bottom: int


class VideoAnchor(AutoName):
    CENTER = auto()
    TOP = auto()
    BOTTOM = auto()
    LEFT = auto()
    RIGHT = auto()
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()


class VideoShift(NamedTuple):
    X: int
    Y: int


# Picked over the shape a video's list says, where it says one: the video's
# own aspect ratio, and no crop. Without a list the same as nothing picked.
OWN_ASPECT_RATIO = "own"
NO_CROP_RATIO = "none"

# the shapes offered to pick, in the menu and for new videos, in VLC's order
ASPECT_RATIO_PRESETS = (
    "16:9",
    "4:3",
    "1:1",
    "16:10",
    "2.21:1",
    "2.35:1",
    "2.39:1",
    "5:4",
)
CROP_RATIO_PRESETS = (
    "16:10",
    "16:9",
    "4:3",
    "1.85:1",
    "2.21:1",
    "2.35:1",
    "2.39:1",
    "5:3",
    "5:4",
    "1:1",
)


def is_crop_unpicked(crop_ratio: str, crop) -> bool:
    """Cut to no shape picked and by no margins: to its list's shape,
    where it says one."""

    return not crop_ratio and not any(crop)


class ViewParams(NamedTuple):
    """How a video is fitted into its pane, as one value.

    What every view update carries from the widget to the player.
    """

    cell_view_mode: VideoCellViewMode = VideoCellViewMode.FILL
    scale: float = 1.0
    crop: VideoCrop = VideoCrop(0, 0, 0, 0)
    anchor: VideoAnchor = VideoAnchor.CENTER
    shift: VideoShift = VideoShift(0, 0)
    # whether the shift may take the picture past the pane's edges, with
    # black showing where it has gone from
    is_shift_past_edges: bool = False
    # the shape the whole picture is shown in, as it is shown, turned or
    # not: "16:9", "2.35:1". Empty for the shape the video gives it, or its
    # list; OWN_ASPECT_RATIO for the video's own, whatever its list says
    aspect_ratio: str = ""
    # the shape the picture is cut to, as it is shown, or empty for the
    # crop's own margins, or its list's shape; NO_CROP_RATIO for none,
    # whatever its list says. With one, the crop is the margins that cut it so,
    # worked out where the frame is known (see calc_ratio_crop)
    crop_ratio: str = ""
    # the two above are the ones the video's list says, nothing being
    # picked: to be shown, and never kept as picked (see with_list)
    is_aspect_ratio_listed: bool = False
    is_crop_ratio_listed: bool = False

    def with_list(self, list_aspect_ratio: str, list_crop_ratio: str) -> "ViewParams":
        """The view with the shapes the video's list says where none is
        picked: an aspect ratio where it has none, a crop where it is cut
        to no shape and by no margins."""

        is_aspect_listed = not self.aspect_ratio and bool(list_aspect_ratio)
        is_crop_listed = is_crop_unpicked(self.crop_ratio, self.crop) and bool(
            list_crop_ratio
        )

        return self._replace(
            aspect_ratio=list_aspect_ratio if is_aspect_listed else self.aspect_ratio,
            crop_ratio=list_crop_ratio if is_crop_listed else self.crop_ratio,
            is_aspect_ratio_listed=is_aspect_listed,
            is_crop_ratio_listed=is_crop_listed,
        )

    def picked(self) -> "ViewParams":
        """The view as picked, the list's shapes left out."""

        view = self

        if view.is_aspect_ratio_listed:
            view = view._replace(aspect_ratio="", is_aspect_ratio_listed=False)

        if view.is_crop_ratio_listed:
            view = view._replace(
                crop=VideoCrop(0, 0, 0, 0), crop_ratio="", is_crop_ratio_listed=False
            )

        return view


class VideoTransform(AutoName):
    ROTATE_90 = auto()
    ROTATE_180 = auto()
    ROTATE_270 = auto()
    HFLIP = auto()
    VFLIP = auto()
    TRANSPOSE = auto()
    ANTITRANSPOSE = auto()
    NONE = auto()


# The transforms that turn the picture on its side. VLC 3 still hands the
# frame over at its unrotated size, with the turned picture squeezed into it.
ROTATION_TRANSFORMS = frozenset(
    {
        VideoTransform.ROTATE_90,
        VideoTransform.ROTATE_270,
        VideoTransform.TRANSPOSE,
        VideoTransform.ANTITRANSPOSE,
    }
)


class VideoDeinterlace(AutoName):
    AUTO = auto()
    ON = auto()
    OFF = auto()


class VideoDeinterlaceMode(AutoName):
    AUTO = auto()
    DISCARD = auto()
    BLEND = auto()
    MEAN = auto()
    BOB = auto()
    LINEAR = auto()
    X = auto()
    YADIF = auto()
    YADIF2X = auto()
    PHOSPHOR = auto()
    IVTC = auto()


class VideoEndAction(AutoName):
    LOOP_FILE = auto()
    NEXT_FILE = auto()
    PREVIOUS_FILE = auto()
    SHUFFLE_FILE = auto()
    PAUSE = auto()
    STOP = auto()
    CLOSE = auto()


# the end actions that go along a list, for a cell that plays one
LIST_STEP_END_ACTIONS = frozenset(
    {
        VideoEndAction.NEXT_FILE,
        VideoEndAction.PREVIOUS_FILE,
        VideoEndAction.SHUFFLE_FILE,
    }
)


class ListFailAction(AutoName):
    """What a cell playing a list does when a video of it won't play."""

    SHOW_ERROR = auto()
    PLAY_NEXT = auto()


# how long a failed item's error may be shown before the next one, in seconds
MAX_LIST_FAIL_WAIT_SEC = 300


class ListEndAction(AutoName):
    """What a cell does once it has played through its list.

    The list is over when Next would go round to its first item, Previous
    to its last, or a random one would start another round: every item
    played once.
    """

    START_OVER = auto()
    PAUSE = auto()
    STOP = auto()
    CLOSE = auto()


class AddMode(AutoName):
    """How files, folders and lists added together are put into cells."""

    # a cell for each file, and one for each folder and list, which plays
    # what is in it one after the other
    CELL_EACH = auto()
    # everything in one cell, one after the other
    ONE_CELL = auto()
    # a cell for every file, those in folders and lists as well
    CELL_PER_FILE = auto()
    ASK = auto()


class ListView(AutoName):
    """What the items of a list are shown by in its window."""

    TITLES = auto()
    # the title, and the file's path or the link under it
    TITLES_AND_LOCATIONS = auto()
    LOCATIONS = auto()
    # the video's picture, and its title with what its site says of it under
    # it: offered for lists read from a site that has pictures
    THUMBNAILS = auto()


class ListSourceKind(AutoName):
    """Where a list was read from, to read it again from."""

    FOLDER = auto()
    FILE = auto()
    URL = auto()


class ListUpdate(AutoName):
    """How often a linked list is read again from its source."""

    # each time the playlist is loaded, and not while it is open
    ON_LOAD = auto()
    # once what was read is this old: as the playlist is loaded, and
    # while it is open
    FIVE_MINUTES = auto()
    FIFTEEN_MINUTES = auto()
    HOURLY = auto()
    SIX_HOURS = auto()
    DAILY = auto()
    # only by Refresh
    MANUAL = auto()
    # a list's own: once what was read is as old as it says
    CUSTOM = auto()


class ListSort(AutoName):
    """An order a list was put in by what its items are, kept for a list
    read again from its source each time to be put in it again."""

    NAME = auto()
    LENGTH = auto()
    GROUP = auto()
    # most first
    VIEWS = auto()
    # newest first
    PUBLISHED = auto()
    SHUFFLE = auto()


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


class SponsorBlockMode(AutoName):
    """What becomes of a kind of segment SponsorBlock's users have marked."""

    # passed over as the video plays into it
    SKIP = auto()
    # marked on the seek bar and named under the mouse, and played through
    SHOW = auto()
    OFF = auto()


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


class SubtitleOutline(AutoName):
    """The rim drawn around every glyph, which is what keeps text readable.

    Named rather than measured in pixels because that is what VLC offers:
    it takes one of four thicknesses, and Normal is what it draws unless
    it is told otherwise.
    """

    NONE = auto()
    THIN = auto()
    NORMAL = auto()
    THICK = auto()


class CacheMode(AutoName):
    """Where what is kept to save downloading it again is kept."""

    # on disk, up to a size, for the next time the app runs
    DISK = auto()
    # in memory, gone when the app closes: nothing on disk
    MEMORY = auto()


class ColorScheme(AutoName):
    SYSTEM = auto()
    LIGHT = auto()
    DARK = auto()


class ScreenshotFormat(AutoName):
    PNG = auto()
    JPG = auto()


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
