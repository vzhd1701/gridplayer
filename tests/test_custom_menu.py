import pytest
from PyQt5.QtCore import QEvent, QSize
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import QAction, QApplication, QWidget

from gridplayer.main.init_resources import init_resources
from gridplayer.params.theme import current_colors
from gridplayer.player.managers.actions import QDynamicAction
from gridplayer.widgets.custom_menu import ICON_SIZE, CustomMenu, checked_icon

RED = QColor("#ff0000")


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window():
    window = QWidget()

    yield window

    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _red_icon():
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(RED)

    return QIcon(pixmap)


def _image(icon, state, mode=QIcon.Normal):
    return icon.pixmap(QSize(ICON_SIZE, ICON_SIZE), mode, state).toImage()


def _pixels(image):
    return [
        image.pixelColor(x, y)
        for x in range(image.width())
        for y in range(image.height())
    ]


def _text():
    return QColor(current_colors()["text"])


def test_custom_menu_does_not_activate_disabled_actions():
    menu = CustomMenu()
    disabled = QAction("Save Playlist", menu)
    disabled.setEnabled(False)
    enabled = QAction("About", menu)
    menu.addAction(disabled)
    menu.addAction(enabled)

    menu.setActiveAction(disabled)
    assert menu.activeAction() is None

    menu.setActiveAction(enabled)
    assert menu.activeAction() is enabled


def test_custom_menu_leaves_a_checked_row_unfilled():
    """Checked is told by the icon's mark; a filled row is hover alone."""

    assert ":checked" not in CustomMenu().styleSheet()


@pytest.mark.parametrize("is_choice", [False, True])
def test_checked_icon_is_the_icon_itself_while_unchecked(is_choice):
    image = _image(checked_icon(_red_icon(), is_choice=is_choice), QIcon.Off)

    assert all(color == RED for color in _pixels(image))


def test_checked_setting_has_a_ticked_disc_cut_into_its_icons_corner():
    image = _image(checked_icon(_red_icon(), is_choice=False), QIcon.On)

    # the icon is left as it is away from the corner
    assert image.pixelColor(3, 3) == RED
    # a gap round the disc, the row showing through
    assert image.pixelColor(11, 18).alpha() < 16
    # the disc
    assert image.pixelColor(18, 14) == _text()
    # the tick is a hole through it
    assert image.pixelColor(17, 20).alpha() < 128


def test_checked_choice_has_a_holed_disc_cut_into_its_icons_corner():
    image = _image(checked_icon(_red_icon(), is_choice=True), QIcon.On)

    assert image.pixelColor(3, 3) == RED
    assert image.pixelColor(11, 18).alpha() < 16
    assert image.pixelColor(18, 14) == _text()
    # the hole in the middle of the disc
    assert image.pixelColor(18, 18).alpha() == 0


def test_checked_item_without_an_icon_gets_the_mark_alone():
    tick = checked_icon(QIcon(), is_choice=False)
    dot = checked_icon(QIcon(), is_choice=True)

    for icon in (tick, dot):
        assert all(color.alpha() == 0 for color in _pixels(_image(icon, QIcon.Off)))

    # a dot in the middle for a choice, a tick round it for a setting
    assert _image(dot, QIcon.On).pixelColor(11, 11) == _text()
    assert _image(tick, QIcon.On).pixelColor(11, 11).alpha() == 0
    assert any(color == _text() for color in _pixels(_image(tick, QIcon.On)))


def test_themes_empty_icon_counts_as_none():
    """The menus keep their rows lined up with a blank icon called empty;
    the mark goes where its picture would be, not in its corner."""

    init_resources()

    theme = QIcon.themeName()
    QIcon.setThemeName("dark")

    try:
        empty = QIcon.fromTheme("empty")
        assert not empty.isNull()

        image = _image(checked_icon(empty, is_choice=True), QIcon.On)
    finally:
        QIcon.setThemeName(theme)

    assert image.pixelColor(11, 11) == _text()
    assert image.pixelColor(18, 14).alpha() == 0


def test_mark_of_a_disabled_item_is_greyed_with_its_text():
    image = _image(checked_icon(QIcon(), is_choice=True), QIcon.On, QIcon.Disabled)

    assert image.pixelColor(11, 11) == QColor(current_colors()["text_disabled"])


@pytest.mark.parametrize("is_choice", [False, True])
def test_checked_menu_item_carries_the_mark_of_its_kind(window, is_choice):
    action = QDynamicAction(title="Fit Cells", icon_id=None, parent=window)
    action.check_if = lambda: True
    action.is_choice = is_choice

    menu = CustomMenu(parent=window)
    proxy = action.to_menu_action(menu)

    assert proxy.isChecked()

    middle = _image(proxy.icon(), QIcon.On).pixelColor(11, 11)

    if is_choice:
        assert middle == _text()
    else:
        assert middle.alpha() == 0
