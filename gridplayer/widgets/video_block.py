import os
import random
import secrets

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor, QIcon
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLabel, QStackedLayout, QWidget

from gridplayer.exceptions import PlayerException
from gridplayer.params_static import PLAYER_ID_LENGTH
from gridplayer.settings import Settings
from gridplayer.utils.misc import qt_connect
from gridplayer.video import MAX_RATE, MAX_SCALE, MIN_RATE, MIN_SCALE
from gridplayer.widgets.video_overlay import OverlayBlock, OverlayBlockFloating


def only_initialized(func):
    def wrapper(self, *args, **kwargs):
        if not self.video_driver.is_video_initialized:
            return None

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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAutoFillBackground(True)

        # Due to Qt video block glitch, cannot hide video block
        # workaround - make overlay loading screen 99% opaque
        # so it will appear visually solid while video block is invisible
        effect = QGraphicsOpacityEffect(self)
        almost_opaque = 0.99
        effect.setOpacity(almost_opaque)
        self.setGraphicsEffect(effect)

        self.setAlignment(Qt.AlignCenter)

        self._set_pic(QIcon.fromTheme("processing"))

    def resizeEvent(self, event):
        self._set_pic_to_half_size(event.size())

    def set_error(self):
        self._set_pic(QIcon.fromTheme("close"))

    def _set_pic(self, pic_path):
        reasonably_big = 512
        self.pic = QIcon(pic_path).pixmap(QSize(reasonably_big, reasonably_big))

        self._set_pic_to_half_size(self.size())

    def _set_pic_to_half_size(self, size):
        half_size_multiplier = 0.75

        width = int(size.width() * half_size_multiplier)
        height = int(size.height() * half_size_multiplier)

        self.setPixmap(
            self.pic.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )


class VideoBlock(QWidget):  # noqa: WPS230
    load_video = pyqtSignal(str)

    exit_request = pyqtSignal(str)

    time_change = pyqtSignal(int, int)
    volume_change = pyqtSignal(float)
    label_change = pyqtSignal(str)
    loop_start_change = pyqtSignal(float)
    loop_end_change = pyqtSignal(float)
    is_paused_change = pyqtSignal(bool)
    is_muted_change = pyqtSignal(bool)
    info_change = pyqtSignal(str)

    def __init__(self, video_driver, **kwargs):
        super().__init__(**kwargs)

        # Internal
        self.video_driver = video_driver(parent=self)
        self.id = secrets.token_hex(PLAYER_ID_LENGTH)

        # Static Params
        self.video_params = None

        # Dynamic Params
        self.is_active = False
        self.is_error = False

        self.overlay_hide_timer = QTimer(self)
        self.overlay_hide_timer.setSingleShot(True)
        self.overlay_hide_timer.timeout.connect(self.hide_overlay)

        self.ui_video_driver()

        self.ui_overlay()

        self.ui_setup()

        self.status_label.show()
        self.overlay.raise_()
        self.overlay.hide()

    def ui_video_driver(self):
        qt_connect(
            (self.video_driver.video_ready, self.load_video_finish),
            (self.video_driver.time_changed, self.time_changed),
            (self.video_driver.error, self.error),
            (self.video_driver.crash, self.crash),
            (self.load_video, self.video_driver.load_video),
        )

    def ui_overlay(self):
        if self.video_driver.is_opengl:
            self.overlay = OverlayBlockFloating(self)
            self.installEventFilter(self.overlay)
        else:
            self.overlay = OverlayBlock(self)

        qt_connect(
            (self.overlay.set_vid_pos, self.seek_percent),
            (self.overlay.set_volume, self.set_volume),
            (self.overlay.exit_clicked, self.exit),
            (self.overlay.play_pause_clicked, self.play_pause),
            (self.overlay.mute_unmute_clicked, self.mute_unmute),
            (self.time_change, self.overlay.set_position),
            (self.volume_change, self.overlay.set_volume_position),
            (self.label_change, self.overlay.set_label),
            (self.loop_start_change, self.overlay.set_loop_start),
            (self.loop_end_change, self.overlay.set_loop_end),
            (self.is_paused_change, self.overlay.set_is_paused),
            (self.is_muted_change, self.overlay.set_is_muted),
            (self.info_change, self.overlay.set_info_label),
        )

    def ui_setup(self):
        self.setMouseTracking(True)

        if self.video_driver.is_opengl:
            self.layout_main = QStackedLayoutFloating(self)
        else:
            self.layout_main = QStackedLayout(self)

        self.layout_main.setSpacing(0)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setStackingMode(QStackedLayout.StackAll)

        self.status_label = StatusLabel(parent=self)
        self.status_label.setWindowFlags(Qt.WindowTransparentForInput)
        self.status_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.layout_main.addWidget(self.status_label)
        self.layout_main.addWidget(self.video_driver)
        self.layout_main.addWidget(self.overlay)

    def crash(self, traceback_txt):
        raise PlayerException(traceback_txt)

    def cleanup(self):
        if self.is_error:
            self.status_label.hide()
            return

        self.video_driver.is_video_initialized = False
        self.overlay.hide()
        self.video_driver.hide()

        self.status_label.show()
        self.repaint()

        self.video_driver.cleanup()

        self.status_label.hide()
        self.repaint()

    def error(self):
        self.video_driver.is_video_initialized = False
        self.is_error = True

        self.overlay.hide()
        self.video_driver.hide()

        self.status_label.set_error()
        self.status_label.show()
        self.repaint()

    def exit(self):
        self.exit_request.emit(self.id)

    def wheelEvent(self, event):
        is_shift_forward = event.angleDelta().y() < 0
        is_big_shift = event.modifiers() & Qt.ShiftModifier

        shift_percent = 5 if is_big_shift else 1

        if is_shift_forward:
            self.seek_shift_percent(shift_percent)
        else:
            self.seek_shift_percent(-shift_percent)

        event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.play_pause()

        event.ignore()

    def hideEvent(self, event):
        self.hide_overlay()

    def is_under_cursor(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    @property
    def time(self):
        return self.video_params.current_position

    @time.setter
    def time(self, time):
        self.video_params.current_position = time

        self.time_change.emit(time, self.video_driver.length)

    @property
    def position(self):
        if not self.time or not self.video_driver.length:
            return 0

        return self.time / self.video_driver.length

    @property
    def loop_start(self):
        if self.video_params.loop_start is None:
            return 0
        return self.video_params.loop_start

    @property
    def loop_end(self):
        if self.video_params.loop_end is None:
            # Loop end 250 ms before actual end for seamless loop
            before_end_gap = 250
            return self.video_driver.length - before_end_gap
        return self.video_params.loop_end

    @only_initialized
    def show_overlay(self):
        self.overlay.show()
        self.overlay_hide_timer.start(1000 * Settings().get("misc/overlay_timeout"))

    def hide_overlay(self):
        if self.is_active:
            self.overlay_hide_timer.start(
                1000 * Settings().get("misc/overlay_timeout"),
            )
            return

        self.overlay.hide()

    @only_initialized
    def time_changed(self, new_time):
        self.time = new_time

        # 100ms headspace for slow callbacks
        if self.time < self.loop_start - 100:
            self.seek(self.loop_start)

        elif self.time > self.loop_end:
            if self.video_params.is_start_random:
                self.seek_random()
            else:
                self.seek(self.loop_start)

    def set_video(self, video_params):
        self.video_params = video_params

        self.load_video.emit(self.video_params.file_path)

    def load_video_finish(self):  # noqa: WPS213
        self.label_change.emit(os.path.basename(self.video_params.file_path))

        self.video_driver.set_aspect_ratio(self.video_params.aspect_mode)
        self.video_driver.set_scale(self.video_params.scale)
        self.video_driver.set_playback_rate(self.video_params.rate)

        if self.video_params.loop_start:
            self.set_loop_start_time(self.video_params.loop_start)

        if self.video_params.loop_end:
            self.set_loop_end_time(self.video_params.loop_end)

        is_video_start = self.video_params.current_position == 0

        if self.video_params.is_start_random and is_video_start:
            self.seek_random()
        else:
            self.seek(self.video_params.current_position)

        self.set_volume(self.video_params.volume)
        self.set_muted(self.video_params.is_muted)
        self.set_pause(self.video_params.is_paused)

        self.status_label.hide()

    @only_initialized
    def set_aspect(self, aspect):
        self.video_params.aspect_mode = aspect

        self.video_driver.set_aspect_ratio(self.video_params.aspect_mode)

    @only_initialized
    def toggle_loop_random(self):
        self.video_params.is_start_random = not self.video_params.is_start_random

    @only_initialized
    def set_loop_start(self):
        self.set_loop_start_time(self.time)

    @only_initialized
    def set_loop_start_time(self, new_time):
        if new_time == self.video_params.loop_end:
            return

        self.video_params.loop_start = new_time

        self.loop_start_change.emit(new_time / self.video_driver.length)

    @only_initialized
    def set_loop_end(self):
        self.set_loop_end_time(self.time)

    @only_initialized
    def set_loop_end_time(self, new_time):
        if new_time == self.video_params.loop_start:
            return

        self.video_params.loop_end = new_time

        self.loop_end_change.emit(new_time / self.video_driver.length)

    @only_initialized
    def reset_loop(self):
        self.video_params.loop_start = None
        self.video_params.loop_end = None

        self.loop_start_change.emit(0)
        self.loop_end_change.emit(100.0)

    @only_initialized
    def seek_shift_percent(self, shift_percent):
        seek_ms = int(shift_percent / 100 * self.video_driver.length)

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
        random_ms = random.randint(self.loop_start, self.loop_end)  # noqa: S311

        self.seek(random_ms)

    @only_initialized
    def seek_percent(self, percent):
        seek_ms = int(percent * self.video_driver.length)

        self.seek(seek_ms)

    @only_initialized
    def seek(self, seek_ms):
        if seek_ms < self.loop_start or seek_ms > self.loop_end:
            seek_ms = self.loop_start

        self.video_driver.set_time(seek_ms)
        self.time = seek_ms

    @only_initialized
    def step_frame(self, frames):
        if not self.video_params.is_paused:
            self.set_pause(True)

        ms_per_frame = self.video_driver.get_ms_per_frame()

        self.seek_shift(ms_per_frame * frames)

    @only_initialized
    def scale_increase(self):
        self.video_params.scale += 0.1
        self.video_params.scale = round(self.video_params.scale, 1)

        if self.video_params.scale > MAX_SCALE:
            self.video_params.scale = MAX_SCALE
            self.info_change.emit("Zoom: {0}".format(self.video_params.scale))
            return

        self.video_driver.set_scale(self.video_params.scale)
        self.info_change.emit("Zoom: {0}".format(self.video_params.scale))

    @only_initialized
    def scale_decrease(self):
        self.video_params.scale -= 0.1
        self.video_params.scale = round(self.video_params.scale, 1)

        if self.video_params.scale < MIN_SCALE:
            self.video_params.scale = MIN_SCALE
            self.info_change.emit("Zoom: {0}".format(self.video_params.scale))
            return

        self.video_driver.set_scale(self.video_params.scale)
        self.info_change.emit("Zoom: {0}".format(self.video_params.scale))

    @only_initialized
    def scale_reset(self):
        self.video_params.scale = 1.0

        self.video_driver.set_scale(self.video_params.scale)
        self.info_change.emit("Zoom: {0}".format(self.video_params.scale))

    @only_initialized
    def rate_increase(self):
        self.video_params.rate += 0.1
        self.video_params.rate = round(self.video_params.rate, 1)

        if self.video_params.rate > MAX_RATE:
            self.video_params.rate = MAX_RATE
            self.info_change.emit("Speed: {0}".format(self.video_params.rate))
            return

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    @only_initialized
    def rate_decrease(self):
        self.video_params.rate -= 0.1
        self.video_params.rate = round(self.video_params.rate, 1)

        if self.video_params.rate < MIN_RATE:
            self.video_params.rate = MIN_RATE
            self.info_change.emit("Speed: {0}".format(self.video_params.rate))
            return

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    @only_initialized
    def rate_reset(self):
        self.video_params.rate = 1.0

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    @only_initialized
    def set_pause(self, paused):
        self.video_params.is_paused = paused

        if self.video_params.is_paused:
            self.video_driver.set_pause(self.video_params.is_paused)
        else:
            self.video_driver.play()

        self.is_paused_change.emit(self.video_params.is_paused)

    @only_initialized
    def mute_unmute(self):
        self.set_muted(not self.video_params.is_muted)

    @only_initialized
    def set_muted(self, muted):
        self.video_params.is_muted = muted

        self.video_driver.audio_set_mute(self.video_params.is_muted)

        self.is_muted_change.emit(self.video_params.is_muted)

    @only_initialized
    def set_volume(self, percent):
        self.video_params.volume = round(percent, 2)

        volume = int(self.video_params.volume * 100)

        self.video_driver.audio_set_volume(volume)

        self.volume_change.emit(percent)

    @only_initialized
    def play_pause(self):
        self.set_pause(not self.video_params.is_paused)
