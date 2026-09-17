import time
from threading import Thread

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.utils import cookies

# what the test hosts check for before they serve anything
LOGIN_NAME = "SID"
LOGIN_VALUE = "abc"
LOGIN = f"{LOGIN_NAME}={LOGIN_VALUE}"

COOKIE_LIFETIME_SEC = 10000


class _FakeCookieSettings:
    """The cookie switches, answering for themselves."""

    def __init__(self, values):
        self._values = values

    def get(self, key):
        return self._values[key]


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


@pytest.fixture(autouse=True)
def _no_real_cookies(tmp_path, monkeypatch):
    """Keep every test away from the jar the user actually has.

    The resolvers ask the store whether a URL needs a cookie before they
    decide who fetches it, and the store answers out of the app data
    directory unless it is pointed somewhere else. A test that found a
    login there would resolve differently on the machine that has one.
    """

    store = cookies.CookieStore(tmp_path / "cookies.txt")

    monkeypatch.setattr(cookies, "cookie_store", lambda: store)

    return store


@pytest.fixture
def serving():
    """Run servers on their own threads for the length of a test.

    Every proxy test needs at least two of them up at once, and a test
    that leaves one running leaks a thread into the next.
    """

    running = []

    def _serve(server):
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        running.append((server, thread))

        return server

    yield _serve

    for server, thread in running:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def local_login(_no_real_cookies, monkeypatch):
    """A stored login for 127.0.0.1, where the test hosts live.

    The switches come with it, so a test is not at the mercy of whatever
    the person running it has cookies set to.
    """

    values = {"cookies/enabled": True, "cookies/allow_update": False}

    monkeypatch.setattr(cookies, "Settings", lambda: _FakeCookieSettings(values))

    expires = int(time.time()) + COOKIE_LIFETIME_SEC

    _no_real_cookies.save(
        cookies.parse_cookies(
            "# Netscape HTTP Cookie File\n"
            f"127.0.0.1\tFALSE\t/\tFALSE\t{expires}\t{LOGIN_NAME}\t{LOGIN_VALUE}\n"
        )
    )

    return values
