"""A template's icon drawn from the template itself, as the built-in ones
(resources/icons/custom/grid template *.svg) are: on a square of 600 with a
margin of 19, the cells on a pitch of 600 over the longer side, gaps of 37.5
between them, the grid in the middle of the shorter side; small cells solid,
big ones an outline 25 wide; corners rounded by 12.5. The gaps and the
corners shrink for a grid of more than four cells a side, to keep cells to
see."""

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QIconEngine, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QApplication, QStyleOption

from gridplayer.params.static import GridTemplate

_BOX = 600
_MARGIN = 19
_CONTENT = 562.5
_GAP = 37.5
_RIM = 25
_RADIUS = 12.5


def grid_template_icon(template: GridTemplate) -> QIcon:
    return QIcon(_TemplateIconEngine(template))


def template_shapes(template: GridTemplate) -> list[tuple[QRectF, bool]]:
    """Each cell's square, on the 600 square, and whether it is a big one."""

    longest = max(template.rows, template.cols)
    pitch = (_CONTENT + _GAP) / longest
    gap = min(_GAP, pitch / 4)

    left = (_CONTENT - (template.cols * pitch - gap)) / 2
    top = (_CONTENT - (template.rows * pitch - gap)) / 2

    big = set(template.big)

    return [
        (
            QRectF(
                _MARGIN + left + col * pitch,
                _MARGIN + top + row * pitch,
                colspan * pitch - gap,
                rowspan * pitch - gap,
            ),
            (row, col, rowspan, colspan) in big,
        )
        for row, col, rowspan, colspan in template.places()
    ]


def _color() -> QColor:
    # the theme's icons are black, or white in the dark one
    return QColor(Qt.white if QIcon.themeName() == "dark" else Qt.black)


class _TemplateIconEngine(QIconEngine):
    def __init__(self, template: GridTemplate):
        super().__init__()

        self._template = template

    def paint(self, painter, rect, mode, state):
        ratio = painter.device().devicePixelRatioF()

        pixmap = self.pixmap(rect.size() * ratio, mode, state)
        pixmap.setDevicePixelRatio(ratio)

        painter.drawPixmap(rect, pixmap)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        side = min(size.width(), size.height())
        painter.translate((size.width() - side) / 2, (size.height() - side) / 2)
        painter.scale(side / _BOX, side / _BOX)

        painter.fillPath(self._path(), _color())
        painter.end()

        if mode == QIcon.Disabled:
            return QApplication.style().generatedIconPixmap(
                QIcon.Disabled, pixmap, QStyleOption()
            )

        return pixmap

    def _path(self) -> QPainterPath:
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)

        for cell, is_big in template_shapes(self._template):
            radius = min(_RADIUS, cell.width() / 4, cell.height() / 4)
            path.addRoundedRect(cell, radius, radius)

            if is_big:
                rim = min(_RIM, cell.width() / 4, cell.height() / 4)
                path.addRect(cell.adjusted(rim, rim, -rim, -rim))

        return path

    def clone(self):
        return _TemplateIconEngine(self._template)
