import random
import secrets
from pathlib import Path
from typing import Optional

from pydantic.color import Color
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QStackedLayout, QWidget

from gridplayer.dialogs.rename_dialog import QVideoRenameDialog
from gridplayer.exceptions import PlayerException
from gridplayer.params_static import PLAYER_ID_LENGTH, VideoRepeat
from gridplayer.settings import Settings
from gridplayer.utils.misc import qt_connect
from gridplayer.utils.next_file import next_video_file
from gridplayer.video import MAX_RATE, MAX_SCALE, MIN_RATE, MIN_SCALE, Video
from gridplayer.widgets.video_block_status import StatusLabel
from gridplayer.widgets.video_overlay import OverlayBlock, OverlayBlockFloating


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


class VideoBlock(QWidget):  # noqa: WPS230
    load_video = pyqtSignal(Path)

    exit_request = pyqtSignal(str)
    percent_changed = pyqtSignal(float)

    time_change = pyqtSignal(int, int)
    volume_change = pyqtSignal(float)
    label_change = pyqtSignal(str)
    color_change = pyqtSignal(str)
    loop_start_change = pyqtSignal(float)
    loop_end_change = pyqtSignal(float)
    is_paused_change = pyqtSignal(bool)
    is_muted_change = pyqtSignal(bool)
    info_change = pyqtSignal(str)

    def __init__(self, video_driver, **kwargs):
        super().__init__(**kwargs)

        # Internal
        self.video_driver_cls = video_driver
        self.id = secrets.token_hex(PLAYER_ID_LENGTH)

        # Static Params
        self.video_params: Optional[Video] = None

        # Dynamic Params
        self.is_active = False
        self.is_error = False

        self.overlay_hide_timer = QTimer(self)
        self.overlay_hide_timer.setSingleShot(True)
        self.overlay_hide_timer.timeout.connect(self.hide_overlay)

        self.video_driver = self.init_video_driver()
        self.overlay = self.init_overlay()

        self.ui_setup()

        self.status_label.show()
        self.overlay.raise_()
        self.overlay.hide()

    def init_video_driver(self):
        video_driver = self.video_driver_cls(parent=self)

        qt_connect(
            (video_driver.video_ready, self.load_video_finish),
            (video_driver.time_changed, self.time_changed),
            (video_driver.error, self.error),
            (video_driver.crash, self.crash),
            (self.load_video, video_driver.load_video),
        )

        return video_driver

    def reset_video_driver(self):
        self.video_driver.video_ready.disconnect()
        self.video_driver.time_changed.disconnect()
        self.video_driver.error.disconnect()
        self.video_driver.crash.disconnect()
        self.load_video.disconnect()

        self.layout_main.takeAt(1).widget()
        self.video_driver = self.init_video_driver()
        self.layout_main.insertWidget(1, self.video_driver)

    def init_overlay(self):
        if self.video_driver.is_opengl:
            overlay = OverlayBlockFloating(self)
            self.installEventFilter(overlay)
        else:
            overlay = OverlayBlock(self)

        qt_connect(
            (overlay.set_vid_pos, self.seek_percent),
            (overlay.set_vid_pos, self.percent_changed),
            (overlay.set_volume, self.set_volume),
            (overlay.exit_clicked, self.exit),
            (overlay.play_pause_clicked, self.play_pause),
            (overlay.mute_unmute_clicked, self.mute_unmute),
            (self.time_change, overlay.set_position),
            (self.volume_change, overlay.set_volume_position),
            (self.label_change, overlay.set_label),
            (self.color_change, overlay.set_color),
            (self.loop_start_change, overlay.set_loop_start),
            (self.loop_end_change, overlay.set_loop_end),
            (self.is_paused_change, overlay.set_is_paused),
            (self.is_muted_change, overlay.set_is_muted),
            (self.info_change, overlay.set_info_label),
        )

        return overlay

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
        if not self.is_video_initialized:
            event.ignore()
            return

        is_shift_forward = event.angleDelta().y() < 0
        is_big_shift = event.modifiers() & Qt.ShiftModifier

        shift_percent = 5 if is_big_shift else 1

        if is_shift_forward:
            self.seek_shift_percent(shift_percent)
        else:
            self.seek_shift_percent(-shift_percent)

        self.percent_changed.emit(self.position)

        event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        if not self.is_video_initialized:
            event.ignore()
            return

        if event.button() == Qt.LeftButton:
            self.play_pause()

        event.ignore()

    def hideEvent(self, event):
        self.hide_overlay()

    def showEvent(self, event):
        if self.is_video_initialized and not Settings().get("misc/overlay_hide"):
            self.show_overlay()

    def is_under_cursor(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    @property
    def is_video_initialized(self):
        if self.video_driver is None:
            return False

        return self.video_driver.is_video_initialized

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

    def show_overlay(self):
        self.overlay.show()
        if Settings().get("misc/overlay_hide"):
            self.overlay_hide_timer.start(1000 * Settings().get("misc/overlay_timeout"))

    def hide_overlay(self):
        if not Settings().get("misc/overlay_hide"):
            return

        if self.is_active:
            self.overlay_hide_timer.start(1000 * Settings().get("misc/overlay_timeout"))
            return

        self.overlay.hide()

    def time_changed(self, new_time):
        if not self.is_video_initialized:
            return

        self.time = new_time

        # 100ms headspace for slow callbacks
        if self.time < self.loop_start - 100:
            self.seek(self.loop_start)

        elif self.time > self.loop_end:
            self.loop_end_action()

    def loop_end_action(self):
        is_single_file = self.video_params.repeat_mode == VideoRepeat.SINGLE_FILE

        if self.video_params.loop_end is not None or is_single_file:
            if self.video_params.is_start_random:
                self.seek_random()
            else:
                self.seek(self.loop_start)
        elif self.video_params.repeat_mode == VideoRepeat.DIR:
            self.next_video()
        elif self.video_params.repeat_mode == VideoRepeat.DIR_SHUFFLE:
            self.shuffle_video()

    def set_video(self, video_params: Video):
        is_first_video = self.video_params is None

        self.video_params = video_params

        # Shut down current video
        if not is_first_video:
            self.cleanup()
            self.reset_video_driver()

        self.load_video.emit(self.video_params.file_path)

    def load_video_finish(self):  # noqa: WPS213
        self.label_change.emit(self.video_params.title)
        self.color_change.emit(self.video_params.color.as_hex())

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
        self.show_overlay()

    def set_aspect(self, aspect):
        self.video_params.aspect_mode = aspect

        self.video_driver.set_aspect_ratio(self.video_params.aspect_mode)

    def toggle_loop_random(self):
        self.video_params.is_start_random = not self.video_params.is_start_random

    def set_loop_start(self):
        self.set_loop_start_time(self.time)

    def set_loop_start_time(self, new_time):
        if new_time == self.video_params.loop_end:
            return

        self.video_params.loop_start = new_time

        self.loop_start_change.emit(new_time / self.video_driver.length)

    def set_loop_end(self):
        self.set_loop_end_time(self.time)

    def set_loop_end_time(self, new_time):
        if new_time == self.video_params.loop_start:
            return

        self.video_params.loop_end = new_time

        self.loop_end_change.emit(new_time / self.video_driver.length)

    def reset_loop(self):
        self.video_params.loop_start = None
        self.video_params.loop_end = None

        self.loop_start_change.emit(0)
        self.loop_end_change.emit(100.0)

    def set_repeat_mode(self, repeat_mode: VideoRepeat):
        self.video_params.repeat_mode = repeat_mode

    def seek_shift_percent(self, shift_percent):
        seek_ms = int(shift_percent / 100 * self.video_driver.length)

        self.seek_shift(seek_ms)

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

    def seek_random(self):
        random_ms = random.randint(self.loop_start, self.loop_end)  # noqa: S311

        self.seek(random_ms)

    def seek_percent(self, percent):
        seek_ms = int(percent * self.video_driver.length)

        self.seek(seek_ms)

    def seek(self, seek_ms):
        if seek_ms < self.loop_start or seek_ms > self.loop_end:
            seek_ms = self.loop_start

        self.video_driver.set_time(seek_ms)
        self.time = seek_ms

    def step_frame(self, frames):
        if not self.video_params.is_paused:
            self.set_pause(True)

        ms_per_frame = self.video_driver.get_ms_per_frame()

        self.seek_shift(ms_per_frame * frames)

    def scale_increase(self):
        self.video_params.scale += 0.1
        self.video_params.scale = round(self.video_params.scale, 1)

        if self.video_params.scale > MAX_SCALE:
            self.video_params.scale = MAX_SCALE
            self.info_change.emit("Zoom: {0}".format(self.video_params.scale))
            return

        self.video_driver.set_scale(self.video_params.scale)
        self.info_change.emit("Zoom: {0}".format(self.video_params.scale))

    def scale_decrease(self):
        self.video_params.scale -= 0.1
        self.video_params.scale = round(self.video_params.scale, 1)

        if self.video_params.scale < MIN_SCALE:
            self.video_params.scale = MIN_SCALE
            self.info_change.emit("Zoom: {0}".format(self.video_params.scale))
            return

        self.video_driver.set_scale(self.video_params.scale)
        self.info_change.emit("Zoom: {0}".format(self.video_params.scale))

    def scale_reset(self):
        self.video_params.scale = 1.0

        self.video_driver.set_scale(self.video_params.scale)
        self.info_change.emit("Zoom: {0}".format(self.video_params.scale))

    def rate_increase(self):
        self.video_params.rate += 0.1
        self.video_params.rate = round(self.video_params.rate, 1)

        if self.video_params.rate > MAX_RATE:
            self.video_params.rate = MAX_RATE
            self.info_change.emit("Speed: {0}".format(self.video_params.rate))
            return

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    def rate_decrease(self):
        self.video_params.rate -= 0.1
        self.video_params.rate = round(self.video_params.rate, 1)

        if self.video_params.rate < MIN_RATE:
            self.video_params.rate = MIN_RATE
            self.info_change.emit("Speed: {0}".format(self.video_params.rate))
            return

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    def rate_reset(self):
        self.video_params.rate = 1.0

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    def set_pause(self, paused):
        self.video_params.is_paused = paused

        if self.video_params.is_paused:
            self.video_driver.set_pause(self.video_params.is_paused)
        else:
            self.video_driver.play()

        self.is_paused_change.emit(self.video_params.is_paused)

    def mute_unmute(self):
        self.set_muted(not self.video_params.is_muted)

    def set_muted(self, muted):
        self.video_params.is_muted = muted

        self.video_driver.audio_set_mute(self.video_params.is_muted)

        self.is_muted_change.emit(self.video_params.is_muted)

    def set_volume(self, percent):
        self.video_params.volume = round(percent, 2)

        volume = int(self.video_params.volume * 100)

        self.video_driver.audio_set_volume(volume)

        self.volume_change.emit(percent)

    def play_pause(self):
        self.set_pause(not self.video_params.is_paused)

    def previous_video(self):
        # Stop new commands
        self.video_driver.is_video_initialized = False

        self.switch_video(next_video_file(self.video_params.file_path, is_before=True))

    def next_video(self):
        # Stop new commands
        self.video_driver.is_video_initialized = False

        self.switch_video(next_video_file(self.video_params.file_path))

    def shuffle_video(self):
        # Stop new commands
        self.video_driver.is_video_initialized = False

        self.switch_video(next_video_file(self.video_params.file_path, is_shuffle=True))

    def switch_video(self, new_video):
        # If single file in the dir and was removed, highly unlikely but still
        if new_video is None:
            self.cleanup()
            self.error()
            return

        if new_video == self.video_params.file_path:
            self.video_driver.is_video_initialized = True
            self.seek(self.loop_start)
            return

        self.reset_loop()
        self.video_params.current_position = 0
        self.video_params.file_path = new_video
        self.video_params.is_paused = False

        self.set_video(self.video_params)

    def rename(self):
        new_name, new_color = QVideoRenameDialog.get_edits(
            self.parent(),
            self.tr("Rename video"),
            self.video_params.file_path.name,
            self.video_params.title,
            self.video_params.color.as_rgb_tuple(),
        )

        self.video_params.title = new_name
        self.video_params.color = Color(new_color)

        self.label_change.emit(self.video_params.title)
        self.color_change.emit(self.video_params.color.as_hex())
