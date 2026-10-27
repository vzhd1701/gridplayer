from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtWidgets import QApplication

# how soon after a popup closes, not by a pick, a click is taken for the one
# that closed it
CLOSING_CLICK_MS = 300


class EatenClick(QObject):
    """The click that closed a popup, eaten: its press, where it comes on
    to the window under the pointer after the popup is gone (a video's
    overlay over a hardware video is a window of its own, which neither
    WA_NoMouseReplay nor the order Qt closes popups in on every system keeps
    it from), and its release. On the popup's own button, it so closes it
    rather than opening it again. Should none come at once, it was not
    closed by a click."""

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
