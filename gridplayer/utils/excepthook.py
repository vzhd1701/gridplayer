import contextlib
import logging
import traceback

from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.exception import ExceptionDialog
from gridplayer.utils.misc import force_terminate

# drags under way: the system holds the mouse for one, and a dialog shown
# from inside it cannot be clicked until it is over
_drags = 0

# what went wrong during one, to be said once it is over
_untold: str | None = None


@contextlib.contextmanager
def dragging():
    """A drag under way, for what goes wrong meanwhile to be said once it
    is over: it is called off for that."""

    global _drags

    _drags += 1

    try:
        yield
    finally:
        _drags -= 1

        if not _drags and _untold is not None:
            _tell_and_quit(_untold)


def excepthook(exc_type, exc_value, exc_tb):
    global _untold

    if exc_type is KeyboardInterrupt:
        logging.info("KeyboardInterrupt")  # noqa: LOG015
        force_terminate()

    # Log into file
    exception_txt = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    logging.getLogger("UNHANDLED").critical(exception_txt)

    # Terminate if Qt is not up
    if QApplication.instance() is None:
        force_terminate(1)

    if _drags:
        if _untold is None:
            _untold = exception_txt

        QDrag.cancel()
        return

    _tell_and_quit(exception_txt)


def _tell_and_quit(exception_txt: str):
    for w in QApplication.topLevelWidgets():
        w.hide()
    QApplication.restoreOverrideCursor()

    exc_dialog = ExceptionDialog(exception_txt)
    exc_dialog.exec_()

    force_terminate()
