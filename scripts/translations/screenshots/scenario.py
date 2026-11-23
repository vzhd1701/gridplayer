"""Screenshots of the app in English for Crowdin, with where each text is.

Run by `tr.py screenshots`, which uses tests/real_app:

    uv run python -m tests.real_app.run scripts/translations/screenshots/scenario.py --out DIR

Leaves in DIR a `gp-<name>.png` for each screen, and tags.json: per screen
its size and the texts seen on it, each with its rectangle, for tr.py to
match against en_US.ts.
"""

import html
import json
import re
import time

SETTINGS = {
    "player/language": "en_US",
    # not the run's own folder, which would show in Settings
    "screenshots/dir": "~/Pictures/GridPlayer",
}

PREFIX = "gp-"
SUBMENU_DEPTH = 2
# how long a window has to show up before it is taken for one that won't
WINDOW_WAIT_S = 3
# where the list and the broken file are served, the same each run
SERVED_PORT = 47811

# dialogs a cell's menu opens: the action, and the screen's name
CELL_DIALOGS = [
    ("Rename", "rename"),
    ("Timecode", "timecode"),
    ("Set Position", "position"),
    ("Set Crop", "crop"),
    ("Audio Delay: %v", "audio-delay"),
    ("Subtitle Delay: %v", "subtitle-delay"),
    ("On Network Error Attempts: %v", "network-attempts"),
    ("When Video Fails Next After: %v", "next-after"),
    ("Auto Reload: %v", "auto-reload"),
    ("Fixed Grid", "grid-size"),
    ("Save Grid Template", "grid-template"),
    ("Manage Bookmarks", "bookmarks"),
    ("Bookmarks in Playlist", "playlist-bookmarks"),
    ("Lists in Playlist", "playlist-lists"),
    ("Add - URL(s)", "add-urls"),
]

FAKE_TRACEBACK = """Traceback (most recent call last):
  File "gridplayer/player/player.py", line 1, in example
    raise RuntimeError("an example, for the screenshots")
RuntimeError: an example, for the screenshots"""


def scenario(d):
    from PyQt6.QtWidgets import QApplication

    # a text cursor that blinks would make a screen differ from run to run
    QApplication.setCursorFlashTime(0)
    shots = {}

    def capture(name, widget):
        name = PREFIX + _slug(name)
        d.shot(name, widget)
        shots[name] = {
            "size": [widget.width(), widget.height()],
            "texts": texts_in(widget),
        }

    def window(name, open_it, inspect=None):
        _window(d, name, open_it, inspect or (lambda w: capture(name, w)))

    base = _served(d)
    d.open(f"{base}/folder/a.mp4", f"{base}/folder/b.mp4")
    block = d.wait_for_cell("a.mp4")
    d.wait_for_cell("b.mp4")
    _hold_still(d)
    capture("main", d.player)

    _menus(d, block, capture)

    # before the dialogs below, one of which sets a grid with no room left
    _broken_cell(d, capture, window, base)
    _list_cell(d, window, base)

    for action, name in CELL_DIALOGS:
        window(name, lambda action=action: d.act(block, action))

    d.act(block, "Edit Grid")
    d.pump(0.5)
    capture("edit-grid", d.player)
    d.act(block, "Edit Grid")
    d.pump(0.3)

    def pages(prefix, extra=None):
        def look(dialog):
            for page_id in list(dialog.pages):
                dialog.show_page(page_id)
                d.pump(0.3)
                capture(f"{prefix}-{page_id}", dialog)
                full = _scrolled_content(dialog)
                if full is not None:
                    capture(f"{prefix}-{page_id}-all", full)
                _choices(d, dialog, f"{prefix}-{page_id}", capture)
            if extra is not None:
                extra(dialog)

        return look

    def checkups(dialog):
        from gridplayer.dialogs import checkup

        # the steps and their hints, not what the network says
        checkup.CheckRunner.start = lambda self: None
        window("checkup-network", dialog.run_network_checkup)
        window("checkup-youtube", dialog.run_youtube_checkup)

    window("settings", lambda: d.act(block, "Settings"), pages("settings", checkups))
    window(
        "playlist", lambda: d.act(block, "Edit Playlist Settings"), pages("playlist")
    )
    window("about", lambda: d.act(block, "About"))

    def show_exception():
        from gridplayer.dialogs.exception import ExceptionDialog

        ExceptionDialog(FAKE_TRACEBACK).exec()

    window("exception", show_exception)

    (d.out / "tags.json").write_text(
        json.dumps(shots, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    d.note(f"{len(shots)} screens")


def _window(d, name, open_it, inspect):
    """Look at the window open_it opens, then close it. Unlike the driver's
    through_modal, one that never shows is noted, not a failure: some
    actions open nothing for this cell."""
    from PyQt6.QtCore import QTimer

    before = set(d.windows())
    started = time.monotonic()
    done = []

    def look():
        new = [w for w in d.windows() if w not in before]
        if not new:
            if time.monotonic() - started < WINDOW_WAIT_S:
                QTimer.singleShot(100, look)
            else:
                done.append(None)
            return
        shown = new[-1]
        try:
            inspect(shown)
        except Exception as e:
            d.note(f"{name}: {type(e).__name__}: {e}")
        done.append(shown)
        shown.close()

    QTimer.singleShot(500, look)
    try:
        open_it()
    except Exception as e:
        d.note(f"{name} did not open: {type(e).__name__}: {e}")
        return
    deadline = time.monotonic() + WINDOW_WAIT_S + 10
    while not done and time.monotonic() < deadline:
        d.pump(0.05)
    if not done or done[0] is None:
        d.note(f"{name}: no window")


def _hold_still(d):
    """Every cell paused on the same frame, so a screen comes out the same
    each run and is not sent again."""
    for cell in d.cells:
        if cell.is_playable:
            cell.set_pause(True)
            cell.seek(5000)
    d.pump(1)


def _choices(d, dialog, prefix, capture):
    """The lists of choices of a page's drop-downs, opened one by one."""
    from PyQt6.QtWidgets import QComboBox

    page = dialog.section_page.currentWidget()
    combos = [
        c for c in page.findChildren(QComboBox) if c.isVisible() and c.count() > 1
    ]
    for n, combo in enumerate(combos, 1):
        combo.showPopup()
        d.pump(0.2)
        popup = combo.view().window()
        if popup.isVisible():
            capture(f"{prefix}-choices-{n}", popup)
        combo.hidePopup()
        d.pump(0.1)


def _broken_cell(d, capture, window, base):
    """What adding a file that is gone says; a cell whose file is no video,
    its error and the details of it."""
    window("add-missing", lambda: d.open(f"{base}/missing/gone.mp4"))
    window("add-broken", lambda: d.open(f"{base}/broken.mp4"))

    def failed():
        try:
            return d.cell("broken.mp4").status.last_error is not None
        except LookupError:
            return False

    if not _until(d, failed, 30):
        d.note("broken.mp4 shows no error")
        return
    cell = d.cell("broken.mp4")
    d.pump(0.5)
    capture("error", cell)
    window("error-details", cell.status.show_error_details)


def _served(d) -> str:
    """The list and a file that is no video, at the same address each run:
    a screen showing a path on this computer would show where the run was,
    and differ from one run to the next."""
    import shutil
    import threading
    from functools import partial

    from gridplayer.utils.local_server import LocalHTTPServer
    from tests.real_app.driver import RangesHandler

    root = (d.out / "served").resolve()
    (root / "folder").mkdir(parents=True, exist_ok=True)
    for clip in d.media.clips:
        shutil.copy(clip, root / "folder" / clip.name)
    (root / "broken.mp4").write_bytes(b"not a video " * 1000)

    handler = partial(RangesHandler, directory=str(root))
    try:
        server = LocalHTTPServer(("127.0.0.1", SERVED_PORT), handler)
    except OSError:
        server = LocalHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    d._servers.append(server)
    base = f"http://127.0.0.1:{server.server_address[1]}"

    # the list's items by their whole address: a list read off the web
    # names them so
    lines = ["#EXTM3U"]
    for clip, title in zip(d.media.clips, ("Clip A", "Clip B", "Clip C")):
        lines += [f"#EXTINF:20,{title}", f"{base}/folder/{clip.name}"]
    (root / "list.m3u").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return base


def _until(d, predicate, timeout) -> bool:
    """Like the driver's wait_until, but no failure of the run."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        d.pump(0.1)
    return False


def _list_cell(d, window, base):
    """A cell reading a list, and the List window."""
    window("add-list", lambda: d.open(f"{base}/list.m3u"))

    def playing():
        try:
            return d.cell("list.m3u").is_playable
        except LookupError:
            return False

    if not _until(d, playing, 30):
        d.note("the list cell does not play")
        return
    cell = d.cell("list.m3u")
    _hold_still(d)
    window("list", lambda: d.act(cell, "List"))


def _menus(d, block, capture):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication

    # offscreen, the clipboard has no data until some is set, and "Add from
    # Clipboard" asking it raises
    QApplication.clipboard().setText("GridPlayer")
    d.ctx.active_block = block
    menu = d.player._managers_inst["menu"].make_menu()
    menu.popup(d.player.mapToGlobal(QPoint(40, 40)))
    d.pump(0.3)
    capture("menu", menu)

    def submenus(parent, path, depth):
        for action in parent.actions():
            sub = action.menu()
            if sub is None or not action.isVisible() or depth > SUBMENU_DEPTH:
                continue
            sub.popup(parent.mapToGlobal(parent.actionGeometry(action).topRight()))
            d.pump(0.3)
            if sub.actions():
                name = f"{path}-{action.text()}"
                capture(name, sub)
                submenus(sub, name, depth + 1)
            sub.hide()

    submenus(menu, "menu", 1)
    menu.hide()
    menu.deleteLater()
    d.pump(0.2)


def _scrolled_content(dialog):
    """The page's whole content, when it is taller than what shows."""
    from PyQt6.QtWidgets import QScrollArea

    page = dialog.section_page.currentWidget()
    for area in page.findChildren(QScrollArea):
        content = area.widget()
        if (
            area.isVisible()
            and content is not None
            and content.height() > area.viewport().height() + 8
        ):
            return content
    return None


def texts_in(root) -> list[dict]:
    """The texts drawn by root and its children, each with the part of root
    it is seen in."""
    from PyQt6.QtCore import (
        QAbstractListModel,
        QAbstractTableModel,
        QModelIndex,
        QRect,
        Qt,
    )
    from PyQt6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QComboBox,
        QGroupBox,
        QLabel,
        QLineEdit,
        QMenu,
        QTabBar,
        QWidget,
    )

    found = []

    def add(text, rect, widget, shortcut=False):
        text = _plain(text, shortcut)
        if not text:
            return
        seen = _visible(rect, widget, root)
        if seen is not None and not seen.isEmpty():
            found.append(
                {
                    "text": text,
                    "rect": [seen.x(), seen.y(), seen.width(), seen.height()],
                }
            )

    if isinstance(root, QMenu):
        for action in root.actions():
            if action.isVisible() and not action.isSeparator():
                add(action.text(), root.actionGeometry(action), root, shortcut=True)
        return found

    for w in [root, *root.findChildren(QWidget)]:
        if not w.isVisible():
            continue
        whole = QRect(0, 0, w.width(), w.height())
        if isinstance(w, QLabel):
            add(w.text(), whole, w)
        elif isinstance(w, QAbstractButton):
            add(w.text(), whole, w, shortcut=True)
            add(w.toolTip(), whole, w)
        elif isinstance(w, QGroupBox):
            add(w.title(), QRect(0, 0, w.width(), 24), w)
        elif isinstance(w, QLineEdit):
            add(w.placeholderText(), whole, w)
        elif isinstance(w, QComboBox):
            add(w.currentText(), whole, w)
        elif isinstance(w, QTabBar):
            for i in range(w.count()):
                add(w.tabText(i), w.tabRect(i), w)
        elif isinstance(w, QAbstractItemView) and w.model() is not None:
            viewport = w.viewport()

            def rows(parent, depth=0, w=w, viewport=viewport):
                model = w.model()
                # list and table models keep these to themselves
                flat = isinstance(model, (QAbstractListModel, QAbstractTableModel))
                columns = (
                    1
                    if isinstance(model, QAbstractListModel)
                    else model.columnCount(parent)
                )
                for r in range(min(model.rowCount(parent), 300)):
                    for c in range(columns):
                        index = model.index(r, c, parent)
                        text = index.data(Qt.ItemDataRole.DisplayRole)
                        if isinstance(text, str):
                            add(text, w.visualRect(index), viewport)
                    first = model.index(r, 0, parent)
                    if not flat and depth < 3 and model.hasChildren(first):
                        rows(first, depth + 1)

            rows(QModelIndex())

    return found


def _visible(rect, widget, root):
    """rect of widget, in root, cut to what its parents let show."""
    from PyQt6.QtCore import QPoint, QRect

    r = QRect(rect)
    w = widget
    while w is not None and w is not root:
        parent = w.parentWidget()
        if parent is None:
            return None
        r.translate(w.mapTo(parent, QPoint(0, 0)))
        r = r.intersected(QRect(0, 0, parent.width(), parent.height()))
        w = parent
    if w is None:
        return None
    return r.intersected(QRect(0, 0, root.width(), root.height()))


_TAG = re.compile(r"<[^>]+>")


def _plain(text, shortcut=False) -> str:
    """The words, without markup, and without the & that marks a shortcut."""
    if not isinstance(text, str):
        return ""
    if "<" in text:
        text = html.unescape(_TAG.sub(" ", text))
    if shortcut:
        text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    # a menu item's key, after a tab
    text = text.split("\t")[0]
    return " ".join(text.split())


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", _plain(text)).strip("-").lower()
