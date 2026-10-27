"""A row of links to the sections of a long settings page, over what
scrolls: the one in view marked, and a click scrolls to the one clicked."""

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from gridplayer.widgets.settings_controls import FlowLayout, ToggleBox

LINK_PADDING = 9
LINK_HEIGHT = 22
LINK_SPACING = 6


class _Link(ToggleBox):
    """A section's name in a pill, filled in while it is the one in view."""

    padding = LINK_PADDING
    box_height = LINK_HEIGHT
    radius = None
    off_color = "base"

    def __init__(self, text: str):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)


class SectionLinks(QWidget):
    """Links to the sections of the page in a scroll area."""

    def __init__(self, scroll: QScrollArea, sections: list[tuple[str, QWidget]]):
        super().__init__()

        self._scroll = scroll
        self._sections = [widget for _, widget in sections]
        # the one clicked last, for when the page can't scroll as far as it
        self._picked = None

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = FlowLayout(self, LINK_SPACING)
        for index, (title, _) in enumerate(sections):
            link = _Link(title)
            self._group.addButton(link, index)
            layout.addWidget(link)

        self._group.idClicked.connect(self._go_to)
        scroll.verticalScrollBar().valueChanged.connect(self._follow)

        self._follow()

    @property
    def links(self) -> list[QAbstractButton]:
        return self._group.buttons()

    def _top_of(self, section: QWidget) -> int:
        return section.mapTo(self._scroll.widget(), QPoint(0, 0)).y()

    def _go_to(self, index: int):
        self._picked = index
        bar = self._scroll.verticalScrollBar()
        bar.setValue(min(self._top_of(self._sections[index]), bar.maximum()))
        self._follow()

    def _follow(self, *_):
        bar = self._scroll.verticalScrollBar()

        shown = [
            index
            for index, section in enumerate(self._sections)
            if section.isVisibleTo(self._scroll)
        ]
        is_at_end = bar.maximum() > 0 and bar.value() >= bar.maximum()

        if self._picked is not None and is_at_end:
            # down at the end, the one clicked rather than one above it
            current = self._picked
        elif is_at_end and shown:
            # the last can't reach the top, but it is the one being read
            self._picked = None
            current = shown[-1]
        else:
            self._picked = None
            current = 0
            for index in shown:
                if self._top_of(self._sections[index]) <= bar.value():
                    current = index

        self._group.button(current).setChecked(True)
