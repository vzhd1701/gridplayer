from PyQt5.QtCore import QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget

from gridplayer.utils.layout.lines import SnapKind, Target
from gridplayer.utils.qt import translate

# a light line with a dark edge either side, to show over any picture
LINE_COLOR = QColor("#eeeeee")
EDGE_COLOR = QColor("#111111")


def snap_word(target: Target, is_column: bool) -> str:
    """What a line that snapped says it stopped at: for a video that fits,
    on which side of it."""

    if target.kind is SnapKind.ALIGNED:
        return translate("Grid Lines", "Aligned")
    if target.kind is SnapKind.EVEN:
        return translate("Grid Lines", "Even")

    if target.side == 0:
        return translate("Grid Lines", "Both fit")
    if is_column:
        if target.side < 0:
            return translate("Grid Lines", "Left fits")
        return translate("Grid Lines", "Right fits")
    if target.side < 0:
        return translate("Grid Lines", "Top fits")
    return translate("Grid Lines", "Bottom fits")


class FloatingMark(QWidget):
    """Something shown over the player: a line, a word, a tile's frame.

    A window of its own, as a tip is: nothing painted in the player's own
    window shows over a hardware video, which is a native window. It never
    takes the mouse, nor is it ever made the active window.
    """

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.ToolTip
            | Qt.FramelessWindowHint
            | Qt.WindowTransparentForInput
            | Qt.NoDropShadowWindowHint,
        )

        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def show_at(self, rect: QRect) -> None:
        """Shown at rect on the screen, painted anew if it is not the size
        it was."""

        if rect != self.geometry():
            if rect.size() != self.size():
                self.update()
            self.setGeometry(rect)

        if self.isHidden():
            self.show()

            # made on its first show, the window can be put where the
            # geometry says in device pixels, on a screen that scales
            if self.geometry() != rect:
                self.setGeometry(rect)


class GridLineMark(FloatingMark):
    """The line between two cells that the pointer is on, to be moved, or
    that is being moved: thicker where it has snapped (see GridLines.snaps).
    """

    # the light middle of the line, of one snapped, and either dark edge
    core = 2
    snapped_core = 4
    edge = 1

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_column = True

    def show_line(
        self, is_column: bool, position: int, start: int, end: int, is_snapped: bool
    ) -> None:
        """Show the line: a column's at x = position from y = start to end,
        a row's at y = position from x = start to end, on the screen."""

        core = self.snapped_core if is_snapped else self.core
        thickness = core + 2 * self.edge
        low = position - thickness // 2

        if is_column:
            rect = QRect(low, start, thickness, end - start)
        else:
            rect = QRect(start, low, end - start, thickness)

        if is_column != self._is_column:
            self._is_column = is_column
            self.update()

        self.show_at(rect)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), EDGE_COLOR)

        if self._is_column:
            core = self.rect().adjusted(self.edge, 0, -self.edge, 0)
        else:
            core = self.rect().adjusted(0, self.edge, 0, -self.edge)

        painter.fillRect(core, LINE_COLOR)


class GridLineTag(FloatingMark):
    """A word beside a line being moved that has snapped, saying why it
    stopped there: a video fits, or the cells are even."""

    # between the word and the box's edge, and between the box and the line
    padding = QSize(6, 2)
    gap = 8

    def __init__(self, parent=None):
        super().__init__(parent)

        self._text = ""

    def show_snap(
        self,
        target: Target | None,
        is_column: bool,
        position: int,
        pointer: QPoint,
        area: QRect,
    ) -> None:
        """Say what a line moved to position in the area, on the screen,
        snapped to (see snap_word), beside it by the pointer; nothing where
        it has not."""

        if target is None:
            if self.isVisible():
                self.hide()
            return

        if is_column:
            at = QPoint(area.x() + position, pointer.y())
        else:
            at = QPoint(pointer.x(), area.y() + position)
        self.show_text(snap_word(target, is_column), is_column, at, area)

    def show_text(self, text: str, is_column: bool, at: QPoint, room: QRect) -> None:
        """Show the word beside a column's line at x = at.x(), or under a
        row's at y = at.y(), by the pointer, kept inside room."""

        metrics = self.fontMetrics()
        size = QSize(
            metrics.horizontalAdvance(text) + 2 * self.padding.width(),
            metrics.height() + 2 * self.padding.height(),
        )

        if is_column:
            x = at.x() + self.gap
            if x + size.width() > room.right():
                x = at.x() - self.gap - size.width()
            y = at.y() - size.height() // 2
        else:
            x = at.x() - size.width() // 2
            y = at.y() + self.gap
            if y + size.height() > room.bottom():
                y = at.y() - self.gap - size.height()

        x = min(max(x, room.left()), room.right() - size.width())
        y = min(max(y, room.top()), room.bottom() - size.height())
        rect = QRect(QPoint(x, y), size)

        if text != self._text:
            self._text = text
            self.update()

        self.show_at(rect)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), EDGE_COLOR)
        painter.fillRect(self.rect().adjusted(1, 1, -1, -1), LINE_COLOR)
        painter.setPen(EDGE_COLOR)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
