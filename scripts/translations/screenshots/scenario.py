"""Screenshots of the app in English for Crowdin, with where each text is.

Run by `tr.py screenshots`, which uses tests/real_app:

    uv run python -m tests.real_app.run scripts/translations/screenshots/scenario.py --out DIR

Leaves in DIR a `gp-<name>.png` for each screen, and tags.json: per screen
its size and the texts seen on it, each with its rectangle, for tr.py to
match against en_US.ts.
"""

import html
import json
import os
import re
import sys
import time

SETTINGS = {
    "player/language": "en_US",
    # not the run's own folder, which would show in Settings
    "screenshots/dir": "~/Pictures/GridPlayer",
}
# room for the longest menu, every item of it shown, and for the submenus
# beside it: on Qt's own 800 by 800 they scroll, their ends cut off
SCREEN = (1920, 1600)

PREFIX = "gp-"
# the Settings dialog's height while a long tree of it is shot
ROWS_DIALOG_HEIGHT = 1400
# grid templates of one's own, made for the run: a name, columns, rows
OWN_TEMPLATES_SETTING = "player/grid_templates"
OWN_TEMPLATES = (("Two by two", 2, 2), ("Three across", 3, 1))
# where the snap words go down the editor, and how far apart
SNAP_WORDS_TOP = 80
SNAP_WORDS_STEP = 48
# the cells that show what a cell can say, a few states to a screen
GALLERY_CELLS = 6
# the host named in the errors shown on them
GALLERY_HOST = "example.com"
# the HTTP statuses whose errors are shown
GALLERY_HTTP = (400, 401, 403, 404, 405, 408, 410, 416, 429, 451, 500, 502, 503, 504)
# how long ago loading started, for the time it has taken to show
GALLERY_ELAPSED_S = (12, 75)
# bookmarks added to the feature cell's own at 5 s, and the loop set across
# them: one before it, one in it, the one at 5 s after it
BOOKMARK_TIMES_MS = (500, 2000)
BOOKMARK_LOOP_MS = (1000, 3000)
# files past those a question lists, for its "and so many more"
MORE_FILES = 3
# the data folder a tip names, in place of the run's own
DATA_DIR_STAND_IN = (
    r"C:\Users\Name\AppData\Local\GridPlayer"
    if sys.platform == "win32"
    else "/home/name/.local/share/gridplayer"
)
# the sound devices the menu lists, in place of the computer's own
STAND_IN_DEVICES = ("Speakers", "Headphones")
# a key added to an action, to show it changed
EXTRA_SHORTCUT = "Ctrl+Alt+F12"
# how deep submenus are opened, below the menu itself
# what is kept of the menus above and below an open submenu's cascade
FOCUS_MARGIN = 60
SUBMENU_DEPTH = 3
# the title bar drawn over a window's shot, and its frame
TITLE_BAR = 32
FRAME = 1
# the room after the title: a gap and the close button
TITLE_RIGHT = 52
# where the mouse is taken to rest for a tip, from the left of what it is
# about, and the width of the screen its lines wrap for
TIP_CURSOR_X = 40
TIP_SCREEN_WIDTH = 1920
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
    d.note(f"screen {QApplication.primaryScreen().geometry()}")
    shots = {}

    def save(name, picture, size, texts):
        name = PREFIX + _slug(name)
        picture.save(str(d.out / f"{name}.png"))
        d.note(f"screenshot {name}.png")
        shots[name] = {"size": [size.width(), size.height()], "texts": texts}

    def capture(name, widget, only=None):
        """widget as it is; with only, a function of a text, just the
        texts it takes tagged: what changed since its own screen."""
        picture, size, _, texts = _framed(widget)
        if only is not None:
            texts = [t for t in texts if only(t["text"])]
        save(name, picture, size, texts)

    def capture_over(name, under, popup, popup_texts):
        """A popup or a tip drawn over the window it came from, as one
        screen; only its own texts tagged, the window's are on its own
        screen."""
        save(name, *_over(under, [(popup, popup_texts)]))

    def capture_layers(name, under, layers, focus=None):
        """Menus opened one from another over under, each (menu, texts);
        with focus, a span of the screen's heights, only that part."""
        save(name, *_over(under, layers, focus))

    # the items of each drop-down and the text of each tip shot so far: one
    # the same as another (SponsorBlock's, a page in both dialogs, a Reset
    # button) is shot once
    seen_choices = set()
    seen_tips = set()
    # the items of each menu shot so far, the same way
    seen_menus = set()

    def tips(prefix, window, layers_under=()):
        """The tips in window, each shot over window or, with
        layers_under, over the main window with those layers (windows of
        their own over it) between."""

        def capture_tip(name, tip, texts):
            if layers_under:
                capture_layers(name, d.player, [*layers_under, (tip, texts)])
            else:
                capture_over(name, window, tip, texts)

        _tips(d, window, prefix, capture_tip, seen_tips)

    def menus_in(prefix, window):
        _menus_in(d, window, prefix, capture_layers, seen_menus)

    def window(name, open_it, inspect=None, then=None):
        def look(shown):
            capture(name, shown)
            tips(name, shown)
            menus_in(name, shown)
            if then is not None:
                then(shown)

        _window(d, name, open_it, inspect or look)

    # rows only on another system or player, or under a switch that is off,
    # shown all the same: greyed out where they can't be used here
    _show_every_setting()

    base = _served(d)
    d.open(f"{base}/folder/a.mp4", f"{base}/folder/b.mp4")
    block = d.wait_for_cell("a.mp4")
    d.wait_for_cell("b.mp4")
    _hold_still(d)
    capture("main", d.player)

    # the menu of a video with chapters, tracks and a bookmark, so that the
    # lists made of them have items
    feature = _feature_cell(d, base)
    _add_own_templates()
    _menus(d, feature or block, capture, capture_layers, seen_menus)

    # before the dialogs below, one of which sets a grid with no room left
    _broken_cell(d, capture, window, base)
    _list_cell(d, window, base)

    for action, name in CELL_DIALOGS:
        window(name, lambda action=action: d.act(block, action))

    if feature is not None:
        _bookmark_states(d, feature, window, capture, capture_layers, seen_menus)

    def pages(prefix, extra=None):
        def look(dialog):
            for page_id in list(dialog.pages):
                dialog.show_page(page_id)
                d.pump(0.3)
                capture(f"{prefix}-{page_id}", dialog)
                full = _scrolled_content(dialog)
                if full is not None:
                    capture(f"{prefix}-{page_id}-all", full)
                _choices(d, dialog, f"{prefix}-{page_id}", capture_over, seen_choices)
                _all_rows(d, dialog, f"{prefix}-{page_id}", capture)
                tips(f"{prefix}-{page_id}", dialog)
                menus_in(f"{prefix}-{page_id}", dialog)
            window(f"{prefix}-reset-page", dialog.ask_reset_page)
            if extra is not None:
                extra(dialog)

        return look

    def checkups(dialog):
        _help_boxes(window, dialog)
        _reset_questions(window, dialog)

        from gridplayer.dialogs import checkup

        # the steps and their hints, not what the network says
        checkup.CheckRunner.start = lambda self: None
        window("checkup-network", dialog.run_network_checkup)
        window("checkup-youtube", dialog.run_youtube_checkup)

        _shortcut_editor(d, dialog, window, capture, capture_layers, seen_menus)

    window("settings", lambda: d.act(block, "Settings"), pages("settings", checkups))
    window(
        "playlist", lambda: d.act(block, "Edit Playlist Settings"), pages("playlist")
    )
    window(
        "about",
        lambda: d.act(block, "About"),
        then=lambda shown: _all_text(d, shown, "about", capture),
    )

    def show_exception():
        from gridplayer.dialogs.exception import ExceptionDialog

        ExceptionDialog(FAKE_TRACEBACK).exec()

    window("exception", show_exception)

    # last, as the grid is left another kind than the dialogs above had
    _grid_templates(d, block, window)
    _edit_grid_kinds(d, block, capture_layers, tips)
    # last of all: every cell is closed for it
    _status_gallery(d, base, capture)

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


def _choices(d, dialog, prefix, capture_over, seen):
    """The lists of choices of a page's drop-downs, opened one by one, each
    shown open in the dialog, scrolled to where it is. A list with the same
    items as one already shot is left out."""
    from PyQt6.QtWidgets import QComboBox

    page = dialog.section_page.currentWidget()
    combos = [
        c for c in page.findChildren(QComboBox) if c.isVisible() and c.count() > 1
    ]
    n = 0
    for combo in combos:
        items = tuple(combo.itemText(i) for i in range(combo.count()))
        if items in seen:
            continue
        seen.add(items)

        _scroll_to(d, combo)
        combo.showPopup()
        d.pump(0.2)
        popup = combo.view().window()
        if popup.isVisible():
            n += 1
            capture_over(f"{prefix}-choices-{n}", dialog, popup, texts_in(popup))
        combo.hidePopup()
        d.pump(0.1)

    _scroll_back(page)


def _tips(d, window, prefix, capture_tip, seen):
    """The tip of each thing in window that has one, as the app shows it
    when the mouse rests there, one screen each. A text already shot is
    left out."""
    from PyQt6.QtCore import QPoint, QRect
    from PyQt6.QtWidgets import QWidget

    widgets = [w for w in [window, *window.findChildren(QWidget)] if w.isVisible()]
    n = 0
    for widget in widgets:
        text = widget.toolTip()
        if not text or text in seen or not widget.isVisible():
            continue

        _scroll_to(d, widget)
        if widget is not window and not _in_view(widget, window):
            d.note(f"{prefix}: no tip for what can't be scrolled to: {text[:40]!r}")
            continue
        seen.add(text)

        anchor = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
        tip, tip_texts = _tip_at(d, window, text, anchor)
        n += 1
        capture_tip(f"{prefix}-tip-{n}", tip, tip_texts)
        tip.hide_now()
        tip.deleteLater()

    if hasattr(window, "section_page"):
        _scroll_back(window.section_page.currentWidget())
    d.pump(0.1)


def _tip_at(d, window, text, anchor):
    """A tip of window saying text, shown where the app puts one for the
    mouse resting at anchor (on the screen), and its text where it is."""
    from PyQt6.QtCore import QPoint, QRect
    from PyQt6.QtGui import QFontMetrics

    from gridplayer.widgets.tooltip import TipWindow, tip_position

    # a screen big enough for the tip to go under what it is about, as on
    # a real one, not over it as at the bottom of the offscreen one
    area = QRect(-10000, -10000, 20000, 20000)

    # the run's own folder, where a tip names the data folder, would show
    # where the run was
    data_dir = os.environ.get("GP_USER_DATA_DIR")
    if data_dir:
        text = text.replace(data_dir, DATA_DIR_STAND_IN)

    tip = TipWindow(window)
    tip.set_text(text, TIP_SCREEN_WIDTH)
    cursor = anchor.topLeft() + QPoint(
        min(TIP_CURSOR_X, anchor.width() // 2), anchor.height() // 2
    )
    line_height = QFontMetrics(tip.font()).lineSpacing()
    tip.move_box(tip_position(anchor, cursor, tip.box_size(), area, line_height))
    tip.show_now()
    d.pump(0.2)

    box = tip.box_geometry()
    box.translate(-tip.mapToGlobal(QPoint(0, 0)))
    rect = [box.x(), box.y(), box.width(), box.height()]
    texts = [{"text": _plain(text), "rect": rect}]
    # each line its own string, as a tip made of several often is
    lines = [_plain(line) for line in _BREAK.split(text)]
    if len(lines) > 1:
        texts += [{"text": line, "rect": rect} for line in lines if line]
    return tip, texts


def _item_tip(d, window, view, index, name, capture_layers):
    """The tip of a row of view (its model's), shot over window."""
    from PyQt6.QtCore import QRect, Qt

    text = index.data(Qt.ItemDataRole.ToolTipRole)
    if not text:
        d.note(f"{name}: the row has no tip")
        return
    view.scrollTo(index)
    d.pump(0.1)
    rect = view.visualRect(index)
    anchor = QRect(view.viewport().mapToGlobal(rect.topLeft()), rect.size())
    tip, texts = _tip_at(d, window, text, anchor)
    capture_layers(name, window, [(tip, texts)])
    tip.hide_now()
    tip.deleteLater()


def _scroll_to(d, widget):
    """widget scrolled into view, where it is in a scrolled page or in a
    row of a list (the languages)."""
    from PyQt6.QtCore import QAbstractListModel
    from PyQt6.QtWidgets import QAbstractItemView, QScrollArea

    view = _ancestor(widget, QAbstractItemView)
    if view is not None and view.model() is not None:
        model = view.model()
        # a list model keeps its column count to itself
        columns = 1 if isinstance(model, QAbstractListModel) else model.columnCount()
        for r in range(model.rowCount()):
            for c in range(columns):
                index = model.index(r, c)
                row = view.indexWidget(index)
                if row is not None and (row is widget or row.isAncestorOf(widget)):
                    view.scrollTo(index)
                    d.pump(0.1)
                    break

    area = _ancestor(widget, QScrollArea)
    if area is not None:
        area.ensureWidgetVisible(widget)
        d.pump(0.1)


def _in_view(widget, window) -> bool:
    """Whether any of widget shows in window, not cut off by a list or a
    page scrolled past it."""
    from PyQt6.QtCore import QRect

    seen = _visible(QRect(0, 0, widget.width(), widget.height()), widget, window)
    return seen is not None and not seen.isEmpty()


def _scroll_back(page):
    """Back to the top, as the page's own shot showed it: its lists too."""
    from PyQt6.QtWidgets import QAbstractScrollArea

    for area in page.findChildren(QAbstractScrollArea):
        area.verticalScrollBar().setValue(0)


def _ancestor(widget, kind):
    w = widget.parentWidget()
    while w is not None and not isinstance(w, kind):
        w = w.parentWidget()
    return w


def _grab(widget):
    """widget as a picture, as the driver's shot takes it: the videos in it
    too."""
    from gridplayer.widgets.video_surface_gl import GLVideoSurface
    from tests.real_app.composed import grab_composed, has_own_window_video

    if has_own_window_video(widget):
        return grab_composed(widget)
    with GLVideoSurface.grabbing():
        return widget.grab().toImage()


def _has_title_bar(widget) -> bool:
    """A window with a title: an empty bar would tell a translator nothing."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMenu

    return (
        widget.isWindow()
        and bool(widget.windowTitle().replace("[*]", "").strip())
        and not isinstance(widget, QMenu)
        and widget.windowType() not in (Qt.WindowType.Popup, Qt.WindowType.ToolTip)
    )


def _framed(widget):
    """widget as a picture with its texts; a window with a title bar drawn
    over it, which offscreen windows have none of, its title one of the
    texts. Returns the picture, its size, where widget is in it and the
    texts, each with its rectangle in the picture."""
    from PyQt6.QtCore import QPoint, QRect, QSize, Qt
    from PyQt6.QtGui import QFontMetrics, QImage, QPainter, QPalette, QPen
    from PyQt6.QtWidgets import QWidget

    image = _grab(widget)
    texts = texts_in(widget)
    size = QSize(widget.width(), widget.height())
    if not _has_title_bar(widget):
        return image, size, QPoint(0, 0), texts

    # the rename dialog has a "palette" of its own, of colors
    palette = QWidget.palette(widget)
    title = widget.windowTitle().replace("[*]", "")
    icon = widget.windowIcon()
    metrics = QFontMetrics(widget.font())
    title_left = 10 + (0 if icon.isNull() else 24)
    # the whole title, for the translator: a window narrower than it is
    # drawn wider, its own background filling the rest
    width = max(
        size.width(), title_left + metrics.horizontalAdvance(title) + TITLE_RIGHT
    )
    origin = QPoint(FRAME, TITLE_BAR)
    framed_size = QSize(width + 2 * FRAME, size.height() + TITLE_BAR + FRAME)

    ratio = image.devicePixelRatio()
    framed = QImage(framed_size * ratio, QImage.Format.Format_ARGB32_Premultiplied)
    framed.setDevicePixelRatio(ratio)
    framed.fill(palette.color(QPalette.ColorRole.Mid))

    painter = QPainter(framed)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    window_color = palette.color(QPalette.ColorRole.Window)
    painter.fillRect(QRect(origin, QSize(width, size.height())), window_color)
    bar = QRect(FRAME, FRAME, width, TITLE_BAR - FRAME)
    painter.fillRect(bar, window_color.darker(108))

    if not icon.isNull():
        icon.paint(painter, QRect(bar.left() + 10, bar.center().y() - 7, 16, 16))

    text_color = palette.color(QPalette.ColorRole.WindowText)
    cross = QPoint(bar.right() - 18, bar.center().y() + 1)
    painter.setPen(QPen(text_color, 1.2))
    painter.drawLine(cross - QPoint(5, 5), cross + QPoint(5, 5))
    painter.drawLine(cross + QPoint(-5, 5), cross + QPoint(5, -5))

    texts = list(_moved(texts, origin))
    if title:
        text_rect = QRect(
            bar.left() + title_left,
            bar.top(),
            metrics.horizontalAdvance(title),
            bar.height(),
        )
        painter.setFont(widget.font())
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            title,
        )
        r = text_rect
        texts.insert(
            0, {"text": _plain(title), "rect": [r.x(), r.y(), r.width(), r.height()]}
        )

    painter.drawImage(origin, image)
    painter.end()
    return framed, framed_size, origin, texts


def _moved(texts, by):
    for t in texts:
        x, y, w, h = t["rect"]
        yield {**t, "rect": [x + by.x(), y + by.y(), w, h]}


def _over(under, layers, focus=None):
    """under, framed, with layers (a widget and its texts) drawn over it
    where they show; the picture can reach past under where they do.
    Returns the picture, its size and the texts of the layers, where they
    are in it: under's are on its own screen.

    focus, a top and a bottom on the screen, cuts the picture to that
    height, give or take FOCUS_MARGIN."""
    from PyQt6.QtCore import QPoint, QRect, Qt
    from PyQt6.QtGui import QImage, QPainter

    base, base_size, origin, _ = _framed(under)
    where = origin - under.mapToGlobal(QPoint(0, 0))

    placed = []
    area = QRect(QPoint(0, 0), base_size)
    for widget, texts in layers:
        at = widget.mapToGlobal(QPoint(0, 0)) + where
        placed.append((_grab(widget), at, texts))
        area = area.united(QRect(at, widget.size()))
    shift = -area.topLeft()

    ratio = base.devicePixelRatio()
    picture = QImage(area.size() * ratio, QImage.Format.Format_ARGB32_Premultiplied)
    picture.setDevicePixelRatio(ratio)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    painter.drawImage(shift, base)
    found = []
    for image, at, texts in placed:
        painter.drawImage(at + shift, image)
        found += _moved(texts, at + shift)
    painter.end()

    if focus is None:
        return picture, area.size(), found
    return _cut(picture, found, focus, where.y() + shift.y())


def _cut(picture, texts, focus, offset):
    """picture cut to focus (a top and a bottom on the screen; offset takes
    them into the picture), with FOCUS_MARGIN above and below, and the
    texts left in it, moved to match."""
    from PyQt6.QtCore import QPoint, QRect, QSize

    ratio = picture.devicePixelRatio()
    width = round(picture.width() / ratio)
    height = round(picture.height() / ratio)
    top = max(0, focus[0] + offset - FOCUS_MARGIN)
    bottom = min(height, focus[1] + offset + FOCUS_MARGIN)

    cut = picture.copy(
        QRect(0, round(top * ratio), picture.width(), round((bottom - top) * ratio))
    )
    cut.setDevicePixelRatio(ratio)
    kept = [
        t
        for t in _moved(texts, QPoint(0, -top))
        if t["rect"][1] >= 0 and t["rect"][1] + t["rect"][3] <= bottom - top
    ]
    return cut, QSize(width, bottom - top), kept


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
    shutil.copytree(d.media.feature.parent, root / "feature", dirs_exist_ok=True)

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
    window(
        "list",
        lambda: d.act(cell, "List"),
        then=lambda shown: _list_questions(window, shown),
    )


def _menus(d, block, capture, capture_layers, seen):
    """The cell's menu and its submenus, every item shown whether this
    cell would have it or not; then again with each item that says one of
    two things saying the other. A submenu is shot open from the menus it
    comes from, its own items the ones tagged."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication

    # offscreen, the clipboard has no data until some is set, and "Add from
    # Clipboard" asking it raises
    QApplication.clipboard().setText("GridPlayer")
    d.ctx.active_block = block

    for name, flipped in (("menu", False), ("menu-other", True)):
        # the second time as for a file on this computer, with a file of
        # sound and one of subtitles added: what the tracks menus offer
        # only then
        local = _as_local_file(block) if flipped else _nothing()
        with _every_item_shown(d, flipped), _stand_in_devices(block), local:
            menu = d.player._managers_inst["menu"].make_menu()
            menu.popup(d.player.mapToGlobal(QPoint(40, 40)))
            d.pump(0.3)
            items = _menu_items(menu)
            if items not in seen:
                seen.add(items)
                capture(name, menu)
            _submenus(d, [menu], name, menu, capture_layers, seen)
            menu.hide()
            menu.deleteLater()
            d.pump(0.2)


def _submenus(d, chain, path, under, capture_layers, seen, depth=1):
    """The submenus of the last menu of chain, each shot open over under
    from the menus before it, down to SUBMENU_DEPTH."""
    from PyQt6.QtWidgets import QMenu

    parent = chain[-1]
    if depth > SUBMENU_DEPTH:
        return
    for action in parent.actions():
        sub = action.menu()
        if sub is None or not action.isVisible():
            continue
        parent.setActiveAction(action)
        sub.popup(parent.mapToGlobal(parent.actionGeometry(action).topRight()))
        d.pump(0.3)
        if sub.actions():
            name = f"{path}-{action.text()}"
            items = _menu_items(sub)
            if items not in seen:
                seen.add(items)
                layers = [(m, []) for m in chain if m is not under]
                capture_layers(
                    name,
                    under,
                    [*layers, (sub, texts_in(sub))],
                    _focus(chain, sub) if isinstance(under, QMenu) else None,
                )
            _submenus(d, [*chain, sub], name, under, capture_layers, seen, depth + 1)
        sub.hide()


def _focus(chain, sub) -> tuple[int, int]:
    """The heights on the screen of sub and of the items of chain it was
    opened from: the part of a cascade worth showing."""
    from PyQt6.QtCore import QPoint

    top = sub.mapToGlobal(QPoint(0, 0)).y()
    bottom = top + sub.height()
    for menu in chain:
        action = menu.activeAction()
        if action is None:
            continue
        item = menu.actionGeometry(action)
        y = menu.mapToGlobal(item.topLeft()).y()
        top, bottom = min(top, y), max(bottom, y + item.height())
    return top, bottom


def _menu_items(menu) -> tuple:
    return tuple(
        a.text() for a in menu.actions() if a.isVisible() and not a.isSeparator()
    )


class _every_item_shown:
    """While in it, every action of the menus is shown, whatever its
    show_if; those that work out a title, a tick or their items from the
    cell give a stand-in where this cell has none. flipped: each title of
    two says the other."""

    def __init__(self, d, flipped=False):
        self._actions = list(d.ctx.actions.values())
        self._flipped = flipped
        self._saved = []

    def __enter__(self):
        stand_ins = {
            "value_getter": "…",
            "check_if": False,
            "enable_if": True,
            "toggle": False,
            "menu_generator": [],
            "menu_templates": [],
        }
        for action in self._actions:
            self._saved.append(
                (action, {k: getattr(action, k) for k in ("show_if", *stand_ins)})
            )
            action.show_if = None
            for attr, stand_in in stand_ins.items():
                f = getattr(action, attr)
                if f is not None:
                    setattr(action, attr, _safe(f, stand_in))
            if self._flipped and action.toggle is not None:
                toggle = action.toggle
                action.toggle = lambda toggle=toggle: not toggle()
        return self

    def __exit__(self, *exc):
        for action, saved in self._saved:
            for attr, value in saved.items():
                setattr(action, attr, value)
        return False


class _nothing:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _as_local_file:
    """While in it, block is taken for a file on this computer (its address
    a bare file name, not a path that would show where the run is), with a
    file of sound and one of subtitles added; nothing is read from them."""

    def __init__(self, block):
        self._block = block

    def __enter__(self):
        from pathlib import Path, PurePosixPath
        from urllib.parse import urlparse

        params = self._block.video_params
        self._params = (params.uri, params.external_audio, params.external_subtitles)
        params.uri = Path(PurePosixPath(urlparse(str(params.uri)).path).name)
        params.external_audio = [Path("commentary.mka")]
        params.external_subtitles = [Path("commentary.srt")]
        return self

    def __exit__(self, *exc):
        params = self._block.video_params
        params.uri, params.external_audio, params.external_subtitles = self._params
        return False


class _stand_in_devices:
    """While in it, block's sound goes out of made-up devices: the menu of
    them would show those of the computer the run is on."""

    def __init__(self, block):
        self._audio = block.audio

    def __enter__(self):
        from types import SimpleNamespace

        audio = self._audio
        self._kind = type(audio)
        original = self._kind.devices
        made_up = tuple(
            SimpleNamespace(id=f"device-{n}", name=name)
            for n, name in enumerate(STAND_IN_DEVICES, 1)
        )

        def devices(part):
            return made_up if part is audio else original.fget(part)

        self._original = original
        self._kind.devices = property(devices)
        return self

    def __exit__(self, *exc):
        self._kind.devices = self._original
        return False


def _safe(f, stand_in):
    """f, or stand_in where it fails or gives nothing of the kind (a value
    of None where the title wants a text)."""

    def call(*args):
        try:
            result = f(*args)
        except Exception:
            return stand_in
        if result is None or not isinstance(result, type(stand_in)):
            # a bool stands for any truth, a list for any items
            if isinstance(stand_in, str):
                return stand_in
        return result

    return call


def _feature_cell(d, base):
    """A cell playing the file with chapters, two audio tracks and
    subtitles, served so as not to show a path on this computer, with a
    bookmark."""

    d.open(f"{base}/feature/feature.mkv")

    def playing():
        try:
            return d.cell("feature.mkv").is_playable
        except LookupError:
            return False

    if not _until(d, playing, 30):
        d.note("the feature cell does not play")
        return None
    cell = d.cell("feature.mkv")
    _hold_still(d)
    d.act(cell, "Add Bookmark")
    d.pump(0.3)
    return cell


def _bookmark_states(d, feature, window, capture, capture_layers, seen):
    """The feature cell's bookmarks with a loop set across them: the list's
    marks of where the loop is, a row out of the loop and its tip, a row's
    menu; the menu of a marker on the bar; and what is asked as bookmarks
    stop or start being shared between cells."""
    from pathlib import Path

    from PyQt6.QtCore import QPoint

    from gridplayer.player.managers import bookmarks

    for time_ms in BOOKMARK_TIMES_MS:
        feature.seek(time_ms)
        if not _until(d, lambda t=time_ms: abs(feature.time - t) < 300, 5):
            d.note(f"the feature cell did not get to {time_ms} ms")
        d.act(feature, "Add Bookmark")
        d.pump(0.3)
    feature.seek(BOOKMARK_LOOP_MS[1] - 500)
    feature.loop.set_start_time(BOOKMARK_LOOP_MS[0])
    feature.loop.set_end_time(BOOKMARK_LOOP_MS[1])
    d.pump(0.5)

    def look(shown):
        capture("bookmarks-loop", shown)
        view = shown._list
        model = view.model()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if feature.bookmarker.is_reachable_at(row):
                continue
            _item_tip(d, shown, view, index, "bookmarks-loop-tip", capture_layers)
            break

        view.setCurrentIndex(model.index(0, 0))
        d.pump(0.1)
        at = view.viewport().mapToGlobal(view.visualRect(model.index(0, 0)).center())

        def look_menu(menu):
            name = "bookmarks-row-menu"
            capture_layers(name, shown, [(menu, texts_in(menu))])
            _submenus(d, [menu], name, shown, capture_layers, seen)

        _popup_from(d, lambda: shown._show_row_menu(at), look_menu)

    window("bookmarks-loop", lambda: d.act(feature, "Manage Bookmarks"), inspect=look)

    # no loop for the bar's menu, whose Jump is greyed out past it
    feature.loop.reset()
    _hold_still(d)

    def look_marker(menu):
        name = "bookmark-marker-menu"
        capture_layers(name, d.player, [(menu, texts_in(menu))])
        _submenus(d, [menu], name, d.player, capture_layers, seen)

    last = feature.bookmarks[-1].time_ms
    at = d.player.mapToGlobal(QPoint(200, 200))
    _popup_from(d, lambda: feature.bookmarker.show_marker_menu(at, [last]), look_marker)

    manager = d.player._managers_inst["bookmarks"]
    window("bookmarks-stop-sharing", manager._confirm_split)

    registry = manager._registry
    files = [
        (Path(f"clip-{n}.mp4"), 2)
        for n in range(1, bookmarks.MERGE_FILES_LISTED + MORE_FILES + 1)
    ]
    registry.disagreeing = lambda cells: files
    try:
        window("bookmarks-merge", manager._confirm_merge)
    finally:
        del registry.disagreeing


def _shortcut_editor(d, dialog, window, capture, capture_layers, seen):
    """The Shortcuts page's own windows and states: an action's menu, the
    windows adding a key, a mouse button and a drag, a key taken by another
    action and the question of taking it, a drag that can't be one, the
    rows' tips, the count of those changed, the filter's other kinds."""
    from PyQt6.QtCore import QModelIndex, Qt

    from gridplayer.params.gestures import GestureKind
    from gridplayer.utils.keymap import HOLD_KEYS, MouseButtonSequence
    from gridplayer.widgets import keymap_tree_view as kv

    dialog.show_page("shortcuts")
    d.pump(0.3)
    editor = dialog.findChild(kv.KeymapEditor)
    if editor is None:
        d.note("no shortcut editor")
        return
    tree = editor.tree
    model = tree.source_model()
    before = {t["text"] for t in texts_in(dialog)}

    def new(text):
        return text not in before

    def items():
        return list(kv._iter_action_items(model))

    def first(kind, with_keys=False):
        for item in items():
            if item.data(kv.DATA_KIND) is kind and (
                not with_keys or item.data(kv.DATA_SHORTCUTS)
            ):
                return item
        return None

    action = first(None, with_keys=True)
    drag = first(GestureKind.DRAG)
    if action is None or drag is None:
        d.note("no action or drag to show the shortcut windows with")
        return
    action_id = action.data(kv.DATA_ACTION_ID)

    # changed, so its menu has Reset and the page counts it
    tree.set_action_shortcuts(
        action_id, [*action.data(kv.DATA_SHORTCUTS), EXTRA_SHORTCUT]
    )
    editor._update_status()
    d.pump(0.2)
    capture("settings-shortcuts-changed", dialog, only=new)

    def tip_of(item, name):
        if item is None:
            return
        index = tree._proxy_index_for_item(item)
        _item_tip(d, dialog, tree, index, name, capture_layers)

    tip_of(kv._find_action_item(model, action_id), "settings-shortcuts-row-tip-1")
    for n, kind in enumerate(
        (GestureKind.DRAG, GestureKind.HOLD, GestureKind.FIXED), 2
    ):
        tip_of(first(kind), f"settings-shortcuts-row-tip-{n}")

    def action_menu(item, name):
        item_id = item.data(kv.DATA_ACTION_ID)
        index = tree._proxy_index_for_item(item)
        tree.scrollTo(index)
        d.pump(0.1)
        at = tree.viewport().mapToGlobal(tree.visualRect(index).center())

        def look(menu):
            capture_layers(name, dialog, [(menu, texts_in(menu))])
            _submenus(d, [menu], name, dialog, capture_layers, seen)

        _popup_from(d, lambda: editor._show_action_menu(item_id, at), look)

    action = kv._find_action_item(model, action_id)
    action_menu(action, "settings-shortcuts-action-menu")
    action_menu(drag, "settings-shortcuts-drag-menu")

    title = action.text()
    path = action.data(kv.DATA_PATH) or []
    keys = list(action.data(kv.DATA_SHORTCUTS) or [])

    def keyboard(shown):
        conflicts = shown._conflict_map
        if not conflicts:
            return
        taken = next(iter(conflicts))
        shown._key_edit.set_sequence_text(taken)
        d.pump(0.3)
        capture("settings-shortcuts-add-keyboard-taken", shown)
        window(
            "settings-shortcuts-reassign",
            lambda: shown._confirm_reassign(taken, shown._conflicts_for(taken)),
        )

    window(
        "settings-shortcuts-add-keyboard",
        lambda: editor._add_keyboard(action_id, title, path, keys),
        then=keyboard,
    )
    window(
        "settings-shortcuts-add-mouse",
        lambda: editor._add_mouse(action_id, title, path, keys),
    )

    def drags(shown):
        plain = MouseButtonSequence.from_drag_press(
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )
        shown._mouse_field.set_sequence(str(plain))
        d.pump(0.3)
        capture("settings-shortcuts-add-drag-plain", shown)
        modifier = HOLD_KEYS.get(shown._hold_key)
        if modifier is None:
            return
        held = MouseButtonSequence.from_drag_press(Qt.MouseButton.LeftButton, modifier)
        shown._mouse_field.set_sequence(str(held))
        d.pump(0.3)
        capture("settings-shortcuts-add-drag-held", shown)

    drag_keys = list(drag.data(kv.DATA_SHORTCUTS) or [])
    window(
        "settings-shortcuts-add-drag",
        lambda: editor._add_drag(
            drag.data(kv.DATA_ACTION_ID),
            drag.text(),
            drag.data(kv.DATA_PATH) or [],
            drag_keys,
        ),
        then=drags,
    )

    # the filter's placeholder for each kind of search but the first
    for n in range(1, editor.filter_scope.count()):
        editor.filter_scope.setCurrentIndex(n)
        d.pump(0.2)
        capture(f"settings-shortcuts-filter-{n}", dialog, only=new)
    editor.filter_scope.setCurrentIndex(0)
    tree.scrollTo(QModelIndex())


def _menus_in(d, window, prefix, capture_layers, seen):
    """The menus a window has: its buttons' and those its lists show on a
    right click, on a row and below the rows; each with its submenus."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QApplication,
        QPushButton,
        QToolButton,
        QWidget,
    )
    from PyQt6.QtCore import Qt

    openers = []
    for w in window.findChildren(QAbstractButton):
        if (
            isinstance(w, (QPushButton, QToolButton))
            and w.menu() is not None
            and w.isVisible()
            and w.isEnabled()
            and _in_view(w, window)
        ):
            openers.append(w.showMenu)

    for view in window.findChildren(QAbstractItemView):
        model = view.model()
        if not view.isVisible() or model is None:
            continue
        viewport = view.viewport()
        spots = []
        if model.rowCount() > 0:
            spots.append(view.visualRect(model.index(0, 0)).center())
        empty = QPoint(8, viewport.height() - 8)
        if not view.indexAt(empty).isValid():
            spots.append(empty)
        for spot in spots:

            def right_click(viewport=viewport, spot=spot):
                event = QContextMenuEvent(
                    QContextMenuEvent.Reason.Mouse,
                    spot,
                    viewport.mapToGlobal(spot),
                )
                QApplication.sendEvent(viewport, event)

            openers.append(right_click)

    for w in [window, *window.findChildren(QWidget)]:
        if (
            w.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
            and w.isVisible()
            and not isinstance(w, QAbstractItemView)
        ):
            openers.append(lambda w=w: w.customContextMenuRequested.emit(QPoint(8, 8)))

    n = 0
    for opener in openers:

        def look(menu):
            nonlocal n
            items = _menu_items(menu)
            if not items or items in seen:
                return
            seen.add(items)
            n += 1
            name = f"{prefix}-menu-{n}"
            capture_layers(name, window, [(menu, texts_in(menu))])
            _submenus(d, [menu], name, window, capture_layers, seen)

        _popup_from(d, opener, look)


def _popup_from(d, open_it, look):
    """Look at the popup menu open_it shows, then close it; open_it may
    wait for it to close (exec), or not."""
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMenu

    started = time.monotonic()
    done = []

    def check():
        popup = QApplication.activePopupWidget()
        if not isinstance(popup, QMenu):
            if time.monotonic() - started < 2:
                QTimer.singleShot(100, check)
            else:
                done.append(None)
            return
        try:
            look(popup)
        except Exception as e:
            d.note(f"menu: {type(e).__name__}: {e}")
        done.append(popup)
        popup.close()

    QTimer.singleShot(300, check)
    try:
        open_it()
    except Exception as e:
        d.note(f"menu did not open: {type(e).__name__}: {e}")
    deadline = time.monotonic() + 15
    while not done and time.monotonic() < deadline:
        d.pump(0.05)
    d.pump(0.1)


def _all_rows(d, dialog, prefix, capture):
    """A page's tree with every folder open (the shortcuts), shot as it is
    scrolled down a screen at a time."""
    from PyQt6.QtWidgets import QTreeView

    page = dialog.section_page.currentWidget()
    for tree in page.findChildren(QTreeView):
        if not tree.isVisible():
            continue
        tree.expandAll()
        d.pump(0.3)
        bar = tree.verticalScrollBar()
        if bar.maximum() == 0:
            # all of it on the page's own screen
            tree.collapseAll()
            continue
        # taller while it is shot, for fewer screens of it
        size = dialog.size()
        dialog.resize(size.width(), ROWS_DIALOG_HEIGHT)
        d.pump(0.3)
        n = 0
        value = 0
        while True:
            bar.setValue(value)
            d.pump(0.2)
            n += 1
            capture(f"{prefix}-rows-{n}", dialog)
            if bar.value() >= bar.maximum():
                break
            value = bar.value() + bar.pageStep()
        tree.collapseAll()
        bar.setValue(0)
        dialog.resize(size)
        d.pump(0.2)


def _show_every_setting():
    """The settings forms show every row: one only on another system or
    with another player greyed out instead, as one it can't use here is;
    one under a switch that is off shown with it."""
    from gridplayer.widgets.settings_form import SettingsForm

    check_available = SettingsForm._check_available

    def check(self, spec, row):
        check_available(self, spec, row)
        self._hidden.discard(spec.settings_key)

    SettingsForm._check_available = check
    SettingsForm._is_shown = lambda self, key, is_on: True

    # an example of what goes in a field, kept while it is greyed out
    from gridplayer.widgets.settings_editors import _TextEditor

    set_enabled = _TextEditor.set_enabled

    def keep_placeholder(self, enabled):
        set_enabled(self, enabled)
        if self.spec.placeholder:
            self.widget.setPlaceholderText(self.spec.placeholder)

    _TextEditor.set_enabled = keep_placeholder


def _edit_grid_kinds(d, block, capture_layers, tips):
    """Edit Grid with the grid as it is, then with Free Tiles and with
    Mosaic, each with its tips and the popups of its bar's buttons. The
    editor is a window of its own over the main window: shot over it."""
    from PyQt6.QtWidgets import QApplication, QPushButton

    from gridplayer.widgets.layout_editor import (
        EditorPopup,
        LayoutEditor,
        _BarButton,
    )

    # the cells that failed, whose errors would show through the editor
    for cell in list(d.cells):
        if not cell.is_playable:
            d.act(cell, "Close")
    d.pump(0.5)

    # the words by the pointer once for each editor: Mosaic's are Free
    # Tiles'
    snaps_shown = set()
    for kind in (None, "Free Tiles", "Mosaic"):
        name = "edit-grid" if kind is None else f"edit-grid-{_slug(kind)}"
        if kind is not None:
            d.act(block, kind)
            d.pump(0.5)
        d.act(block, "Edit Grid")
        d.pump(0.5)
        editor = next(
            (e for e in d.player.findChildren(LayoutEditor) if e.isVisible()), None
        )
        if editor is None:
            d.note(f"{name}: no editor")
            continue
        capture_layers(name, d.player, [(editor, texts_in(editor))])

        n = 0
        for button in editor.findChildren(QPushButton):
            if not (
                isinstance(button, _BarButton)
                and button.isCheckable()
                and button.isVisible()
                and button.isEnabled()
            ):
                continue
            button.click()
            d.pump(0.3)
            popup = QApplication.activePopupWidget()
            if isinstance(popup, EditorPopup):
                n += 1
                capture_layers(
                    f"{name}-popup-{n}",
                    d.player,
                    [(editor, []), (popup, texts_in(popup))],
                )
                popup.close()
                d.pump(0.2)
            else:
                # a switch, not a popup: back as it was
                button.click()
                d.pump(0.2)

        if editor.is_tiles not in snaps_shown:
            snaps_shown.add(editor.is_tiles)
            _snap_words(d, editor, f"{name}-snaps", capture_layers)
        tips(name, editor, layers_under=[(editor, [])])
        d.act(block, "Edit Grid")
        d.pump(0.3)


def _list_questions(window, dialog):
    """What the List window asks before it unlinks, links or reloads a
    list, each answered no."""
    window("list-unlink", lambda: dialog._is_unlink_confirmed(dialog._media_list))
    window("list-link", lambda: dialog._is_link_confirmed(2))
    window("list-reload", dialog._is_reload_confirmed)


def _help_boxes(window, dialog):
    """The boxes the Settings dialog's help buttons open; the one about
    MPV's video outputs as each system has it."""
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QWidget

    from gridplayer.params import env

    window("settings-help-cookies", dialog.show_cookies_howto)
    window("settings-help-screenshot-name", dialog.show_screenshot_template_help)

    def on(is_windows, is_macos):
        def open_it():
            saved = env.IS_WINDOWS, env.IS_MACOS
            env.IS_WINDOWS, env.IS_MACOS = is_windows, is_macos

            def put_back():
                env.IS_WINDOWS, env.IS_MACOS = saved

            # the text is picked before the box waits: back at once after
            QTimer.singleShot(0, put_back)
            dialog.show_mpv_output_help()

        return open_it

    for system, is_windows, is_macos in (
        ("windows", True, False),
        ("macos", False, True),
        ("linux", False, False),
    ):
        window(f"settings-help-video-output-{system}", on(is_windows, is_macos))

    for w in dialog.findChildren(QWidget):
        if hasattr(w, "show_wildcard_help"):
            window("settings-help-wildcard", w.show_wildcard_help)
            break


def _reset_questions(window, dialog):
    """What resetting every shortcut asks, answered no: asked only with
    one changed, so it is taken that one is."""
    from gridplayer.widgets.keymap_tree_view import KeymapEditor

    for editor in dialog.findChildren(KeymapEditor):
        tree = editor.tree
        tree.modified_count = lambda: 1
        try:
            window("settings-reset-shortcuts", editor._on_reset_all)
        finally:
            del tree.modified_count


def _add_own_templates():
    """Two grid templates of one's own, so that the menus have them and
    deleting them asks."""
    from gridplayer.models.grid_templates import OwnGridTemplate
    from gridplayer.settings import Settings

    templates = Settings().get(OWN_TEMPLATES_SETTING)
    for name, cols, rows in OWN_TEMPLATES:
        templates = templates.added(OwnGridTemplate(name=name, cols=cols, rows=rows))
    Settings().set(OWN_TEMPLATES_SETTING, templates)


def _grid_templates(d, block, window):
    """Saving a Fixed Grid as a template, a name taken already, and
    deleting one or all of one's own, each answered no."""
    from gridplayer.params.static import GridTemplate

    d.ctx.commands.apply_grid_template(GridTemplate(3, 3, ()))
    d.pump(0.5)
    manager = d.player._managers_inst["grid_templates"]
    window("grid-template", lambda: d.act(block, "Save Grid Template"))
    window(
        "grid-template-replace",
        lambda: manager._confirm_replace(OWN_TEMPLATES[0][0]),
    )
    window("grid-template-delete", lambda: manager.cmd_delete(0))
    window("grid-template-delete-all", manager.cmd_delete_all)


def _snap_words(d, editor, name, capture_layers):
    """The words by the pointer saying what a line or a tile snapped to,
    every one of them, a few at a time as a drag shows them, down the
    middle of the editor: one screen."""
    from types import SimpleNamespace

    from PyQt6.QtCore import QPoint, QRect

    from gridplayer.utils.layout.free_tiles import GuideKind
    from gridplayer.utils.layout.lines import SnapKind, Target
    from gridplayer.widgets.grid_line_mark import (
        GridLineTag,
        snap_word,
        tile_snap_words,
    )

    if editor.is_tiles:
        kinds = list(GuideKind)

        def guides(of):
            return [SimpleNamespace(kind=kind) for kind in of]

        shown = [
            tile_snap_words(guides(kinds[:3]), fits=True),
            tile_snap_words(guides(kinds[3:]), has_gaps=True),
        ]
    else:
        shown = [
            snap_word(Target(0, SnapKind.ALIGNED), True),
            snap_word(Target(0, SnapKind.EVEN), True),
            snap_word(Target(0, SnapKind.FITS, 0), True),
            snap_word(Target(0, SnapKind.FITS, -1), True),
            snap_word(Target(0, SnapKind.FITS, 1), True),
            snap_word(Target(0, SnapKind.FITS, -1), False),
            snap_word(Target(0, SnapKind.FITS, 1), False),
        ]

    room = QRect(editor.mapToGlobal(QPoint(0, 0)), editor.size())
    layers = [(editor, [])]
    tags = []
    for n, text in enumerate(shown):
        tag = GridLineTag(editor)
        at = editor.mapToGlobal(
            QPoint(editor.width() // 2 - 120, SNAP_WORDS_TOP + n * SNAP_WORDS_STEP)
        )
        tag.show_text(text, False, at, room)
        tags.append(tag)
        whole = [0, 0, tag.width(), tag.height()]
        # each word on its own: a few of them are shown together
        layers.append((tag, [{"text": w, "rect": whole} for w in text.split(", ")]))
    d.pump(0.3)
    capture_layers(name, d.player, layers)
    for tag in tags:
        tag.hide()
        tag.deleteLater()
    d.pump(0.1)


def _all_text(d, window, name, capture):
    """A window's scrolled box of rich text (the About box's credits): the
    window made taller, then shot scrolled to each heading not yet seen,
    the rest being names and versions."""
    from PyQt6.QtWidgets import QTextBrowser

    for box in window.findChildren(QTextBrowser):
        if not box.isVisible() or box.verticalScrollBar().maximum() == 0:
            continue
        size = window.size()
        window.resize(size.width(), ROWS_DIALOG_HEIGHT)
        d.pump(0.3)

        doc = box.document()
        layout = doc.documentLayout()
        headings = []
        block = doc.begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0:
                headings.append(layout.blockBoundingRect(block))
            block = block.next()

        bar = box.verticalScrollBar()
        height = box.viewport().height()
        n = 0
        shown_to = -1.0
        for heading in headings:
            if heading.bottom() <= shown_to:
                continue
            bar.setValue(round(heading.top()))
            d.pump(0.2)
            n += 1
            capture(f"{name}-text-{n}", window)
            shown_to = bar.value() + height
        bar.setValue(0)
        window.resize(size)
        d.pump(0.2)


def _status_gallery(d, base, capture):
    """What a cell can say as it loads and when it fails, set on a few
    failed cells by the app's own makers of it, a few states to a screen:
    every kind of error, for a video and for a list, the HTTP statuses,
    and the stages of loading."""
    for cell in list(d.cells):
        d.act(cell, "Close")
    d.pump(0.5)

    # a link failing is tried again, over what is set on its cell here:
    # not for these, last of the run, so no screen shows the setting
    from gridplayer.params.static import NetworkRetryMode

    d.change_setting("video_defaults/network_retry_mode", NetworkRetryMode.OFF)
    d.open(*(f"{base}/broken.mp4?{n}" for n in range(1, GALLERY_CELLS + 1)))

    def failed():
        cells = list(d.cells)
        return len(cells) == GALLERY_CELLS and all(
            c.status.last_error is not None for c in cells
        )

    if not _until(d, failed, 30):
        d.note("the gallery cells did not fail")
        return
    cells = list(d.cells)
    states = _status_states(cells[0])

    for n, start in enumerate(range(0, len(states), GALLERY_CELLS), 1):
        for cell, state in zip(cells, states[start : start + GALLERY_CELLS]):
            state(cell)
        d.pump(0.3)
        capture(f"cells-{n}", d.player)


def _status_states(block) -> list:
    """Each state to set a cell in, a function of the cell: the errors
    one of each title and line, then the loading stages."""
    import dataclasses

    from gridplayer.params.static import ListSourceKind
    from gridplayer.utils.list_errors import ReadError, ReadErrorKind
    from gridplayer.utils.video_errors import (
        empty_link_list_error,
        shown_read_error,
        stream_offline_error,
        unresolved_error,
    )
    from gridplayer.widgets.video_status import LoadStage

    url = f"https://{GALLERY_HOST}/video"
    errors = []
    for kind in ReadErrorKind:
        if kind is ReadErrorKind.HTTP:
            continue
        for is_video, source in (
            (True, ListSourceKind.URL),
            (False, ListSourceKind.URL),
            (False, ListSourceKind.FILE),
        ):
            read = ReadError(
                kind=kind,
                raw="",
                source_kind=source,
                host=GALLERY_HOST,
                limit_mb=10,
            )
            errors.append(shown_read_error(read, is_video=is_video))
    for status in GALLERY_HTTP:
        read = ReadError(
            kind=ReadErrorKind.HTTP, raw="", status=status, host=GALLERY_HOST
        )
        errors.append(shown_read_error(read))
    errors += [
        stream_offline_error(url),
        unresolved_error(url),
        empty_link_list_error(url),
    ]

    said = _recovery_texts(block)

    states = []
    seen = set()
    for error in errors:
        key = (error.title, error.about, error.where, error.code)
        if key in seen:
            continue
        seen.add(key)
        states.append(lambda b, error=error: b.video_status.show_error(error))

    def cant_play(b):
        b.status.last_error = None
        b.status.show_error_card()

    def noted(note):
        error = dataclasses.replace(errors[0])
        return lambda b: b.video_status.show_error(error, note)

    def steps(b):
        b.status.load_steps = (LoadStage.LINK, LoadStage.LIST, LoadStage.VIDEO)
        b.status.show_resolving_link("yt-dlp")

    def reconnect(b):
        b.video_status.show_reconnect(7, 10, said["try_of"])

    def reconnect_no_limit(b):
        b.video_status.show_reconnect(7, 10, said["try"])

    def taking(seconds):
        def state(b):
            b.status.show_opening()
            b.video_status._started_at -= seconds

        return state

    # the player's own words, said by it as it opens a video
    def player_says(text):
        return lambda b: b.status.show_stage(LoadStage.VIDEO, text)

    states += [
        cant_play,
        noted(said["next"]),
        noted(said["previous"]),
        lambda b: b.status.show_opening(),
        lambda b: b.status.on_driver_status("Buffering", 45),
        steps,
        reconnect,
        reconnect_no_limit,
        player_says("Parsing media"),
        player_says("Preparing video output"),
        *(taking(seconds) for seconds in GALLERY_ELAPSED_S),
    ]
    return states


def _recovery_texts(block) -> dict[str, str]:
    """What the recovery part says of its tries and of the count down to
    the next file, made with its counts set for it, then put back."""
    recovery = block.recovery
    kind = type(recovery)
    said = {}

    retry_limit, retries = kind.retry_limit, recovery._retries
    try:
        recovery._retries = 2
        kind.retry_limit = property(lambda self: 5)
        said["try_of"] = recovery._attempt_txt
        kind.retry_limit = property(lambda self: -1)
        said["try"] = recovery._attempt_txt
    finally:
        kind.retry_limit = retry_limit
        recovery._retries = retries

    # running long enough that it is read, not run out
    recovery._skip_timer.start(600_000)
    is_going_back = kind.is_going_back
    try:
        said["next"] = recovery.skip_note()
        kind.is_going_back = property(lambda self: True)
        said["previous"] = recovery.skip_note()
    finally:
        kind.is_going_back = is_going_back
        recovery._skip_timer.stop()

    return said


def _painted_texts(widget, module=None, grabbed=None) -> list[tuple[str, object]]:
    """The texts a widget paints itself (a cell's status), each with where:
    the painter of the module that paints it (video_status's by default)
    recorded while it, or grabbed, is grabbed. A line wrapped in two is
    given as a whole and in parts too (texts_in splits those joined by
    " · ")."""
    from itertools import pairwise

    from PyQt6.QtCore import QRect, QRectF
    from PyQt6.QtGui import QPainter

    if module is None:
        from gridplayer.widgets import video_status as module

    drawn = []

    class Recording(QPainter):
        def drawText(self, *args):
            if len(args) >= 3 and isinstance(args[2], str):
                rect = args[0]
                if isinstance(rect, QRectF):
                    rect = rect.toAlignedRect()
                drawn.append((args[2], QRect(rect)))
            super().drawText(*args)

    painter_class = module.QPainter
    module.QPainter = Recording
    try:
        (grabbed or widget).grab()
    finally:
        module.QPainter = painter_class

    texts = list(drawn)
    for (first, first_at), (second, second_at) in pairwise(drawn):
        texts.append((f"{first} {second}", first_at.united(second_at)))
    return texts


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


def _block_lines(block):
    """A block of rich text cut at its line breaks (<br>), as a translated
    text is one of them: each part's text and its rectangle in the block,
    over the lines it is laid out on."""
    from PyQt6.QtCore import QRect

    text = block.text()
    layout = block.layout()
    start = 0
    for part in text.split(" "):
        end = start + len(part)
        rect = QRect()
        for i in range(layout.lineCount()):
            line = layout.lineAt(i)
            if line.textStart() < end and line.textStart() + line.textLength() > start:
                rect = rect.united(line.rect().toAlignedRect())
        if not rect.isEmpty():
            yield part, rect
        start = end + 1


def texts_in(root) -> list[dict]:
    """The texts drawn by root and its children, each with the part of root
    it is seen in."""
    from PyQt6.QtCore import (
        QAbstractListModel,
        QAbstractTableModel,
        QModelIndex,
        QPoint,
        QRect,
        Qt,
    )
    from PyQt6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QComboBox,
        QGroupBox,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMenu,
        QTabBar,
        QTextEdit,
        QWidget,
    )

    from gridplayer.widgets.settings_controls import SegmentedChoice
    from gridplayer.widgets.video_status import VideoStatus

    found = []

    def add(text, rect, widget, shortcut=False):
        text = _plain(text, shortcut)
        if not text:
            return
        seen = _visible(rect, widget, root)
        if seen is not None and not seen.isEmpty():
            where = [seen.x(), seen.y(), seen.width(), seen.height()]
            found.append({"text": text, "rect": where})
            # "Bookmarks: 3 · Files: 2": strings of their own, joined
            if " · " in text:
                found.extend(
                    {"text": part, "rect": where} for part in text.split(" · ")
                )

    if isinstance(root, QMenu):
        for action in root.actions():
            if action.isVisible() and not action.isSeparator():
                rect = root.actionGeometry(action)
                add(action.text(), rect, root, shortcut=True)
                # "Delay: 0 ms", "Load Snapshot (3)": the name alone too
                for name in _named(_plain(action.text(), shortcut=True)):
                    add(name, rect, root)
        return found

    for w in [root, *root.findChildren(QWidget)]:
        if not w.isVisible():
            continue
        whole = QRect(0, 0, w.width(), w.height())
        if isinstance(w, QLabel):
            add(w.text(), whole, w)
        elif isinstance(w, QAbstractButton):
            add(w.text(), whole, w, shortcut=True)
        elif isinstance(w, QGroupBox):
            add(w.title(), QRect(0, 0, w.width(), 24), w)
        elif isinstance(w, QLineEdit):
            add(w.placeholderText(), whole, w)
        elif isinstance(w, QComboBox):
            add(w.currentText(), whole, w)
        elif isinstance(w, VideoStatus):
            for text, rect in _painted_texts(w):
                add(text, rect, w)
        elif isinstance(w, SegmentedChoice):
            # drawn, not buttons: each text in its segment; an icon's text
            # is its tip
            for segment, (text, _), icon in zip(
                w._segments(), w._items, w._icons, strict=True
            ):
                if icon is None:
                    add(text, segment.toAlignedRect(), w)
        elif isinstance(w, QHeaderView):
            # before item views, which headers are too
            model = w.model()
            if model is None:
                continue
            for i in range(w.count()):
                if w.isSectionHidden(i):
                    continue
                text = model.headerData(i, w.orientation(), Qt.ItemDataRole.DisplayRole)
                at, length = w.sectionViewportPosition(i), w.sectionSize(i)
                if w.orientation() == Qt.Orientation.Horizontal:
                    rect = QRect(at, 0, length, w.height())
                else:
                    rect = QRect(0, at, w.width(), length)
                add(text, rect, w.viewport())
        elif isinstance(w, QTextEdit):
            # each paragraph, or table cell, of rich text where it is
            doc = w.document()
            layout = doc.documentLayout()
            dx = w.horizontalScrollBar().value()
            dy = w.verticalScrollBar().value()
            block = doc.begin()
            while block.isValid():
                top_left = layout.blockBoundingRect(block).topLeft().toPoint()
                for text, rect in _block_lines(block):
                    rect.translate(top_left - QPoint(dx, dy))
                    add(text, rect, w.viewport())
                block = block.next()
        elif isinstance(w, QTabBar):
            for i in range(w.count()):
                add(w.tabText(i), w.tabRect(i), w)
        elif isinstance(w, QAbstractItemView) and w.model() is not None:
            viewport = w.viewport()

            # what the list paints itself: a word on an empty one, marks
            # across its rows
            module = sys.modules.get(type(w).__module__)
            if module is not None and hasattr(module, "QPainter"):
                for text, rect in _painted_texts(w, module, viewport):
                    add(text, rect, viewport)

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
# where a text breaks into lines, plain or rich
_BREAK = re.compile(r"\n|<br\s*/?>", re.IGNORECASE)


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


_NAMED = (re.compile(r"^(.+?): \S.*$"), re.compile(r"^(.+?) \(\d+\)$"))


def _named(text: str) -> list[str]:
    """The name of a menu item that shows a value after it."""
    return [m.group(1) for pattern in _NAMED if (m := pattern.match(text))]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", _plain(text)).strip("-").lower()
