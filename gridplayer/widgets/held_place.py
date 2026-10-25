from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QSizePolicy, QWidget

from gridplayer.utils.qt import translate
from gridplayer.widgets.cell_chrome import (
    TEXT_ALPHA,
    chrome_color,
    dashed_frame,
    paint_solid_outline,
)


class HeldPlace(QWidget):
    """In the Fixed Strip, the place of the video shown big, kept for it:
    a frame saying so. Pointing at it is pointing at that video (see
    GridManager.strip_held_video_at)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.video_block = None

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_video(self, video_block):
        if video_block is self.video_block:
            return

        self.video_block = video_block
        self.update()

    def minimumSizeHint(self):
        return QSize(0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        paint_solid_outline(self, painter)

        if self.video_block is None:
            return

        # not "playing": the big one may be paused
        text = translate("Main Window", "Current")
        rect, stroke, _ = dashed_frame(self)
        inset = stroke * 4
        text_rect = rect.adjusted(inset, inset, -inset, -inset)

        painter.setPen(chrome_color(self, TEXT_ALPHA))
        painter.drawText(
            text_rect,
            Qt.AlignCenter,
            painter.fontMetrics().elidedText(
                text, Qt.ElideRight, int(text_rect.width())
            ),
        )
