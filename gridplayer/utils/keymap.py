"""Keymap helpers: default bindings, mouse sequences, settings merge."""

from __future__ import annotations

from enum import Enum, auto

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeySequence, QWheelEvent
from PyQt5.QtWidgets import QApplication

from gridplayer.models.keymap_overrides import KeymapOverrides
from gridplayer.params.actions import ACTIONS
from gridplayer.params.gestures import GESTURE_DROP_SWITCH, GESTURES, GestureKind
from gridplayer.settings import Settings


class WheelDirection(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


# One notch of a plain mouse wheel, in the eighths of a degree Qt counts a
# turn in.
WHEEL_NOTCH = 120

# Left that long, what a wheel turned short of a notch is let go, so that a
# brush of a touchpad does not finish a notch begun minutes before.
WHEEL_PAUSE_MS = 500


class WheelNotches:
    """Whole notches out of a wheel's turns, however finely it reports them.

    A plain mouse wheel reports each notch as it clicks. A touchpad or a
    smooth scrolling wheel reports a notch in many small turns, and a
    shortcut fired on every one of them would seek or zoom many times over
    for one stroke. Turns are added up here and a shortcut fired once for
    each whole notch they come to. Turned the other way, on the other axis
    or with other keys held, it starts over.
    """

    def __init__(self):
        self._rest = 0
        self._turned = None
        self._last_ms = None

    def notches(self, event) -> int:
        """How many notches the wheel has come to with this turn."""

        delta = event.angleDelta()
        is_vertical = delta.y() != 0
        turn = delta.y() if is_vertical else delta.x()
        turned = (is_vertical, turn > 0, int(event.modifiers()))

        ms = event.timestamp()
        is_paused = self._last_ms is not None and ms - self._last_ms > WHEEL_PAUSE_MS

        if turned != self._turned or is_paused:
            self._rest = 0

        self._turned = turned
        self._last_ms = ms

        self._rest += abs(turn)
        notches, self._rest = divmod(self._rest, WHEEL_NOTCH)

        return notches


# The key held while a video is dropped, to drop it the other way, as the
# keymap stores it. Meta is not one: the desktop has it, and on macOS it is
# the Control key, with which a click is a right click.
HOLD_KEYS = {
    "Hold Shift": Qt.ShiftModifier,
    "Hold Ctrl": Qt.ControlModifier,
    "Hold Alt": Qt.AltModifier,
}


class DragProblem(Enum):
    """Why a mouse drag cannot be one to set."""

    NOT_A_DRAG = auto()
    # with the left button and no key, it moves the video to another cell
    MOVES_VIDEO = auto()
    # the menu opens on the press on X11 and macOS, before it is a drag
    RIGHT_BUTTON = auto()
    # the desktop's, and on macOS the Control key, which makes a right click
    META = auto()


class MouseButtonSequence:
    modifier_map = {
        Qt.ControlModifier: "Ctrl",
        Qt.AltModifier: "Alt",
        Qt.ShiftModifier: "Shift",
        Qt.MetaModifier: "Meta",
    }

    click_map = {
        Qt.LeftButton: "Click",
        Qt.RightButton: "Right-Click",
        Qt.MiddleButton: "Middle-Click",
        Qt.BackButton: "Back-Click",
        Qt.ForwardButton: "Forward-Click",
        Qt.TaskButton: "Task-Click",
        Qt.ExtraButton4: "Click-4",
        Qt.ExtraButton5: "Click-5",
        Qt.ExtraButton6: "Click-6",
        Qt.ExtraButton7: "Click-7",
        Qt.ExtraButton8: "Click-8",
        Qt.ExtraButton9: "Click-9",
        Qt.ExtraButton10: "Click-10",
        Qt.ExtraButton11: "Click-11",
        Qt.ExtraButton12: "Click-12",
        Qt.ExtraButton13: "Click-13",
        Qt.ExtraButton14: "Click-14",
        Qt.ExtraButton15: "Click-15",
        Qt.ExtraButton16: "Click-16",
        Qt.ExtraButton17: "Click-17",
        Qt.ExtraButton18: "Click-18",
        Qt.ExtraButton19: "Click-19",
        Qt.ExtraButton20: "Click-20",
        Qt.ExtraButton21: "Click-21",
        Qt.ExtraButton22: "Click-22",
        Qt.ExtraButton23: "Click-23",
        Qt.ExtraButton24: "Click-24",
    }

    wheel_direction_map = {
        WheelDirection.UP: "Wheel-Up",
        WheelDirection.DOWN: "Wheel-Down",
        WheelDirection.LEFT: "Wheel-Left",
        WheelDirection.RIGHT: "Wheel-Right",
    }

    # the same buttons pressed and moved: "Middle-Drag", "Drag-4"
    drag_map = {
        button: name.replace("Click", "Drag") for button, name in click_map.items()
    }

    def __init__(self, sequence: str):
        *modifiers, button = sequence.split("+")
        if set(modifiers) - set(self.modifier_map.values()):
            raise ValueError("Bad mouse sequence")

        if button not in self.allowed_buttons:
            raise ValueError("Bad mouse sequence")

        self.modifiers = [m for m in self.modifier_map.values() if m in modifiers]
        self.button_name = button
        # the keys always in the same order, the one a press writes them in
        self.sequence = "+".join([*self.modifiers, button])

    def __eq__(self, other):
        if not isinstance(other, MouseButtonSequence):
            return NotImplemented
        return self.sequence == other.sequence

    def __hash__(self):
        return hash(self.sequence)

    def __str__(self):
        return self.sequence

    @property
    def allowed_buttons(self) -> set:
        double = {f"Double {button}" for button in self.click_map.values()}
        return {
            *self.click_map.values(),
            *self.wheel_direction_map.values(),
            *double,
            *self.drag_map.values(),
        }

    @property
    def is_wheel(self) -> bool:
        return self.button_name in self.wheel_direction_map.values()

    @property
    def is_drag(self) -> bool:
        return self.button_name in self.drag_map.values()

    @property
    def is_click(self) -> bool:
        return not self.is_wheel and not self.is_drag

    @property
    def drag_button(self) -> Qt.MouseButton | None:
        """The button a drag is made with, None if it is not a drag."""

        for button, name in self.drag_map.items():
            if name == self.button_name:
                return button

        return None

    @classmethod
    def is_mouse_sequence(cls, text: str) -> bool:
        try:
            cls(text)
        except ValueError:
            return False
        return True

    @classmethod
    def from_event(cls, event):
        # Press (capture UI) and Release (video actions) both map to Click
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            return cls._convert_button(
                button=event.button(),
                is_double=False,
                wheel_direction=None,
                modifiers=event.modifiers(),
            )

        if event.type() == QEvent.MouseButtonDblClick:
            return cls._convert_button(
                button=event.button(),
                is_double=True,
                wheel_direction=None,
                modifiers=event.modifiers(),
            )

        if isinstance(event, QWheelEvent) or event.type() == QEvent.Wheel:
            delta = event.angleDelta()
            if delta.y() > 0:
                wheel_direction = WheelDirection.UP
            elif delta.y() < 0:
                wheel_direction = WheelDirection.DOWN
            elif delta.x() > 0:
                wheel_direction = WheelDirection.LEFT
            elif delta.x() < 0:
                wheel_direction = WheelDirection.RIGHT
            else:
                raise ValueError("Empty wheel event")

            return cls._convert_button(
                button=None,
                is_double=False,
                wheel_direction=wheel_direction,
                modifiers=event.modifiers(),
            )

        raise ValueError("Unsupported event")

    @classmethod
    def from_drag_press(cls, button, modifiers):
        """The drag a press starts, with the keys held as it went down."""

        return cls._convert_button(
            button=button,
            is_double=False,
            wheel_direction=None,
            modifiers=modifiers,
            is_drag=True,
        )

    @classmethod
    def _convert_button(
        cls, button, is_double, wheel_direction, modifiers, is_drag=False
    ):
        if button is not None and is_drag:
            key_name = cls.drag_map.get(button)
        elif button is not None:
            key_name = cls.click_map.get(button)
        elif wheel_direction is not None:
            key_name = cls.wheel_direction_map[wheel_direction]
        else:
            key_name = None

        if not key_name:
            raise ValueError("Bad mouse sequence")

        if is_double:
            key_name = f"Double {key_name}"

        sequence = [key for mod, key in cls.modifier_map.items() if modifiers & mod]
        sequence.append(key_name)
        return cls("+".join(sequence))


def normalize_shortcut(shortcut: str) -> str | None:
    """Canonical form for conflict checks and QAction binding.

    Keyboard chords are round-tripped through ``QKeySequence.PortableText`` so
    ``u`` and ``U`` (etc.) compare equal. Mouse sequences are validated as-is.
    Returns None if the shortcut is empty or not a valid keyboard/mouse chord.

    Main-keyboard Return and keypad Enter are stored as the single logical name
    ``Enter`` (see ``qkeysequences_for_shortcut`` for applying both physical keys).
    """
    if not shortcut or not str(shortcut).strip():
        return None

    text = str(shortcut).strip()
    if text in HOLD_KEYS:
        return text

    if MouseButtonSequence.is_mouse_sequence(text):
        return str(MouseButtonSequence(text))

    seq = QKeySequence(text, QKeySequence.PortableText)
    portable = seq.toString(QKeySequence.PortableText)
    if not portable:
        # e.g. unknown key names → count may be >0 but string is empty
        return None
    # PortableText uses "Return" for the main Enter key and "Enter" for numpad.
    # Users expect one "Enter" binding for both.
    return portable.replace("Return", "Enter")


def qkeysequences_for_shortcut(shortcut: str) -> list[QKeySequence]:
    """Build QKeySequence list for a normalized keyboard shortcut string.

    Logical ``Enter`` (with optional modifiers) is expanded to both main-keyboard
    Return and keypad Enter so either key triggers the action.
    """
    if MouseButtonSequence.is_mouse_sequence(shortcut):
        return []

    variants = [shortcut]
    parts = shortcut.split("+")
    if parts and parts[-1] == "Enter":
        variants.append(
            "+".join([*parts[:-1], "Return"]) if len(parts) > 1 else "Return"
        )
    elif parts and parts[-1] == "Return":
        variants.append("+".join([*parts[:-1], "Enter"]) if len(parts) > 1 else "Enter")

    result: list[QKeySequence] = []
    seen_codes: set[int] = set()
    for variant in variants:
        seq = QKeySequence(variant, QKeySequence.PortableText)
        if not seq.count():
            continue
        code = int(seq[0])
        if code in seen_codes:
            continue
        if not seq.toString(QKeySequence.PortableText):
            continue
        seen_codes.add(code)
        result.append(seq)
    return result


def normalize_shortcuts(shortcuts: list[str] | None) -> list[str]:
    """Normalize a list, drop invalids, preserve order, unique."""
    if not shortcuts:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in shortcuts:
        normalized = normalize_shortcut(item)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def default_shortcuts(action: dict) -> list[str]:
    """Resolve default shortcut list from an ACTIONS entry (`keys` or legacy `key`)."""
    if "keys" in action:
        keys = action["keys"]
        if isinstance(keys, str):
            raw = [keys]
        else:
            raw = [str(k) for k in keys]
    else:
        key = action.get("key")
        if not key:
            return []
        if isinstance(key, (list, tuple)):
            raw = [str(k) for k in key]
        else:
            raw = [str(key)]

    return normalize_shortcuts(raw)


def default_keymap() -> dict[str, list[str]]:
    keymap = {
        action_id: default_shortcuts(action)
        for action_id, action in ACTIONS.items()
        if not action.get("menu_generator")
    }

    keymap.update(_default_gesture_keymap())

    return keymap


def _default_gesture_keymap() -> dict[str, list[str]]:
    return {
        gesture_id: list(gesture.keys)
        for gesture_id, gesture in GESTURES.items()
        if gesture.kind is not GestureKind.FIXED
    }


def drag_problem(shortcut: str) -> DragProblem | None:
    """Why a drag cannot be set, None if it can."""

    try:
        sequence = MouseButtonSequence(shortcut)
    except ValueError:
        return DragProblem.NOT_A_DRAG

    if not sequence.is_drag:
        return DragProblem.NOT_A_DRAG

    if "Meta" in sequence.modifiers:
        return DragProblem.META

    if sequence.drag_button == Qt.RightButton:
        return DragProblem.RIGHT_BUTTON

    if sequence.drag_button == Qt.LeftButton and not sequence.modifiers:
        return DragProblem.MOVES_VIDEO

    return None


def _is_drag(shortcut: str) -> bool:
    return (
        MouseButtonSequence.is_mouse_sequence(shortcut)
        and MouseButtonSequence(shortcut).is_drag
    )


def fit_shortcuts(action_id: str, shortcuts: list[str]) -> list[str]:
    """The shortcuts that can be what the action or gesture is set to.

    A drag only to a drag, the key held through a drop only to that, and
    neither to an action: the editor never lets them be, a settings file
    written by hand might.
    """

    shortcuts = normalize_shortcuts(shortcuts)
    gesture = GESTURES.get(action_id)

    if gesture is None:
        return [s for s in shortcuts if s not in HOLD_KEYS and not _is_drag(s)]

    if gesture.kind is GestureKind.DRAG:
        return [s for s in shortcuts if drag_problem(s) is None]

    if gesture.kind is GestureKind.HOLD:
        return [s for s in shortcuts if s in HOLD_KEYS][:1]

    return list(gesture.keys)


def merge_keymap(
    defaults: dict[str, list[str]] | None = None,
    overrides: dict[str, list[str]] | KeymapOverrides | None = None,
) -> dict[str, list[str]]:
    """Full effective map: defaults with sparse overrides applied."""
    defaults = defaults or default_keymap()
    result = {k: list(v) for k, v in defaults.items()}

    if overrides is None:
        return dedupe_keymap(result, defaults)

    for action_id, shortcuts in overrides.items():
        if action_id not in result and action_id not in ACTIONS:
            continue
        result[action_id] = fit_shortcuts(action_id, list(shortcuts))

    return dedupe_keymap(result, defaults)


def gesture_shortcuts(
    gesture_id: str,
    overrides: dict[str, list[str]] | KeymapOverrides | None = None,
) -> list[str]:
    """What a gesture is set to, as the keymap in the settings has it.

    Only the gestures are gone through, not every action: this is asked on
    every press of a mouse button.
    """

    if overrides is None:
        overrides = Settings().get("player/keymap")

    defaults = _default_gesture_keymap()
    gestures = {
        g_id: fit_shortcuts(g_id, list(overrides.get(g_id, keys)))
        for g_id, keys in defaults.items()
    }

    return dedupe_keymap(gestures, defaults).get(gesture_id, [])


def is_gesture_press(gesture_id: str, event) -> bool:
    """Whether a press starts a drag the gesture is set to.

    The keys held have to be the very ones of the drag, no more: with one
    drag set to Ctrl and another to Ctrl and Shift, each is only the one.
    """

    # as the drop does: the press may not say, where the window was not
    # focused when it came
    held = QApplication.queryKeyboardModifiers() | event.modifiers()

    try:
        drag = MouseButtonSequence.from_drag_press(event.button(), held)
    except ValueError:
        return False

    return drag.sequence in gesture_shortcuts(gesture_id)


def drop_switch_modifier(
    overrides: dict[str, list[str]] | KeymapOverrides | None = None,
) -> Qt.KeyboardModifier | None:
    """The key held while a video is dropped to drop it the other way."""

    held = gesture_shortcuts(GESTURE_DROP_SWITCH, overrides)

    return HOLD_KEYS[held[0]] if held else None


def dedupe_keymap(
    bindings: dict[str, list[str]],
    defaults: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Ensure each shortcut is owned by at most one action.

    When several actions claim the same chord (e.g. reassign then reset
    another action to defaults), keep a single winner:

    1. Prefer an owner where the shortcut is **not** a default for that action
       (explicit user assignment wins over a default restored by reset).
    2. If several such owners exist, or all owners have it as a default, keep
       the first owner in stable ``ACTIONS`` / defaults order and strip the rest.
    """
    defaults = defaults or default_keymap()
    # Normalize so ``u`` / ``U`` are the same chord before ownership is decided
    result = {
        action_id: normalize_shortcuts(list(shortcuts))
        for action_id, shortcuts in bindings.items()
    }
    defaults_norm = {
        action_id: normalize_shortcuts(list(shortcuts))
        for action_id, shortcuts in defaults.items()
    }

    order: list[str] = list(defaults_norm.keys())
    for action_id in result:
        if action_id not in order:
            order.append(action_id)

    owners: dict[str, list[str]] = {}
    for action_id in order:
        for shortcut in result.get(action_id, []):
            owners.setdefault(shortcut, []).append(action_id)

    for shortcut, action_ids in owners.items():
        if len(action_ids) <= 1:
            continue

        non_default_owners = [
            action_id
            for action_id in action_ids
            if shortcut not in defaults_norm.get(action_id, [])
        ]
        if len(non_default_owners) == 1:
            winner = non_default_owners[0]
        elif non_default_owners:
            winner = next(
                action_id for action_id in order if action_id in non_default_owners
            )
        else:
            winner = next(action_id for action_id in order if action_id in action_ids)

        for action_id in action_ids:
            if action_id != winner:
                result[action_id] = [s for s in result[action_id] if s != shortcut]

    return result


def sparse_overrides(
    bindings: dict[str, list[str]],
    defaults: dict[str, list[str]] | None = None,
) -> KeymapOverrides:
    """Keep only actions whose shortcuts differ from defaults.

    Bindings are deduplicated first so one shortcut cannot be saved on two actions.
    """
    defaults = defaults or default_keymap()
    bindings = dedupe_keymap(bindings, defaults)
    overrides = {
        action_id: list(shortcuts)
        for action_id, shortcuts in bindings.items()
        if list(shortcuts) != list(defaults.get(action_id, []))
    }
    return KeymapOverrides(overrides)


def normalize_key_sequence(seq: QKeySequence) -> str:
    """Portable single-chord string matching ACTIONS style."""
    text = seq.toString(QKeySequence.PortableText)
    if not text:
        return ""
    text = text.split(", ")[0]
    # Same logical Enter as normalize_shortcut
    return text.replace("Return", "Enter")


def key_sequence_from_event(event) -> str | None:
    """Build a single portable shortcut string from a key event, or None if incomplete."""
    key = event.key()
    if key in (
        Qt.Key_Control,
        Qt.Key_Shift,
        Qt.Key_Alt,
        Qt.Key_Meta,
        Qt.Key_AltGr,
        Qt.Key_unknown,
    ):
        return None

    modifiers = event.modifiers()
    modifiers &= ~(Qt.KeypadModifier | Qt.GroupSwitchModifier)

    if key == Qt.Key_Backtab:
        key = Qt.Key_Tab
        modifiers |= Qt.ShiftModifier

    return normalize_key_sequence(QKeySequence(int(modifiers) | key))


def split_shortcuts(shortcuts: list[str]) -> tuple[list[str], list[str]]:
    """Split into (keyboard_shortcuts, mouse_shortcuts). Inputs should be normalized."""
    keyboard: list[str] = []
    mouse: list[str] = []
    for sc in normalize_shortcuts(shortcuts):
        if MouseButtonSequence.is_mouse_sequence(sc):
            mouse.append(sc)
        else:
            keyboard.append(sc)
    return keyboard, mouse


def find_duplicate_shortcuts(
    bindings: dict[str, list[str]],
) -> dict[str, list[str]]:
    """shortcut -> [action_ids that use it] for any shortcut used more than once."""
    owners: dict[str, list[str]] = {}
    for action_id, shortcuts in bindings.items():
        for sc in normalize_shortcuts(shortcuts):
            owners.setdefault(sc, []).append(action_id)
    return {sc: ids for sc, ids in owners.items() if len(ids) > 1}
