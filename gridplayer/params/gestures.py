"""Mouse drags, and the key held through one, set alongside the shortcuts.

Not actions: a drag is pressed, moved and let go of, with the picture going
along all the while, and a press with no move after it is still a click for
the keymap to have. They are kept in the keymap all the same, under ids of
their own, so that one drag is never two things and Reset all resets them
too (see utils/keymap.py).

Nothing here is translated as it is imported: the settings import this
before the app has a translator.
"""

from enum import Enum, auto
from types import MappingProxyType
from typing import NamedTuple

from gridplayer.utils.qt import translate

GESTURE_MOVE_VIDEO = "gesture:move_video"
GESTURE_DROP_SWITCH = "gesture:drop_switch"
GESTURE_PAN = "gesture:pan"
GESTURE_ZOOM_SELECT = "gesture:zoom_select"


class GestureKind(Enum):
    # drags with a button and the keys held, as many as wanted
    DRAG = auto()
    # a key held while a video is dropped, one or none
    HOLD = auto()
    # shown for what it is, never set
    FIXED = auto()


class Gesture(NamedTuple):
    kind: GestureKind
    keys: tuple[str, ...]
    icon: str


# in the order they are listed in, the first having a drag two of them claim
GESTURES = MappingProxyType(
    {
        GESTURE_MOVE_VIDEO: Gesture(GestureKind.FIXED, ("Drag",), "grid"),
        GESTURE_DROP_SWITCH: Gesture(GestureKind.HOLD, ("Hold Shift",), "drop-switch"),
        GESTURE_PAN: Gesture(GestureKind.DRAG, ("Middle-Drag",), "anchor"),
        GESTURE_ZOOM_SELECT: Gesture(
            GestureKind.DRAG, ("Ctrl+Drag",), "zoom-selection"
        ),
    }
)


def gesture_title(gesture_id: str) -> str:
    titles = {
        GESTURE_MOVE_VIDEO: translate("Keymap", "Move video to another cell"),
        GESTURE_DROP_SWITCH: translate("Keymap", "Hold to switch drop action"),
        GESTURE_PAN: translate("Keymap", "Move picture within its cell"),
        GESTURE_ZOOM_SELECT: translate("Keymap", "Zoom into a part of the picture"),
    }

    return titles[gesture_id]
