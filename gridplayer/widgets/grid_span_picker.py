from PyQt5.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.utils.compositor_linux import is_compositor_running
from gridplayer.utils.qt import translate

# the cells of the grid shown to pick from, as many as it has up to this
MAX_PICK = 10

CELL = 16
GAP = 3
PADDING = 8
# under the cells, the size picked
LABEL_HEIGHT = 20

BACK_COLOR = QColor(24, 24, 24, 238)
BORDER_COLOR = QColor("#555555")
CELL_COLOR = QColor("#6a6a6a")
CURRENT_COLOR = QColor("#e6e6e6")
PICK_COLOR = QColor("#e6e6e6")
NO_ROOM_COLOR = QColor(230, 230, 230, 70)
TEXT_COLOR = QColor("#e6e6e6")

# between the columns and the rows of the size picked
TIMES = "\u00d7"

# how soon after the picker closes, not by a pick, a click is taken for the
# one that closed it
CLOSING_CLICK_MS = 300


class _EatenClick(QObject):
    """The click that closed a popup, eaten: its press, where it comes on
    to the window under the pointer after the popup is gone (a video's
    overlay over a hardware video is a window of its own, which neither
    WA_NoMouseReplay nor the order Qt closes popups in on every system keeps
    it from), and its release. Should none come at once, it was not closed
    by a click."""

    def __init__(self):
        app = QApplication.instance()
        super().__init__(app)
        app.installEventFilter(self)
        self._is_done = False
        self._is_pressed = False
        QTimer.singleShot(CLOSING_CLICK_MS, self._expire)

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind in {QEvent.MouseButtonPress, QEvent.MouseButtonDblClick}:
            self._is_pressed = True
            return True
        if kind == QEvent.MouseButtonRelease:
            # the window's and then its widget's, each eaten
            QTimer.singleShot(0, self._done)
            return True
        return False

    def _expire(self) -> None:
        # held down still: its release, whenever it comes
        if not self._is_pressed and QApplication.mouseButtons() == Qt.NoButton:
            self._done()

    def _done(self) -> None:
        if self._is_done:
            return
        self._is_done = True
        QApplication.instance().removeEventFilter(self)
        self.deleteLater()


class GridSpanPicker(QWidget):
    """A video's cell's size picked as a table's is in a word processor:
    the grid's cells shown, from the top left as far as the pointer, and
    clicked. The cell's size as it is now is outlined; one there is no
    room for is filled faintly, and says so."""

    picked = pyqtSignal(int, int)
    closed = pyqtSignal()

    def __init__(self, rows, cols, span, can_set, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)

        self.setAttribute(Qt.WA_DeleteOnClose)
        # a click outside closes it, as a menu, and does nothing else: on
        # its own button too, which so closes it
        self.setAttribute(Qt.WA_NoMouseReplay)
        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._rows = min(rows, MAX_PICK)
        self._cols = min(cols, MAX_PICK)
        self._span = span
        self._can_set = can_set

        self._pick: tuple[int, int] = span
        # closed by a click inside it, not outside
        self._is_picked = False
        self._is_pick_ok = True

        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(
            2 * PADDING + self._cols * (CELL + GAP) - GAP,
            2 * PADDING + self._rows * (CELL + GAP) - GAP + LABEL_HEIGHT,
        )

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # closed by a click outside it: that click does nothing else
        if not self._is_picked:
            _EatenClick()
        self.closed.emit()

    def popup_under(self, under: QRect) -> None:
        """Shown under a button, its right edge in line with the button's,
        kept on the screen."""

        place = QRect(QPoint(0, 0), self.size())
        place.moveTopRight(under.bottomRight() + QPoint(0, 4))

        screen = QGuiApplication.screenAt(under.center())
        if screen is not None:
            room = screen.availableGeometry()
            if place.bottom() > room.bottom():
                place.moveBottom(under.top() - 4)
            place.moveLeft(
                min(max(place.left(), room.left()), room.right() - place.width())
            )

        self.move(place.topLeft())
        self.show()

    def _cell_rect(self, row: int, col: int) -> QRectF:
        return QRectF(
            PADDING + col * (CELL + GAP), PADDING + row * (CELL + GAP), CELL, CELL
        )

    def _cell_at(self, point: QPoint) -> tuple[int, int]:
        col = (point.x() - PADDING) // (CELL + GAP)
        row = (point.y() - PADDING) // (CELL + GAP)
        return min(max(row, 0), self._rows - 1), min(max(col, 0), self._cols - 1)

    def mouseMoveEvent(self, event) -> None:
        row, col = self._cell_at(event.pos())
        pick = (row + 1, col + 1)
        if pick != self._pick:
            self._pick = pick
            self._is_pick_ok = pick == self._span or self._can_set(*pick)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self.rect().contains(event.pos()):
            return

        if self._is_pick_ok:
            self.picked.emit(*self._pick)
        self._is_picked = True
        self.close()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        back = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._is_translucent:
            painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.setPen(QPen(BORDER_COLOR, 1))
        painter.setBrush(BACK_COLOR)
        painter.drawRoundedRect(back, 6, 6)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        rows, cols = self._pick
        fill = PICK_COLOR if self._is_pick_ok else NO_ROOM_COLOR
        for row in range(self._rows):
            for col in range(self._cols):
                rect = self._cell_rect(row, col)
                is_current = row < self._span[0] and col < self._span[1]
                painter.setPen(QPen(CURRENT_COLOR if is_current else CELL_COLOR, 1))
                painter.setBrush(fill if row < rows and col < cols else Qt.transparent)
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 2, 2)

        if self._is_pick_ok:
            text = f"{cols} {TIMES} {rows}"
        else:
            text = translate("Edit Grid", "No room")

        label = QRectF(
            0, self.height() - PADDING - LABEL_HEIGHT, self.width(), LABEL_HEIGHT
        )
        painter.setPen(TEXT_COLOR)
        painter.drawText(label, Qt.AlignCenter, text)
