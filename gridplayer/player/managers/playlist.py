import logging
import os

from PyQt5.QtCore import QDir, QEvent, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.params_static import GridMode, WindowState
from gridplayer.player.managers.base import ManagerBase
from gridplayer.playlist import Playlist
from gridplayer.utils.files import filter_valid_files
from gridplayer.video import Video

logger = logging.getLogger(__name__)


class PlaylistManager(ManagerBase):
    playlist_closed = pyqtSignal()
    playlist_loaded = pyqtSignal()
    window_state_loaded = pyqtSignal(WindowState)
    grid_mode_loaded = pyqtSignal(GridMode)
    videos_loaded = pyqtSignal(list)

    alert = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._saved_playlist = None

    @property
    def event_map(self):
        return {QEvent.Close: self.cmd_close_playlist}

    @property
    def commands(self):
        return {
            "open_playlist": self.cmd_open_playlist,
            "save_playlist": self.cmd_save_playlist,
            "close_playlist": self.cmd_close_playlist,
        }

    def cmd_open_playlist(self):
        dialog = QFileDialog(self.parent())
        dialog.setFileMode(QFileDialog.ExistingFile)

        dialog.setNameFilter("GridPlayer Playlists (*.gpls)")

        if dialog.exec():
            files = dialog.selectedFiles()

            if files:
                self.load_playlist_file(files[0])

    def cmd_close_playlist(self):
        self.check_playlist_save()

        self.playlist_closed.emit()

    def cmd_save_playlist(self):
        playlist = self._make_playlist()

        if self._saved_playlist is not None:
            save_path = self._saved_playlist["path"]
        else:
            save_path = os.path.join(QDir.homePath(), "Untitled.gpls")

        logger.debug(f"Proposed playlist save path: {save_path}")

        file_path = QFileDialog.getSaveFileName(
            self.parent(), "Where to save playlist", save_path, "*.gpls"
        )

        if not file_path[0]:
            return

        file_path = os.path.abspath(file_path[0])

        # filename placeholder is not available if file doesn't exist
        # problematic for new playlists, need to prevent accidental overwrite
        # occurs in Flatpak, maybe in other sandboxes that use portal
        if not file_path.endswith(".gpls"):
            file_path = f"{file_path}.gpls"

            if self._is_overwrite_denied(file_path):
                return

        playlist.save(file_path)

        self._saved_playlist = {
            "path": file_path,
            "state": hash(playlist.dumps()),
        }

    def process_arguments(self, argv):
        files = filter_valid_files(argv)

        if not files:
            self.error.emit("No supported files!")
            return

        if files[0].endswith("gpls"):
            self.load_playlist_file(files[0])
            return

        playlist = Playlist(videos=[Video(file_path=f) for f in files])

        self.load_playlist(playlist)

        self._saved_playlist = None

    def load_playlist_file(self, filename):
        try:
            playlist = Playlist.read(filename)
        except ValueError:
            return self.error.emit(f"Invalid playlist format!\n\n{filename}")
        except FileNotFoundError:
            return self.error.emit(f"File not found!\n\n{filename}")

        if not playlist.videos:
            return self.error.emit(f"Empty or invalid playlist!\n\n{filename}")

        self.load_playlist(playlist)

        self._saved_playlist = {
            "path": filename,
            "state": hash(self._make_playlist().dumps()),
        }

    def load_playlist(self, playlist):
        self.cmd_close_playlist()

        self.videos_loaded.emit(playlist.videos)

        if playlist.grid_mode is not None:
            self.grid_mode_loaded.emit(playlist.grid_mode)

        if playlist.window_state is not None:
            self.window_state_loaded.emit(playlist.window_state)

        self.playlist_loaded.emit()

    def check_playlist_save(self):
        if not self._ctx.video_blocks:
            return

        if self._saved_playlist is not None:
            playlist_state = hash(self._make_playlist().dumps())

            is_playlist_changed = playlist_state != self._saved_playlist["state"]
        else:
            is_playlist_changed = True

        if is_playlist_changed:
            self.alert.emit()

            ret = QCustomMessageBox.question(
                self.parent(), "Playlist", "Do you want to save the playlist?"
            )

            if ret == QMessageBox.Yes:
                self.cmd_save_playlist()

    def _is_overwrite_denied(self, file_path):
        if os.path.isfile(file_path):
            file_name = os.path.basename(file_path)

            ret = QCustomMessageBox.question(
                self.parent(), "Playlist", f"Do you want to overwrite {file_name}?"
            )

            if ret != QMessageBox.No:
                return True

        return False

    def _make_playlist(self):
        return Playlist(
            grid_mode=self._ctx.grid_mode,
            window_state=self._ctx.window_state,
            videos=self._ctx.video_blocks.videos,
        )
