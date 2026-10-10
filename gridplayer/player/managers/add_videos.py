import contextlib
import functools
import itertools
import logging
import threading
from collections import deque
from pathlib import Path
from typing import NamedTuple

from pydantic import ValidationError
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QDialog, QFileDialog, qApp

from gridplayer.dialogs.add_choice import (
    AddChoiceDialog,
    AddOption,
    ManyCellsDialog,
    many_cells_txt,
)
from gridplayer.dialogs.add_urls import QAddURLsDialog
from gridplayer.models.media_list import (
    MediaList,
    item_of_video,
    list_step_action,
)
from gridplayer.models.video import Video
from gridplayer.models.video_uri import URL_ALLOWED_SCHEMES
from gridplayer.params.extensions import (
    SUPPORTED_AUDIO_EXT,
    SUPPORTED_MEDIA_EXT,
    SUPPORTED_VIDEO_EXT,
)
from gridplayer.params.static import (
    MANY_CELLS,
    AddMode,
    VideoEndAction,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.drop_zone import DropZone, adds_to_list
from gridplayer.utils.files import extract_mime_uris
from gridplayer.utils.folder_navigator import scan_rules
from gridplayer.utils.list_files import (
    LIST_FILE_EXT,
    MAX_LIST_FILE_BYTES,
    ListTooLargeError,
    decode_list_text,
    is_list_file_name,
    looks_like_list,
)
from gridplayer.utils.list_progress import ReadingStopped, Throttled, reading_txt
from gridplayer.utils.list_refresh import with_added
from gridplayer.utils.media_import import (
    Expanded,
    ListInput,
    choices_for,
    count_cells,
    expand_inputs,
    is_list_url,
    items_of,
    plan_cells,
    recent_uris,
)
from gridplayer.utils.misc import is_url
from gridplayer.utils.next_file import MAX_MISSING_FILES, ScanRules
from gridplayer.utils.off_thread import interface_first
from gridplayer.utils.qt import count_txt, translate
from gridplayer.utils.url_resolve.static import PLUGIN_URLS
from gridplayer.utils.web_lists import (
    is_web_list_url,
    read_web_list,
    video_in_list,
    without_list,
)

# how much of what a link to a list leads to is read before it is looked
# at, to stop there if it is no list: a live stream behind a link like a
# list's would otherwise be read for as long as it goes on
LIST_SNIFF_BYTES = 64 * 1024

# what the viewer picked in place of the ways to put things into cells
_ADD_TO_CELL = "add_to_cell"

# how long what is added is read before the viewer is shown how far it has
# got: what takes less is asked about, or put into cells, once it is read
SHOW_READING_AFTER_MS = 400

# a question put in the dialog already up, its answer still to come
_ASKING = "asking"

# what reading counts, of all that is added: the files of a folder and the
# items of a list, as opposed to the bytes of one being downloaded
_COUNTED = frozenset(("files", "items"))


class _Drop(NamedTuple):
    """Where on the grid things were dropped."""

    dst: object
    zone: object
    is_replace: bool


class _Request(NamedTuple):
    uris: list
    drop: _Drop | None


class _Reading:
    """What was added, read before it is put into cells: asked to stop, and
    nothing of it kept, or to end with what is found by then."""

    def __init__(self, request: _Request):
        self.request = request
        self.stop = threading.Event()
        self.enough = threading.Event()

        # thought better of: let go once the reading has stopped
        self.is_cancelled = False


class _Reader(QObject):
    """Reads what was added off the interface thread, says how far it has
    got, and says when done."""

    # what is told, how many, and of what, as reading_txt takes them; the
    # files and items counted are all those found so far
    progress = pyqtSignal(str, object, object)

    done = pyqtSignal(object, object)

    def read(self, reading: _Reading, rules: ScanRules, max_list_bytes: int) -> None:
        threading.Thread(
            target=self._read,
            args=(reading, rules, max_list_bytes),
            daemon=True,
            name="add-media",
        ).start()

    def _read(self, reading, rules, max_list_bytes):
        try:
            with interface_first():
                expanded = self._read_each(reading, rules, max_list_bytes)
        except ReadingStopped:
            expanded = Expanded()
        except Exception as e:
            logging.getLogger(__name__).exception("Failed to read what was added")
            expanded = Expanded(
                failed=tuple((uri, str(e)) for uri in reading.request.uris)
            )

        # (the player may be gone by the time a slow one is done)
        with contextlib.suppress(RuntimeError):
            self.done.emit(reading, expanded)

    def _read_each(self, reading, rules, max_list_bytes) -> Expanded:
        groups, failed = [], []
        found = 0

        for uri in reading.request.uris:
            if reading.stop.is_set():
                break

            # asked to end: what needs no reading is still added
            if reading.enough.is_set() and _is_read_slowly(uri):
                continue

            tell = Throttled(
                functools.partial(self._tell, found),
                stop=reading.stop,
                enough=reading.enough,
            )

            expanded = expand_inputs([uri], rules, **list_readers(tell, max_list_bytes))

            groups.extend(expanded.groups)
            failed.extend(expanded.failed)
            found += count_cells(expanded.groups, AddMode.CELL_PER_FILE)

        return Expanded(groups=tuple(groups), failed=tuple(failed))

    def _tell(self, found, what, count, of=None):
        # counted on from what was found of the things added before
        if what in _COUNTED:
            count += found

        with contextlib.suppress(RuntimeError):
            self.progress.emit(what, count, of)


class _CellReader(QObject):
    """Reads the lists cells wait for, off the interface thread, one cell's
    after another, and says how far each has got."""

    # the waiting cell's video id, what is told, how many, and of what: the
    # bytes downloaded of those there are to come, if that is known, or the
    # items read and how far through the list in percent; see reading_txt
    progress = pyqtSignal(object, str, object, object)

    # the waiting cell's video id, and what was read for it; None where
    # the cell waits no more, closed
    done = pyqtSignal(object, object)

    def read(self, cells: list[tuple], rules: ScanRules, max_list_bytes: int) -> None:
        threading.Thread(
            target=self._read,
            args=(cells, rules, max_list_bytes),
            daemon=True,
            name="add-media-cells",
        ).start()

    def _read(self, cells, rules, max_list_bytes):
        with interface_first():
            self._read_each(cells, rules, max_list_bytes)

    def _read_each(self, cells, rules, max_list_bytes):
        for video_id, uris, stop in cells:
            if stop.is_set():
                self.done.emit(video_id, None)
                continue

            tell = Throttled(
                lambda what, count, of=None, video_id=video_id: self.progress.emit(
                    video_id, what, count, of
                ),
                stop=stop,
            )

            try:
                expanded = expand_inputs(
                    uris, rules, **list_readers(tell, max_list_bytes)
                )
            except ReadingStopped:
                expanded = None
            except Exception as e:
                logging.getLogger(__name__).exception("Failed to read what was added")
                expanded = Expanded(failed=tuple((uri, str(e)) for uri in uris))

            self.done.emit(video_id, expanded)


def fetch_list_url(url: str, progress=None, max_bytes=None) -> bytes:
    """A list a link leads to, fetched the way the rest of the app reaches
    out, with the proxy and the user agent the settings ask for. progress
    is told how much has come so far, and of how much where the link says:
    ("bytes", count, expected or None).

    Raises ValueError for a list larger than max_bytes. What turns out not
    to be a list at all is read only as far as it takes to tell.
    """

    max_bytes = max_bytes or MAX_LIST_FILE_BYTES

    from streamlink import Streamlink

    from gridplayer.utils.network import (
        HTTPStatusError,
        configure_session,
        fetch_capped,
    )

    session = Streamlink()
    configure_session(session)

    on_read = None if progress is None else functools.partial(progress, "bytes")

    # a byte more than is kept, to tell a list cut short from one that fits
    status, data = fetch_capped(
        session,
        url,
        max_bytes + 1,
        on_read=on_read,
        keep_reading=_ListSoFar(),
    )

    if status >= 400:
        raise HTTPStatusError(status)

    if len(data) > max_bytes:
        raise ListTooLargeError(max_bytes)

    return data


class _ListSoFar:
    """Whether to go on reading: yes until enough is read to tell, and then
    only for what starts the way a list does. Told once: a channel list
    read on is told of after each chunk of hundreds of megabytes."""

    def __init__(self):
        self._is_list = None

    def __call__(self, read: bytearray) -> bool:
        if self._is_list is not None:
            return self._is_list

        if len(read) < LIST_SNIFF_BYTES:
            return True

        head = decode_list_text(bytes(read[:LIST_SNIFF_BYTES]), is_utf8=True)
        self._is_list = looks_like_list(head)

        return self._is_list


def list_readers(progress=None, max_bytes=None) -> dict:
    """How the lists behind links are read, for expand_inputs and
    read_source: each telling progress how far it has got, and none read
    that is larger than max_bytes."""

    return {
        "fetch": functools.partial(
            fetch_list_url, progress=progress, max_bytes=max_bytes
        ),
        "read_web": functools.partial(read_web_list, progress=progress),
        "progress": progress,
        "max_list_bytes": max_bytes,
    }


def list_read_limit() -> int:
    """The largest list to read, in bytes: the computer's memory being the
    same whatever playlist is open, one limit for all of them."""

    return Settings().get("player/list_max_mb") * 2**20


def _is_read_slowly(uri: str) -> bool:
    """Whether a thing added has to be read first, which may take a while:
    a folder, a list file, or a link to a list."""

    if is_url(uri):
        return is_list_url(uri) or is_web_list_url(uri)

    if is_list_file_name(uri):
        return True

    try:
        return Path(uri).is_dir()
    except OSError:
        return False


class AddVideosManager(ManagerBase):
    videos_added = pyqtSignal(list)

    error = pyqtSignal(str)
    warning = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._reader = _Reader(self)
        self._reader.progress.connect(self._tell_reading)
        self._reader.done.connect(self._read)

        self._cell_reader = _CellReader(self)
        self._cell_reader.progress.connect(self._tell_cell)
        self._cell_reader.done.connect(self._cell_read)

        # how many cells are still waiting for what is read for them
        self.cells_reading = 0

        # one add at a time, in the order they came: a second folder dropped
        # while the first is still being read, or asked about, goes after it
        self._requests: deque[_Request] = deque()
        self._is_reading = False
        self._is_cursor_busy = False

        # what is being read before it is put into cells, and how far it
        # has got, as last told
        self._reading: _Reading | None = None
        self._told: tuple | None = None

        # the dialog saying how far it has got, once it has taken a while,
        # and asking about it once it is read; what it asks about then, as
        # (request, expanded, groups)
        self._dialog: AddChoiceDialog | None = None
        self._asked: tuple | None = None

        self._show_reading_timer = QTimer(self)
        self._show_reading_timer.setSingleShot(True)
        self._show_reading_timer.setInterval(SHOW_READING_AFTER_MS)
        self._show_reading_timer.timeout.connect(self._show_reading)

    @property
    def commands(self):
        return {
            "add_videos": self.cmd_add_videos,
            "add_folder": self.cmd_add_folder,
            "add_urls": self.cmd_add_urls,
            "add_from_clipboard": self.cmd_add_from_clipboard,
            "is_clipboard_full": self.is_clipboard_full,
            "add_media": self.add_media,
            "read_for_cell": self.read_for_cell,
        }

    def cmd_add_videos(self):
        dialog = QFileDialog(
            parent=self.parent(),
            caption=translate("Dialog - Add Files", "Add Files", "Header"),
        )
        dialog.setFileMode(QFileDialog.ExistingFiles)

        dialog.setNameFilters(media_name_filters())

        if dialog.exec():
            self.add_media(dialog.selectedFiles())

    def cmd_add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            parent=self.parent(),
            caption=translate("Dialog - Add Folder", "Add Folder", "Header"),
        )

        if folder:
            self.add_media([folder])

    def cmd_add_urls(self):
        urls = QAddURLsDialog.get_urls(
            parent=self.parent(),
            title=translate("Dialog - Add URLs", "Add URL(s)", "Header"),
            supported_schemas=URL_ALLOWED_SCHEMES,
            supported_urls=PLUGIN_URLS,
        )

        valid_urls = [url for url in urls if is_url(url)]

        if urls and not valid_urls:
            self.error.emit(translate("Error", "No valid URLs found!"))

        if valid_urls:
            self.add_media(valid_urls)

    def cmd_add_from_clipboard(self):
        if not self.is_clipboard_full():
            return

        self.add_media(extract_mime_uris(qApp.clipboard().mimeData()))

    def is_clipboard_full(self):
        return bool(extract_mime_uris(qApp.clipboard().mimeData()))

    def add_media(self, uris, drop=None):
        """Put files, folders, list files and links into cells.

        A folder, a list file or a link to a list is read first, which may
        take a while, so it is read off the interface thread; anything else
        goes into its cell there and then. A drop says where on the grid,
        as (cell, zone, is the cell's video replaced); without one they go
        where added videos always went.
        """

        uris = self._videos_or_their_playlists([str(uri) for uri in uris])

        if not uris:
            return

        request = _Request(uris=uris, drop=None if drop is None else _Drop(*drop))

        self._requests.append(request)
        self._next_request()

    def _videos_or_their_playlists(self, uris):
        """A video opened from a playlist carries the playlist along in its
        link; whether the video alone is meant or the playlist is for the
        viewer to say. Left out, the viewer thinking better of it."""

        kept = []

        for uri in uris:
            if not (is_web_list_url(uri) and video_in_list(uri)):
                kept.append(uri)
                continue

            choice = AddChoiceDialog.ask(
                translate("Adding", "Add just this video, or its playlist?"),
                [uri],
                [
                    AddOption("video", translate("Adding", "Just this video")),
                    AddOption(
                        "playlist",
                        translate("Adding", "The whole playlist"),
                        about=translate(
                            "Adding", "Plays the playlist from this video."
                        ),
                    ),
                ],
                parent=self.parent(),
            )

            if choice == "video":
                kept.append(without_list(uri))
            elif choice == "playlist":
                kept.append(uri)

        return kept

    def _next_request(self):
        if self._is_reading or not self._requests:
            return

        request = self._requests.popleft()

        if not any(_is_read_slowly(uri) for uri in request.uris):
            self._place(request, expand_inputs(request.uris, scan_rules()))
            self._next_request()
            return

        if self._place_waiting(request):
            self._next_request()
            return

        self._is_reading = True
        self._is_cursor_busy = True
        QApplication.setOverrideCursor(Qt.BusyCursor)

        self._reading = _Reading(request)
        self._told = None
        self._reader.read(self._reading, scan_rules(), list_read_limit())
        self._show_reading_timer.start()

    def _show_reading(self):
        """What is added has taken a while to read: the viewer is shown how
        far it has got, with Stop, and asked about it once it is read."""

        reading = self._reading

        if reading is None or self._dialog is not None:
            return

        self._restore_cursor()

        uris = reading.request.uris
        is_asked = PlaylistSettings().get(
            "playlist/add_mode"
        ) == AddMode.ASK and not _is_onto_list(reading.request.drop)

        if is_asked:
            question = _question_txt(len(uris))
        else:
            question = translate("Adding", "Finding the videos to add…")

        dialog = AddChoiceDialog.reading(
            question, [_uri_name(uri) for uri in uris], is_asked, self.parent()
        )
        dialog.stop_asked.connect(reading.enough.set)
        dialog.finished.connect(functools.partial(self._dialog_closed, dialog))

        # as far as it had got before the dialog was up
        if self._told is not None:
            dialog.tell_reading(*reading_txt(*self._told))

        self._dialog = dialog
        dialog.open()

    def _tell_reading(self, what: str, count: int, of: int | None = None):
        self._told = (what, count, of)

        if self._dialog is not None:
            self._dialog.tell_reading(*reading_txt(what, count, of))

    def _dialog_closed(self, dialog, result):
        if dialog is not self._dialog:
            return

        self._dialog = None
        dialog.deleteLater()

        asked, self._asked = self._asked, None

        if asked is None:
            # thought better of as it was read: once it stops, it is let go
            if self._reading is not None:
                self._reading.is_cancelled = True
                self._reading.stop.set()
            return

        request, expanded, groups = asked
        choice = dialog.choice() if result == QDialog.Accepted else None

        if choice is not None:
            self._place_as(request, expanded, groups, choice)

        self._done_with_request()

    def _close_dialog(self):
        dialog, self._dialog = self._dialog, None

        if dialog is not None:
            dialog.done(QDialog.Rejected)
            dialog.deleteLater()

    def _restore_cursor(self):
        if self._is_cursor_busy:
            self._is_cursor_busy = False
            QApplication.restoreOverrideCursor()

    def _done_with_request(self):
        self._is_reading = False
        self._next_request()

    def _place_waiting(self, request: _Request) -> bool:
        """Cells put in at once for what has to be read first, each saying
        so with how far it has got, and playing what is read for it once it
        is. What needs no reading goes into its cell there and then.

        Only where it is known before reading how many cells there will be:
        a cell for each thing added, or one for them all. Where the viewer
        is asked, or each file gets a cell, it is not: False then, and they
        are read before any cell is put in, as before. Many cells are
        warned of first.
        """

        mode = PlaylistSettings().get("playlist/add_mode")

        # what goes on a cell's list has no cell of its own to wait in
        if mode not in {AddMode.CELL_EACH, AddMode.ONE_CELL} or _is_onto_list(
            request.drop
        ):
            return False

        if mode == AddMode.CELL_EACH and not self._is_added_anyway(len(request.uris)):
            return True

        rules = scan_rules()
        uris = request.uris

        if mode == AddMode.ONE_CELL and len(uris) > 1:
            waiting = _waiting_video(uris[0])
            videos, reads, failed, groups = [waiting], [(waiting, uris)], [], []
        else:
            videos, reads, failed, groups = [], [], [], []

            for uri in uris:
                if _is_read_slowly(uri):
                    waiting = _waiting_video(uri)
                    videos.append(waiting)
                    reads.append((waiting, [uri]))
                    continue

                expanded = expand_inputs([uri], rules)
                failed.extend(expanded.failed)

                for group in expanded.groups:
                    video = self._video_for(group)

                    if video is not None:
                        videos.append(video)
                        groups.append(group)

        videos = [video for video in videos if video is not None]

        stops = {
            waiting.id: self._ctx.lists.wait_for_list(waiting.id)
            for waiting, _uris in reads
            if waiting is not None
        }

        if videos:
            self._put_in_cells(videos, request.drop)

        # a full grid turns some away: what they waited for is not read
        to_read = []
        for waiting, read_uris in reads:
            if waiting is None:
                failed.extend((uri, "not a file") for uri in read_uris)
            elif self._ctx.video_blocks.by_video_id(waiting.id) is None:
                self._ctx.lists.stop_waiting(waiting.id)
            else:
                to_read.append((waiting.id, read_uris, stops[waiting.id]))

        if to_read:
            self.cells_reading += len(to_read)
            self._cell_reader.read(to_read, rules, list_read_limit())

        if groups:
            self._ctx.commands.add_recent_uris(recent_uris(groups))

        if failed:
            self.warning.emit(_failed_txt(failed))

        return True

    def _put_in_cells(self, videos, drop):
        if drop is None:
            self.videos_added.emit(videos)
        else:
            self._ctx.commands.layout_drop(
                videos, None, drop.dst, drop.zone, drop.is_replace
            )
            self._ctx.commands.activate_window()

        # a full grid turns some away, and their lists with them
        for video in videos:
            if self._ctx.video_blocks.by_video_id(video.id) is None:
                self._ctx.lists.drop_if_untaken(video.list_id)

    def read_for_cell(self, video: Video):
        """What a cell waits for read again: one saved with the playlist as
        it waited for a folder, a list file or a link to a list to be
        read, the playlist opened again."""

        stop = self._ctx.lists.wait_for_list(video.id)

        self.cells_reading += 1
        self._cell_reader.read(
            [(video.id, [str(video.uri)], stop)], scan_rules(), list_read_limit()
        )

    def _tell_cell(self, video_id, what: str, count: int, of: int | None = None):
        text, percent = reading_txt(what, count, of)

        self._ctx.lists.tell_waiting(video_id, text, percent)

    def _cell_read(self, video_id, expanded: Expanded):
        """What was read for a waiting cell put in it: the list played from
        its first item, or the one video it turned out to be. A cell closed
        meanwhile has nothing put in it; one that nothing could be read for
        is closed, and why is said."""

        self.cells_reading -= 1
        self._ctx.lists.stop_waiting(video_id)

        block = self._ctx.video_blocks.by_video_id(video_id)

        if expanded is None or block is None or block.is_closing:
            return

        # read: waiting for it no more, should the playlist be saved
        block.video_params.read_as_list = None

        groups = list(expanded.groups)

        if not groups:
            block.close()
            self.error.emit(_failed_txt(expanded.failed))
            return

        (group,) = plan_cells(groups, AddMode.ONE_CELL)

        if isinstance(group, ListInput):
            is_played = self._play_read_list(block, group)
        else:
            block.play_read(group.uri)
            is_played = True

        if is_played:
            self._ctx.commands.add_recent_uris(recent_uris(groups))

        if expanded.failed:
            self.warning.emit(_failed_txt(expanded.failed))

    def _play_read_list(self, block, read: ListInput) -> bool:
        """The list played in the cell from the first item there is of it,
        from where it says to start; False where there is none, and the
        cell goes."""

        first = _first_playable(read)

        if first is None:
            block.close()
            self.error.emit(translate("Error", "No supported files or URLs!"))
            return False

        media_list = self._ctx.lists.add(
            MediaList.read_from(read.name, read.items, read.source)
        )
        self._tell_added(media_list)

        block.take_list(media_list.id, first)
        block.play_list_item(first)

        return True

    def _read(self, reading, expanded):
        self._reading = None
        self._show_reading_timer.stop()
        self._restore_cursor()

        if reading.is_cancelled:
            self._done_with_request()
            return

        if self._dialog is None:
            self._place(reading.request, expanded)
            self._done_with_request()
            return

        groups = list(expanded.groups)

        if not groups:
            self._close_dialog()

            # stopped before anything was found, there is nothing to tell
            if not reading.enough.is_set():
                self.error.emit(_failed_txt(expanded.failed))

            self._done_with_request()
            return

        choice = self._add_mode(groups, reading.request.drop, ask=self._ask_in_dialog)

        if choice == _ASKING:
            self._asked = (reading.request, expanded, groups)
            return

        self._close_dialog()

        if choice is not None:
            self._place_as(reading.request, expanded, groups, choice)

        self._done_with_request()

    def _place(self, request: _Request, expanded: Expanded):
        groups = list(expanded.groups)

        if not groups:
            self.error.emit(_failed_txt(expanded.failed))
            return

        choice = self._add_mode(groups, request.drop)

        if choice is not None:
            self._place_as(request, expanded, groups, choice)

    def _place_as(self, request: _Request, expanded: Expanded, groups, choice):
        if choice == _ADD_TO_CELL:
            self._add_to_cell(request.drop.dst, groups)
            is_opened = True
        else:
            is_opened = self._open_in_cells(plan_cells(groups, choice), request.drop)

        # a file not found is none to open again
        if is_opened:
            self._ctx.commands.add_recent_uris(
                recent_uris(group for group in groups if _is_openable(group))
            )

        if expanded.failed:
            self.warning.emit(_failed_txt(expanded.failed))

    def _add_mode(self, groups, drop, ask=None):
        """How to put the groups into cells, as the playlist says or as the
        viewer picks; None for none at all, the viewer thinking better of
        it. Where the playlist says how, many cells are warned of first.

        ask is what asks the viewer, as _ask does, and what it answers is
        what this does."""

        ask = ask or self._ask

        # dropped in the middle of a cell playing a list: on its list, as
        # the drop showed, however the playlist says to add
        if _is_onto_list(drop):
            return _ADD_TO_CELL

        mode = PlaylistSettings().get("playlist/add_mode")
        target = _video_cell_dropped_in(drop)

        if mode != AddMode.ASK:
            if not self._is_added_anyway(count_cells(groups, mode)):
                return None

            return mode

        choices = choices_for(groups)

        # one way, and no cell to add them to instead: nothing to ask
        if len(choices) == 1 and target is None:
            return choices[0]

        return ask(groups, choices, target)

    def _ask(self, groups, choices, target):
        question = self._question(groups, choices, target)

        return AddChoiceDialog.ask(
            question.question, question.what, question.options, self.parent()
        )

    def _ask_in_dialog(self, groups, choices, target):
        """Asked in the dialog that is up, saying how far reading has got:
        the answer comes once the viewer gives it."""

        question = self._question(groups, choices, target)

        self._dialog.set_question(question.question, question.what, question.options)

        return _ASKING

    def _question(self, groups, choices, target):
        """What the viewer is asked of the groups: how to put them into
        cells, a way that adds many warned of under it."""

        free = self._ctx.commands.grid_free_capacity()
        options = [
            _warned(option, groups, free)
            for option in add_options(groups, choices, target, free)
        ]
        what = [_name_of(group) for group in groups]

        return _Question(_question_txt(len(groups)), what, options)

    def _is_added_anyway(self, count: int) -> bool:
        """Whether this many cells are added: many are warned of first, the
        dialog saying how far reading has got out of the way. Don't warn
        again, ticked as they are added, is for this playlist and those
        after it."""

        free = self._ctx.commands.grid_free_capacity()
        cells = count if free is None else min(count, free)

        if not _is_warned_of(cells):
            return True

        self._close_dialog()

        is_added, is_warned_again = ManyCellsDialog.ask(cells, self.parent())

        if is_added and not is_warned_again:
            Settings().set("playlist/warn_many_cells", False)

            if PlaylistSettings().is_overridden("playlist/warn_many_cells"):
                PlaylistSettings().set("playlist/warn_many_cells", False)

        return is_added

    def _open_in_cells(self, cells, drop) -> bool:
        videos = [video for video in map(self._video_for, cells) if video is not None]

        if not videos:
            self.error.emit(translate("Error", "No supported files or URLs!"))
            return False

        self._put_in_cells(videos, drop)

        return True

    def _video_for(self, cell) -> Video | None:
        """The video for a cell to play: a file or link of its own, or the
        first item there is of a list."""

        if not isinstance(cell, ListInput):
            return _video(cell.uri, title=cell.title, http_headers=cell.http_headers)

        first = _first_playable(cell)

        if first is None:
            return None

        media_list = self._ctx.lists.add(
            MediaList.read_from(cell.name, cell.items, cell.source)
        )
        self._tell_added(media_list)

        return _video(
            cell.items[first].uri,
            list_id=media_list.id,
            list_index=first,
            end_action=list_end_action(),
        )

    def _add_to_cell(self, block, groups):
        """The groups' files and links on the list of the cell they were
        dropped on, after what it has; a cell with no list gets one, the
        video it plays first on it."""

        items = tuple(items_of(groups))
        media_list = block.media_list

        if media_list is not None:
            media_list, added = with_added(media_list, items)

            self._ctx.lists.put(media_list)
            self._ctx.lists.tell_added(media_list.id, [item.key for item in added])
            block.tell_added_to_list(len(added))
            return

        params = block.video_params

        media_list = self._ctx.lists.add(
            MediaList(
                name=params.uri_name,
                items=(item_of_video(params), *items),
            )
        )
        self._tell_added(media_list)

        block.take_list(media_list.id, 0)
        block.tell_added_to_list(len(items))

    def _tell_added(self, media_list):
        """A list made of what was added: its items, for what is known of
        them to be looked up, where the playlist says to."""

        self._ctx.lists.tell_added(
            media_list.id, [item.key for item in media_list.items]
        )


class _Question(NamedTuple):
    question: str
    what: list
    options: list


def _question_txt(count: int) -> str:
    if count == 1:
        return translate("Adding", "How should this be added?")

    return translate("Adding", "How should these be added?")


def _is_warned_of(cells: int) -> bool:
    """Whether adding this many cells at once is warned of: more than
    MANY_CELLS, where the playlist says to warn."""

    return cells > MANY_CELLS and PlaylistSettings().get("playlist/warn_many_cells")


def _warned(option, groups, free):
    """An option that adds many cells, saying what that can do."""

    if option is None or option.data == _ADD_TO_CELL:
        return option

    cells = count_cells(groups, option.data)
    cells = cells if free is None else min(cells, free)

    if not _is_warned_of(cells):
        return option

    return option._replace(warning=many_cells_txt(cells))


def _uri_name(uri: str) -> str:
    """What is being added, as the viewer is told it before it is read: a
    file or folder by its name, a link as it is."""

    if is_url(uri):
        return uri

    return Path(uri).name or uri


def list_end_action() -> VideoEndAction:
    """What a cell made to play a list does at the end of each item: what
    it is set to by default, where that goes along the list, else on to the
    next."""

    # a cell made to play a list goes along it, whatever a cell playing
    # one file is set to do by default
    return list_step_action(PlaylistSettings().get("video_defaults/end_action"))


def _video(uri, **fields) -> Video | None:
    try:
        return Video(uri=uri, **{k: v for k, v in fields.items() if v is not None})
    except ValidationError:
        return None


def _first_playable(read: ListInput) -> int | None:
    """The place of the first item there is of a list, from where it says
    to start; None for none."""

    return next(
        (
            index
            for index in _places_to_try(len(read.items), read.start)
            if _video(read.items[index].uri) is not None
        ),
        None,
    )


def _places_to_try(count: int, start: int):
    """The places on a list from start on, round to it, to look for the
    first item there is at: no more than MAX_MISSING_FILES, each looked
    for on the interface thread, and a list of a drive not plugged in all
    gone."""

    start = start if 0 <= start < count else 0
    places = itertools.chain(range(start, count), range(start))

    return itertools.islice(places, MAX_MISSING_FILES)


def _is_openable(group) -> bool:
    """Whether a thing added can be put into a cell: a list, or a file
    there or a link."""

    return isinstance(group, ListInput) or _video(group.uri) is not None


def _waiting_video(uri: str) -> Video | None:
    """The video of a cell waiting for what is read from uri: a link or a
    list file as it is, a folder by its path as text, never loaded as it
    is while the cell waits. Named after where it is read from."""

    if is_url(uri):
        return _video(uri, read_as_list=True)

    path = Path(uri)

    return _video(path if path.is_file() else str(path), read_as_list=True)


def _cell_dropped_on(drop):
    """The cell with a video things were dropped on, None for none, or for
    an empty one."""

    if drop is None or drop.dst is None:
        return None

    if getattr(drop.dst, "is_empty_cell", False):
        return None

    return drop.dst if getattr(drop.dst, "video_params", None) is not None else None


def _is_onto_list(drop) -> bool:
    """Whether what was dropped goes on the list of the cell it was dropped
    in the middle of."""

    return drop is not None and adds_to_list(drop.dst, drop.zone, drop.is_replace)


def _video_cell_dropped_in(drop):
    """The cell playing a video of its own, not a list, things were dropped
    in the middle of, its video kept: to be offered to play them after it.
    None for none."""

    target = _cell_dropped_on(drop)

    if (
        target is None
        or drop.zone != DropZone.CENTER
        or drop.is_replace
        or target.media_list is not None
    ):
        return None

    return target


def add_options(groups, choices, target, free) -> list:
    """The ways to put the groups into cells, as the viewer is offered
    them: each with how many cells it takes, and whether that many fit,
    free the cells there are room for, None for no end to them.

    target is the cell playing a video of its own they were dropped in the
    middle of, offered to play them after it, after a gap; None for none.
    """

    options = [_mode_option(groups, mode, free) for mode in choices]

    # one file, asked of only where it may go in the cell it was dropped on
    if len(groups) == 1 and not isinstance(groups[0], ListInput):
        title = translate("Adding", "In a cell of its own")
        options = [option._replace(title=title) for option in options]

    if target is None:
        return options

    to_cell = AddOption(
        _ADD_TO_CELL,
        translate("Adding", "Play in this cell, after its video"),
        about=translate("Adding", "Makes a list that starts with its video."),
    )

    return [*options, None, to_cell]


def _mode_option(groups, mode, free) -> AddOption:
    cells = count_cells(groups, mode)
    lists = [group for group in groups if isinstance(group, ListInput)]

    if mode == AddMode.ONE_CELL:
        return AddOption(
            mode,
            translate("Adding", "One cell for everything"),
            about=translate("Adding", "Plays all {COUNT} videos as a list.").format(
                COUNT=count_txt(count_cells(groups, AddMode.CELL_PER_FILE))
            ),
        )

    if mode == AddMode.CELL_PER_FILE:
        option = AddOption(
            mode,
            translate("Adding", "A cell for each video"),
            about=translate("Adding", "Including videos inside folders and playlists."),
        )
    elif not lists:
        option = AddOption(mode, translate("Adding", "A cell for each video"))
    elif len(groups) == 1:
        option = AddOption(
            mode,
            translate("Adding", "One cell"),
            about=translate("Adding", "Plays them as a list."),
        )
    else:
        option = AddOption(
            mode,
            translate("Adding", "A cell for each file, folder and playlist"),
            about=translate(
                "Adding",
                "A folder or playlist plays as a list.",
            ),
        )

    if cells < 2:
        return option

    if free is not None and cells > free:
        note = translate("Adding", "{COUNT} cells, only {FREE} fit").format(
            COUNT=count_txt(cells), FREE=count_txt(free)
        )
    else:
        note = translate("Adding", "{COUNT} cells").format(COUNT=count_txt(cells))

    return option._replace(note=note)


def _name_of(group) -> str:
    """What is being added, as the viewer is told it: a list by its name and
    how much is on it, a file by its own."""

    if isinstance(group, ListInput):
        return translate("Adding", "{NAME} — {COUNT} items").format(
            NAME=group.name, COUNT=count_txt(len(group.items))
        )

    return group.title or group.uri_name


def _failed_txt(failed) -> str:
    if not failed:
        return translate("Error", "No supported files or URLs!")

    lines = [f"{where}\n    {why}" for where, why in failed[:_FAILED_LISTED]]

    if len(failed) > _FAILED_LISTED:
        lines.append(
            translate("Adding", "and {COUNT} more").format(
                COUNT=len(failed) - _FAILED_LISTED
            )
        )

    return "{}\n\n{}".format(
        translate("Adding", "Could not be read:"), "\n".join(lines)
    )


# how many of the things that could not be read are named
_FAILED_LISTED = 5


def media_name_filters() -> list[str]:
    ext_types = [
        {
            "name": translate("Dialog - Add Files", "Media", "File formats"),
            "extensions": SUPPORTED_MEDIA_EXT | LIST_FILE_EXT,
        },
        {
            "name": translate("Dialog - Add Files", "Video", "File formats"),
            "extensions": SUPPORTED_VIDEO_EXT,
        },
        {
            "name": translate("Dialog - Add Files", "Audio", "File formats"),
            "extensions": SUPPORTED_AUDIO_EXT,
        },
        {
            "name": translate("Dialog - Add Files", "Playlists", "File formats"),
            "extensions": LIST_FILE_EXT,
        },
        {
            "name": translate("Dialog - Add Files", "All", "File formats"),
            "extensions": {"*"},
        },
    ]

    name_filers = []

    for ext_type in ext_types:
        ext_with_asterisk = (f"*.{e}" for e in sorted(ext_type["extensions"]))
        ext_list = " ".join(ext_with_asterisk)
        name_filers.append(f"{ext_type['name']} ({ext_list})")

    return name_filers
