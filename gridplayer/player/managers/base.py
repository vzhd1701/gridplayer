import inspect
import logging

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import QApplication, QWidget

from gridplayer.widgets.video_overlay import OverlayBlock

# how many arguments each handler of an event_map takes, by its function:
# asked of inspect once, not at every event (a move of the mouse is a dozen)
_param_counts: dict = {}


def _param_count(handler) -> int:
    key = getattr(handler, "__func__", handler)
    count = _param_counts.get(key)
    if count is None:
        count = _param_counts[key] = len(inspect.signature(handler).parameters)
    return count


class ManagerBase(QObject):
    def __init__(self, context, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._ctx = context

    def eventFilter(self, event_object, event) -> bool:
        try:
            event_function = self.event_map.get(event.type())
        except AttributeError:
            return False

        if event_function is not None:
            nparams = _param_count(event_function)
            if nparams == 0:
                result = event_function()
            elif nparams == 1:
                result = event_function(event)
            else:
                result = event_function(event, event_object)
            return result is True

        return False

    def is_elsewhere(self, event_object) -> bool:
        """Whether an event is for a window over the player rather than the
        player's own, or a video's overlay of its own: the List window, say.
        Whatever videos are under it, its mouse and its drops are its own.

        Filtering the whole application, an event is seen at the window it
        came to before the widget it is for, see PanManager.
        """

        widget = event_object

        if isinstance(widget, QWindow):
            widget = QWidget.find(widget.winId())

        # the application's own, or a window that is no widget's
        if not isinstance(widget, QWidget):
            return False

        window = widget.window()

        # one never taking the mouse, a line or a word shown over the player
        if window.windowFlags() & Qt.WindowType.WindowTransparentForInput:
            return False

        return window is not self.parent() and not isinstance(window, OverlayBlock)

    def is_elsewhere_at(self, global_pos) -> bool:
        """Whether a window over the player is where the pointer is."""

        window = QApplication.topLevelAt(global_pos)

        return window is not None and self.is_elsewhere(window)
