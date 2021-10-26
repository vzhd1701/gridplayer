import base64
import logging
import os

from PyQt5.QtCore import QDir
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.params_static import WindowState
from gridplayer.playlist import Playlist
from gridplayer.utils.files import filter_valid_files
from gridplayer.video import Video

logger = logging.getLogger(__name__)


class PlayerPlaylistMixin(object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.playlist = None
        self.saved_playlist = None

    def closeEvent(self, event):
        self.cmd_close_playlist()

        super().closeEvent(event)

    def cmd_open_playlist(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFile)

        dialog.setNameFilter("GridPlayer Playlists (*.gpls)")

        if dialog.exec():
            files = dialog.selectedFiles()

            if files:
                self.load_playlist_file(files[0])

    def cmd_close_playlist(self):
        self.check_playlist_save()

        self.close_all()

        if not self.isMaximized() and not self.isFullScreen():
            self.resize(self._minimum_size)

    def cmd_save_playlist(self):
        playlist = self._export_playlist()

        if self.saved_playlist is not None:
            save_path = self.saved_playlist["path"]
        else:
            save_path = os.path.join(QDir.homePath(), "Untitled.gpls")

        logger.debug(f"Proposed playlist save path: {save_path}")

        file_path = QFileDialog.getSaveFileName(
            self, "Where to save playlist", save_path, "*.gpls"
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

        self.saved_playlist = {
            "path": file_path,
            "state": hash(playlist.dumps()),
        }

    def add_videos(self, files):
        if not files:
            return

        if not self.is_videos:
            self.playlist = Playlist()

        for f_path in files:
            self.add_new_video_block(f_path)

        self.reload_video_grid()

    def process_arguments(self, argv):
        files = filter_valid_files(argv)

        if not files:
            self.error("No supported files!")
            return

        if files[0].endswith("gpls"):
            self.load_playlist_file(files[0])
            return

        playlist = Playlist(videos=[Video(file_path=f) for f in files])

        self.check_playlist_save()
        self.load_playlist(playlist)

        self.saved_playlist = None

    def reload_playlist(self):
        playlist = self._export_playlist() if self.is_videos else None

        self.close_all()

        if playlist is not None:
            self.load_playlist(playlist)

    def load_playlist_file(self, filename):
        self.check_playlist_save()

        try:
            playlist = Playlist.read(filename)
        except ValueError:
            return self.error(f"Invalid playlist format!\n\n{filename}")
        except FileNotFoundError:
            return self.error(f"File not found!\n\n{filename}")

        if not playlist.videos:
            return self.error(f"Empty or invalid playlist!\n\n{filename}")

        self.load_playlist(playlist)

        self.saved_playlist = {
            "path": filename,
            "state": hash(self._export_playlist().dumps()),
        }

    def load_playlist(self, playlist):
        self.close_all()

        self.playlist = playlist

        for video in playlist.videos:
            self.add_new_video_block(video)

        self.reload_video_grid()

        if self.playlist.window_state is not None:
            self._restore_window_state()

        self.raise_()
        self.activateWindow()

    def check_playlist_save(self):
        if not self.is_videos:
            return

        if self.saved_playlist is not None:
            playlist_state = hash(self._export_playlist().dumps())

            is_playlist_changed = playlist_state != self.saved_playlist["state"]
        else:
            is_playlist_changed = True

        if is_playlist_changed:
            self.raise_()
            self.activateWindow()

            ret = QCustomMessageBox.question(
                self, "Playlist", "Do you want to save the playlist?"
            )

            if ret == QMessageBox.Yes:
                self.cmd_save_playlist()

    def _is_overwrite_denied(self, file_path):
        if os.path.isfile(file_path):
            file_name = os.path.basename(file_path)

            ret = QCustomMessageBox.question(
                self, "Playlist", f"Do you want to overwrite {file_name}?"
            )

            if ret != QMessageBox.No:
                return True

        return False

    def _export_playlist(self):
        self.playlist.window_state = self._get_window_state()
        self.playlist.videos = [v.video_params for v in self.video_blocks.values()]

        return self.playlist

    def _get_window_state(self):
        return WindowState(
            is_maximized=self.isMaximized() or self.is_maximized_pre_fullscreen,
            is_fullscreen=self.isFullScreen(),
            geometry=base64.b64encode(bytes(self.saveGeometry())).decode(),
        )

    def _restore_window_state(self):
        geometry = base64.b64decode(self.playlist.window_state.geometry.encode())
        self.restoreGeometry(geometry)

        if self.playlist.window_state.is_fullscreen:
            if self.playlist.window_state.is_maximized:
                self.is_maximized_pre_fullscreen = True
                self.showFullScreen()

        elif self.playlist.window_state.is_maximized:
            self.showMaximized()
