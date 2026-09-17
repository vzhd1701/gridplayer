import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.playlist_settings import PlaylistSettings


@pytest.fixture(scope="session", autouse=True)
def _qapp_session():
    """Hold one QApplication open for the whole run.

    Destroying a QApplication destroys every QObject alive at the time,
    and the settings singleton keeps a QSettings among them. Modules that
    make their own only ever get this one back, so nothing outlives its
    application.
    """

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clear_playlist_settings():
    PlaylistSettings().clear()
    yield
    PlaylistSettings().clear()
