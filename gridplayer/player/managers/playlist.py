from pathlib import Path
from typing import Any

from PyQt5.QtCore import QDir, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.playlist_settings import PlaylistSettingsDialog
from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import filter_video_uris
from gridplayer.params.static import SeekSyncMode, WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist_settings import (
    PlaylistSettings,
    grid_overrides_from_state,
    grid_state_for_dump,
    overrides_from_playlist,
)
from gridplayer.settings import Settings
from gridplayer.utils.files import get_playlist_path
from gridplayer.utils.qt import translate

_TITLE_REFRESH_MS = 500


class PlaylistManager(ManagerBase):
    playlist_closed = pyqtSignal()
    playlist_file_loaded = pyqtSignal(Path)
    playlist_saved = pyqtSignal(Path)
    window_state_loaded = pyqtSignal(WindowState)
    grid_state_loaded = pyqtSignal(GridState)
    snapshots_loaded = pyqtSignal(dict)
    seek_sync_mode_loaded = pyqtSignal(SeekSyncMode)
    shuffle_on_load_loaded = pyqtSignal(bool)
    disable_mouse_click_events_loaded = pyqtSignal(bool)
    disable_mouse_wheel_events_loaded = pyqtSignal(bool)
    disable_overlay_loaded = pyqtSignal(bool)
    pause_background_videos_loaded = pyqtSignal(bool)
    pause_minimized_loaded = pyqtSignal(bool)
    show_overlay_border_loaded = pyqtSignal(bool)
    overlay_hide_on_timeout_loaded = pyqtSignal(bool)
    overlay_timeout_loaded = pyqtSignal(int)
    videos_loaded = pyqtSignal(list)

    alert = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.is_shuffle_on_load = Settings().get("playlist/shuffle_on_load")

        self._saved_playlist_path: Path | None = None
        self._saved_playlist_state: int | None = None

        self._title_timer = QTimer(self)
        self._title_timer.setInterval(_TITLE_REFRESH_MS)
        self._title_timer.timeout.connect(self.update_window_title)

    def init(self):
        self._set_saved_playlist(None)

    @property
    def commands(self):
        return {
            "open_playlist": self.cmd_open_playlist,
            "save_playlist": self.cmd_save_playlist,
            "save_playlist_as": self.cmd_save_playlist_as,
            "close_playlist": self.cmd_close_playlist,
            "is_playlist_changed": self._is_playlist_changed,
            "is_playlist_saved": lambda: self._saved_playlist_path is not None,
            "is_shuffle_on_load": lambda: self._ctx.is_shuffle_on_load,
            "set_shuffle_on_load": self.set_shuffle_on_load,
            "toggle_shuffle_on_load": self.toggle_shuffle_on_load,
            "playlist_settings": self.cmd_playlist_settings,
        }

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
        PlaylistSettings().replace(dialog.result_overrides())
        self._apply_effective_session()
        self._ctx.commands.apply_grid_config(
            dialog.result_grid_state(self._ctx.grid_state)
        )

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
        if not self.check_playlist_save():
            return False

        self.playlist_closed.emit()
        self._reset_playlist_session()
        self._set_saved_playlist(None)

        return True

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

        playlist = get_playlist_path(argv)

        if playlist:
            self.load_playlist_file(playlist)
            return

        videos = filter_video_uris(argv)

        if not videos:
            self.error.emit(translate("Error", "No supported files or URLs!"))
            return

        self._ctx.commands.add_videos_to_layout(videos)
        self.alert.emit()

    def load_playlist_file(self, playlist_file: Path):
        try:
            playlist_txt = playlist_file.read_text(encoding="utf-8")
            playlist = Playlist.parse(playlist_txt)
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

        if not playlist.videos and not _has_playlist_params(playlist_txt):
            self.error.emit(
                "{}\n\n{}".format(
                    translate("Error", "Empty or invalid playlist!"), playlist_file
                )
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
        if not PlaylistSettings().get("playlist/track_changes"):
            return True

        if self._is_playlist_changed():
            self.alert.emit()

            ret = QCustomMessageBox.cancellable_question(
                self.parent(),
                translate("Dialog - Playlist close", "Playlist", "Header"),
                translate(
                    "Dialog - Playlist close", "Do you want to save the playlist?"
                ),
            )

            if ret == QMessageBox.Yes:
                if not self.cmd_save_playlist():
                    return False

            elif ret == QMessageBox.Cancel:
                return False

        return True

    def _is_playlist_changed(self):
        if self._saved_playlist_state is None:
            return False

        playlist_state = hash(self._make_playlist().dumps())
        return playlist_state != self._saved_playlist_state

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
                    self.seek_sync_mode_loaded,
                    session.get("playlist/seek_sync_mode"),
                ),
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
            )

    def _set_saved_playlist(self, path: Path | None) -> None:
        self._saved_playlist_path = path
        self._saved_playlist_state = hash(self._make_playlist().dumps())

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

        return Playlist(
            grid_state=grid_state_for_dump(grid_state),
            window_state=self._ctx.window_state,
            videos=videos,
            snapshots=self._ctx.snapshots,
            **PlaylistSettings().playlist_kwargs(),
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


def _has_playlist_params(playlist_txt: str) -> bool:
    return any(line.strip().startswith("#P:") for line in playlist_txt.splitlines())


def _emit_if_not_empty(*properties: tuple[pyqtSignal, Any]):
    for signal, property_value in properties:
        if property_value:
            signal.emit(property_value)


def _emit(*properties: tuple[pyqtSignal, Any]):
    for signal, property_value in properties:
        signal.emit(property_value)
