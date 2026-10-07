"""A wheel fires its shortcut once a notch, however finely it reports a turn.

A touchpad or a smooth scrolling wheel reports one notch as many small
turns; fired on each of them, one stroke would seek or zoom many times over.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QMouseEvent, QWheelEvent

from gridplayer.player.managers.actions import ActionsManager
from gridplayer.utils.keymap import WHEEL_NOTCH, WHEEL_PAUSE_MS, WheelNotches


def _wheel(dy=0, dx=0, ms=0, modifiers=Qt.NoModifier):
    event = QWheelEvent(
        QPoint(0, 0),
        QPoint(0, 0),
        QPoint(0, 0),
        QPoint(dx, dy),
        0,
        Qt.Vertical if dy else Qt.Horizontal,
        Qt.NoButton,
        modifiers,
    )
    event.setTimestamp(ms)
    return event


def _turned(notches, *turns):
    return [notches.notches(turn) for turn in turns]


class TestCountingNotches:
    def test_a_mouse_wheel_fires_each_notch(self):
        notches = WheelNotches()

        assert _turned(notches, _wheel(dy=120), _wheel(dy=120)) == [1, 1]

    def test_small_turns_add_up_to_a_notch(self):
        notches = WheelNotches()

        turns = [_wheel(dy=15, ms=ms) for ms in range(0, 160, 10)]

        # 16 turns of an eighth of a notch: two notches, on the 8th and 16th
        assert _turned(notches, *turns) == [0] * 7 + [1] + [0] * 7 + [1]

    def test_down_counts_as_well_as_up(self):
        notches = WheelNotches()

        assert _turned(notches, _wheel(dy=-60), _wheel(dy=-60)) == [0, 1]

    def test_a_turn_of_several_notches_fires_them_all(self):
        notches = WheelNotches()

        assert _turned(notches, _wheel(dy=360)) == [3]

    def test_the_rest_of_a_turn_carries_over(self):
        notches = WheelNotches()

        assert _turned(notches, _wheel(dy=200), _wheel(dy=40)) == [1, 1]

    def test_turned_back_it_starts_over(self):
        notches = WheelNotches()

        assert _turned(notches, _wheel(dy=100), _wheel(dy=-100)) == [0, 0]
        assert _turned(notches, _wheel(dy=-20)) == [1]

    def test_on_the_other_axis_it_starts_over(self):
        notches = WheelNotches()

        assert _turned(notches, _wheel(dy=100), _wheel(dx=100)) == [0, 0]

    def test_with_other_keys_held_it_starts_over(self):
        notches = WheelNotches()

        assert _turned(
            notches, _wheel(dy=100), _wheel(dy=100, modifiers=Qt.ControlModifier)
        ) == [0, 0]

    def test_a_turn_left_a_while_is_let_go(self):
        notches = WheelNotches()

        assert _turned(
            notches, _wheel(dy=100, ms=1000), _wheel(dy=100, ms=1001 + WHEEL_PAUSE_MS)
        ) == [0, 0]

    def test_a_turn_kept_going_is_not(self):
        notches = WheelNotches()

        assert _turned(
            notches, _wheel(dy=100, ms=1000), _wheel(dy=100, ms=1000 + WHEEL_PAUSE_MS)
        ) == [0, 1]


class TestFiringShortcuts:
    @pytest.fixture
    def manager(self):
        manager = Mock()
        manager._ctx = SimpleNamespace(
            is_disable_mouse_click_events=False,
            is_disable_mouse_wheel_events=False,
            commands=SimpleNamespace(handle_fake_drag_click=lambda event: False),
        )
        manager._mouse_index = {
            "Wheel-Down": "+1%",
            "Ctrl+Wheel-Up": "Zoom In",
            "Click": "Play / Pause",
        }
        manager._wheel_notches = WheelNotches()
        manager.trigger.return_value = True
        return manager

    def _handle(self, manager, event):
        return ActionsManager.handle_mouse_event(manager, event)

    def test_a_notch_fires_its_shortcut_once(self, manager):
        assert self._handle(manager, _wheel(dy=-WHEEL_NOTCH))

        manager.trigger.assert_called_once_with("+1%")

    def test_a_stroke_of_small_turns_fires_once_a_notch(self, manager):
        for ms in range(0, 240, 10):
            assert self._handle(manager, _wheel(dy=-10, ms=ms))

        assert manager.trigger.call_count == 2

    def test_held_keys_pick_the_shortcut(self, manager):
        self._handle(manager, _wheel(dy=WHEEL_NOTCH, modifiers=Qt.ControlModifier))

        manager.trigger.assert_called_once_with("Zoom In")

    def test_short_of_a_notch_the_turn_is_still_taken(self, manager):
        """Let go, it would go on to the player window and count twice."""

        assert self._handle(manager, _wheel(dy=-30))

        manager.trigger.assert_not_called()

    def test_a_turn_with_no_shortcut_is_left_alone(self, manager):
        assert not self._handle(manager, _wheel(dy=WHEEL_NOTCH))

        manager.trigger.assert_not_called()

    def test_with_the_wheel_off_nothing_is_counted(self, manager):
        manager._ctx.is_disable_mouse_wheel_events = True

        assert not self._handle(manager, _wheel(dy=-WHEEL_NOTCH))

        manager.trigger.assert_not_called()

    def test_clicks_still_fire_as_they_did(self, manager):
        release = QMouseEvent(
            QEvent.MouseButtonRelease,
            QPoint(0, 0),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )

        assert self._handle(manager, release)

        manager.trigger.assert_called_once_with("Play / Pause")
