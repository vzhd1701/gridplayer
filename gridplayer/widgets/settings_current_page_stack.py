from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QSizePolicy, QStackedWidget

from gridplayer.widgets.settings_page_scroll_area import PageScrollArea


class CurrentPageStackedWidget(QStackedWidget):
    """Size to the current page's height, but keep enough width for the
    widest page so switching to a scrolling page does not clip the bar.

    *min_width* is a floor under that, not a minimum width: one set on the
    widget would be taken over the hint, and a page wider than it, with a
    larger font or a longer translation, would be cut off at the right.
    """

    def __init__(self, parent=None, *, min_width: int = 0):
        super().__init__(parent)
        self._min_width = min_width
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        current = self.currentWidget()
        width = self._min_width
        for i in range(self.count()):
            width = max(width, self.widget(i).sizeHint().width())
        height = self._page_height(current)
        return QSize(width, height)

    def minimumSizeHint(self):
        current = self.currentWidget()
        width = self._min_width
        for i in range(self.count()):
            width = max(width, self.widget(i).minimumSizeHint().width())
        height = current.minimumSizeHint().height() if current is not None else 0
        return QSize(width, height)

    def _page_height(self, page) -> int:
        """A page that scrolls can be any height, so it is made as tall as
        the tallest page that cannot needs to be: those all fit, and the
        long ones scroll rather than make the dialog taller. Needs rather
        than would like: what one would like has room to spare."""

        if page is None:
            return 0

        if not isinstance(page, PageScrollArea):
            return page.sizeHint().height()

        fixed = [
            self.widget(i).minimumSizeHint().height()
            for i in range(self.count())
            if not isinstance(self.widget(i), PageScrollArea)
        ]

        return max(fixed, default=page.sizeHint().height())
