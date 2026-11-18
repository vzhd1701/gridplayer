from __future__ import annotations

from collections.abc import Callable, Iterable

from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QRect, QSize, QVariantAnimation, pyqtSignal
from PyQt6.QtWidgets import QLayout, QWidget, QWidgetItem

from gridplayer.utils.layout.boxes import Box, box_rect

Place = Callable[[int, int], Iterable[tuple[QWidget, Box]]]

# how long a cell takes to slide to its place, in ms (see CellLayout.glide)
GLIDE_MS = 170


def _place_nothing(_width: int, _height: int) -> Iterable[tuple[QWidget, Box]]:
    return ()


class CellLayout(QLayout):
    """Puts each cell in its box, all of them in one pass.

    Where the cells go is asked of a function, given the area's size, each
    time the area is laid out. A cell gets its place even while hidden, so
    one about to be shown is in place before it is on screen: a hardware
    video's cell is a native window, and one shown and then moved takes the
    pixels it covered along with it.

    Showing a hidden cell lays the area out there and then. Since every
    place is known before any cell is shown, showing several in a row, as
    leaving single mode does, never resizes the cells already on show
    through the grids in between. A hardware video sends the first size to
    VLC at once and holds the rest back (see NATIVE_VIEW_RESIZE_INTERVAL_MS),
    so it would be drawn stretched or zoomed into its cell for a moment.

    Told to (see glide), the cells slide to their places the next time the
    area is laid out, not jump there. One on its way stays on it while the
    area is laid out again with the same place for it; given another, it
    jumps there, unless told to slide again.
    """

    # each time the cells have been put in their places
    laid_out = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)

        self._items: list[QWidgetItem] = []
        self._place: Place = _place_nothing

        # where the cells went the last time the area was laid out
        self._placed: list[tuple[QWidget, Box]] = []

        # laid out next, the cells slide to their places, all but these;
        # None, they jump there
        self._still: list[QWidget] | None = None
        # the cells on their way: where each started from, and where to
        self._gliding: dict[QWidget, tuple[QRect, QRect]] = {}
        self._glide = QVariantAnimation(self)
        self._glide.setDuration(GLIDE_MS)
        self._glide.setStartValue(0.0)
        self._glide.setEndValue(1.0)
        self._glide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._glide.valueChanged.connect(self._glide_to)
        self._glide.finished.connect(self._glide_done)

    def set_widgets(self, widgets: Iterable[QWidget]) -> None:
        while self.takeAt(0) is not None:
            pass

        for widget in widgets:
            self.addWidget(widget)

    def set_place(self, place: Place) -> None:
        self._place = place
        self.invalidate()

    def placed(self) -> list[tuple[QWidget, Box]]:
        """The cells and their boxes, as the area was last laid out."""

        return [
            (widget, box) for widget, box in self._placed if not sip.isdeleted(widget)
        ]

    def glide(self, still: Iterable[QWidget] = ()) -> None:
        """The next time the area is laid out, the cells on show slide to
        their places, all but these."""

        self._still = list(still)
        self.invalidate()

    def is_gliding(self) -> bool:
        return bool(self._gliding)

    def set_cells(self, cells: list[tuple[QWidget, Box]]) -> list[QWidget]:
        """Lay out these widgets in these boxes, whatever the area's size.
        Returns the widgets."""

        widgets = [widget for widget, _box in cells]
        self.set_widgets(widgets)
        self.set_place(lambda _width, _height: cells)
        return widgets

    # --- QLayout ---

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def sizeHint(self):
        return QSize(0, 0)

    def minimumSize(self):
        return QSize(0, 0)

    def setGeometry(self, rect):
        super().setGeometry(rect)

        # a widget deleted since is out of the items, still in the place
        laid_out = {id(item.widget()) for item in self._items}

        still, self._still = self._still, None
        started = False

        self._placed = []
        for widget, box in self._place(rect.width(), rect.height()):
            if id(widget) not in laid_out or sip.isdeleted(widget):
                continue

            self._placed.append((widget, box))

            x, y, width, height = box_rect(box, rect.width(), rect.height())
            to = QRect(rect.x() + x, rect.y() + y, width, height)

            on_its_way = self._gliding.get(widget)
            is_sliding = (
                still is not None
                and widget.isVisible()
                and not any(widget is other for other in still)
            )
            if is_sliding and widget.geometry() != to:
                self._gliding[widget] = (widget.geometry(), to)
                started = True
            elif on_its_way is None or on_its_way[1] != to:
                self._gliding.pop(widget, None)
                widget.setGeometry(to)

        # those placed no more are stopped where they are
        placed = {id(widget) for widget, _box in self._placed}
        self._gliding = {
            widget: way for widget, way in self._gliding.items() if id(widget) in placed
        }

        if started:
            # those on their way already go on from where they are
            self._gliding = {
                widget: (widget.geometry(), to)
                for widget, (_start, to) in self._gliding.items()
            }
            self._glide.stop()
            self._glide.start()
        elif not self._gliding:
            self._glide.stop()

        self.laid_out.emit()

    def _glide_to(self, share: float) -> None:
        def at(a: int, b: int) -> int:
            return round(a + (b - a) * share)

        for widget, (start, to) in list(self._gliding.items()):
            if sip.isdeleted(widget):
                del self._gliding[widget]
                continue

            widget.setGeometry(
                QRect(
                    at(start.x(), to.x()),
                    at(start.y(), to.y()),
                    at(start.width(), to.width()),
                    at(start.height(), to.height()),
                )
            )

    def _glide_done(self) -> None:
        self._glide_to(1.0)
        self._gliding = {}
        # the cells in their places only now: laid_out came as they set off
        self.laid_out.emit()
