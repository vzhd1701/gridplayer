"""Screenshots of what Qt draws, to compare PyQt5 with PyQt6 (docs/plans/QT6_PLAN.md,
stages 0.4 and 3.3). The same scenario runs on both:

    uv run python -m tests.real_app.run scripts/qt6_port/look.py --out DIR

and with QT_SCALE_FACTOR=1.5 for 150%. It leaves one PNG per window, page and menu:
the player with four paused cells, the context menu and each of its submenus, every
page of Settings and of the Playlist window, and the dialogs the menus open.

With LOOK_HIDDEN=1 and REAL_APP_QT_PLATFORM=windows it draws with the real Windows
platform (its fonts, DirectWrite on Qt 6) without a window ever on the screen: every
window is WA_DontShowOnScreen, and the run ends at once should one show after all.
"""

import ctypes
import os
import sys
import threading
import time

try:
    from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
    from PyQt6.QtWidgets import QApplication, QWidget
except ImportError:
    from PyQt5.QtCore import QEvent, QObject, QPoint, Qt
    from PyQt5.QtWidgets import QApplication, QWidget

IS_HIDDEN = os.environ.get("LOOK_HIDDEN") == "1"

SETTINGS = {}
if IS_HIDDEN:
    # nothing of the app's in the system's own corners either
    SETTINGS |= {
        "player/media_keys_background": False,
        "player/inhibit_screensaver": False,
    }
# LOOK_SCHEME=dark (or light, system): the colour scheme setting
if os.environ.get("LOOK_SCHEME"):
    SETTINGS["player/color_scheme"] = os.environ["LOOK_SCHEME"]


def _hide(widget) -> None:
    if widget.isWindow():
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


class _HideWindows(QObject):
    """Windows shown from C++ (a dialog's exec(), a menu's popup): hidden as
    they are polished, which comes before Qt shows them."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Polish and isinstance(obj, QWidget):
            _hide(obj)
        return False


def _watch_windows() -> None:
    """Ends the run should a window of ours be on the screen after all."""

    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    pid = os.getpid()
    each_window = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def shown():
        found = []

        def one(hwnd, _):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True

        user32.EnumWindows(each_window(one), 0)
        return found

    while True:
        if shown():
            print("look.py: a window was shown, stopping", flush=True)
            os._exit(3)
        time.sleep(0.02)


# the filter, once there is an application to put it on
_HIDING: list = []


if IS_HIDDEN:
    _real_show = QWidget.show

    def _hidden_show(self):
        # from the first show on (the player's, before the scenario starts),
        # every window polished is hidden, and those polished before as well
        if not _HIDING:
            _HIDING.append(_HideWindows())
            QApplication.instance().installEventFilter(_HIDING[0])
            for window in QApplication.topLevelWidgets():
                _hide(window)
        _hide(self)
        _real_show(self)

    QWidget.show = _hidden_show
    if sys.platform == "win32":
        threading.Thread(target=_watch_windows, daemon=True).start()

# what a dialog opened from a cell's menu is called in the shots
DIALOGS = {
    "About": "about",
    "Rename": "rename",
    "Set Position": "set_position",
    "Set Crop": "set_crop",
    "Audio Delay: %v": "audio_delay",
    "Subtitle Delay: %v": "subtitle_delay",
    "Grid Size: %v": "grid_size",
    "Add - URL(s)": "add_urls",
    "Bookmarks in Playlist": "bookmarks",
    "Lists in Playlist": "lists",
}


def scenario(d):
    # LOOK_QT_SCHEME=dark: Qt told the system went dark (Qt 6.8+), whatever
    # the app's own setting is, which mustn't change what it shows
    if os.environ.get("LOOK_QT_SCHEME") and hasattr(Qt, "ColorScheme"):
        scheme = getattr(Qt.ColorScheme, os.environ["LOOK_QT_SCHEME"].title())
        d.app.styleHints().setColorScheme(scheme)
        d.pump(0.5)

    d.open(*d.media.clips, d.media.feature)
    for clip in d.media.clips:
        d.wait_for_cell(clip.name)
    block = d.wait_for_cell("feature.mkv")

    d.act(block, "Pause [ALL]")
    d.wait_until(lambda: all(b.video_params.is_paused for b in d.cells), "all paused")
    d.pump(1)
    d.shot("player")

    _menus(d, block)
    _paged(d, block, "Settings", "settings")
    _paged(d, block, "Edit Playlist Settings", "playlist")

    for action, name in DIALOGS.items():
        d.through_modal(lambda action=action: d.act(block, action), f"dialog_{name}")


def _menus(d, block):
    # offscreen has no clipboard: its mimeData() is None, which Add - Clipboard's
    # check doesn't expect (a harness limit, not the app's)
    d.ctx.actions["Add - Clipboard"].enable_if = lambda: False

    d.ctx.active_block = block
    menu = d.player._managers_inst["menu"].make_menu()
    menu.popup(d.player.mapToGlobal(QPoint(40, 40)))
    d.pump(0.5)
    d.shot("menu", menu)

    for action in menu.actions():
        submenu = action.menu()
        if submenu is None or not action.isEnabled():
            continue
        menu.setActiveAction(action)
        submenu.popup(menu.mapToGlobal(menu.actionGeometry(action).topRight()))
        d.pump(0.3)
        name = action.text().replace("&", "").replace("/", "-").strip().lower()
        d.shot(f"menu_{'_'.join(name.split())}", submenu)
        submenu.hide()

    menu.hide()
    menu.deleteLater()
    d.pump(0.2)


def _paged(d, block, action, prefix):
    def each_page(dialog):
        for page_id in list(dialog.pages):
            dialog.show_page(page_id)
            d.pump(0.3)
            d.shot(f"{prefix}_{page_id}", dialog)

    d.through_modal(lambda: d.act(block, action), f"{prefix}_first", each_page)
