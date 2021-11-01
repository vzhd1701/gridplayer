from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QPainter
from PyQt5.QtWidgets import qApp

from gridplayer.widgets.video_overlay_elements import OverlayWidget
from gridplayer.widgets.video_overlay_icons import (
    draw_cross,
    draw_pause,
    draw_play,
    draw_volume_off,
    draw_volume_on,
)


class OverlayButton(OverlayWidget):
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumSize(self.minimumWidth(), self.minimumHeight())

        self._is_off = False

    def icon(self):
        raise NotImplementedError

    def icon_off(self):
        raise NotImplementedError

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.underMouse():
            color_bg = Qt.gray
            color_fg = Qt.white
        else:
            color_bg = Qt.white
            color_fg = Qt.gray

        painter.fillRect(self.rect(), color_bg)

        if self._is_off:
            self.icon_off(self.rect(), painter, color_fg)
        else:
            self.icon(self.rect(), painter, color_fg)

    def underMouse(self):
        return qApp.widgetAt(QCursor.pos()) is self

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        """Consume to avoid parent event"""

        if event.button() == Qt.LeftButton:
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

        event.ignore()

    def mouseDoubleClickEvent(self, event):
        """Consume to avoid parent event"""
        self.mousePressEvent(event)

        event.accept()

    @property
    def is_off(self):
        return self._is_off

    @is_off.setter
    def is_off(self, is_off):
        self._is_off = is_off
        self.update()


class OverlayExitButton(OverlayButton):
    def __init__(self):
        super().__init__()

        self.icon = draw_cross


class OverlayPlayPauseButton(OverlayButton):
    def __init__(self):
        super().__init__()

        self.icon = draw_play
        self.icon_off = draw_pause


class OverlayVolumeButton(OverlayButton):
    def __init__(self):
        super().__init__()

        self.icon = draw_volume_on
        self.icon_off = draw_volume_off
