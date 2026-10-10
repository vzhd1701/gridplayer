import weakref
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QDir, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.playlist_settings import PlaylistSettingsDialog
from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist, UnsupportedPlaylistVersion
from gridplayer.params.static import SeekSyncMode, UnsavedChangesMode, WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import (
    PlaylistSettings,
    grid_overrides_from_state,
    grid_state_for_dump,
    overrides_from_playlist,
)
from gridplayer.settings import Settings
from gridplayer.utils.files import get_playlist_path
from gridplayer.utils.qt import is_modal_open, translate

_TITLE_REFRESH_MS = 500

# how often files sent from outside look for the dialog they wait on to close
_ARGUMENTS_WAIT_MS = 250


class PlaylistManager(ManagerBase):
    playlist_closed = pyqtSignal()
    playlist_file_loaded = pyqtSignal(Path)
    playlist_saved = pyqtSignal(Path)
    window_state_loaded = pyqtSignal(WindowState)
    grid_state_loaded = pyqtSignal(GridState)
    snapshots_loaded = pyqtSignal(dict)
    # the files' bookmarks, and the ids of the videos about to open
    bookmarks_loaded = pyqtSignal(list, list)
    # the lists the cells play from
    lists_loaded = pyqtSignal(list)
    bookmarks_shared_loaded = pyqtSignal(bool)
    seek_sync_mode_loaded = pyqtSignal(SeekSyncMode)
    view_sync_loaded = pyqtSignal(bool)
    pause_sync_loaded = pyqtSignal(bool)
    rate_sync_loaded = pyqtSignal(bool)
    shuffle_on_load_loaded = pyqtSignal(bool)
    disable_mouse_click_events_loaded = pyqtSignal(bool)
    disable_mouse_wheel_events_loaded = pyqtSignal(bool)
    disable_overlay_loaded = pyqtSignal(bool)
    pause_background_videos_loaded = pyqtSignal(bool)
    pause_minimized_loaded = pyqtSignal(bool)
    show_overlay_border_loaded = pyqtSignal(bool)
    overlay_hide_on_timeout_loaded = pyqtSignal(bool)
    overlay_timeout_loaded = pyqtSignal(int)
    subtitle_encoding_loaded = pyqtSignal(str)
    videos_loaded = pyqtSignal(list)

    alert = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_shuffle_on_load = Settings().get("playlist/shuffle_on_load")

        self._saved_playlist_path: Path | None = None
        self._saved_playlist_state: tuple | None = None

        self._title_timer = QTimer(self)
        self._title_timer.setInterval(_TITLE_REFRESH_MS)
        self._title_timer.timeout.connect(self.update_window_title)

        # files and playlists sent from outside while a dialog was open
        self._waiting_arguments: list[list[str]] = []
        self._arguments_timer = QTimer(self)
        self._arguments_timer.setInterval(_ARGUMENTS_WAIT_MS)
        self._arguments_timer.timeout.connect(self._process_waiting_arguments)

    def init(self):
        self._set_saved_playlist(None)

    @property
    def commands(self):
        return {
            "open_playlist": self.cmd_open_playlist,
            "save_playlist": self.cmd_save_playlist,
            "save_playlist_as": self.cmd_save_playlist_as,
            "close_playlist": self.cmd_close_playlist,
            "force_close_playlist": self.cmd_force_close_playlist,
            "check_playlist_save": self.check_playlist_save,
            "is_playlist_changed": self._is_playlist_changed,
            "is_playlist_saved": lambda: self._saved_playlist_path is not None,
            "is_shuffle_on_load": lambda: self._ctx.is_shuffle_on_load,
            "set_shuffle_on_load": self.set_shuffle_on_load,
            "toggle_shuffle_on_load": self.toggle_shuffle_on_load,
            "playlist_settings": self.cmd_playlist_settings,
            "remember_last_playlist": self.remember_last_playlist,
        }

    def remember_last_playlist(self) -> None:
        """Keep the playlist file that is open as the player closes.

        Synced here because the player ends with os._exit, which leaves
        nothing to write what QSettings still has pending.
        """

        path = self._saved_playlist_path

        if path is None or not Settings().get("player/reopen_last_playlist"):
            Settings().set("last_playlist", "")
        else:
            Settings().set("last_playlist", str(path))

        Settings().sync()

    def restore_last_playlist(self) -> None:
        """Open the playlist that was open when the player was last closed.

        Not over anything opened meanwhile, such as a file sent from the
        file manager. Forgotten before it opens, and remembered again on a
        clean close: a playlist that brings the player down would otherwise
        bring it down on every start.
        """

        if not Settings().get("player/reopen_last_playlist"):
            return

        last_playlist = Settings().get("last_playlist")

        if not last_playlist:
            return

        if self._saved_playlist_path is not None or self._ctx.video_blocks:
            return

        path = Path(last_playlist)

        # a drive that isn't there today is no reason for an error on start
        if not path.is_file():
            self._log.info(f"Last playlist not found: {path}")
            return

        Settings().set("last_playlist", "")
        Settings().sync()

        self.load_playlist_file(path)

    def set_shuffle_on_load(self, is_shuffle_on_load):
        self._ctx.is_shuffle_on_load = is_shuffle_on_load

    def toggle_shuffle_on_load(self):
        self._ctx.is_shuffle_on_load = not self._ctx.is_shuffle_on_load
        PlaylistSettings().set("playlist/shuffle_on_load", self._ctx.is_shuffle_on_load)

    def cmd_playlist_settings(self):
        dialog = PlaylistSettingsDialog(
            overrides=PlaylistSettings().as_dict(),
            grid_state=self._ctx.grid_state,
            parent=self.parent(),
        )
        if not dialog.exec_():
            return
        PlaylistSettings().replace(
            self._with_bookmarks_sharing_confirmed(dialog.result_overrides())
        )
        self._apply_effective_session()
        self._ctx.commands.apply_grid_config(
            dialog.result_grid_state(self._ctx.grid_state)
        )

    def _with_bookmarks_sharing_confirmed(self, overrides: dict) -> dict:
        """The overrides, but for the bookmarks' sharing where the viewer
        thought better of the change: those stay as they are."""

        key = "playlist/bookmarks_shared"
        is_shared = overrides.get(key, Settings().get(key))

        if self._ctx.commands.confirm_bookmarks_shared(is_shared):
            return overrides

        return {**overrides, key: not is_shared}

    def cmd_open_playlist(self):
        dialog = QFileDialog(
            parent=self.parent(),
            caption=translate("Dialog - Open Playlist", "Open Playlist", "Header"),
        )
        dialog.setFileMode(QFileDialog.ExistingFile)

        dialog.setNameFilter(
            "{} (*.gpls)".format(
                translate(
                    "Dialog - Open Playlist", "GridPlayer Playlists", "File format"
                )
            )
        )

        if dialog.exec():
            files = dialog.selectedFiles()

            if files:
                self.load_playlist_file(Path(files[0]))

    def cmd_close_playlist(self) -> bool:
        """Ask about unsaved changes, then close the playlist."""
        if not self.check_playlist_save():
            return False

        self.cmd_force_close_playlist()

        return True

    def cmd_force_close_playlist(self) -> None:
        """Close the playlist without asking about unsaved changes.

        For callers that have already asked: closing the window asks first so
        that it can go off screen before the video players are torn down, and
        asking again here would prompt twice after a Discard.
        """
        self.playlist_closed.emit()
        self._reset_playlist_session()
        self._set_saved_playlist(None)

    def cmd_save_playlist(self) -> bool:
        playlist = self._make_playlist()

        if self._saved_playlist_path is not None:
            return self._write_playlist(playlist, self._saved_playlist_path)

        return self._save_playlist_via_dialog(playlist)

    def cmd_save_playlist_as(self) -> bool:
        return self._save_playlist_via_dialog(self._make_playlist())

    def update_window_title(self) -> None:
        window = self.parent()

        if self._saved_playlist_path is None:
            if window.windowFilePath():
                window.setWindowFilePath("")
            window.setWindowModified(False)
            return

        file_path = str(self._saved_playlist_path)
        if window.windowFilePath() != file_path:
            window.setWindowFilePath(file_path)

        window.setWindowModified(self._is_playlist_changed())

    def process_arguments(self, argv):
        if not argv:
            return

        # Sent from outside while a dialog is open, as a file opened from the
        # file manager is, they wait for it to close, as a drop does: a
        # playlist opened under a dialog leaves it working on one gone.
        if is_modal_open():
            self._waiting_arguments.append(argv)
            self._arguments_timer.start()
            self.alert.emit()
            return

        playlist = get_playlist_path(argv)

        if playlist:
            self.load_playlist_file(playlist)
            return

        self._ctx.commands.add_media(argv)
        self.alert.emit()

    def _process_waiting_arguments(self):
        if is_modal_open():
            return

        self._arguments_timer.stop()

        waiting, self._waiting_arguments = self._waiting_arguments, []

        for argv in waiting:
            self.process_arguments(argv)

    def load_playlist_file(self, playlist_file: Path):
        try:
            playlist = Playlist.read(playlist_file)
        except UnsupportedPlaylistVersion as e:
            self._log.error(f"Playlist parse error: {e}")
            self.error.emit(
                "{}\n\n{}".format(
                    translate(
                        "Error",
                        "This playlist was saved with a newer GridPlayer",
                    ),
                    playlist_file,
                )
            )
            return
        except ValueError as e:
            self._log.error(f"Playlist parse error: {e}")
            self.error.emit(
                "{}\n\n{}".format(
                    translate("Error", "Invalid playlist format!"), playlist_file
                )
            )
            return
        except FileNotFoundError:
            self.error.emit(
                "{}\n\n{}".format(translate("Error", "File not found!"), playlist_file)
            )
            return

        if not self.load_playlist(playlist):
            return

        self._set_saved_playlist(playlist_file)

        self.playlist_file_loaded.emit(playlist_file)

    def load_playlist(self, playlist: Playlist):
        if not self.cmd_close_playlist():
            return False

        overrides = overrides_from_playlist(playlist)
        overrides.update(grid_overrides_from_state(playlist.grid_state))
        PlaylistSettings().replace(overrides)
        self._apply_effective_session()

        # in place before the videos, for each to find its own as it opens
        self.lists_loaded.emit(list(playlist.lists or []))
        self.bookmarks_loaded.emit(
            list(playlist.bookmarks or []),
            [video.id for video in playlist.videos or []],
        )

        self.grid_state_loaded.emit(playlist.grid_state)
        self.videos_loaded.emit(list(playlist.videos or []))

        _emit_if_not_empty(
            (self.window_state_loaded, playlist.window_state),
            (self.snapshots_loaded, playlist.snapshots),
        )

        if playlist.shuffle_on_load and playlist.videos:
            self._ctx.commands.shuffle_layout()

        self.alert.emit()

        return True

    def check_playlist_save(self) -> bool:
        if not self._is_playlist_changed():
            return True

        mode = PlaylistSettings().get("playlist/unsaved_changes")

        if mode == UnsavedChangesMode.DISCARD:
            return True

        if mode in (
            UnsavedChangesMode.AUTO_SAVE_DISCARD,
            UnsavedChangesMode.AUTO_SAVE_ASK,
        ):
            if self._saved_playlist_path is not None:
                if self.cmd_save_playlist():
                    return True
                return self._ask_playlist_save()

            if mode == UnsavedChangesMode.AUTO_SAVE_DISCARD:
                return True

        return self._ask_playlist_save()

    def _ask_playlist_save(self) -> bool:
        self.alert.emit()

        ret = QCustomMessageBox.cancellable_question(
            self.parent(),
            translate("Dialog - Playlist close", "Playlist", "Header"),
            translate("Dialog - Playlist close", "Do you want to save the playlist?"),
        )

        if ret == QMessageBox.Yes:
            return self.cmd_save_playlist()

        return ret != QMessageBox.Cancel

    def _is_playlist_changed(self):
        if self._saved_playlist_state is None:
            return False

        return not _is_same_state(self._playlist_state(), self._saved_playlist_state)

    def _playlist_state(self) -> tuple:
        """What the playlist is now, to tell a change from: the lists by the
        lists themselves, the rest by what it would be written as.

        A list is a new one whenever it is edited, so the same list is the
        same contents; writing out its items each time to compare them took
        seconds for a channel list, and the menu and the window title ask.

        A linked list by what the playlist keeps of it, the few items the
        viewer did something to: read again as the playlist opens, it is
        another list, but the playlist is not changed by that. Nor by where
        on it its cells are now: the same item is at another place once its
        source has more or less, or could not be read, and is found by what
        it is.
        """

        playlist = self._make_playlist()
        lists = tuple(playlist.lists_as_saved())

        linked = {media_list.id for media_list in lists if media_list.is_linked}
        videos = [
            video.model_copy(update={"list_index": None})
            if video.list_id in linked
            else video
            for video in playlist.videos or []
        ]

        rest = playlist.model_copy(update={"lists": None, "videos": videos}).dumps()

        return hash(rest), lists

    def _save_playlist_via_dialog(self, playlist: Playlist) -> bool:
        if self._saved_playlist_path is not None:
            save_path = self._saved_playlist_path
        else:
            save_path = Path(QDir.homePath()) / "Untitled.gpls"

        self._log.debug(f"Proposed playlist save path: {save_path}")

        file_path, _ = QFileDialog.getSaveFileName(
            parent=self.parent(),
            caption=translate("Dialog - Save Playlist", "Save Playlist", "Header"),
            directory=str(save_path),
            filter="*.gpls",
        )

        if not file_path:
            return False

        file_path = Path(file_path)

        # filename placeholder is not available if file doesn't exist
        # problematic for new playlists, need to prevent accidental overwrite
        # occurs in Flatpak, maybe in other sandboxes that use portal
        if file_path.suffix.lower() != ".gpls":
            file_path = file_path.with_suffix(".gpls")

            if self._is_overwrite_denied(file_path):
                return False

        return self._write_playlist(playlist, file_path)

    def _write_playlist(self, playlist: Playlist, file_path: Path) -> bool:
        try:
            playlist.save(file_path)
        except OSError as e:
            self._log.error(f"Playlist save error: {e}")
            self.error.emit(
                "{}\n\n{}".format(
                    translate("Error", "Failed to save playlist!"), file_path
                )
            )
            return False

        # those of the cells closed meanwhile were left out of it
        self._ctx.commands.forget_bookmarks_of_cells_gone()
        self._ctx.commands.forget_left_lists()

        self._set_saved_playlist(file_path)

        self.playlist_saved.emit(file_path)

        return True

    def _reset_playlist_session(self) -> None:
        PlaylistSettings().clear()
        self._apply_effective_session()
        self.grid_state_loaded.emit(GridState())

    def _apply_effective_session(self) -> None:
        session = PlaylistSettings()
        with session.suppress_capture():
            _emit(
                (
                    self.bookmarks_shared_loaded,
                    session.get("playlist/bookmarks_shared"),
                ),
                (
                    self.seek_sync_mode_loaded,
                    session.get("playlist/seek_sync_mode"),
                ),
                (self.view_sync_loaded, session.get("playlist/view_sync")),
                (self.pause_sync_loaded, session.get("playlist/pause_sync")),
                (self.rate_sync_loaded, session.get("playlist/rate_sync")),
                (
                    self.shuffle_on_load_loaded,
                    session.get("playlist/shuffle_on_load"),
                ),
                (
                    self.disable_mouse_click_events_loaded,
                    session.get("playlist/disable_mouse_click_events"),
                ),
                (
                    self.disable_mouse_wheel_events_loaded,
                    session.get("playlist/disable_mouse_wheel_events"),
                ),
                (
                    self.disable_overlay_loaded,
                    session.get("playlist/disable_overlay"),
                ),
                (
                    self.pause_background_videos_loaded,
                    session.get("playlist/pause_background_videos"),
                ),
                (
                    self.pause_minimized_loaded,
                    session.get("playlist/pause_minimized"),
                ),
                (
                    self.show_overlay_border_loaded,
                    session.get("playlist/show_overlay_border"),
                ),
                (
                    self.overlay_hide_on_timeout_loaded,
                    session.get("playlist/overlay_hide_on_timeout"),
                ),
                (
                    self.overlay_timeout_loaded,
                    session.get("playlist/overlay_timeout"),
                ),
                (
                    self.subtitle_encoding_loaded,
                    session.get("video_defaults/subtitle_encoding"),
                ),
            )

    def _set_saved_playlist(self, path: Path | None) -> None:
        self._saved_playlist_path = path
        self._saved_playlist_state = _held_lightly(self._playlist_state())

        if path is None:
            self._title_timer.stop()
        elif not self._title_timer.isActive():
            self._title_timer.start()

        self.update_window_title()

    def _is_overwrite_denied(self, file_path: Path):
        if file_path.is_file():
            q_message = translate(
                "Dialog - Playlist overwrite", "Do you want to overwrite {FILE_NAME}?"
            ).replace("{FILE_NAME}", file_path.name)

            ret = QCustomMessageBox.question(
                self.parent(),
                translate("Dialog - Playlist overwrite", "Playlist", "Header"),
                q_message,
            )

            if ret != QMessageBox.No:
                return True

        return False

    def _make_playlist(self):
        videos, grid_state = self._playlist_videos_and_grid_state()
        bookmarks = self._ctx.commands.bookmarks_to_save()
        settings = PlaylistSettings().playlist_kwargs()

        # With bookmarks, a playlist says how they are kept, whatever the
        # default: opened where the default is the other way, the cells' own
        # lists would be merged, or a file's shared list given to only the
        # first cell to open it.
        if bookmarks:
            settings["bookmarks_shared"] = self._ctx.commands.is_bookmarks_shared()

        return Playlist(
            grid_state=grid_state_for_dump(grid_state),
            window_state=self._ctx.window_state,
            videos=videos,
            snapshots=self._ctx.snapshots,
            bookmarks=bookmarks,
            lists=self._ctx.commands.lists_to_save(),
            **settings,
        )

    def _playlist_videos_and_grid_state(self):
        grid_state = self._ctx.grid_state
        if self._ctx.is_shuffle_on_load:
            videos = sorted(self._ctx.video_blocks.videos, key=lambda v: str(v.uri))
            cells = grid_state.cells
            if cells:
                ids = iter(str(v.id) for v in videos)
                cells = [
                    c.model_copy(update={"video_id": next(ids)}) if c.video_id else c
                    for c in cells
                ]
            grid_state = grid_state.model_copy(
                update={"video_order": [], "cells": cells}
            )
            return videos, grid_state

        videos = [
            b.video_params
            for b in self._ctx.video_blocks.blocks_for_ids(
                self._ctx.commands.layout_order()
            )
        ]
        return videos, grid_state


def _emit_if_not_empty(*properties: tuple[pyqtSignal, Any]):
    for signal, property_value in properties:
        if property_value:
            signal.emit(property_value)


def _emit(*properties: tuple[pyqtSignal, Any]):
    for signal, property_value in properties:
        signal.emit(property_value)


def _is_same_state(one: tuple, other: tuple) -> bool:
    rest, lists = one
    other_rest, other_lists = other

    return (
        rest == other_rest
        and len(lists) == len(other_lists)
        and all(_is_same_list(a, b) for a, b in zip(lists, other_lists, strict=True))
    )


def _held_lightly(state: tuple) -> tuple:
    """The playlist as saved, kept to tell a change from: a list kept whole
    by a weak reference, a list edited being another list, and the one
    replaced let go of; a channel list is a hundred megabytes."""

    rest, lists = state

    return rest, tuple(
        media_list if media_list.is_linked else weakref.ref(media_list)
        for media_list in lists
    )


def _is_same_list(one, other) -> bool:
    if isinstance(other, weakref.ref):
        return other() is one

    if one is other:
        return True

    # a linked one is a few items, told apart item by item; read again
    # as the playlist opens, it was read at another time, which is no
    # change of the playlist's
    if not (one.is_linked and other.is_linked):
        return False

    return one.model_copy(update={"read_at": None}) == other.model_copy(
        update={"read_at": None}
    )
