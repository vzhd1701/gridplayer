import pytest
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.about import AboutDialog
from gridplayer.version import (
    __app_bugtracker_url__,
    __app_license_url__,
    __app_url__,
    __display_name__,
    __version__,
)


@pytest.fixture
def dialog():
    dialog = AboutDialog(None)

    yield dialog

    dialog.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_it_shows_the_app(dialog):
    assert dialog.windowTitle() == "About"
    assert dialog.name.text() == __display_name__
    assert __version__ in dialog.version.text()
    assert not dialog.logo.pixmap().isNull()


def test_it_links_to_the_project(dialog):
    for url in (__app_url__, __app_bugtracker_url__, __app_license_url__):
        assert url in dialog.info.text()


def test_it_lists_what_it_was_built_with(dialog):
    attributions = dialog.attributions_box.toPlainText()

    for title in ("Python", "Qt", "VLC", "streamlink", "yt-dlp", "SponsorBlock"):
        assert title in attributions
