from pathlib import Path
from typing import Any, Tuple

from PyQt5.QtCore import QDir, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import filter_video_uris
from gridplayer.params.static import SeekSyncMode, WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.files import get_playlist_path
from gridplayer.utils.qt import translate


class PlaylistManager(ManagerBase):
    playlist_closed = pyqtSignal()
    playlist_loaded = pyqtSignal()
    window_state_loaded = pyqtSignal(WindowState)
    grid_state_loaded = pyqtSignal(GridState)
    snapshots_loaded = pyqtSignal(dict)
    seek_sync_mode_loaded = pyqtSignal(SeekSyncMode)
    shuffle_on_load_loaded = pyqtSignal(bool)
    disable_click_pause_loaded = pyqtSignal(bool)
    disable_wheel_seek_loaded = pyqtSignal(bool)
    videos_loaded = pyqtSignal(list)

    alert = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._saved_playlist = None

    @property
    def commands(self):
        return {
            "open_playlist": self.cmd_open_playlist,
            "save_playlist": self.cmd_save_playlist,
            "close_playlist": self.cmd_close_playlist,
        }

    def cmd_open_playlist(self):
        dialog = QFileDialog(
            parent=self.parent(),
            caption=translate("Dialog - Open Playlist", "Open Playlist", "Header"),
        )
        dialog.setFileMode(QFileDialog.ExistingFile)

        dialog.setNameFilter(
            "{0} (*.gpls)".format(
                translate(
                    "Dialog - Open Playlist", "GridPlayer Playlists", "File format"
                )
            )
        )

        if dialog.exec():
            files = dialog.selectedFiles()

            if files:
                self.load_playlist_file(files[0])

    def cmd_close_playlist(self) -> bool:
        if not self.check_playlist_save():
            return False

        self.playlist_closed.emit()

        return True

    def cmd_save_playlist(self):
        playlist = self._make_playlist()

        if self._saved_playlist is not None:
            save_path = self._saved_playlist["path"]
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
            return

        file_path = Path(file_path)

        # filename placeholder is not available if file doesn't exist
        # problematic for new playlists, need to prevent accidental overwrite
        # occurs in Flatpak, maybe in other sandboxes that use portal
        if file_path.suffix.lower() != ".gpls":
            file_path = file_path.with_suffix(".gpls")

            if self._is_overwrite_denied(file_path):
                return

        playlist.save(file_path)

        self._saved_playlist = {
            "path": file_path,
            "state": hash(playlist.dumps()),
        }

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

        self.videos_loaded.emit(videos)

        self.alert.emit()

    def load_playlist_file(self, playlist_file: Path):
        try:
            playlist = Playlist.read(playlist_file)
        except ValueError as e:
            self._log.error(f"Playlist parse error: {e}")
            self.error.emit(
                "{0}\n\n{1}".format(
                    translate("Error", "Invalid playlist format!"), playlist_file
                )
            )
            return
        except FileNotFoundError:
            self.error.emit(
                "{0}\n\n{1}".format(
                    translate("Error", "File not found!"), playlist_file
                )
            )
            return

        if not playlist.videos:
            self.error.emit(
                "{0}\n\n{1}".format(
                    translate("Error", "Empty or invalid playlist!"), playlist_file
                )
            )
            return

        self.load_playlist(playlist)

        self._saved_playlist = {
            "path": playlist_file,
            "state": hash(self._make_playlist().dumps()),
        }

    def load_playlist(self, playlist: Playlist):
        self.cmd_close_playlist()

        self.videos_loaded.emit(playlist.videos)

        _emit_if_not_empty(
            (self.grid_state_loaded, playlist.grid_state),
            (self.window_state_loaded, playlist.window_state),
            (self.snapshots_loaded, playlist.snapshots),
        )

        _emit(
            (self.seek_sync_mode_loaded, playlist.seek_sync_mode),
            (self.shuffle_on_load_loaded, playlist.shuffle_on_load),
            (self.disable_click_pause_loaded, playlist.disable_click_pause),
            (self.disable_wheel_seek_loaded, playlist.disable_wheel_seek),
        )

        self.alert.emit()

    def check_playlist_save(self) -> bool:
        if not Settings().get("playlist/track_changes"):
            return True

        if not self._ctx.video_blocks:
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
                self.cmd_save_playlist()

            elif ret == QMessageBox.Cancel:
                return False

        return True

    def _is_playlist_changed(self):
        if self._saved_playlist is None:
            return True

        playlist_state = hash(self._make_playlist().dumps())
        return playlist_state != self._saved_playlist["state"]

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
        # if shuffle on load is ON, keep videos in the same order to maintain save state
        if self._ctx.is_shuffle_on_load:
            videos = sorted(self._ctx.video_blocks.videos, key=lambda v: str(v.uri))
        else:
            videos = self._ctx.video_blocks.videos

        return Playlist(
            grid_state=self._ctx.grid_state,
            window_state=self._ctx.window_state,
            videos=videos,
            snapshots=self._ctx.snapshots,
            seek_sync_mode=self._ctx.seek_sync_mode,
            shuffle_on_load=self._ctx.is_shuffle_on_load,
            disable_click_pause=self._ctx.is_disable_click_pause,
            disable_wheel_seek=self._ctx.is_disable_wheel_seek,
        )


def _emit_if_not_empty(*properties: Tuple[pyqtSignal, Any]):
    for signal, property_value in properties:
        if property_value:
            signal.emit(property_value)


def _emit(*properties: Tuple[pyqtSignal, Any]):
    for signal, property_value in properties:
        signal.emit(property_value)
