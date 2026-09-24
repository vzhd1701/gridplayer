"""Where a screenshot goes, what it is called, and putting it there.

VLC hands the frame over as a PNG in a folder of its own (see
VlcPlayerBase.screenshot), since libVLC 3 writes nothing else. Moving it
to its place, cropping it and re-encoding it on the way where that is
asked for, is left to a pool thread: a 4K frame takes long enough to
decode and encode that doing it on the GUI thread would be a visible hitch.

File names come from a template in the style of mpv's screenshot-template,
cut down to the specifiers a grid of videos has a use for:

    %f   video name, as the player shows it
    %F   video name without its file extension
    %p   position in the video, HH-MM-SS
    %P   position in the video, HH-MM-SS.mmm
    %n   number, 0001 and up, the first one not taken yet
    %D   date now, 2026-09-24
    %T   date and time now, 2026-09-24_13-05-09
    %tX  date and time now, X being one of Y y m d H M S as in strftime
    %%   a percent sign

mpv's colon in %p has no place in a Windows file name, so it is a dash.
"""

import logging
import os
import re
import shutil
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QObject, QRect, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtGui import QImage, QImageReader

from gridplayer.params.static import ScreenshotFormat, VideoAspect, VideoCrop
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.aspect_calc import calc_crop_region, calc_view_borders

SCREENSHOTS_DIR_NAME = "screenshots"

DEFAULT_STEM = "screenshot"

TIME_SPECIFIERS = "YymdHMS"

# %D and %T, so the usual ways of putting a date in a file name need no
# spelling out; sorted as text, they sort by date too
DATE_FORMAT = "%Y-%m-%d"
DATE_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"

# longer than any video extension, short enough that "Part.2 of 3" keeps its tail
MAX_EXTENSION_LENGTH = 5

FORMAT_EXTENSIONS = {
    ScreenshotFormat.PNG: "png",
    ScreenshotFormat.JPG: "jpg",
}

# Well short of the 255 a name can have, leaving room for the extension and
# a " (N)" suffix, and for the folder on Windows, where the whole path is
# still held to 260 characters by most of what would open the file.
MAX_STEM_LENGTH = 150

# the video name is cut shorter still, so what the template puts after it,
# the %n above all, is not the part that goes
MAX_TITLE_LENGTH = 100

# How far %n counts, or " (N)" without it. Every number is one failed file
# open, which is quick, and a folder of more than this many screenshots
# of one name is somebody else's folder anyway.
MAX_NAME_TRIES = 100_000

# a specifier, or what is left of one at the end of the template
_SPECIFIER_RE = re.compile(r"%(t.?|.?)", re.DOTALL)

# forbidden on Windows, and the separators everywhere
_UNSAFE_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')

_WINDOWS_RESERVED_NAMES = frozenset(
    (
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    )
)


@dataclass(frozen=True)
class ScreenshotName:
    """What a file name is made from, before the number in it is known."""

    template: str
    title: str
    position_ms: int
    now: datetime

    @property
    def has_counter(self) -> bool:
        return has_counter(self.template)

    def stem(self, number: int = 1) -> str:
        return render_filename(
            self.template, self.title, self.position_ms, self.now, number
        )


def default_screenshots_dir() -> Path:
    return get_app_data_dir() / SCREENSHOTS_DIR_NAME


def screenshots_dir(setting_value: str) -> Path:
    """The folder a screenshot is saved in, for the folder setting as stored.

    Empty means the default, looked up now rather than stored, so it goes
    where the data folder is on the day: portable, moved by
    GP_USER_DATA_DIR, or the usual one.
    """

    setting_value = setting_value.strip()

    if not setting_value:
        return default_screenshots_dir()

    return Path(setting_value).expanduser()


def _is_known(specifier: str) -> bool:
    if specifier in {"f", "F", "p", "P", "n", "D", "T", "%"}:
        return True

    return (
        len(specifier) == 2 and specifier[0] == "t" and specifier[1] in TIME_SPECIFIERS
    )


def unknown_specifiers(template: str) -> list[str]:
    """The specifiers in a template that nothing fills in, as written."""

    return [
        f"%{match.group(1)}"
        for match in _SPECIFIER_RE.finditer(template)
        if not _is_known(match.group(1))
    ]


def has_counter(template: str) -> bool:
    return any(match.group(1) == "n" for match in _SPECIFIER_RE.finditer(template))


def position_txt(position_ms: int, with_ms: bool = True) -> str:
    """A video position as it can go into a file name: 01-02-03.456"""

    position_ms = max(0, int(position_ms))

    seconds, milliseconds = divmod(position_ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    position = f"{hours:02d}-{minutes:02d}-{seconds:02d}"

    if not with_ms:
        return position

    return f"{position}.{milliseconds:03d}"


def render_filename(
    template: str,
    title: str,
    position_ms: int,
    now: datetime,
    number: int = 1,
) -> str:
    """The file name, without an extension, a template gives for a frame.

    A specifier nothing fills in is left the way it was written, the same
    as a percent sign at the very end.
    """

    title = (title or "")[:MAX_TITLE_LENGTH]

    values = {
        "f": title,
        "F": _without_extension(title),
        "p": position_txt(position_ms, with_ms=False),
        "P": position_txt(position_ms),
        "n": f"{number:04d}",
        "D": now.strftime(DATE_FORMAT),
        "T": now.strftime(DATE_TIME_FORMAT),
        "%": "%",
    }

    def _fill(match):
        specifier = match.group(1)

        if not _is_known(specifier):
            return match.group(0)

        if specifier.startswith("t"):
            return now.strftime(f"%{specifier[1]}")

        return values[specifier]

    return sanitize_filename(_SPECIFIER_RE.sub(_fill, template))


def _without_extension(title: str) -> str:
    """The title short of what looks like a file extension on the end of it.

    Not os.path's idea of one: a title is as often a URL, and the slashes
    in that are no folders.
    """

    stem, dot, extension = title.rpartition(".")

    if dot and stem and extension.isalnum() and len(extension) <= MAX_EXTENSION_LENGTH:
        return stem

    return title


def sanitize_filename(name: str) -> str:
    """Make a name that can be a file name on every platform.

    A title is often a URL or whatever a site calls its stream, and it goes
    into the name as it is, so anything a file name cannot hold is replaced.
    """

    # before the unsafe ones, which would take a tab or a line break too
    name = re.sub(r"\s+", " ", name)
    name = _UNSAFE_CHARS_RE.sub("_", name)

    # Windows drops a trailing dot or space without a word, and the file
    # asked for is then not the one made
    name = name[:MAX_STEM_LENGTH].strip().rstrip(". ")

    if not name:
        return DEFAULT_STEM

    if name.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        name = f"_{name}"

    return name


def _candidate_paths(directory: Path, name: ScreenshotName, extension: str):
    if name.has_counter:
        for number in range(1, MAX_NAME_TRIES + 1):
            yield directory / f"{name.stem(number)}.{extension}"
        return

    stem = name.stem()

    for number in range(1, MAX_NAME_TRIES + 1):
        suffix = "" if number == 1 else f" ({number})"
        yield directory / f"{stem}{suffix}.{extension}"


def reserve_path(directory: Path, name: ScreenshotName, extension: str) -> Path:
    """Make an empty file under a name not taken yet, and return its path.

    The name is taken by creating the file, not by looking for it, so two
    screenshots saved at once can't both settle on the same one. That is
    what %n counts up with; a template without it gets " (2)" and on.
    """

    for path in _candidate_paths(directory, name, extension):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue

        os.close(fd)

        return path

    raise FileExistsError(f"No free file name for {name.stem()} in {directory}")


@dataclass(frozen=True)
class ScreenshotView:
    """How a frame is on show, for cutting a screenshot down to the same.

    Only frames drawn here need it. The hardware drivers have VLC crop the
    frame to the view, and its snapshot comes out cropped with it.
    """

    size: tuple[int, int]
    aspect: VideoAspect
    crop: VideoCrop

    def rect(self, width: int, height: int) -> QRect | None:
        """What of a frame this size the view keeps, None for all of it.

        Worked out for the frame as it is, not as it was on show: the
        buffer drawn from is padded out to what the decoder likes, which
        the PNG VLC writes is not.
        """

        if width <= 0 or height <= 0:
            return None

        borders = calc_view_borders((width, height), self.size, self.aspect, self.crop)

        if not any(borders):
            return None

        return QRect(*calc_crop_region((width, height), borders))


def save_screenshot(
    source: str | QImage,
    directory: Path,
    name: ScreenshotName,
    image_format: ScreenshotFormat,
    jpg_quality: int,
    view: ScreenshotView | None = None,
) -> Path:
    """Put a frame in the folder, as the format asked for.

    The source is a PNG file VLC wrote, or the frame itself where VLC could
    not give one. The view is what to cut it down to, where VLC left the
    cropping to us. A PNG file wanted as it is gets copied untouched.
    """

    directory.mkdir(parents=True, exist_ok=True)

    path = reserve_path(directory, name, FORMAT_EXTENSIONS[image_format])

    try:
        _write_frame(source, path, image_format, jpg_quality, view)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    return path


def _write_frame(
    source: str | QImage,
    path: Path,
    image_format: ScreenshotFormat,
    jpg_quality: int,
    view: ScreenshotView | None,
) -> None:
    is_file = isinstance(source, str)

    # the header is enough to tell whether there is anything to cut
    size = QImageReader(source).size() if is_file else source.size()

    rect = view.rect(size.width(), size.height()) if view is not None else None

    if is_file and image_format == ScreenshotFormat.PNG and rect is None:
        shutil.copyfile(source, path)
        return

    image = QImage(source) if is_file else source

    if image.isNull():
        raise OSError(f"Cannot read the frame from {source}")

    if rect is not None:
        image = image.copy(rect)

    extension = FORMAT_EXTENSIONS[image_format].upper()
    quality = jpg_quality if image_format == ScreenshotFormat.JPG else -1

    # False is all QImage says, whether the folder is not writable or,
    # in a build that left the plugin out, there is no JPG writer at all
    if not image.save(str(path), extension, quality):
        raise OSError(f"Cannot write {extension} image to {path}")


def remove_frame_file(frame_file: str) -> None:
    """Remove a PNG VLC wrote, along with the folder made for it."""

    Path(frame_file).unlink(missing_ok=True)

    with suppress(OSError):
        Path(frame_file).parent.rmdir()


class ScreenshotJob(QObject):
    """Saving one screenshot, off the GUI thread.

    The result comes back through the signals, which Qt delivers on the
    thread of whatever they are connected to.
    """

    saved = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        source: str | QImage,
        directory: Path,
        name: ScreenshotName,
        image_format: ScreenshotFormat,
        jpg_quality: int,
        view: ScreenshotView | None = None,
    ):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)

        self._source = source
        self._directory = directory
        self._name = name
        self._format = image_format
        self._jpg_quality = jpg_quality
        self._view = view

    def start(self) -> None:
        QThreadPool.globalInstance().start(_JobRunnable(self))

    def run(self) -> None:
        try:
            path = save_screenshot(
                self._source,
                self._directory,
                self._name,
                self._format,
                self._jpg_quality,
                self._view,
            )
        except Exception as err:
            self._log.error(f"Failed to save screenshot: {err}")
            self.failed.emit(str(err))
        else:
            self._log.info(f"Screenshot saved to {path}")
            self.saved.emit(str(path))
        finally:
            if isinstance(self._source, str):
                remove_frame_file(self._source)


class _JobRunnable(QRunnable):
    def __init__(self, job: ScreenshotJob):
        super().__init__()

        self._job = job

    def run(self):
        self._job.run()
