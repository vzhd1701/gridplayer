import pytest
from PyQt5.QtWidgets import QAction, QApplication

from gridplayer.widgets.custom_menu import CustomMenu


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


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
