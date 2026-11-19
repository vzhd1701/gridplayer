"""The system's environment for what the AppImage starts: what AppRun changed
taken back while inside, ours after, and every URL opened that way."""

import os

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication

from gridplayer.utils import host_env


@pytest.fixture(autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def apprun(monkeypatch):
    """As AppRun leaves it: PATH and LD_LIBRARY_PATH changed, the system had
    a PATH and no LD_LIBRARY_PATH."""

    monkeypatch.setenv("PATH", "/app/usr/bin:/usr/bin")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/app/usr/lib")
    monkeypatch.setenv(host_env.HOST_VARS, "PATH:LD_LIBRARY_PATH")
    monkeypatch.setenv("GRIDPLAYER_HOST_PATH", "/usr/bin")
    monkeypatch.delenv("GRIDPLAYER_HOST_LD_LIBRARY_PATH", raising=False)


def test_nothing_to_take_back_outside_the_appimage(monkeypatch):
    monkeypatch.delenv(host_env.HOST_VARS, raising=False)

    assert host_env.host_values() == {}


def test_the_system_s_values_while_inside_ours_after(apprun):
    assert host_env.host_values() == {"PATH": "/usr/bin", "LD_LIBRARY_PATH": None}

    with host_env.host_environment():
        assert os.environ["PATH"] == "/usr/bin"
        assert "LD_LIBRARY_PATH" not in os.environ

    assert os.environ["PATH"] == "/app/usr/bin:/usr/bin"
    assert os.environ["LD_LIBRARY_PATH"] == "/app/usr/lib"


def test_ours_back_when_what_ran_inside_failed(apprun):
    with pytest.raises(RuntimeError), host_env.host_environment():
        raise RuntimeError

    assert os.environ["LD_LIBRARY_PATH"] == "/app/usr/lib"


def test_urls_opened_in_the_system_s_environment(apprun, monkeypatch):
    seen = []

    def open_url(url):
        seen.append((url.toString(), os.environ.get("LD_LIBRARY_PATH")))
        return True

    app = QApplication.instance()
    host_env.open_urls_in_host_environment(app)
    # Qt's, which hands the URL to the handler; the handler's own call, with
    # itself unset, is the stand-in's: nothing opened for real
    qt_open = QDesktopServices.openUrl
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(open_url))

    try:
        assert qt_open(QUrl("https://example.com"))
        # set again for the next one
        assert qt_open(QUrl("file:///tmp"))
    finally:
        host_env._unset_handlers()
        del app._host_opener

    assert seen == [("https://example.com", None), ("file:///tmp", None)]
    assert os.environ["LD_LIBRARY_PATH"] == "/app/usr/lib"


def test_no_handler_outside_the_appimage(monkeypatch):
    monkeypatch.delenv(host_env.HOST_VARS, raising=False)
    app = QApplication.instance()

    host_env.open_urls_in_host_environment(app)

    assert not hasattr(app, "_host_opener")
