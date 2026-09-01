from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QSizePolicy, QStackedWidget


class CurrentPageStackedWidget(QStackedWidget):
    """Size to the current page's height, but keep enough width for the
    widest page so switching to a scrolling page does not clip the bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        current = self.currentWidget()
        width = self.minimumWidth()
        for i in range(self.count()):
            width = max(width, self.widget(i).sizeHint().width())
        height = current.sizeHint().height() if current is not None else 0
        return QSize(width, height)

    def minimumSizeHint(self):
        current = self.currentWidget()
        width = self.minimumWidth()
        for i in range(self.count()):
            width = max(width, self.widget(i).minimumSizeHint().width())
        height = current.minimumSizeHint().height() if current is not None else 0
        return QSize(width, height)
