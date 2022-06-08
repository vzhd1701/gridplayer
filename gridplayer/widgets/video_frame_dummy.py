import random

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget

from gridplayer.vlc_player.static import MediaInput, MediaTrack
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC

FAKE_VIDEO_LENGTH = 100000
FAKE_VIDEO_FPS = 25


class VideoDriverDummy(VLCVideoDriver):
    def cleanup(self):
        ...

    def load_video(self, media_input: MediaInput):
        ...

    def snapshot(self):
        ...

    def play(self):
        ...

    def set_pause(self, is_paused):
        ...

    def set_time(self, seek_ms):
        ...

    def set_playback_rate(self, rate):
        ...

    def audio_set_mute(self, is_muted):
        ...

    def audio_set_volume(self, volume):
        ...


class VideoFrameDummy(VideoFrameVLC):
    is_opengl = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._color = QColor(random.choice(QColor.colorNames()))  # noqa: S311

        self._fake_media_track = MediaTrack(
            is_audio_only=False,
            length=FAKE_VIDEO_LENGTH,
            video_dimensions=(100, 100),
            fps=FAKE_VIDEO_FPS,
        )

        self._fake_player_time = 0
        self._ms_per_frame = 100

        self._fake_player_timer = QTimer(self)
        self._fake_player_timer.timeout.connect(self._fake_player_forward)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._color)

    def driver_setup(self) -> VLCVideoDriver:
        return VideoDriverDummy(parent=self)

    def ui_video_surface(self):
        return QWidget(self)

    def load_video(self, media_input: MediaInput):
        self.load_video_finish(self._fake_media_track)

        self.time_changed.emit(0)
        self.playback_status_changed.emit(media_input.video.is_paused)
        if not media_input.video.is_paused:
            self.play()

    def play(self):
        self._fake_player_timer.start(self._ms_per_frame)
        self.playback_status_changed.emit(True)

    def set_pause(self, is_paused):
        if is_paused:
            self._fake_player_timer.stop()
        else:
            self._fake_player_timer.start(self._ms_per_frame)

        self.playback_status_changed.emit(is_paused)

    def set_time(self, seek_ms):
        self._fake_player_time = seek_ms

    def get_ms_per_frame(self):  # noqa: WPS615
        return self._ms_per_frame

    def _fake_player_forward(self):
        if self._fake_player_time + self._ms_per_frame > self.length:
            self._fake_player_time = 0
        else:
            self._fake_player_time += self._ms_per_frame

        self.time_changed.emit(self._fake_player_time)
        self.update()
