"""Unit tests for gridplayer.utils.keymap."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QKeyEvent, QKeySequence, QMouseEvent, QWheelEvent
from PyQt5.QtWidgets import QApplication

from gridplayer.utils.keymap import (
    KeymapOverrides,
    MouseButtonSequence,
    WheelDirection,
    dedupe_keymap,
    default_keymap,
    default_shortcuts,
    find_duplicate_shortcuts,
    key_sequence_from_event,
    merge_keymap,
    normalize_key_sequence,
    normalize_shortcut,
    normalize_shortcuts,
    qkeysequences_for_shortcut,
    sparse_overrides,
    split_shortcuts,
)


# QKeySequence / event helpers need a QApplication
@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


# ---------------------------------------------------------------------------
# KeymapOverrides
# ---------------------------------------------------------------------------


def test_keymap_overrides_mapping_api():
    empty = KeymapOverrides({})
    assert not empty
    assert list(empty) == []
    assert empty.get("missing") is None
    assert empty.get("missing", []) == []

    o = KeymapOverrides({"A": ["X"], "B": ["Y"]})
    assert bool(o)
    assert o["A"] == ["X"]
    assert o.get("B") == ["Y"]
    assert dict(o.items()) == {"A": ["X"], "B": ["Y"]}
    assert set(o) == {"A", "B"}


def test_keymap_overrides_json_roundtrip():
    original = KeymapOverrides({"Play / Pause": ["Space", "Middle-Click"]})
    raw = original.model_dump_json()
    restored = KeymapOverrides.model_validate_json(raw)
    assert restored.root == original.root


# ---------------------------------------------------------------------------
# MouseButtonSequence
# ---------------------------------------------------------------------------


def test_mouse_sequence_parse_and_properties():
    assert MouseButtonSequence.is_mouse_sequence("Click")
    assert MouseButtonSequence.is_mouse_sequence("Double Click")
    assert MouseButtonSequence.is_mouse_sequence("Shift+Wheel-Up")
    assert MouseButtonSequence.is_mouse_sequence("Ctrl+Alt+Middle-Click")
    assert not MouseButtonSequence.is_mouse_sequence("Ctrl+Space")
    assert not MouseButtonSequence.is_mouse_sequence("NotAKey")
    assert not MouseButtonSequence.is_mouse_sequence("Ctrl+Foo")

    seq = MouseButtonSequence("Shift+Wheel-Down")
    assert str(seq) == "Shift+Wheel-Down"
    assert seq.is_wheel
    assert not seq.is_click

    seq = MouseButtonSequence("Double Click")
    assert seq.is_click
    assert not seq.is_wheel


def test_mouse_sequence_eq_hash():
    a = MouseButtonSequence("Click")
    b = MouseButtonSequence("Click")
    c = MouseButtonSequence("Right-Click")
    assert a == b
    assert a != c
    assert hash(a) == hash(b)
    assert {a, b, c} == {a, c}
    assert a != "Click"  # NotImplemented path for non-sequence


def test_mouse_sequence_rejects_bad_input():
    with pytest.raises(ValueError):
        MouseButtonSequence("NotAButton")
    with pytest.raises(ValueError):
        MouseButtonSequence("Foo+Click")  # unknown modifier
    with pytest.raises(ValueError):
        MouseButtonSequence("Ctrl+NotAButton")


def _mouse_event(event_type, button=Qt.LeftButton, modifiers=Qt.NoModifier):
    return QMouseEvent(
        event_type,
        QPoint(0, 0),
        button,
        button,
        modifiers,
    )


def _wheel_event(dx=0, dy=0, modifiers=Qt.NoModifier):
    # PyQt5 QWheelEvent constructor variants differ; use the common form
    return QWheelEvent(
        QPoint(0, 0),
        QPoint(0, 0),
        QPoint(0, 0),
        QPoint(dx, dy),
        0,
        Qt.Vertical if dy else Qt.Horizontal,
        Qt.NoButton,
        modifiers,
    )


def test_mouse_sequence_from_press_release_and_double():
    press = _mouse_event(QEvent.MouseButtonPress, Qt.LeftButton)
    assert str(MouseButtonSequence.from_event(press)) == "Click"

    release = _mouse_event(QEvent.MouseButtonRelease, Qt.MiddleButton, Qt.ShiftModifier)
    assert str(MouseButtonSequence.from_event(release)) == "Shift+Middle-Click"

    dbl = _mouse_event(QEvent.MouseButtonDblClick, Qt.LeftButton, Qt.ControlModifier)
    assert str(MouseButtonSequence.from_event(dbl)) == "Ctrl+Double Click"


def test_mouse_sequence_from_wheel_directions():
    assert str(MouseButtonSequence.from_event(_wheel_event(dy=120))) == "Wheel-Up"
    assert str(MouseButtonSequence.from_event(_wheel_event(dy=-120))) == "Wheel-Down"
    assert str(MouseButtonSequence.from_event(_wheel_event(dx=120))) == "Wheel-Left"
    assert str(MouseButtonSequence.from_event(_wheel_event(dx=-120))) == "Wheel-Right"

    shift_up = _wheel_event(dy=120, modifiers=Qt.ShiftModifier)
    assert str(MouseButtonSequence.from_event(shift_up)) == "Shift+Wheel-Up"


def test_mouse_sequence_from_event_errors():
    empty_wheel = _wheel_event(dx=0, dy=0)
    with pytest.raises(ValueError, match="Empty wheel"):
        MouseButtonSequence.from_event(empty_wheel)

    key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier)
    with pytest.raises(ValueError, match="Unsupported"):
        MouseButtonSequence.from_event(key_ev)

    # Unknown mouse button not in click_map
    bad = _mouse_event(QEvent.MouseButtonPress, Qt.MouseButton(0))
    with pytest.raises(ValueError, match="Bad mouse"):
        MouseButtonSequence.from_event(bad)


def test_wheel_direction_enum_used_in_map():
    assert MouseButtonSequence.wheel_direction_map[WheelDirection.UP] == "Wheel-Up"


# ---------------------------------------------------------------------------
# Normalize / qkeysequences
# ---------------------------------------------------------------------------


def test_normalize_shortcut_edge_cases():
    assert normalize_shortcut("") is None
    assert normalize_shortcut("   ") is None
    assert normalize_shortcut(None) is None  # type: ignore[arg-type]
    assert normalize_shortcut("not-a-real-key-xyz") is None
    assert normalize_shortcut("Click") == "Click"
    assert normalize_shortcut("  Ctrl+Space  ") == "Ctrl+Space"


def test_normalize_letter_case_for_conflicts():
    """Defaults use ``u``; capture produces ``U`` — must be the same chord."""
    assert normalize_shortcut("u") == "U"
    assert normalize_shortcut("U") == "U"
    assert normalize_shortcut("Ctrl+u") == "Ctrl+U"
    assert normalize_shortcuts(["u", "U", "Click"]) == ["U", "Click"]
    assert normalize_shortcuts(None) == []
    assert normalize_shortcuts([]) == []

    defaults = {
        "Crop Left +": ["U"],
        "Auto Reload: %v": [],
    }
    bindings = {
        "Crop Left +": ["u"],
        "Auto Reload: %v": ["U"],
    }
    cleaned = dedupe_keymap(bindings, defaults)
    owners = [aid for aid, scs in cleaned.items() if "U" in scs]
    assert owners == ["Auto Reload: %v"]
    assert cleaned["Crop Left +"] == []


def test_enter_and_return_are_one_logical_shortcut():
    assert normalize_shortcut("Return") == "Enter"
    assert normalize_shortcut("Enter") == "Enter"
    assert normalize_shortcut("Ctrl+Return") == "Ctrl+Enter"

    seqs = qkeysequences_for_shortcut("Enter")
    codes = {int(s[0]) for s in seqs}
    assert codes == {
        int(QKeySequence("Return", QKeySequence.PortableText)[0]),
        int(QKeySequence("Enter", QKeySequence.PortableText)[0]),
    }

    assert len(qkeysequences_for_shortcut("Ctrl+Enter")) == 2
    assert len(qkeysequences_for_shortcut("Return")) == 2
    assert qkeysequences_for_shortcut("Click") == []
    assert qkeysequences_for_shortcut("Space")  # single ordinary key
    # Unknown / empty portable text → skipped (count>0 but empty string, or count==0)
    assert qkeysequences_for_shortcut("not-a-real-key-xyz") == []
    # Empty portable sequence: count()==0 branch
    assert qkeysequences_for_shortcut("") == []


def test_qkeysequences_skips_empty_count_and_duplicate_codes(monkeypatch):
    """Defensive continues: count()==0 and repeated key codes."""
    from gridplayer.utils import keymap as keymap_mod

    class _FakeSeq:
        def __init__(self, count: int, code: int, text: str):
            self._count = count
            self._code = code
            self._text = text

        def count(self):
            return self._count

        def __getitem__(self, _index):
            return self._code

        def toString(self, *_args):
            return self._text

    real_qks = keymap_mod.QKeySequence

    class _FakeQKeySequence:
        PortableText = real_qks.PortableText

        def __new__(cls, *args, **kwargs):
            return cls._queue.pop(0)

    # Enter expands to two variants → two constructions
    _FakeQKeySequence._queue = [
        _FakeSeq(0, 0, ""),  # skipped: not seq.count()
        _FakeSeq(1, 50, "X"),  # kept
    ]
    monkeypatch.setattr(keymap_mod, "QKeySequence", _FakeQKeySequence)
    result = keymap_mod.qkeysequences_for_shortcut("Enter")
    assert len(result) == 1
    assert result[0].toString() == "X"

    # Both variants same key code → only first kept
    _FakeQKeySequence._queue = [
        _FakeSeq(1, 99, "First"),
        _FakeSeq(1, 99, "Dup"),
    ]
    monkeypatch.setattr(keymap_mod, "QKeySequence", _FakeQKeySequence)
    result2 = keymap_mod.qkeysequences_for_shortcut("Enter")
    assert len(result2) == 1
    assert result2[0].toString() == "First"


def test_convert_button_requires_button_or_wheel():
    with pytest.raises(ValueError, match="Bad mouse"):
        MouseButtonSequence._convert_button(
            button=None,
            is_double=False,
            wheel_direction=None,
            modifiers=Qt.NoModifier,
        )


def test_normalize_key_sequence_and_from_event():
    assert normalize_key_sequence(QKeySequence()) == ""
    assert normalize_key_sequence(QKeySequence("Return")) == "Enter"
    assert normalize_key_sequence(QKeySequence("Ctrl+A, Ctrl+B")).startswith("Ctrl+A")

    # Modifier-only → incomplete
    for key in (
        Qt.Key_Control,
        Qt.Key_Shift,
        Qt.Key_Alt,
        Qt.Key_Meta,
        Qt.Key_AltGr,
        Qt.Key_unknown,
    ):
        ev = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
        assert key_sequence_from_event(ev) is None

    letter = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier)
    assert key_sequence_from_event(letter) == "Ctrl+A"

    # Shift+Tab often arrives as Backtab
    backtab = QKeyEvent(QEvent.KeyPress, Qt.Key_Backtab, Qt.ShiftModifier)
    assert key_sequence_from_event(backtab) in ("Shift+Tab", "Tab")
    # At least produces a sequence
    assert key_sequence_from_event(backtab)


# ---------------------------------------------------------------------------
# Defaults / merge / dedupe / sparse
# ---------------------------------------------------------------------------


def test_default_mouse_bindings():
    defaults = default_keymap()

    assert "Click" in defaults["Play / Pause"]
    assert "Ctrl+Space" in defaults["Play / Pause"]
    assert defaults["Single Mode ON / OFF"] == ["Double Click"]
    assert "Wheel-Down" in defaults["+1%"]
    assert "Wheel-Up" in defaults["-1%"]
    assert "Shift+Wheel-Down" in defaults["+5%"]
    assert "Shift+Wheel-Up" in defaults["-5%"]


def test_default_keymap_has_no_duplicate_shortcuts():
    assert find_duplicate_shortcuts(default_keymap()) == {}


def test_default_keymap_skips_menu_generators():
    defaults = default_keymap()
    assert "Stream Quality" not in defaults
    assert "Video Track" not in defaults
    assert "Audio Track" not in defaults


def test_default_shortcuts_key_shapes():
    assert default_shortcuts({"key": "F"}) == ["F"]
    assert default_shortcuts({"key": ["A", "B"]}) == ["A", "B"]
    assert default_shortcuts({"key": ("C",)}) == ["C"]
    assert default_shortcuts({"keys": "Z"}) == ["Z"]
    assert default_shortcuts({"keys": ["A", "Click"]}) == ["A", "Click"]
    assert default_shortcuts({}) == []
    assert default_shortcuts({"key": ""}) == []


def test_split_shortcuts():
    keyboard, mouse = split_shortcuts(["Ctrl+Space", "Click", "F", "Wheel-Up", "u"])
    assert keyboard == ["Ctrl+Space", "F", "U"]
    assert mouse == ["Click", "Wheel-Up"]


def test_find_duplicate_shortcuts_normalizes_case():
    dups = find_duplicate_shortcuts(
        {
            "A": ["u"],
            "B": ["U"],
        }
    )
    assert "U" in dups
    assert set(dups["U"]) == {"A", "B"}


def test_merge_keymap_variants():
    defaults = {"A": ["1"], "B": ["2"], "C": ["3"]}

    # No overrides → still returns a full map
    bare = merge_keymap(defaults, None)
    assert bare["A"] == ["1"]

    overrides = KeymapOverrides({"B": ["X"], "C": ["3"], "UnknownAction": ["Z"]})
    merged = merge_keymap(defaults, overrides)
    assert merged["A"] == ["1"]
    assert merged["B"] == ["X"]
    assert merged["C"] == ["3"]
    assert "UnknownAction" not in merged

    # dict overrides also work
    merged2 = merge_keymap(defaults, {"B": ["Y"]})
    assert merged2["B"] == ["Y"]

    # default_keymap when defaults omitted
    full = merge_keymap(None, None)
    assert "Play / Pause" in full


def test_merge_and_sparse_overrides():
    defaults = {
        "A": ["1"],
        "B": ["2", "Click"],
        "C": ["3"],
    }
    overrides = KeymapOverrides({"B": ["X"], "C": ["3"]})

    merged = merge_keymap(defaults, overrides)
    assert merged["A"] == ["1"]
    assert merged["B"] == ["X"]
    assert merged["C"] == ["3"]

    sparse = sparse_overrides(merged, defaults)
    assert sparse.root == {"B": ["X"]}
    assert not KeymapOverrides({})


def test_dedupe_prefers_non_default_owner():
    defaults = {
        "Play / Pause": ["Ctrl+Space", "Click"],
        "Other": [],
    }
    bindings = {
        "Play / Pause": ["Ctrl+Space", "Click"],
        "Other": ["Click"],
    }
    cleaned = dedupe_keymap(bindings, defaults)
    assert "Click" in cleaned["Other"]
    assert "Click" not in cleaned["Play / Pause"]
    assert "Ctrl+Space" in cleaned["Play / Pause"]


def test_dedupe_stable_order_when_all_default():
    defaults = {
        "A": ["X"],
        "B": ["X"],
    }
    cleaned = dedupe_keymap({"A": ["X"], "B": ["X"]}, defaults)
    assert cleaned["A"] == ["X"]
    assert cleaned["B"] == []


def test_dedupe_multiple_non_default_owners_first_in_order_wins():
    defaults = {
        "First": [],
        "Second": [],
    }
    bindings = {
        "First": ["K"],
        "Second": ["K"],
    }
    cleaned = dedupe_keymap(bindings, defaults)
    assert cleaned["First"] == ["K"]
    assert cleaned["Second"] == []


def test_dedupe_includes_actions_missing_from_defaults_order():
    defaults = {"A": ["1"]}
    bindings = {"A": ["1"], "Extra": ["Z"], "Also": ["Z"]}
    cleaned = dedupe_keymap(bindings, defaults)
    # Extra appears before Also when appended after defaults keys...
    # order: A, then Extra, then Also (insertion from bindings iteration)
    # winners among non-default: first in order among non_default_owners
    assert cleaned["Extra"] == ["Z"] or cleaned["Also"] == ["Z"]
    assert (cleaned["Extra"] == ["Z"]) != (cleaned["Also"] == ["Z"])


def test_sparse_overrides_dedupes_before_save():
    defaults = {
        "Play / Pause": ["Ctrl+Space", "Click"],
        "Other": [],
    }
    bindings = {
        "Play / Pause": ["Ctrl+Space", "Click"],
        "Other": ["Click"],
    }
    sparse = sparse_overrides(bindings, defaults)
    assert sparse.get("Other") == ["Click"]
    assert sparse.get("Play / Pause") == ["Ctrl+Space"]


def test_sparse_overrides_empty_when_all_default():
    defaults = {"A": ["1"], "B": ["2"]}
    sparse = sparse_overrides(defaults, defaults)
    assert sparse.root == {}
    assert not sparse
