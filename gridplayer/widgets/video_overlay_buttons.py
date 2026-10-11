from abc import ABC, abstractmethod
from collections.abc import Callable

from PyQt5.QtCore import (
    QEvent,
    QPropertyAnimation,
    QRect,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QFontMetrics, QPainter
from PyQt5.QtWidgets import QWIDGETSIZE_MAX

from gridplayer.utils.qt import QABC
from gridplayer.widgets.video_overlay_elements import OverlayWidget
from gridplayer.widgets.video_overlay_icons import (
    draw_cross,
    draw_list,
    draw_pause,
    draw_play,
    draw_spin_circle,
    draw_volume_off,
    draw_volume_on,
)


class OverlayButton(OverlayWidget, metaclass=QABC):
    clicked = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMouseTracking(True)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumSize(self.minimumWidth(), self.minimumHeight())

        self._is_off = False

    @abstractmethod
    def icon(self, rect, painter, color_fg, color_bg): ...

    @abstractmethod
    def icon_off(self, rect, painter, color_fg, color_bg): ...

    def paintEvent(self, event):
        painter = QPainter(self)

        color_bg, color_fg = self.colors()

        self.paint_box(painter, fill=color_bg)

        self.draw_icon(painter, color_fg, color_bg)

    def colors(self) -> tuple[QColor, QColor]:
        """Its box's fill and what is drawn on it, the other way round under
        the mouse."""

        if self.underMouse():
            return self.hover_fill_color, self.hover_text_color

        return self.fill_color, self.text_color

    def draw_icon(self, painter: QPainter, color_fg: QColor, color_bg: QColor):
        if self._is_off:
            self.icon_off(self.rect(), painter, color_fg, color_bg)
        else:
            self.icon(self.rect(), painter, color_fg, color_bg)

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


class OverlayButtonDynamic(OverlayButton, ABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._is_in_progress = False
        self._icon_spin = 0

        self._animation = QPropertyAnimation(self, b"icon_spin")
        self._animation.setDuration(500)
        self._animation.setStartValue(0)
        self._animation.setEndValue(360)
        self._animation.setLoopCount(-1)

    @pyqtProperty(int)
    def icon_spin(self):
        return self._icon_spin

    @icon_spin.setter
    def icon_spin(self, icon_spin):
        self._icon_spin = icon_spin
        self.update()

    def draw_icon(self, painter, color_fg, color_bg):
        if self._is_in_progress:
            draw_spin_circle(self.rect(), painter, color_fg, color_bg, self._icon_spin)
        else:
            super().draw_icon(painter, color_fg, color_bg)

    @property
    def is_in_progress(self):
        return self._is_in_progress

    @is_in_progress.setter
    def is_in_progress(self, is_in_progress):
        self._is_in_progress = is_in_progress

        if is_in_progress:
            self._animation.start()
        else:
            self._animation.stop()

        self.update()

    @OverlayButton.is_off.setter
    def is_off(self, is_off):
        self.is_in_progress = False

        OverlayButton.is_off.fset(self, is_off)


class OverlayExitButton(OverlayButton):
    def icon(self, rect, painter, color_fg, color_bg):
        return draw_cross(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg): ...


class OverlayPlayPauseButton(OverlayButtonDynamic):
    def icon(self, rect, painter, color_fg, color_bg):
        return draw_play(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg):
        return draw_pause(rect, painter, color_fg, color_bg)


class OverlayVolumeButton(OverlayButton):
    def icon(self, rect, painter, color_fg, color_bg):
        return draw_volume_on(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg):
        return draw_volume_off(rect, painter, color_fg, color_bg)


class OverlayTextButton(OverlayButton):
    """A button that says what it does, where an icon alone would not: the
    actions of a stopped cell, one still loading, or failed.

    Its sign, where it has one, drawn as the icon buttons draw theirs, the
    same size in the same place: Play, then Stop while it loads, then the
    video's pause, one after the other where the others were."""

    margin = 7
    gap = 6

    # how far in the icon buttons' icons end, from their right edge
    sign_inset = 5

    def __init__(self, text: str = "", sign: Callable | None = None, **kwargs):
        super().__init__(**kwargs)

        self._text = text
        self._sign = sign

        # as wide as what it says, where the others are square
        self.setMaximumWidth(QWIDGETSIZE_MAX)
        self._fit()

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, text: str):
        self._text = text

        self._fit()
        self.update()

    def changeEvent(self, event):
        if event.type() == QEvent.FontChange:
            self._fit()

        super().changeEvent(event)

    def _sign_rect(self) -> QRect:
        side = self.minimumHeight()

        return QRect(0, 0, side, side)

    def _text_left(self) -> int:
        if self._sign is None:
            return self.margin

        return self.minimumHeight() - self.sign_inset + self.gap

    def _fit(self):
        text_width = QFontMetrics(self.font()).horizontalAdvance(self._text)

        self.setFixedWidth(self._text_left() + text_width + self.margin)

    def paintEvent(self, event):
        painter = QPainter(self)

        color_bg, color_fg = self.colors()

        self.paint_box(painter, fill=color_bg)

        if self._sign is not None:
            painter.save()
            self._sign(self._sign_rect(), painter, color_fg, color_bg)
            painter.restore()

        painter.setPen(color_fg)
        painter.drawText(
            self.rect().adjusted(self._text_left(), 0, 0, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            self._text,
        )

    def icon(self, rect, painter, color_fg, color_bg): ...

    def icon_off(self, rect, painter, color_fg, color_bg): ...


class OverlayListPlaceButton(OverlayTextButton):
    """Which item of its list a cell plays, "3/12", after the list's sign:
    clicked, the List window on the list.

    The number in the labels' contrast, to be read as theirs is; the sign
    in the buttons', for it to be seen as one of them.
    """

    # around the sign and the number, and between them
    margin = 6
    gap = 5

    def __init__(self, **kwargs):
        super().__init__(sign=draw_list, **kwargs)

    def _sign_rect(self) -> QRect:
        # as tall as the other buttons' icons are, a little wider
        height = self.minimumHeight() - 10
        width = round(height * 1.2)

        return QRect(self.margin, (self.minimumHeight() - height) // 2, width, height)

    def _text_left(self) -> int:
        return self._sign_rect().right() + 1 + self.gap

    def _fit(self):
        # the sign alone while the list is still being read
        if not self._text:
            self.setFixedWidth(self.margin + self._sign_rect().width() + self.margin)
            return

        super()._fit()
