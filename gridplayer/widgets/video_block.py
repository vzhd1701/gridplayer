import logging
import random
import re
import secrets
from pathlib import Path
from typing import Dict, Optional, Tuple

from pydantic.color import Color
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QStackedLayout, QWidget

from gridplayer.dialogs.rename_dialog import QVideoRenameDialog
from gridplayer.exceptions import PlayerException
from gridplayer.models.video import (
    MAX_RATE,
    MAX_SCALE,
    MIN_RATE,
    MIN_SCALE,
    Video,
    VideoURL,
)
from gridplayer.params.static import (
    OVERLAY_ACTIVITY_EVENT,
    PLAYER_ID_LENGTH,
    VideoRepeat,
)
from gridplayer.settings import Settings
from gridplayer.utils.next_file import next_video_file, previous_video_file
from gridplayer.utils.qt import qt_connect
from gridplayer.utils.url_resolve.static import ResolvedVideo
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolver
from gridplayer.vlc_player.static import MediaInput
from gridplayer.widgets.video_block_status import StatusLabel
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC
from gridplayer.widgets.video_overlay import OverlayBlock, OverlayBlockFloating

IN_PROGRESS_THRESHOLD_MS = 500


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


class Streams(object):
    def __init__(self, streams: Optional[Dict[str, str]] = None):
        if streams:
            self.streams = streams
        else:
            self.streams = {}

    def __len__(self):
        return len(self.streams)

    def __iter__(self):
        return iter(self.streams)

    def __reversed__(self):
        return reversed(self.streams)

    @property
    def best(self) -> Tuple[str, str]:
        return list(self.streams.items())[-1]

    @property
    def worst(self) -> Tuple[str, str]:
        return list(self.streams.items())[0]

    def by_quality(self, quality: str) -> Tuple[str, str]:
        if quality == "best":
            return self.best

        if quality == "worst":
            return self.worst

        if self.streams.get(quality):
            return quality, self.streams[quality]

        return self._guess_quality(quality)

    def _guess_quality(self, quality):
        quality_lines = re.search(r"^(\d+)", quality)
        if not quality_lines:
            return self.best

        quality_lines = int(quality_lines.group(1))
        for quality_code, stream_url in reversed(self.streams.items()):
            stream_lines = re.search(r"^(\d+)", quality_code)
            if not stream_lines:
                continue

            stream_lines = int(stream_lines.group(1))

            if stream_lines <= quality_lines:
                return quality_code, stream_url

        return self.best


class VideoBlock(QWidget):  # noqa: WPS230
    load_video = pyqtSignal(MediaInput)

    about_to_close = pyqtSignal(str)
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
    is_in_progress_change = pyqtSignal()

    def __init__(self, video_driver, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        # Internal
        self.video_driver_cls = video_driver
        self.id = secrets.token_hex(PLAYER_ID_LENGTH)

        # Static Params
        self.video_params: Optional[Video] = None

        # Runtime Params
        self.is_error = False
        self.is_active = False

        self._title = None
        self._default_title = None
        self.is_live = False
        self.streams = Streams()

        self._is_state_change_in_progress = False

        # Components
        self.overlay_hide_timer = QTimer(self)
        self.overlay_hide_timer.setSingleShot(True)
        self.overlay_hide_timer.timeout.connect(self.hide_overlay)

        self._in_progress_timer = QTimer(self)
        self._in_progress_timer.setSingleShot(True)
        self._in_progress_timer.setInterval(IN_PROGRESS_THRESHOLD_MS)
        self._in_progress_timer.timeout.connect(self.is_in_progress_change)

        self.url_resolver = self.init_url_resolver()
        self.video_driver = self.init_video_driver()

        self.overlay = self.init_overlay()

        self.ui_setup()

        self.status_label.show()
        self.overlay.raise_()
        self.overlay.hide()

    def init_video_driver(self) -> VideoFrameVLC:
        video_driver = self.video_driver_cls(parent=self)

        qt_connect(
            (video_driver.video_ready, self.load_video_finish),
            (video_driver.time_changed, self.time_changed),
            (video_driver.end_reached, self.end_reached),
            (video_driver.playback_status_changed, self.playback_status_changed),
            (video_driver.error, self.video_driver_error),
            (video_driver.crash, self.crash),
            (self.load_video, video_driver.load_video),
        )

        return video_driver

    def reset_video_driver(self):
        self.video_driver.video_ready.disconnect()
        self.video_driver.time_changed.disconnect()
        self.video_driver.end_reached.disconnect()
        self.video_driver.error.disconnect()
        self.video_driver.crash.disconnect()
        self.load_video.disconnect()

        old_driver = self.video_driver

        self.layout_main.takeAt(1).widget()
        self.video_driver = self.init_video_driver()
        self.layout_main.insertWidget(1, self.video_driver)

        old_driver.cleanup()

    def init_url_resolver(self):
        url_resolver = VideoURLResolver(parent=self)
        url_resolver.error.connect(self.network_error)
        url_resolver.url_resolved.connect(self.set_video_url)

        return url_resolver

    def reset_url_resolver(self):
        self.url_resolver.error.disconnect()
        self.url_resolver.url_resolved.disconnect()

        self.url_resolver.cleanup()

        self.url_resolver = self.init_url_resolver()

    def reset(self):
        self.is_error = False
        self.set_status("processing")

        self.reset_video_driver()
        self.reset_url_resolver()

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
            (overlay.exit_clicked, self.close),
            (overlay.play_pause_clicked, self.play_pause),
            (overlay.mute_unmute_clicked, self.mute_unmute),
            (self.time_change, overlay.set_position),
            (self.volume_change, overlay.set_volume_position),
            (self.label_change, overlay.set_label),
            (self.color_change, overlay.set_color),
            (self.loop_start_change, overlay.set_loop_start),
            (self.loop_end_change, overlay.set_loop_end),
            (self.is_paused_change, overlay.set_is_paused),
            (self.is_in_progress_change, overlay.set_is_in_progress),
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
        self.status_label.setMouseTracking(True)
        self.status_label.setWindowFlags(Qt.WindowTransparentForInput)
        self.status_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.layout_main.addWidget(self.status_label)
        self.layout_main.addWidget(self.video_driver)
        self.layout_main.addWidget(self.overlay)

    def crash(self, traceback_txt):
        raise PlayerException(traceback_txt)

    def cleanup(self):
        self.overlay_hide_timer.stop()
        self._in_progress_timer.stop()

        self._log.debug(f"Cleaning up resolver {self.id}")
        self.url_resolver.cleanup()

        self._log.debug(f"Cleaning up driver {self.id}")
        self.video_driver.cleanup()

        self._log.debug(f"Cleaning up done {self.id}")

    def video_driver_error(self):
        if isinstance(self.video_params.uri, VideoURL):
            return self.network_error()

        return self.error()

    def error(self):
        self.is_error = True
        self.set_status("error")
        self.cleanup()

    def network_error(self):
        self.is_error = True
        self.set_status("network-error")
        self.cleanup()

    def set_status(self, status):
        self.overlay.hide()
        self.video_driver.hide()

        self.status_label.icon = status
        self.status_label.show()
        self.repaint()

    def reload(self):
        self.is_live = False
        self.is_error = False
        self.streams = Streams()
        self._title = None
        self._default_title = None

        self.reset()

        video_params = self.video_params
        self.video_params = None

        self.set_video(video_params)

    def close_silently(self):
        self.close(notify=False)

    def close(self, notify=True):
        self._log.debug(f"Closing video block {self.id}")

        if notify:
            self.about_to_close.emit(self.id)

        super().close()

    def closeEvent(self, event) -> None:
        self.cleanup()
        event.accept()

    def wheelEvent(self, event):
        if not self.is_video_initialized or self.is_live:
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
        if not Settings().get("misc/overlay_hide"):
            self.show_overlay()

    def customEvent(self, event):
        if event.type() == OVERLAY_ACTIVITY_EVENT:
            self.show_overlay()

    def is_under_cursor(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    @property
    def size_tuple(self) -> Tuple[int, int]:
        return self.size().width(), self.size().height()

    @property
    def is_video_initialized(self):
        if self.video_driver is None:
            return False

        return self.video_driver.is_video_initialized

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, title):
        self._title = title
        self.label_change.emit(self._title)

    @property
    def time(self):
        return self.video_params.current_position

    @time.setter
    def time(self, time):
        if not self.is_video_initialized:
            return

        if not self.is_live:
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
            # Loop end 1000 ms before actual end for seamless loop
            before_end_gap = 1000
            return self.video_driver.length - before_end_gap

        return self.video_params.loop_end

    def show_overlay(self):
        if not self.is_video_initialized:
            return

        self.overlay.show()
        if Settings().get("misc/overlay_hide"):
            self.overlay_hide_timer.start(1000 * Settings().get("misc/overlay_timeout"))

    def hide_overlay(self):
        if not Settings().get("misc/overlay_hide"):
            return

        self.overlay.hide()

    def time_changed(self, new_time):
        if not self.is_video_initialized:
            return

        self.time = new_time

        if self.is_live:
            return

        # 100ms headspace for slow callbacks
        if self.time < self.loop_start - 100:
            self.seek(self.loop_start)

        elif self.time > self.loop_end:
            self.loop_end_action()

    def playback_status_changed(self, is_paused):
        self._is_state_change_in_progress = False
        self._in_progress_timer.stop()

        self.video_params.is_paused = is_paused
        self.is_paused_change.emit(self.video_params.is_paused)

    def end_reached(self):
        if self.is_live:
            return

        self.loop_end_action()
        self.video_driver.set_pause(False)

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
            self.reset()

        if self.video_params.is_http_url:
            self.url_resolver.resolve(self.video_params.uri)
        else:
            self.load_video.emit(
                MediaInput(
                    uri=str(self.video_params.uri),
                    is_live=False,
                    size=self.size_tuple,
                    video=self.video_params,
                )
            )

    def set_video_url(self, video: ResolvedVideo):
        self._default_title = video.title

        if self.video_params.title is None:
            self.title = video.title

        self.streams = Streams(video.urls)
        self.is_live = video.is_live

        self.load_stream_quality(self.video_params.stream_quality)

    def switch_stream_quality(self, quality: str):
        if quality == self.video_params.stream_quality:
            return

        self.reset()

        self.load_stream_quality(quality)

    def load_stream_quality(self, quality: str):
        quality, url = self.streams.by_quality(quality)

        self.video_params.stream_quality = quality

        self.load_video.emit(
            MediaInput(
                uri=url,
                is_live=self.is_live,
                size=self.size_tuple,
                video=self.video_params,
            )
        )

    def load_video_finish(self):
        # final verdict belongs to VLC
        self.is_live = self.video_driver.is_live

        if self._default_title is None:
            self._default_title = self.video_params.uri_name

        if self.title is None:
            if self.video_params.title is None:
                self.title = self._default_title
            else:
                self.title = self.video_params.title

        self.color_change.emit(self.video_params.color.as_hex())

        self.set_volume(self.video_params.volume)
        self.set_muted(self.video_params.is_muted)

        if not self.is_live:
            if self.video_params.loop_start:
                self.set_loop_start_time(self.video_params.loop_start)

            if self.video_params.loop_end:
                self.set_loop_end_time(self.video_params.loop_end)

            self.video_driver.set_playback_rate(self.video_params.rate)

        self.status_label.hide()
        self.show_overlay()

    def set_aspect(self, aspect):
        self.video_params.aspect_mode = aspect

        self.video_driver.set_aspect_ratio(self.video_params.aspect_mode)

    def toggle_loop_random(self):
        if self.is_live:
            return

        self.video_params.is_start_random = not self.video_params.is_start_random

    def set_loop_start(self):
        if self.is_live:
            return

        self.set_loop_start_time(self.time)

    def set_loop_start_time(self, new_time):
        if new_time == self.video_params.loop_end:
            return

        self.video_params.loop_start = new_time

        self.loop_start_change.emit(new_time / self.video_driver.length)

    def set_loop_end(self):
        if self.is_live:
            return

        self.set_loop_end_time(self.time)

    def set_loop_end_time(self, new_time):
        if new_time == self.video_params.loop_start:
            return

        self.video_params.loop_end = new_time

        self.loop_end_change.emit(new_time / self.video_driver.length)

    def reset_loop(self):
        if self.is_live:
            return

        self.video_params.loop_start = None
        self.video_params.loop_end = None

        self.loop_start_change.emit(0)
        self.loop_end_change.emit(100.0)

    def set_repeat_mode(self, repeat_mode: VideoRepeat):
        if self.is_live:
            return

        self.video_params.repeat_mode = repeat_mode

    def seek_shift_percent(self, shift_percent):
        if self.is_live:
            return

        seek_ms = int(shift_percent / 100 * self.video_driver.length)

        self.seek_shift(seek_ms)

    def seek_shift(self, seek_ms):
        if self.is_live:
            return

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
        if self.is_live:
            return

        random_ms = random.randint(self.loop_start, self.loop_end)  # noqa: S311

        self.seek(random_ms)

    def seek_percent(self, percent):
        if self.is_live:
            return

        seek_ms = int(percent * self.video_driver.length)

        self.seek(seek_ms)

    def seek(self, seek_ms):
        if self.is_live:
            return

        self._log.debug(f"Seeking to {seek_ms}ms")

        if seek_ms < self.loop_start or seek_ms > self.loop_end:
            seek_ms = self.loop_start

        self.video_driver.set_time(seek_ms)
        self.time = seek_ms

    def step_frame(self, frames):
        if self.is_live:
            return

        if not self.video_params.is_paused:
            self.set_pause(True)
            return

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
        if self.is_live:
            return

        self.video_params.rate += 0.1
        self.video_params.rate = round(self.video_params.rate, 1)

        if self.video_params.rate > MAX_RATE:
            self.video_params.rate = MAX_RATE
            self.info_change.emit("Speed: {0}".format(self.video_params.rate))
            return

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    def rate_decrease(self):
        if self.is_live:
            return

        self.video_params.rate -= 0.1
        self.video_params.rate = round(self.video_params.rate, 1)

        if self.video_params.rate < MIN_RATE:
            self.video_params.rate = MIN_RATE
            self.info_change.emit("Speed: {0}".format(self.video_params.rate))
            return

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    def rate_reset(self):
        if self.is_live:
            return

        self.video_params.rate = 1.0

        self.video_driver.set_playback_rate(self.video_params.rate)
        self.info_change.emit("Speed: {0}".format(self.video_params.rate))

    def set_pause(self, paused):
        if self._is_state_change_in_progress:
            return

        if self.video_params.is_paused == paused:
            return

        self._is_state_change_in_progress = True
        self._in_progress_timer.start()

        self.video_driver.set_pause(paused)

    def mute_unmute(self):
        self.set_muted(not self.video_params.is_muted)

    def set_muted(self, muted):
        self.video_params.is_muted = muted

        self.video_driver.audio_set_mute(self.video_params.is_muted)

        self.is_muted_change.emit(self.video_params.is_muted)

    def set_volume(self, percent):
        self.video_params.volume = round(percent, 2)

        self.video_driver.audio_set_volume(self.video_params.volume)

        self.volume_change.emit(percent)

    def play_pause(self):
        self.set_pause(not self.video_params.is_paused)

    def previous_video(self):
        self.switch_video(previous_video_file(self.video_params.uri))

    def next_video(self):
        self.switch_video(next_video_file(self.video_params.uri))

    def shuffle_video(self):
        self.switch_video(next_video_file(self.video_params.uri, is_shuffle=True))

    def switch_video(self, new_video: Path):
        if self.is_live:
            return

        # If single file in the dir and was removed, highly unlikely but still
        if new_video is None:
            self.error()
            return

        if new_video == self.video_params.uri:
            self.seek(self.loop_start)
            return

        self.reset_loop()
        self.video_params.current_position = 0
        self.video_params.uri = new_video
        self.video_params.is_paused = False
        self._title = None
        self._default_title = None

        self.set_video(self.video_params)

    def rename(self):
        new_data = QVideoRenameDialog.get_edits(
            parent=self.parent(),
            title=self.tr("Rename video"),
            orig_title=self._default_title,
            cur_title=self.title,
            cur_color=self.video_params.color.as_rgb_tuple(),
        )

        if new_data is None:
            return

        new_name, new_color = new_data

        self.video_params.color = Color(new_color)

        if new_name == self._default_title:
            self.video_params.title = None
        else:
            self.video_params.title = new_name

        self.title = new_name
        self.color_change.emit(self.video_params.color.as_hex())
