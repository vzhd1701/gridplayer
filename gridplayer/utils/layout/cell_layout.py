from __future__ import annotations

from collections.abc import Callable, Iterable

from PyQt5 import sip
from PyQt5.QtCore import QRect, QSize
from PyQt5.QtWidgets import QLayout, QWidget, QWidgetItem

from gridplayer.utils.layout.boxes import Box, box_rect

Place = Callable[[int, int], Iterable[tuple[QWidget, Box]]]


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
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)

        self._items: list[QWidgetItem] = []
        self._place: Place = _place_nothing

        # where the cells went the last time the area was laid out
        self._placed: list[tuple[QWidget, Box]] = []

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

        self._placed = []
        for widget, box in self._place(rect.width(), rect.height()):
            if id(widget) not in laid_out or sip.isdeleted(widget):
                continue

            self._placed.append((widget, box))

            x, y, width, height = box_rect(box, rect.width(), rect.height())
            widget.setGeometry(QRect(rect.x() + x, rect.y() + y, width, height))
