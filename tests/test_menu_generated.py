"""Generated submenus, made afresh each time a menu opens: gone with it."""

import pytest
from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.player.managers.actions import QDynamicAction
from gridplayer.player.managers.menu import _add_action
from gridplayer.widgets.custom_menu import CustomMenu


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window():
    window = QWidget()

    yield window

    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _tracks(window, titles, has_templates=True):
    """A submenu generated as the tracks' are, by the ActionsManager's way."""

    action = QDynamicAction(title="Tracks", icon_id=None, parent=window)

    def generate(parent=None):
        return [
            QDynamicAction(
                title=title, icon_id=None, parent=parent if parent else window
            )
            for title in titles
        ]

    action.menu_generator = generate

    if has_templates:
        action.menu_templates = lambda: list(titles)

    return action


def _open_and_close(window, action):
    menu = CustomMenu(parent=window)
    _add_action(action, menu)

    shown = [a.text() for a in menu.actions()]

    menu.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    return shown


def _left_on(window):
    return len(window.findChildren(QObject))


class TestAGeneratedSubmenu:
    def test_it_is_shown(self, window):
        action = _tracks(window, ["English", "French"])

        assert _open_and_close(window, action) == ["Tracks"]

    def test_opened_again_and_again_it_leaves_nothing_behind(self, window):
        action = _tracks(window, ["English", "French"])
        _open_and_close(window, action)
        left = _left_on(window)

        for _ in range(5):
            _open_and_close(window, action)

        assert _left_on(window) == left

    def test_an_empty_one_is_not_shown_and_leaves_nothing(self, window):
        action = _tracks(window, [])
        left = _left_on(window)

        assert _open_and_close(window, action) == []
        assert _left_on(window) == left

    def test_without_its_templates_told_whether_empty_leaves_nothing(self, window):
        action = _tracks(window, ["English"], has_templates=False)
        _open_and_close(window, action)
        left = _left_on(window)

        for _ in range(5):
            _open_and_close(window, action)

        assert _left_on(window) == left
