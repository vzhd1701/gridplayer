from PyQt5.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    Qt,
    pyqtProperty,
)
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from gridplayer.utils.darkmode import is_dark_mode


class LoadingBars(QWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.bars = [
            JumpingBar(start_percent=start_percent, parent=self)
            for start_percent in (100, 70, 50, 70, 100)
        ]

        for cur_bar in self.bars:
            layout.addWidget(cur_bar)
            if cur_bar != self.bars[-1]:
                layout.addStretch()

    def resizeEvent(self, event):
        # maintain 1:1 ratio

        size_min = min(event.size().width(), event.size().height())

        h_margin = round((self.size().width() - size_min) / 2)

        self.layout().setContentsMargins(h_margin, 0, h_margin, 0)


class JumpingBar(QWidget):
    bar_grow_ms = 100
    bar_wane_ms = 900

    bar_lowest_percent = 30

    def __init__(self, start_percent=100, **kwargs):
        super().__init__(**kwargs)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._color = QColor(Qt.white) if is_dark_mode() else QColor(Qt.black)

        self._bar_percent = min(max(start_percent, self.bar_lowest_percent), 100)

        self._animation = self._init_animation()

        self._initial_time = self._calc_init_time(start_percent)

    @pyqtProperty(int)
    def bar_percent(self):
        return self._bar_percent

    @bar_percent.setter
    def bar_percent(self, percent):  # noqa: WPS440
        self._bar_percent = percent
        self.update()

    @property
    def roundness(self):
        return min(self.width() / 3, 10)

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self._color)
        painter.setBrush(self._color)

        middle = self.rect().center()

        bar_height = (self.rect().height() - 10) * (self._bar_percent / 100)

        bar_rect = QRectF(
            0,
            middle.y() - bar_height / 2,
            self.rect().width(),
            bar_height,
        )

        painter.drawRoundedRect(bar_rect, self.roundness, self.roundness)

    def showEvent(self, event) -> None:
        self._animation.start()
        self._animation.setCurrentTime(self._initial_time)

    def hideEvent(self, event) -> None:
        self._initial_time = self._animation.currentTime()
        self._animation.stop()

    def _init_animation(self):  # noqa: WPS213
        animation_up = QPropertyAnimation(self, b"bar_percent")
        animation_up.setDuration(self.bar_grow_ms)
        animation_up.setStartValue(self.bar_lowest_percent)
        animation_up.setEndValue(100)
        animation_up.setEasingCurve(QEasingCurve.BezierSpline)

        animation_down = QPropertyAnimation(self, b"bar_percent")
        animation_down.setDuration(self.bar_wane_ms)
        animation_down.setStartValue(100)
        animation_down.setEndValue(self.bar_lowest_percent)
        animation_down.setEasingCurve(QEasingCurve.BezierSpline)

        anim_group = QSequentialAnimationGroup(self)
        anim_group.addAnimation(animation_up)
        anim_group.addAnimation(animation_down)
        anim_group.setLoopCount(-1)

        return anim_group

    def _calc_init_time(self, start_percent):
        total_time = self._animation.duration()

        if start_percent == 100:
            return total_time

        return int(
            ((100 - self._bar_percent) / (100 - self.bar_lowest_percent)) * total_time
        )
