import random

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter


class VideoFrameDummy(QtWidgets.QWidget):
    time_changed = QtCore.pyqtSignal(int)
    video_ready = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal()
    crash = QtCore.pyqtSignal(str)

    def __init__(self, master=None):
        super().__init__(master)

        self._ms_per_frame = 100

        self.length = 100000
        self.video_dimensions = (100, 100)

        self.is_video_meta_ready = False
        self.is_video_initialized = False

        self.setWindowFlags(Qt.WindowTransparentForInput)
        self.setMouseTracking(True)

        self.fake_player_timer = QtCore.QTimer()
        self.fake_player_timer.timeout.connect(self.fake_player_forward)

        self.fake_player_time = 0

        self.color = QColor(random.choice(QColor.colorNames()))

    def fake_player_forward(self):
        if self.fake_player_time + self._ms_per_frame > self.length:
            self.fake_player_time = 0
        else:
            self.fake_player_time += self._ms_per_frame

        self.time_changed.emit(self.fake_player_time)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.color)

    def cleanup(self):
        pass

    def resizeEvent(self, event):
        pass

    def load_video(self, file_path):
        self.is_video_initialized = True
        self.video_ready.emit()

    def load_video_process(self):
        pass

    def load_video_finish(self):
        pass

    def play(self):
        self.fake_player_timer.start(self._ms_per_frame)

    def set_pause(self, is_paused):
        if is_paused:
            self.fake_player_timer.stop()
        else:
            self.fake_player_timer.start(self._ms_per_frame)

    def set_time(self, seek_ms):
        self.fake_player_time = seek_ms

    def set_playback_rate(self, rate):
        pass

    def get_ms_per_frame(self):
        return self._ms_per_frame

    def audio_set_mute(self, is_muted):
        pass

    def audio_set_volume(self, volume):
        pass

    def set_aspect_ratio(self, aspect):
        pass

    def set_scale(self, scale):
        pass
