import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel, QStackedLayout, QWidget

from gridplayer.params.static import VideoAspect
from gridplayer.utils.qt import QABC, QT_ASPECT_MAP, qt_connect
from gridplayer.vlc_player.static import MediaInput, MediaTrack
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_status import VideoStatus


class PauseSnapshot(QLabel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color:black;")

        self._snapshot_pixmap = None

    def set_snapshot_file(self, snapshot_file: str):
        # failed snapshot
        if not snapshot_file:
            self._snapshot_pixmap = QPixmap(1, 1)
            self._snapshot_pixmap.fill(Qt.black)
            return

        self._snapshot_pixmap = QPixmap(snapshot_file)

    def adjust_view(self, size: QSize, aspect, scale: float):
        if self._snapshot_pixmap is None:
            return

        scaled_size = QSize(
            int(size.width() * scale),
            int(size.height() * scale),
        )

        self.setPixmap(
            self._snapshot_pixmap.scaled(
                scaled_size, QT_ASPECT_MAP[aspect], Qt.SmoothTransformation
            )
        )

    def reset(self):
        self._snapshot_pixmap = None


class VideoFrameVLC(QWidget, metaclass=QABC):
    time_changed = pyqtSignal(int)
    playback_status_changed = pyqtSignal(bool)
    end_reached = pyqtSignal()

    video_ready = pyqtSignal()

    error = pyqtSignal(str)
    crash = pyqtSignal(str)
    update_status = pyqtSignal(str, int)

    is_opengl: Optional[bool] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._aspect = VideoAspect.FIT
        self._scale = 1

        self._is_status_change_in_progress = False
        self._is_cleanup_requested = False

        self.media_track: Optional[MediaTrack] = None

        self.ui_setup()

        self.audio_only_placeholder = VideoStatus(parent=self, icon="audio-only")
        self.pause_snapshot = PauseSnapshot(parent=self)

        self.ui_helper_widgets()

        self.video_surface = self.ui_video_surface()

        self.layout().addWidget(self.video_surface)
        self.layout().addWidget(self.pause_snapshot)
        self.layout().addWidget(self.audio_only_placeholder)

        self.video_driver: VLCVideoDriver = self.driver_setup()

        self.driver_connect()

    @property
    def length(self) -> int:
        return self.media_track.length

    @property
    def is_live(self) -> bool:
        return self.media_track.is_live

    @property
    def is_live_video(self) -> bool:
        return not self.media_track.is_audio_only and self.media_track.is_live

    @property
    def is_video_initialized(self) -> bool:
        return self.media_track is not None

    @abstractmethod
    def driver_setup(self) -> VLCVideoDriver:
        ...

    @abstractmethod
    def ui_video_surface(self) -> QWidget:
        ...

    def driver_connect(self) -> None:
        qt_connect(
            (
                self.video_driver.playback_status_changed,
                self.playback_status_changed_emit,
            ),
            (self.video_driver.end_reached, self.end_reached_emit),
            (self.video_driver.time_changed, self.time_changed_emit),
            (self.video_driver.load_finished, self.load_video_finish),
            (self.video_driver.snapshot_taken, self.snapshot_taken),
            (self.video_driver.error, self.error_emit),
            (self.video_driver.crash, self.crash_emit),
            (self.video_driver.update_status, self.update_status_emit),
        )

    def ui_setup(self) -> None:
        self.setWindowFlags(Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.setMouseTracking(True)

        QStackedLayout(self)
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setStackingMode(QStackedLayout.StackAll)

    def ui_helper_widgets(self) -> None:
        self.audio_only_placeholder.setMouseTracking(True)
        self.audio_only_placeholder.setWindowFlags(Qt.WindowTransparentForInput)
        self.audio_only_placeholder.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.audio_only_placeholder.hide()

        self.pause_snapshot.setMouseTracking(True)
        self.pause_snapshot.setWindowFlags(Qt.WindowTransparentForInput)
        self.pause_snapshot.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pause_snapshot.hide()

    def crash_emit(self, exception_txt) -> None:
        self.crash.emit(exception_txt)

    def error_emit(self, error: str) -> None:
        self.cleanup()

        self.error.emit(error)

    def update_status_emit(self, status: str, percent) -> None:
        self.update_status.emit(status, percent)

    def cleanup(self) -> Optional[bool]:
        if self._is_cleanup_requested:
            return True

        self._is_cleanup_requested = True

        self.media_track = None

        self.video_driver.cleanup()

    def adjust_view(self) -> Optional[bool]:
        if self._is_cleanup_requested:
            return True

        if not self.is_video_initialized:
            return False

        if self.media_track.is_audio_only:
            return True

        if self.is_live:
            self.pause_snapshot.adjust_view(self.size(), self._aspect, self._scale)

    def resizeEvent(self, event) -> None:
        self.adjust_view()

    def playback_status_changed_emit(self, is_paused) -> None:
        if not self.is_video_initialized:
            return

        if self.is_live_video and not is_paused:
            self.pause_snapshot.hide()
            self.pause_snapshot.reset()

        self._is_status_change_in_progress = False

        self.playback_status_changed.emit(is_paused)

    def end_reached_emit(self) -> None:
        self.end_reached.emit()

    def time_changed_emit(self, new_time) -> None:
        self.time_changed.emit(new_time)

    def load_video(self, media_input: MediaInput) -> None:
        self._aspect = media_input.video.aspect_mode
        self._scale = media_input.video.scale

        self.video_driver.load_video(media_input)

    def load_video_finish(self, media_track: MediaTrack) -> None:
        self.media_track = media_track

        if self.media_track.is_audio_only:
            self.video_surface.hide()
            self.audio_only_placeholder.show()
        else:
            self.adjust_view()

        self.video_ready.emit()

    def play(self) -> None:
        if self._is_status_change_in_progress:
            return

        self._is_status_change_in_progress = True

        self.video_driver.play()

    def set_pause(self, is_paused) -> None:
        if not self.is_video_initialized:
            return

        if self._is_status_change_in_progress:
            return

        self._is_status_change_in_progress = True

        if self.is_live_video and is_paused:
            self.take_snapshot()
        else:
            self.video_driver.set_pause(is_paused)

    def take_snapshot(self) -> None:
        self.video_driver.snapshot()

    def snapshot_taken(self, snapshot_file: str) -> None:
        self.pause_snapshot.set_snapshot_file(snapshot_file)
        self.pause_snapshot.adjust_view(self.size(), self._aspect, self._scale)
        self.pause_snapshot.show()

        if snapshot_file:
            Path(snapshot_file).unlink()
            Path(snapshot_file).parent.rmdir()

        if self._is_status_change_in_progress:
            self.video_driver.set_pause(True)

    def set_time(self, seek_ms) -> None:
        self.video_driver.set_time(seek_ms)

    def set_playback_rate(self, rate) -> None:
        self.video_driver.set_playback_rate(rate)

    def get_ms_per_frame(self) -> int:
        return int(1000 // self.media_track.fps)

    def audio_set_mute(self, is_muted) -> None:
        self.video_driver.audio_set_mute(is_muted)

    def audio_set_volume(self, volume) -> None:
        self.video_driver.audio_set_volume(volume)

    def set_aspect_ratio(self, aspect: VideoAspect) -> None:
        self._aspect = aspect

        self.adjust_view()

    def set_scale(self, scale) -> None:  # noqa: WPS615
        self._scale = scale

        self.adjust_view()


class VideoFrameVLCProcess(VideoFrameVLC, ABC):
    def __init__(self, process_manager, **kwargs):
        self.process_manager = process_manager

        super().__init__(**kwargs)
