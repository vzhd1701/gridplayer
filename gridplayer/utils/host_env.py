"""The system's own environment, for a program of the system the app starts.

The AppImage's AppRun puts its libraries first on LD_LIBRARY_PATH, and sets
other variables of its own. A program of the system started with them,
xdg-open and what it starts in turn, can fail to load: Ubuntu's Rust
coreutils, for one, take the AppImage's older libsystemd and stop there.
AppRun names the variables it changed in GRIDPLAYER_HOST_VARS, and keeps the
system's value of each it had as GRIDPLAYER_HOST_<name>.

Changing them back in os.environ leaves this process as it is: the loader
read LD_LIBRARY_PATH once, as the process started.
"""

import os
from contextlib import contextmanager

from PyQt6.QtCore import QObject, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices

HOST_VARS = "GRIDPLAYER_HOST_VARS"
HOST_VALUE = "GRIDPLAYER_HOST_{}"

# what Qt hands to xdg-open
_SCHEMES = ("http", "https", "file")


def host_values() -> dict[str, str | None]:
    """Each variable AppRun changed, with the system's value: None where the
    system had none. Empty outside the AppImage."""

    names = os.environ.get(HOST_VARS, "")

    return {
        name: os.environ.get(HOST_VALUE.format(name))
        for name in names.split(":")
        if name
    }


@contextmanager
def host_environment():
    """The system's values of what AppRun changed, while inside."""

    host = host_values()
    ours = {name: os.environ.get(name) for name in host}

    _set(host)
    try:
        yield
    finally:
        _set(ours)


def _set(values: dict[str, str | None]) -> None:
    for name, value in values.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class _HostOpener(QObject):
    """Opens a URL as QDesktopServices would, in the system's environment."""

    @pyqtSlot(QUrl)
    def open(self, url: QUrl) -> None:
        # not handed back to itself
        _unset_handlers()
        try:
            with host_environment():
                QDesktopServices.openUrl(url)
        finally:
            _set_handlers(self)


def _set_handlers(opener: QObject) -> None:
    for scheme in _SCHEMES:
        QDesktopServices.setUrlHandler(scheme, opener, "open")


def _unset_handlers() -> None:
    for scheme in _SCHEMES:
        QDesktopServices.unsetUrlHandler(scheme)


def open_urls_in_host_environment(app) -> None:
    """Every URL the app opens (links, Open URL, a folder) opened with the
    system's environment, where AppRun changed it."""

    if not host_values():
        return

    app._host_opener = _HostOpener(app)
    _set_handlers(app._host_opener)
