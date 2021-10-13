import os
import random
import secrets
import time

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QInputEvent, QPalette, QCursor
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLabel, QStackedLayout

from gridplayer.params import VideoParams
from gridplayer.resources import ICONS
from gridplayer.settings import settings
from gridplayer.video_overlay import OverlayBlock, OverlayBlockFloating


def only_initialized(func):
    def wrapper(self, *args, **kwargs):
        if not self.video.is_video_initialized:
            return

        return func(self, *args, **kwargs)

    return wrapper


class QStackedLayoutFloating(QStackedLayout):
    """overridden setGeometry for children is not honored due to type casting inside Qt,
    need to override setGeometry in Layout to make floating windows resize with parent

    https://code.qt.io/cgit/qt/qtbase.git/tree/src/widgets/kernel/qstackedlayout.cpp#n474
    """

    def setGeometry(self, rect):
        if self.stackingMode() == QStackedLayout.StackOne:
            widget = self.currentWidget()
            if widget:
                widget.setGeometry(rect)
        if self.stackingMode() == QStackedLayout.StackAll:
            for i in range(self.count()):
                widget = self.itemAt(i).widget()
                if widget:
                    widget.setGeometry(rect)


class StatusLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAutoFillBackground(True)
        # self.setBackgroundRole(QPalette.Window)

        # Due to Qt video block glitch, cannot hide video block
        # workaround - make overlay loading screen 99% opaque
        # so it will appear visually solid while video block is invisible
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.99)
        self.setGraphicsEffect(effect)

        self.setAlignment(Qt.AlignCenter)

        self._set_pic(ICONS["basic/042-sand clock"])

    def resizeEvent(self, event):
        self._set_pic_to_half_size(event.size())

    def set_error(self):
        self._set_pic(ICONS["basic/031-cancel"])

    def _set_pic(self, pic_path):
        self.pic = QIcon(pic_path).pixmap(QSize(512, 512))

        self._set_pic_to_half_size(self.size())

    def _set_pic_to_half_size(self, size):
        width = int(size.width() * 0.75)
        height = int(size.height() * 0.75)

        self.setPixmap(
            self.pic.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )


class VideoBlock(QtWidgets.QWidget):
    load_video = QtCore.pyqtSignal(str)

    exit_request = QtCore.pyqtSignal(str)

    time_change = QtCore.pyqtSignal(int, int)
    volume_change = QtCore.pyqtSignal(float)
    label_change = QtCore.pyqtSignal(str)
    loop_start_change = QtCore.pyqtSignal(float)
    loop_end_change = QtCore.pyqtSignal(float)
    is_paused_change = QtCore.pyqtSignal(bool)
    is_muted_change = QtCore.pyqtSignal(bool)
    info_change = QtCore.pyqtSignal(str)

    def __init__(self, video_driver, process_manager, is_overlay_floating, parent=None):
        super().__init__(parent)

        # Internal
        self.id = secrets.token_hex(8)

        # Static Params
        self.file_path = None
        self.params = VideoParams()

        # Dynamic Params
        self.is_active = False
        self._is_error = False

        self.setMouseTracking(True)

        if is_overlay_floating:
            self.layout_main = QStackedLayoutFloating(self)
            self.overlay = OverlayBlockFloating(self)
        else:
            self.layout_main = QStackedLayout(self)
            self.overlay = OverlayBlock(self)
        # self.layout_main = QStackedLayoutFloating(self)
        # self.overlay = OverlayBlockFloating(self)

        self.layout_main.setSpacing(0)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setStackingMode(QStackedLayout.StackAll)

        self.status_label = StatusLabel(self)
        self.status_label.setWindowFlags(Qt.WindowTransparentForInput)
        self.status_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.overlay_hide_timer = QtCore.QTimer()
        self.overlay_hide_timer.setSingleShot(True)
        self.overlay_hide_timer.timeout.connect(self.hide_overlay)

        # Video

        if process_manager:
            self.video = video_driver(process_manager, self)
        else:
            self.video = video_driver(self)

        self.video.video_ready.connect(self.load_video_finish)
        self.video.time_changed.connect(self.time_changed)
        self.video.error.connect(self.error)
        self.video.crash.connect(self.parent().crash)
        self.load_video.connect(self.video.load_video)

        # Overlay

        self.overlay.installEventFilter(self)

        self.overlay.set_vid_pos.connect(self.seek_percent)
        self.overlay.set_volume.connect(self.set_volume)
        self.overlay.exit_clicked.connect(self.exit)
        self.overlay.play_pause_clicked.connect(self.play_pause)
        self.overlay.mute_unmute_clicked.connect(self.mute_unmute)

        self.time_change.connect(self.overlay.set_position)
        self.volume_change.connect(self.overlay.set_volume_position)
        self.label_change.connect(self.overlay.set_label)
        self.loop_start_change.connect(self.overlay.set_loop_start)
        self.loop_end_change.connect(self.overlay.set_loop_end)
        self.is_paused_change.connect(self.overlay.set_is_paused)
        self.is_muted_change.connect(self.overlay.set_is_muted)
        self.info_change.connect(self.overlay.set_info_label)

        # Populating layout

        self.layout_main.addWidget(self.status_label)
        self.status_label.show()

        self.layout_main.addWidget(self.video)
        # self.video.lower()
        # self.video.hide()
        # self.video.setMaximumSize(0, 0)

        self.layout_main.addWidget(self.overlay)
        self.overlay.raise_()
        self.overlay.hide()

    def cleanup(self):
        if self._is_error:
            self.status_label.hide()
            return

        self.video.is_video_initialized = False
        self.overlay.hide()
        self.video.hide()

        self.status_label.show()
        self.repaint()

        self.video.cleanup()

        self.status_label.hide()
        self.repaint()

    def error(self):
        self.video.is_video_initialized = False
        self._is_error = True

        self.overlay.hide()
        self.video.hide()

        self.status_label.set_error()
        self.status_label.show()
        self.repaint()

    def exit(self):
        self.exit_request.emit(self.id)

    def wheelEvent(self, event):
        is_shift_forward = event.angleDelta().y() < 0
        is_big_shift = event.modifiers() & QtCore.Qt.ShiftModifier

        shift_percent = 5 if is_big_shift else 1

        if is_shift_forward:
            self.seek_shift_percent(shift_percent)
        else:
            self.seek_shift_percent(-shift_percent)

        event.ignore()

    def mouseMoveEvent(self, event):
        self.show_overlay()

        event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        self.show_overlay()

        if event.button() == QtCore.Qt.LeftButton:
            self.play_pause()

        event.accept()

    def mousePressEvent(self, event):
        self.show_overlay()

        return super().mousePressEvent(event)

    def eventFilter(self, QObject, QEvent) -> bool:
        """Show cursor on any mouse event for children"""

        if isinstance(QEvent, QInputEvent):
            return self.parent().eventFilter(QObject, QEvent)

        return False

    def hideEvent(self, event):
        self.hide_overlay()

    def is_under_cursor(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    @property
    def time(self):
        return self.params.current_position

    @time.setter
    def time(self, value):
        self.params.current_position = value

        self.time_change.emit(value, self.video.length)

    @property
    def position(self):
        if not self.time or not self.video.length:
            return 0.0

        return self.time / self.video.length

    @property
    def loop_start(self):
        if self.params.loop_start is None:
            return 0
        return self.params.loop_start

    @property
    def loop_end(self):
        if self.params.loop_end is None:
            # Loop end 250 ms before actual end for seamless loop
            return self.video.length - 250
        return self.params.loop_end

    @only_initialized
    def show_overlay(self):
        self.overlay.show()
        self.overlay_hide_timer.start(1000 * settings.get("misc/overlay_timeout"))

    def hide_overlay(self):
        if self.is_active:
            self.overlay_hide_timer.start(1000 * settings.get("misc/overlay_timeout"))
            return

        self.overlay.hide()

    @only_initialized
    def time_changed(self, new_time):
        self.time = new_time

        # 100ms headspace for slow callbacks
        if self.time < self.loop_start - 100:
            self.seek(self.loop_start)

        elif self.time > self.loop_end:
            if self.params.is_start_random:
                self.seek_random()
            else:
                self.seek(self.loop_start)

    def set_video(self, file_path, params=None):
        self.file_path = file_path
        self.params = VideoParams() if params is None else params

        self.load_video.emit(self.file_path)

    def load_video_finish(self):
        self.label_change.emit(os.path.basename(self.file_path))

        self.video.set_aspect_ratio(self.params.aspect_mode)
        self.video.set_scale(self.params.scale)
        self.video.set_playback_rate(self.params.rate)

        if self.params.loop_start:
            self.set_loop_start_time(self.params.loop_start)

        if self.params.loop_end:
            self.set_loop_end_time(self.params.loop_end)

        if self.params.is_start_random and self.params.current_position == 0:
            self.seek_random()
        else:
            self.seek(self.params.current_position)

        self.set_volume(self.params.volume)
        self.set_muted(self.params.is_muted)

        self.set_pause(self.params.is_paused)

        self.status_label.hide()
        # self.video.show()
        # self.video.setMaximumSize(QtWidgets.QWIDGETSIZE_MAX, QtWidgets.QWIDGETSIZE_MAX)

    @only_initialized
    def set_aspect(self, aspect):
        self.params.aspect_mode = aspect

        self.video.set_aspect_ratio(self.params.aspect_mode)

    @only_initialized
    def toggle_loop_random(self):
        self.params.is_start_random = not self.params.is_start_random

    @only_initialized
    def set_loop_start(self):
        self.set_loop_start_time(self.time)

    @only_initialized
    def set_loop_start_time(self, new_time):
        if new_time == self.params.loop_end:
            return

        self.params.loop_start = new_time

        self.loop_start_change.emit(new_time / self.video.length)

    @only_initialized
    def set_loop_end(self):
        self.set_loop_end_time(self.time)

    @only_initialized
    def set_loop_end_time(self, new_time):
        if new_time == self.params.loop_start:
            return

        self.params.loop_end = new_time

        self.loop_end_change.emit(new_time / self.video.length)

    @only_initialized
    def reset_loop(self):
        self.params.loop_start = None
        self.params.loop_end = None

        self.loop_start_change.emit(0.0)
        self.loop_end_change.emit(100.0)

    @only_initialized
    def seek_shift_percent(self, shift_percent):
        seek_ms = int(shift_percent / 100 * self.video.length)

        self.seek_shift(seek_ms)

    @only_initialized
    def seek_shift(self, seek_ms):
        seek_stretch = self.loop_end - self.loop_start

        if seek_ms > 0 and self.time + seek_ms > self.loop_end:
            rest = self.loop_end - self.time
            seek_set = seek_ms - rest
            seek_set = seek_set - (seek_set // seek_stretch) * seek_stretch

            new_time = self.loop_start + seek_set

        elif seek_ms < 0 and self.time + seek_ms < self.loop_start:
            seek_ms *= -1

            rest = self.time - self.loop_start
            seek_set = seek_ms - rest
            seek_set = seek_set - (seek_set // seek_stretch) * seek_stretch

            new_time = self.loop_end - seek_set

        else:
            new_time = self.time + seek_ms

        self.seek(new_time)

    @only_initialized
    def seek_random(self):
        random_ms = random.randint(self.loop_start, self.loop_end)

        self.seek(random_ms)

    @only_initialized
    def seek_percent(self, percent):
        seek_ms = int(percent * self.video.length)

        self.seek(seek_ms)

    @only_initialized
    def seek(self, seek_ms):
        if seek_ms < self.loop_start or seek_ms > self.loop_end:
            seek_ms = self.loop_start

        self.video.set_time(seek_ms)
        self.time = seek_ms

    @only_initialized
    def step_frame(self, frames):
        if not self.params.is_paused:
            self.set_pause(True)

        ms_per_frame = self.video.get_ms_per_frame()

        self.seek_shift(ms_per_frame * frames)

    @only_initialized
    def scale_increase(self):
        self.params.scale += 0.1
        self.params.scale = round(self.params.scale, 1)

        if self.params.scale > 3:
            self.params.scale = 3.0
            self.info_change.emit(f"Zoom: {self.params.scale}")
            return

        self.video.set_scale(self.params.scale)
        self.info_change.emit(f"Zoom: {self.params.scale}")

    @only_initialized
    def scale_decrease(self):
        self.params.scale -= 0.1
        self.params.scale = round(self.params.scale, 1)

        if self.params.scale < 1:
            self.params.scale = 1.0
            self.info_change.emit(f"Zoom: {self.params.scale}")
            return

        self.video.set_scale(self.params.scale)
        self.info_change.emit(f"Zoom: {self.params.scale}")

    @only_initialized
    def scale_reset(self):
        self.params.scale = 1.0

        self.video.set_scale(self.params.scale)
        self.info_change.emit(f"Zoom: {self.params.scale}")

    @only_initialized
    def rate_increase(self):
        self.params.rate += 0.1
        self.params.rate = round(self.params.rate, 1)

        if self.params.rate > 12.0:
            self.params.rate = 12.0
            self.info_change.emit(f"Speed: {self.params.rate}")
            return

        self.video.set_playback_rate(self.params.rate)
        self.info_change.emit(f"Speed: {self.params.rate}")

    @only_initialized
    def rate_decrease(self):
        self.params.rate -= 0.1
        self.params.rate = round(self.params.rate, 1)

        if self.params.rate < 0.2:
            self.params.rate = 0.2
            self.info_change.emit(f"Speed: {self.params.rate}")
            return

        self.video.set_playback_rate(self.params.rate)
        self.info_change.emit(f"Speed: {self.params.rate}")

    @only_initialized
    def rate_reset(self):
        self.params.rate = 1.0

        self.video.set_playback_rate(self.params.rate)
        self.info_change.emit(f"Speed: {self.params.rate}")

    @only_initialized
    def set_pause(self, paused):
        self.params.is_paused = paused

        if self.params.is_paused:
            self.video.set_pause(self.params.is_paused)
        else:
            self.video.play()

        self.is_paused_change.emit(self.params.is_paused)

    @only_initialized
    def mute_unmute(self):
        self.set_muted(not self.params.is_muted)

    @only_initialized
    def set_muted(self, muted):
        self.params.is_muted = muted

        self.video.audio_set_mute(self.params.is_muted)

        self.is_muted_change.emit(self.params.is_muted)

    @only_initialized
    def set_volume(self, percent):
        self.params.volume = round(percent, 2)

        volume = int(self.params.volume * 100)

        self.video.audio_set_volume(volume)

        self.volume_change.emit(percent)

    @only_initialized
    def play_pause(self):
        self.set_pause(not self.params.is_paused)

    def set_fullscreen(self, is_fullscreen):
        # Avoid glitches on X11 when fullscreen
        # self.overlay.setWindowFlag(QtCore.Qt.X11BypassWindowManagerHint, is_fullscreen)
        pass
