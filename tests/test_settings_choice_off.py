"""A choice another field greys out (ComboField.off_when): Direct while Window
system is Wayland."""

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QTest

from gridplayer.models.settings_draft import ResetValue, SettingsMode, SetValue
from gridplayer.params.settings_fields.kinds import ComboField, When
from gridplayer.widgets.settings_controls import SegmentedChoice
from gridplayer.widgets.settings_form import SettingsForm

_DEFAULTS = {"a/system": "auto", "a/output": "copy"}


def _form():
    return SettingsForm(
        (
            ComboField(
                settings_key="a/system",
                label="System",
                choices=lambda: {"auto": "Auto", "x11": "X11", "wayland": "Wayland"},
                buttons=True,
            ),
            ComboField(
                settings_key="a/output",
                label="Output",
                choices=lambda: {
                    "copy": "Copy",
                    "shared": "Shared",
                    "direct": "Direct",
                },
                buttons=True,
                off_when=lambda: {
                    "direct": (When("a/system", ("wayland",)), "Needs X11")
                },
                stand_in="copy",
            ),
        ),
        reset_to=_DEFAULTS.get,
        mode=SettingsMode.DEFAULTS,
    )


def _pick(form, key, value):
    widget = form.widget(key)
    widget.setCurrentIndex(widget.findData(value))


class TestAChoiceGreyedOut:
    def test_it_cant_be_picked_and_says_why(self):
        form = _form()
        form.set_values({"a/system": "wayland", "a/output": "shared"})

        assert form.widget("a/output").reason_of("direct") == "Needs X11"
        assert form.widget("a/output").reason_of("shared") is None

        _pick(form, "a/system", "auto")

        assert form.widget("a/output").reason_of("direct") is None

    def test_a_field_on_it_shows_its_stand_in_and_keeps_its_own(self):
        form = _form()
        form.set_values({"a/system": "auto", "a/output": "direct"})

        _pick(form, "a/system", "wayland")

        # what runs in its place, and the field can still be changed
        assert form.value("a/output") == "copy"
        assert form.is_enabled("a/output")
        assert form.persistence_result()["a/output"] == SetValue("direct")

        _pick(form, "a/system", "auto")

        assert form.value("a/output") == "direct"

    def test_stored_on_it_it_opens_on_its_stand_in(self):
        form = _form()
        form.set_values({"a/system": "wayland", "a/output": "direct"})

        assert form.value("a/output") == "copy"
        assert form.is_modified("a/output")

    def test_another_choice_picked_meanwhile_is_its_own(self):
        form = _form()
        form.set_values({"a/system": "wayland", "a/output": "direct"})

        _pick(form, "a/output", "shared")
        _pick(form, "a/system", "auto")

        assert form.value("a/output") == "shared"
        assert form.persistence_result()["a/output"] == SetValue("shared")

    def test_a_reset_meanwhile_resets_its_own(self):
        form = _form()
        form.set_values({"a/system": "wayland", "a/output": "direct"})

        form.reset("a/output")
        _pick(form, "a/system", "auto")

        assert form.value("a/output") == "copy"
        assert isinstance(form.persistence_result()["a/output"], ResetValue)


def _segments():
    widget = SegmentedChoice()
    for value in ("copy", "shared", "direct"):
        widget.addItem(value.title(), value)
    widget.resize(widget.sizeHint())
    widget.set_unavailable({"shared": "Not here"})
    return widget


def test_a_choice_greyed_out_isnt_picked_by_a_click():
    widget = _segments()
    middle = widget._segments()[1].center().toPoint()

    QTest.mouseClick(widget, Qt.LeftButton, pos=QPoint(middle))

    assert widget.currentData() == "copy"


def test_the_arrow_keys_step_over_a_choice_greyed_out():
    widget = _segments()

    QTest.keyClick(widget, Qt.Key_Right)
    assert widget.currentData() == "direct"

    QTest.keyClick(widget, Qt.Key_Right)
    assert widget.currentData() == "direct"

    QTest.keyClick(widget, Qt.Key_Left)
    assert widget.currentData() == "copy"
