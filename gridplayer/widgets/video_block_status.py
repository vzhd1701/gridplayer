from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLabel


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
