"""A file shown in the system's file manager, picked out in its folder.

Where the file is no longer there, the nearest folder of it that still is
gets opened instead, and nothing at all where not even the drive is.

Looking for it is done off the GUI thread: a share that has gone away can
keep a question about a file on it waiting for many seconds.
"""

import ctypes
import logging
import os
import threading
from pathlib import Path

from PyQt5.QtCore import QMetaType, QObject, QProcess, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices

from gridplayer.params import env

COINIT_APARTMENTTHREADED = 0x2

_log = logging.getLogger(__name__)


def existing_place(path: Path) -> Path | None:
    """The file itself if it is there, else the nearest folder that is."""

    try:
        if path.is_file():
            return path

        for folder in path.parents:
            if folder.is_dir():
                return folder
    except OSError as e:
        _log.warning(f"Cannot look for {path}: {e}")

    return None


class FolderRevealer(QObject):
    _found = pyqtSignal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        # emitted from the thread that looked, so it lands on this one
        self._found.connect(self._show)

    def show(self, path: Path) -> None:
        threading.Thread(
            target=self._look, args=(path,), daemon=True, name="show_in_folder"
        ).start()

    def _look(self, path: Path) -> None:
        place = existing_place(path)

        if place is None:
            _log.warning(f"Nothing left of {path} to show")
            return

        is_file = place == path

        if env.IS_WINDOWS:
            # the shell may go to the disk again, so it stays off the GUI too
            _show_windows(place, is_file=is_file)
            return

        try:
            self._found.emit(place, is_file)
        except RuntimeError:
            # the player closed while this was looking
            return

    def _show(self, place: Path, is_file: bool) -> None:
        if env.IS_MACOS:
            args = ["-R", str(place)] if is_file else [str(place)]
            QProcess.startDetached("open", args)
        elif env.IS_LINUX:
            self._show_linux(place, is_file=is_file)
        else:
            open_folder(place if not is_file else place.parent)

    def _show_linux(self, place: Path, is_file: bool) -> None:
        from PyQt5.QtDBus import (
            QDBusArgument,
            QDBusConnection,
            QDBusMessage,
            QDBusPendingCallWatcher,
        )

        folder = place.parent if is_file else place

        bus = QDBusConnection.sessionBus()

        if not bus.isConnected():
            open_folder(folder)
            return

        message = QDBusMessage.createMethodCall(
            "org.freedesktop.FileManager1",
            "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1",
            "ShowItems" if is_file else "ShowFolders",
        )
        # a plain list goes over as variants, which no file manager takes
        uris = QDBusArgument(
            [QUrl.fromLocalFile(str(place)).toString()], QMetaType.QStringList
        )
        message.setArguments([uris, ""])

        watcher = QDBusPendingCallWatcher(bus.asyncCall(message), self)
        watcher.finished.connect(lambda w: self._linux_replied(w, folder))

    @staticmethod
    def _linux_replied(watcher, folder: Path) -> None:
        from PyQt5.QtDBus import QDBusPendingReply

        # PyQt's watcher has no isError() of its own to ask
        reply = QDBusPendingReply(watcher)

        # no file manager that answers to it, or a sandbox that keeps it out
        if reply.isError():
            _log.debug(f"FileManager1 failed: {reply.error().message()}")
            open_folder(folder)

        watcher.deleteLater()


def open_folder(folder: Path) -> None:
    _log.debug(f"Opening folder {folder}")

    if env.IS_SNAP:
        # https://forum.snapcraft.io/t/xdg-open-or-gvfs-open-qdesktopservices-openurl-file-somelocation-file-txt-wont-open-the-file/16824
        QProcess.startDetached("xdg-open", [str(folder)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _show_windows(place: Path, is_file: bool) -> None:
    if not is_file:
        os.startfile(place)
        return

    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")

    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
    shell32.SHOpenFolderAndSelectItems.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]

    is_com_joined = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED) >= 0

    try:
        item = shell32.ILCreateFromPathW(str(place))

        if not item:
            _log.warning(f"The shell does not know {place}")
            os.startfile(place.parent)
            return

        try:
            result = shell32.SHOpenFolderAndSelectItems(item, 0, None, 0)
        finally:
            shell32.ILFree(item)

        if result < 0:
            _log.warning(
                f"SHOpenFolderAndSelectItems failed with {result & 0xFFFFFFFF:#x}"
            )
            os.startfile(place.parent)
    finally:
        if is_com_joined:
            ole32.CoUninitialize()
