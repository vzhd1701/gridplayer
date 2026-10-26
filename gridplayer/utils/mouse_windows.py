import ctypes
from ctypes import wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter, Qt
from PyQt5.QtGui import QGuiApplication

_WM_MOUSEMOVE = 0x0200

# each button's bit in a mouse message's wParam, with its virtual key
_BUTTON_KEYS = (
    (0x0001, 0x01),  # MK_LBUTTON, VK_LBUTTON
    (0x0002, 0x02),  # MK_RBUTTON, VK_RBUTTON
    (0x0010, 0x04),  # MK_MBUTTON, VK_MBUTTON
    (0x0020, 0x05),  # MK_XBUTTON1, VK_XBUTTON1
    (0x0040, 0x06),  # MK_XBUTTON2, VK_XBUTTON2
)
_BUTTON_BITS = 0x0073
_SM_SWAPBUTTON = 23

# kept for as long as the application runs
_FILTER: list = []


def _held_buttons() -> int:
    """The buttons held now, as a mouse message's wParam has them."""

    user32 = ctypes.windll.user32
    # the keys are the buttons as they are, the bits as they are taken: the
    # left one is the right one, swapped
    is_swapped = bool(user32.GetSystemMetrics(_SM_SWAPBUTTON))

    held = 0
    for bit, key in _BUTTON_KEYS:
        if is_swapped and key in {0x01, 0x02}:
            key ^= 0x03
        if user32.GetAsyncKeyState(key) & 0x8000:
            held |= bit
    return held


class _HeldButtonsFilter(QAbstractNativeEventFilter):
    """A window under the pointer shown, moved or painted anew, Windows
    sends a move saying no button is held, one held all the same. Qt takes
    the buttons from it, so a drag would end there as if let go of, and
    another start from where the button is still down. Such a move is
    given the buttons held, before Qt sees it.

    Filtering the whole application, mouse messages are seen as the event
    loop takes them, and the same message is dispatched after. Only while
    Qt takes a button to be held is it asked which are: a move with none
    is otherwise the pointer going over, as it says."""

    def nativeEventFilter(self, eventType, message):
        if (
            QGuiApplication.mouseButtons() != Qt.NoButton
            and bytes(eventType) == b"windows_generic_MSG"
        ):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_MOUSEMOVE and not msg.wParam & _BUTTON_BITS:
                msg.wParam |= _held_buttons()
        # PyQt5 requires (filter, result)
        return False, 0


def keep_held_buttons(app) -> None:
    """Every mouse move on Windows saying the buttons held as they are."""

    if QGuiApplication.platformName() != "windows":
        return

    _FILTER.append(_HeldButtonsFilter())
    app.installNativeEventFilter(_FILTER[-1])
