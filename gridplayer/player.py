import base64
import logging
import math
import os

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QEvent, QMimeData, QSize, Qt
from PyQt5.QtGui import QDrag, QFont, QInputEvent
from PyQt5.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.utils import keepawake, log_config
from gridplayer.dialogs.about import AboutDialog
from gridplayer.params import PlaylistParams
from gridplayer.params_static import (
    SUPPORTED_VIDEO_EXT,
    GridMode,
    VideoDriver,
    WindowState,
)
from gridplayer.player_menu import PlayerMenu
from gridplayer.playlist import read_playlist, save_playlist, dumps_playlist
from gridplayer.settings import settings
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.video_frame_vlc_base import ProcessManagerVLC
from gridplayer.video_block import VideoBlock
from gridplayer.video_frame_dummy import VideoFrameDummy

logger = logging.getLogger(__name__)


def drag_get_files(data, is_check=False):
    files = []

    if not data.hasUrls():
        return False

    for url in data.urls():
        if not url.isLocalFile():
            logger.warning(f"{url} is not a local file!")
            continue

        filepath = os.path.normpath(url.toLocalFile())

        _, ext = os.path.splitext(filepath)

        if ext[1:] == "gpls":
            if len(data.urls()) > 1:
                logger.warning(f"Only single playlist file can be opened at a time!")
                return False
        elif ext[1:] not in SUPPORTED_VIDEO_EXT:
            logger.warning(f"{ext[1:]} format is not supported!")
            continue

        if not (os.path.isfile(filepath) and os.access(filepath, os.R_OK)):
            logger.warning(f"{filepath} file is not accessible!")
            continue

        if is_check:
            return True

        files.append(filepath)

    if is_check:
        return True

    return files


def drag_has_video_id(data: QMimeData):
    return data.hasFormat("application/x-gridplayer-video-id")


def drag_get_video_id(data: QMimeData):
    return bytes(data.data("application/x-gridplayer-video-id")).decode()


def dict_swap_items(d, id1, id2):
    new_dict = {}
    for k, v in d.items():
        if k == id1:
            new_dict[id2] = d[id2]
        elif k == id2:
            new_dict[id1] = d[id1]
        elif k not in (id1, id2):
            new_dict[k] = v
    return new_dict


class PlayerException(Exception):
    pass


class ModalWindow(object):
    def __init__(self, parent, is_modal=True, is_context=False):
        self.parent = parent

        self.is_modal = is_modal
        self.is_context = is_context

    def __enter__(self):
        if self.is_modal:
            self.parent.is_modal_open = True
        self.parent.is_context_open = True

        self.parent.mouse_timer.stop()
        self.parent.mouse_reset()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.is_modal:
            self.parent.is_modal_open = False
        if self.is_context:
            self.parent.is_context_open = False
        self.parent.mouse_reset()


class Player(QtWidgets.QWidget):
    video_count_change = QtCore.pyqtSignal(int)

    hide_overlay = QtCore.pyqtSignal()
    set_pause = QtCore.pyqtSignal(int)
    seek_shift = QtCore.pyqtSignal(int)
    seek_random = QtCore.pyqtSignal()
    set_fullscreen = QtCore.pyqtSignal(bool)

    def __init__(self, master=None):
        super().__init__(master)

        self.playlist_params = None

        self.video_driver = None
        self.process_manager = None
        self.is_overlay_floating = None

        self.is_modal_open = False
        self.is_context_open = False
        self.is_maximized_pre_fullscreen = False
        self.drag_start_position = None

        self.video_blocks = {}
        self.active_video_block = None
        self.is_single_mode = False
        self.pre_single_mode_states = {}
        self.saved_playlist = None
        self.is_screensaver_off = False

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._default_minimum_size = QSize(640, 360)

        self._minimum_video_size = QSize(100, 90)
        self._minimum_size = self._default_minimum_size

        self.setMinimumSize(self._minimum_size)

        self.mouse_timer = QtCore.QTimer()
        self.mouse_timer.timeout.connect(self.check_mouse_state)
        if settings.get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * settings.get("misc/mouse_hide_timeout"))

        self.videogrid = QtWidgets.QGridLayout(self)
        self.videogrid.setSpacing(0)
        self.videogrid.setContentsMargins(0, 0, 0, 0)

        self.menu = PlayerMenu(self)

        self.info_label = QLabel("Drag and drop video files here")
        self.info_label.setAlignment(Qt.AlignCenter)
        font = QFont("Hack", 16, QFont.Bold)
        self.info_label.setFont(font)

        self.init_video_driver()
        self.reload_video_grid()

    def mouseMoveEvent(self, event):
        self.mouse_reset()
        self.update_active_block(event.pos())

        drag_video = self.get_drag_video(event)
        if drag_video is not None:
            drag_video.exec()

    def wheelEvent(self, event):
        self.mouse_reset()

    def leaveEvent(self, event):
        self.update_active_block(None)

    def event(self, event) -> bool:
        if event.type() == QEvent.NonClientAreaMouseMove:
            self.update_active_block(None)

        if event.type() in {QEvent.ShortcutOverride, QEvent.NonClientAreaMouseMove}:
            self.mouse_reset()

            self.cmd_active("show_overlay")

        return super().event(event)

    def contextMenuEvent(self, event):
        with ModalWindow(self, is_context=True):
            menu = self.menu.make_menu()
            menu.exec_(event.globalPos())

    def eventFilter(self, event_object, event) -> bool:
        """Show cursor on any mouse event for children"""

        if isinstance(event, QInputEvent):
            self.mouse_reset()

        return False

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.toggle_single_video()

    def mousePressEvent(self, event):
        self.update_active_block(event.pos())

        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()

    def dragEnterEvent(self, event) -> None:
        data = event.mimeData()

        if not drag_get_files(data, is_check=True) and not drag_has_video_id(data):
            return

        event.setDropAction(Qt.MoveAction)
        event.accept()

    def dropEvent(self, event):
        data = event.mimeData()

        # Add new video
        if drag_get_files(data, is_check=True):
            files = drag_get_files(data)

            if len(files) == 1 and files[0].endswith(".gpls"):
                self.load_playlist_file(files[0])
            else:
                self.add_videos(files)

            event.acceptProposedAction()

        # Swap videos
        elif drag_has_video_id(data):
            dst_video = self.get_hover_video_block()
            if dst_video is None:
                logger.debug("No video under cursor, discarding drop")
                return

            src_video_id = drag_get_video_id(data)
            dst_video_id = dst_video.id

            logger.debug(f"Swapping {src_video_id} with {dst_video_id}")

            self.swap_videos(src_video_id, dst_video_id)

            event.acceptProposedAction()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized() and settings.get("player/pause_minimized"):
                self.pause_all()

    def closeEvent(self, event):
        self.check_playlist_save()

        self.close_all()

        super().closeEvent(event)

    def crash(self, traceback_txt):
        raise PlayerException(traceback_txt)

    def get_window_state(self):
        return WindowState(
            is_maximized=self.isMaximized() or self.is_maximized_pre_fullscreen,
            is_fullscreen=self.isFullScreen(),
            geometry=base64.b64encode(bytes(self.saveGeometry())).decode(),
        )

    def update_active_block(self, pos):
        if self.is_context_open:
            return

        old_active_block = self.active_video_block

        if pos is None:
            self.active_video_block = None
        else:
            self.active_video_block = self.get_hover_video_block()

            if self.active_video_block is not None:
                self.active_video_block.is_active = True

        if old_active_block is not None and self.active_video_block != old_active_block:
            old_active_block.is_active = False

    def swap_videos(self, src_id, dst_id):
        if src_id == dst_id:
            logger.debug("No video swap needed")
            return

        if src_id not in self.video_blocks:
            logger.debug(f"Cannot swap {src_id}, id not found")
            return

        self.video_blocks = dict_swap_items(self.video_blocks, dst_id, src_id)

        self.reload_video_grid()

    def add_videos(self, files):
        if not files:
            return

        # Starting new playlist if no videos
        if not self.video_blocks:
            self.playlist_params = PlaylistParams()

        for f_path in files:
            self.add_new_video_block(f_path)

        self.reload_video_grid()

    def get_drag_video(self, event):
        if not event.buttons() & Qt.LeftButton:
            return

        if not self.drag_start_position:
            return

        drag_distance = (event.pos() - self.drag_start_position).manhattanLength()
        if drag_distance < QApplication.startDragDistance():
            return

        if self.active_video_block is None:
            return

        drag = QDrag(self)

        mimeData = QMimeData()
        mimeData.setData(
            "application/x-gridplayer-video-id", self.active_video_block.id.encode()
        )
        drag.setMimeData(mimeData)

        self.drag_start_position = None

        return drag

    def get_grid_dimensions(self):
        grid_y = math.ceil(math.sqrt(len(self.video_blocks)))
        grid_x = math.ceil(len(self.video_blocks) / grid_y)

        if self.playlist_params.grid_mode == GridMode.AUTO_COLS:
            cols, rows = grid_x, grid_y
        else:
            cols, rows = grid_y, grid_x

        return cols, rows

    def reset_grid_stretch(self):
        for i in range(self.videogrid.columnCount()):
            self.videogrid.setColumnStretch(i, 0)

        for i in range(self.videogrid.rowCount()):
            self.videogrid.setRowStretch(i, 0)

    def adjust_grid_stretch(self):
        cols, rows = self.get_grid_dimensions()

        for i in range(cols):
            self.videogrid.setColumnStretch(i, 1)

        for i in range(rows):
            self.videogrid.setRowStretch(i, 1)

    def adjust_window(self, cols, rows):
        width = cols * self._minimum_video_size.width()
        height = rows * self._minimum_video_size.height()

        width = max(width, self._default_minimum_size.width())
        height = max(height, self._default_minimum_size.height())

        self._minimum_size = QSize(width, height)
        self.setMinimumSize(self._minimum_size)

    def reload_video_grid(self):
        self.info_label.hide()

        self.videogrid.removeWidget(self.info_label)

        for vb in self.video_blocks.values():
            self.videogrid.removeWidget(vb)

        self.reset_grid_stretch()

        # Add drag-n-drop info if no videos
        if len(self.video_blocks) == 0:
            self.videogrid.addWidget(self.info_label, 0, 0)
            self.info_label.show()
            return

        cols, rows = self.get_grid_dimensions()
        grid = ((col, row) for row in range(rows) for col in range(cols))

        self.adjust_window(cols, rows)

        minimum_vb_size = QSize(
            self._minimum_size.width() / cols, self._minimum_size.height() / rows
        )

        for vb in self.video_blocks.values():
            col, row = next(grid)

            vb.setMinimumSize(minimum_vb_size)

            self.videogrid.addWidget(vb, row, col, 1, 1)

        self.adjust_grid_stretch()

        self.layout().activate()

    def cmd_active(self, command, *args):
        if self.active_video_block is None:
            return

        getattr(self.active_video_block, command)(*args)

    def init_video_driver(self):
        video_driver = settings.get("player/video_driver")

        video_drivers = {
            VideoDriver.DUMMY: VideoFrameDummy,
        }

        process_instances = {}

        from gridplayer.video_frame_vlc_hw import InstanceProcessVLCHW, VideoFrameVLCHW
        from gridplayer.video_frame_vlc_sw import InstanceProcessVLCSW, VideoFrameVLCSW

        video_drivers[VideoDriver.VLC_SW] = VideoFrameVLCSW
        video_drivers[VideoDriver.VLC_HW] = VideoFrameVLCHW

        process_instances[VideoDriver.VLC_SW] = InstanceProcessVLCSW
        process_instances[VideoDriver.VLC_HW] = InstanceProcessVLCHW

        is_multiprocess = video_driver in {
            VideoDriver.VLC_SW,
            VideoDriver.VLC_HW,
        }

        # =================

        self.video_driver = video_drivers[video_driver]

        if self.process_manager is not None:
            self.process_manager.cleanup()

        if is_multiprocess:
            self.process_manager = ProcessManagerVLC(process_instances[video_driver])
            self.process_manager.crash.connect(self.crash)
        else:
            self.process_manager = None

        self.is_overlay_floating = video_driver in {
            VideoDriver.VLC_HW,
        }

    def add_new_video_block(self, path, params=None):
        vb = VideoBlock(
            video_driver=self.video_driver,
            process_manager=self.process_manager,
            is_overlay_floating=self.is_overlay_floating,
            parent=self,
        )
        vb.installEventFilter(self)

        con_list = [
            (vb.exit_request, self.close_video_block),
            (vb.is_paused_change, lambda x: self.screensaver_check()),
            (self.set_pause, vb.set_pause),
            (self.seek_shift, vb.seek_shift_percent),
            (self.seek_random, vb.seek_random),
            (self.hide_overlay, vb.hide_overlay),
            (self.set_fullscreen, vb.set_fullscreen),
        ]

        for c_sig, c_slot in con_list:
            c_sig.connect(c_slot)

        vb.set_video(path, params)

        self.video_blocks[vb.id] = vb

        self.video_count_change.emit(len(self.video_blocks))

    def remove_video_blocks(self, *videoblocks):
        for vb in videoblocks:
            self.videogrid.takeAt(self.videogrid.indexOf(vb))

            if vb is self.active_video_block:
                self.active_video_block = None

            vb.cleanup()
            del self.video_blocks[vb.id]

            vb.deleteLater()

        self.video_count_change.emit(len(self.video_blocks))

    def check_mouse_state(self):
        self.mouse_timer.stop()

        if not self.video_blocks:
            return

        if self.isVisible():
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.BlankCursor)

        self.update_active_block(None)

        self.hide_overlay.emit()

    def mouse_reset(self):
        QtWidgets.QApplication.restoreOverrideCursor()

        if not self.is_modal_open and settings.get("misc/mouse_hide"):
            self.mouse_timer.start(1000 * settings.get("misc/mouse_hide_timeout"))

        self.update_active_block(self.get_current_cursor_pos())

    def get_current_cursor_pos(self):
        return self.mapFromGlobal(self.cursor().pos())

    def pause_all(self):
        self.set_pause.emit(True)

    def play_pause_all(self):
        unpaused_vbs = (v for v in self.video_blocks.values() if not v.params.is_paused)

        if next(unpaused_vbs, None) is not None:
            self.set_pause.emit(True)
        else:
            self.set_pause.emit(False)

    def screensaver_check(self):
        if not settings.get("player/inhibit_screensaver"):
            return

        playing_videos = (
            True for v in self.video_blocks.values() if not v.params.is_paused
        )
        is_something_playing = next(playing_videos, False)

        if is_something_playing:
            if not self.is_screensaver_off:
                keepawake.keepawake_on()

                self.is_screensaver_off = True
        elif self.is_screensaver_off:
            keepawake.keepawake_off()
            self.is_screensaver_off = False

    def seek_shift_all(self, percent):
        self.seek_shift.emit(percent)

    def get_hover_video_block(self):
        visible_blocks_under_cursor = (
            v
            for v in self.video_blocks.values()
            if v.isVisible() and v.is_under_cursor()
        )

        return next(visible_blocks_under_cursor, None)

    def is_active_aspect_set_to(self, aspect):
        if self.active_video_block is None:
            return False
        return self.active_video_block.params.aspect_mode == aspect

    def is_active_loop_random(self):
        if self.active_video_block is None:
            return False

        return self.active_video_block.params.is_start_random

    def toggle_single_video(self):
        if len(self.video_blocks) <= 1:
            return

        is_pause_background_videos = settings.get("player/pause_background_videos")

        if self.is_single_mode:
            for vb in self.video_blocks.values():
                if vb == self.active_video_block:
                    continue

                if vb.id in self.pre_single_mode_states:
                    vb.set_pause(self.pre_single_mode_states[vb.id])
                    del self.pre_single_mode_states[vb.id]

                vb.show()

            self.adjust_grid_stretch()
        else:
            for vb in self.video_blocks.values():
                if vb == self.active_video_block:
                    continue

                if is_pause_background_videos:
                    self.pre_single_mode_states[vb.id] = vb.params.is_paused
                    vb.set_pause(True)

                vb.hide()

            self.reset_grid_stretch()

        self.is_single_mode = not self.is_single_mode

    def next_single_video(self):
        if not self.is_single_mode:
            return

        is_pause_background_videos = settings.get("player/pause_background_videos")

        current_sv = next(v for v in self.video_blocks.values() if v.isVisible())

        next_sv_idx = list(self.video_blocks).index(current_sv.id) + 1
        if next_sv_idx > len(self.video_blocks) - 1:
            next_sv_idx = 0
        next_sv = list(self.video_blocks.values())[next_sv_idx]

        if is_pause_background_videos:
            self.pre_single_mode_states[current_sv.id] = current_sv.params.is_paused
            current_sv.set_pause(True)
        current_sv.hide()

        if next_sv.id in self.pre_single_mode_states:
            next_sv.set_pause(self.pre_single_mode_states[next_sv.id])
            del self.pre_single_mode_states[next_sv.id]
        next_sv.show()

    def close_video_block(self, _id):
        if self.is_single_mode:
            self.toggle_single_video()

        self.remove_video_blocks(self.video_blocks[_id])
        self.reload_video_grid()

        self.update_active_block(self.get_current_cursor_pos())
        self.cmd_active("show_overlay")

    def close_all(self):
        self.remove_video_blocks(*list(self.video_blocks.values()))
        self.reload_video_grid()

        if self.is_screensaver_off:
            keepawake.keepawake_off()
            self.is_screensaver_off = False

        if self.process_manager is not None:
            self.process_manager.cleanup()

    def cmd_minimize(self):
        self.showMinimized()

    def cmd_step_forward(self):
        self.pause_all()
        self.step_frame.emit(-1)

    def cmd_step_backward(self):
        self.pause_all()
        self.step_frame.emit(1)

    def cmd_fullscreen(self):
        if not self.isFullScreen():
            self.is_maximized_pre_fullscreen = self.windowState() == Qt.WindowMaximized

            self.set_fullscreen.emit(True)
            self.showFullScreen()
        else:
            self.set_fullscreen.emit(False)

            if self.is_maximized_pre_fullscreen:
                self.showMaximized()
            else:
                self.showNormal()

            self.is_maximized_pre_fullscreen = False

    def cmd_settings(self):
        with ModalWindow(self):
            previous_settings = settings.get_all()

            settings_dialog = SettingsDialog(self)
            settings_dialog.exec_()

            self.apply_settings(previous_settings)

            if self.is_reload_needed(previous_settings):
                self.reload_playlist()

    def cmd_about(self):
        with ModalWindow(self):
            settings_dialog = AboutDialog(self)
            settings_dialog.exec_()

    def apply_settings(self, previous_settings):
        checks = (
            "logging/log_level",
            "logging/log_level_vlc",
            "player/inhibit_screensaver",
        )

        changes = {k: previous_settings[k] != settings.get(k) for k in checks}

        if changes["logging/log_level"]:
            log_config.set_root_level(settings.get("logging/log_level"))

            if self.process_manager:
                self.process_manager.set_log_level(settings.get("logging/log_level"))

        if changes["logging/log_level_vlc"] and self.process_manager:
            self.process_manager.set_log_level_vlc(
                settings.get("logging/log_level_vlc")
            )

        if changes["player/inhibit_screensaver"]:
            if settings.get("player/inhibit_screensaver"):
                self.screensaver_check()
            elif self.is_screensaver_off:
                keepawake.keepawake_off()
                self.is_screensaver_off = False

    def is_reload_needed(self, previous_settings):
        checks = ("player/video_driver", "player/video_driver_players")

        changes = {k: previous_settings[k] != settings.get(k) for k in checks}

        if changes["player/video_driver"]:
            return True

        is_current_engine_multiproc = settings.get("player/video_driver") in (
            VideoDriver.VLC_HW,
            VideoDriver.VLC_SW,
        )

        if changes["player/video_driver_players"] and is_current_engine_multiproc:
            return True

        return False

    def cmd_set_grid_mode(self, mode):
        if self.playlist_params.grid_mode == mode:
            return

        self.playlist_params.grid_mode = mode
        self.reload_video_grid()

    def cmd_add_videos(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFiles)

        supported_exts = " ".join((f"*.{e}" for e in SUPPORTED_VIDEO_EXT))
        dialog.setNameFilter(f"Videos ({supported_exts})")

        if dialog.exec():
            files = dialog.selectedFiles()
            self.add_videos(files)

    def cmd_open_playlist(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFile)

        dialog.setNameFilter("GridPlayer Playlists (*.gpls)")

        if dialog.exec():
            files = dialog.selectedFiles()

            if files:
                self.load_playlist_file(files[0])

    def cmd_save_playlist(self):
        playlist = self.get_playlist()

        if self.saved_playlist is not None:
            save_path = self.saved_playlist["path"]
        else:
            save_path = os.path.join(QtCore.QDir.currentPath(), "Untitled.gpls")

        with ModalWindow(self):
            file_path = QtWidgets.QFileDialog.getSaveFileName(
                self, "Where to save playlist", save_path, "*.gpls"
            )

        if file_path[0]:
            file_path = os.path.abspath(file_path[0])

            # if not file_path.endswith(".gpls"):
            #     file_path += ".gpls"

            save_playlist(file_path, playlist)

            self.saved_playlist = {
                "path": file_path,
                "state": hash(dumps_playlist(playlist)),
            }

    def cmd_close_playlist(self):
        self.check_playlist_save()

        self.close_all()
        self.init_video_driver()

        if not self.isMaximized() and not self.isFullScreen():
            self.resize(self._minimum_size)

    def get_playlist(self):
        self.playlist_params.window_state = self.get_window_state()

        return {
            "params": self.playlist_params,
            "videos": [
                {"path": v.file_path, "params": v.params}
                for v in self.video_blocks.values()
            ],
        }

    def reload_playlist(self):
        if self.video_blocks:
            playlist = self.get_playlist()

            self.close_all()
        else:
            playlist = None

        self.init_video_driver()

        if playlist is not None:
            self.load_playlist(playlist)

    def load_playlist_file(self, filename):
        self.check_playlist_save()

        try:
            playlist = read_playlist(filename)
        except ValueError:
            return self.error(f"Invalid playlist format!\n\n{filename}")
        except FileNotFoundError:
            return self.error(f"File not found!\n\n{filename}")

        if not playlist["videos"]:
            return self.error(f"Empty or invalid playlist!\n\n{filename}")

        self.load_playlist(playlist)

        self.saved_playlist = {
            "path": filename,
            "state": hash(dumps_playlist(self.get_playlist())),
        }

    def load_playlist(self, playlist):
        if self.video_blocks:
            self.close_all()
            self.init_video_driver()

        if playlist["params"] is None:
            self.playlist_params = PlaylistParams()
        else:
            self.playlist_params = playlist["params"]

        for vid in playlist["videos"]:
            self.add_new_video_block(vid["path"], vid["params"])

        self.reload_video_grid()

        if self.playlist_params.window_state is not None:
            geometry = base64.b64decode(
                self.playlist_params.window_state.geometry.encode()
            )
            self.restoreGeometry(geometry)

            if self.playlist_params.window_state.is_fullscreen:
                if self.playlist_params.window_state.is_maximized:
                    self.is_maximized_pre_fullscreen = True
                    self.showFullScreen()

            elif self.playlist_params.window_state.is_maximized:
                self.showMaximized()

        self.raise_()
        self.activateWindow()

    def check_playlist_save(self):
        if not self.video_blocks:
            return

        if self.saved_playlist is not None:
            playlist_state = hash(dumps_playlist(self.get_playlist()))

            is_playlist_changed = playlist_state != self.saved_playlist["state"]
        else:
            is_playlist_changed = True

        if is_playlist_changed:
            self.raise_()
            self.activateWindow()

            with ModalWindow(self):
                ret = QCustomMessageBox.question(
                    self, "Playlist", "Do you want to save the playlist?"
                )

            if ret == QMessageBox.Yes:
                self.cmd_save_playlist()

    def process_arguments(self, argv):
        argv = [os.path.normpath(a) for a in argv]

        if not argv:
            QApplication.alert(self)
            return

        if len(argv) == 1:
            _, ext = os.path.splitext(argv[0])

            if ext[1:] == "gpls":
                self.load_playlist_file(argv[0])
                return

        files = []

        for filepath in argv:
            _, ext = os.path.splitext(filepath)

            if ext[1:] not in SUPPORTED_VIDEO_EXT:
                continue

            if not (os.path.isfile(filepath) and os.access(filepath, os.R_OK)):
                continue

            files.append(filepath)

        if not files:
            return self.error("No supported files!")

        playlist = {
            "params": None,
            "videos": [{"path": f, "params": None} for f in files],
        }

        self.check_playlist_save()
        self.load_playlist(playlist)

        self.saved_playlist = None

    def error(self, message):
        with ModalWindow(self):
            QCustomMessageBox.critical(self, "Error", message)
