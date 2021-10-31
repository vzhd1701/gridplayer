import random

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget


class VideoFrameDummy(QWidget):
    time_changed = pyqtSignal(int)
    video_ready = pyqtSignal()
    error = pyqtSignal()
    crash = pyqtSignal(str)

    is_opengl = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.is_video_initialized = False

        self.length = 100000
        self.video_dimensions = (100, 100)

        self._ms_per_frame = 100
        self._is_video_meta_ready = False

        self._fake_player_timer = QTimer(self)
        self._fake_player_timer.timeout.connect(self.fake_player_forward)

        self._fake_player_time = 0

        self._color = QColor(random.choice(QColor.colorNames()))  # noqa: S311

        self.setWindowFlags(Qt.WindowTransparentForInput)
        self.setMouseTracking(True)

    def fake_player_forward(self):
        if self._fake_player_time + self._ms_per_frame > self.length:
            self._fake_player_time = 0
        else:
            self._fake_player_time += self._ms_per_frame

        self.time_changed.emit(self._fake_player_time)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._color)

    def cleanup(self):
        """dummy"""

    def resizeEvent(self, event):
        """dummy"""

    def load_video(self, file_path):
        self.is_video_initialized = True
        self.video_ready.emit()

    def load_video_process(self):
        """dummy"""

    def load_video_finish(self):
        """dummy"""

    def play(self):
        self._fake_player_timer.start(self._ms_per_frame)

    def set_pause(self, is_paused):
        if is_paused:
            self._fake_player_timer.stop()
        else:
            self._fake_player_timer.start(self._ms_per_frame)

    def set_time(self, seek_ms):
        self._fake_player_time = seek_ms

    def set_playback_rate(self, rate):
        """dummy"""

    def get_ms_per_frame(self):  # noqa: WPS615
        return self._ms_per_frame

    def audio_set_mute(self, is_muted):
        """dummy"""

    def audio_set_volume(self, volume):
        """dummy"""

    def set_aspect_ratio(self, aspect):
        """dummy"""

    def set_scale(self, scale):
        """dummy"""
