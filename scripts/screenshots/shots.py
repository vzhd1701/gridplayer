"""The screenshots of the README and the stores, taken of the real app on a
GNOME desktop (see make.sh, which runs this once a shot):

    SHOT=1 uv run python -m tests.real_app.run scripts/screenshots/shots.py --out DIR

The videos are those of SHOTS_MEDIA (build/screenshot-media by default, as
get_clips.sh makes them): wide/ and mixed/ (of every shape), each taken in
name order and shown AT_S seconds in, paused.

Flathub asks for the window as the desktop draws it, frame and shadow and
all, so the shots are GNOME Shell's own: a screenshot of the player's window.
A menu or a dialog over it is a window of its own, which that leaves out:
then what is inside the frame comes from a screenshot of the screen there.
"""

import os
from pathlib import Path

# the driver puts the app off the desktop's bus as it starts, after this is read
SESSION_BUS = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")

MEDIA = Path(os.environ.get("SHOTS_MEDIA", "build/screenshot-media"))
SHOT = int(os.environ.get("SHOT", "1"))
AT_S = float(os.environ.get("AT_S", "15"))

# The window, frame included, the same in every shot: as big as Flathub asks
# for. A video's menu is taller than that; shot 2 shows the window's.
WINDOW_SIZE = (1000, 700)

SETTINGS = {
    # the app as it comes, where the driver has its own for tests: the
    # Settings shot marks any other value as changed
    "player/video_driver": "mpv_hw",
    "player/one_instance": True,
}

# shot 4: the layout (see LAYOUTS), and whether each tile shows its name
LAYOUT = os.environ.get("LAYOUT", "fit_reorder")
NAMES = os.environ.get("NAMES", "1") == "1"

# Rename's colours, for the names in shot 4
MIXED_COLORS = ("#2e8b57", "#c0392b", "#2c3e50", "#8e44ad", "#d35400", "#2980b9")


def scenario(d):
    desktop = Desktop()

    d.check("the desktop's scale is 1", d.player.devicePixelRatio() == 1)
    _place_window(d)

    SHOTS[SHOT](d, desktop)


# -- the shots


def shot_grid(d, desktop):
    """Main window with 4 videos playing"""

    cells = _open(d, _videos("wide")[:4])
    _overlays(d, cells, [cells[0]])

    _save(d, desktop.window(d), 1)


def shot_menu(d, desktop):
    """Context menu"""

    from PyQt6.QtCore import QPoint, QTimer
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtWidgets import QApplication

    cells = _open(d, _videos("wide")[: len(FREE_TILES)])

    # Free Tiles, placed by hand, with room between them: the menu of the
    # window, asked for there, is shorter than a video's
    d.act(cells[0], "Free Tiles")
    _place_tiles(d, cells)

    _overlays(d, cells, [])
    framed = desktop.window(d)

    grid = d.player._managers_inst["grid"]
    # the widget the tiles are laid out in, and where in it they are
    area, rect = grid.parent(), grid._grid.geometry()
    where = area.mapToGlobal(
        rect.topLeft()
        + QPoint(int(rect.width() * MENU_AT[0]), int(rect.height() * MENU_AT[1]))
    )
    d.check("the menu is asked for between the tiles", grid.get_cell_at(where) is None)
    # no video under the pointer, none the menu is about
    d.ctx.active_block = None

    def look():
        menu = QApplication.activePopupWidget()
        if menu is None:
            QTimer.singleShot(100, look)
            return
        d.pump(0.5)
        _save(d, desktop.over(d, framed, menu), 2)
        menu.close()

    QTimer.singleShot(500, look)
    QApplication.sendEvent(
        area,
        QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, area.mapFromGlobal(where), where
        ),
    )


# Shot 2's tiles, in the order the videos are, the last in front: where each
# goes across and down, and how wide, as shares of the window's width and
# height; as tall as the video's shape says
FREE_TILES = (
    (0.02, 0.03, 0.44),
    (0.02, 0.43, 0.30),
    (0.02, 0.71, 0.30),
    (0.33, 0.36, 0.37),
    (0.36, 0.70, 0.34),
)
# where the menu is asked for: on the room left to the right of them
MENU_AT = (0.725, 0.04)


def _place_tiles(d, cells) -> None:
    from gridplayer.utils.layout.free_tiles import Rect

    grid = d.player._managers_inst["grid"]
    width, height = grid._area_size()

    # the page the window's area, as after a tile is moved
    grid._free.fill(width, height)
    for block, (left, top, share) in zip(cells, FREE_TILES):
        x, y, w = left * width, top * height, share * width
        h = w / block.picture_shape
        grid._free.set_rect(block.video_id, Rect(x, y, x + w, y + h), width, height)
        # the last in front
        grid._free.stack(block.video_id, True)

    grid._is_arranged = False
    grid._grid.invalidate()
    grid.layout_changed.emit()
    d.pump(1.5)


def shot_settings(d, desktop):
    """Settings window"""

    from PyQt6.QtCore import QTimer

    cells = _open(d, _videos("wide")[:6])
    _overlays(d, cells, [])

    framed = desktop.window(d)
    before = set(d.windows())

    def look():
        dialogs = [w for w in d.windows() if w not in before]
        if not dialogs:
            QTimer.singleShot(100, look)
            return
        dialog = dialogs[-1]

        # the desktop centres it on the window, frame and all: on the
        # pictures instead, a little smaller if need be
        client = d.player.geometry()
        frame = dialog.frameGeometry().size() - dialog.geometry().size()
        dialog.resize(
            min(dialog.width(), client.width() - frame.width() - 80),
            min(dialog.height(), client.height() - frame.height() - 40),
        )
        dialog.move(
            client.x() + (client.width() - dialog.frameGeometry().width()) // 2,
            client.y() + (client.height() - dialog.frameGeometry().height()) // 2,
        )
        d.pump(1)
        _save(d, desktop.over(d, framed, dialog), 3)
        dialog.reject()

    QTimer.singleShot(500, look)
    d.act(cells[0], "Settings")


def shot_mixed(d, desktop):
    """Videos of different shapes, each shown whole"""

    from pydantic_extra_types.color import Color

    cells = _open(d, _videos("mixed"))

    for action in LAYOUTS[LAYOUT]:
        d.act(cells[0], action)
    # the tiles moved to their places, Mosaic's gliding there
    d.pump(2)

    shown = []
    if NAMES:
        # named and coloured as Rename does it
        for block, color in zip(cells, MIXED_COLORS):
            block.video_params.color = Color(color)
            block.video_params.title = Path(str(block.video_params.uri)).stem
            block.title = block.video_params.title
            block.color = block.video_params.color.as_hex()
        shown = cells

    _overlays(d, cells, shown)

    _save(d, desktop.window(d), 4)


# what shot 4 shows the mixed shapes in: the menu's actions to choose it
LAYOUTS = {
    "fit": ["Fit Shapes"],
    "fit_reorder": ["Fit Shapes", "Reorder to Fit"],
    "mosaic": ["Mosaic"],
    "auto": [],
}

SHOTS = {1: shot_grid, 2: shot_menu, 3: shot_settings, 4: shot_mixed}


# -- the app


def _videos(kind: str) -> list[Path]:
    folder = MEDIA / kind
    videos = sorted(p for p in folder.glob("*") if p.is_file())

    if not videos:
        raise RuntimeError(f"no videos in {folder}: see get_clips.sh")

    return videos


def _place_window(d) -> None:
    """The window at WINDOW_SIZE, frame included, in the middle of the
    screen."""

    player = d.player

    d.wait_until(
        lambda: player.frameGeometry().height() > player.geometry().height(),
        "the window has its frame",
    )

    frame = player.frameGeometry().size() - player.geometry().size()
    width, height = WINDOW_SIZE
    player.resize(width - frame.width(), height - frame.height())

    screen = player.screen().availableGeometry()
    player.move(
        screen.x() + (screen.width() - width) // 2,
        screen.y() + (screen.height() - height) // 2,
    )
    d.pump(1)


def _open(d, videos: list[Path]) -> list:
    d.open(*videos)

    cells = [d.wait_for_cell(video.name) for video in videos]
    at_ms = int(AT_S * 1000)

    for block in cells:
        block.set_pause(True)
        block.seek(at_ms)

    for block in cells:
        d.wait_until(
            lambda b=block: abs(b.time - at_ms) < 200, f"{_name(block)} at {AT_S}s"
        )

    # the pictures painted, the grid settled
    d.pump(1.5)

    return cells


def _name(block) -> str:
    return Path(str(block.video_params.uri)).name


def _overlays(d, cells, shown) -> None:
    for block in cells:
        if block not in shown:
            block.overlay.hide()

    for block in shown:
        block.show_overlay()

    d.pump(0.5)


def _save(d, image, number: int) -> None:
    path = d.out / f"screenshot-{number:03d}.png"
    image.save(str(path))
    d.check(f"saved {path.name}", path.exists(), f"{image.width()}x{image.height()}")


# -- the desktop


class Desktop:
    """GNOME Shell's screenshots, of a window or of a part of the screen."""

    def __init__(self):
        from PyQt6.QtDBus import QDBusConnection, QDBusInterface

        if not SESSION_BUS:
            raise RuntimeError("no desktop session: run this inside GNOME")

        self._bus = QDBusConnection.connectToBus(SESSION_BUS, "screenshots")

        # GNOME Shell takes screenshots only for its own tools: this is the
        # name of its Screenshot tool
        if not self._bus.registerService("org.gnome.Screenshot"):
            raise RuntimeError("org.gnome.Screenshot is taken: close GNOME Screenshot")

        self._shell = QDBusInterface(
            "org.gnome.Shell.Screenshot",
            "/org/gnome/Shell/Screenshot",
            "org.gnome.Shell.Screenshot",
            self._bus,
        )
        self._taken = 0

    def window(self, d):
        """The player's window, frame and shadow and all."""

        d.player.raise_()
        d.player.activateWindow()
        d.pump(0.5)

        image = self._take(d, "ScreenshotWindow", True, False, False)

        # the shot is of whichever window has the focus
        frame = _opaque_rect(image)
        d.check(
            "the window shot is the player's",
            frame.size() == d.player.frameGeometry().size(),
            f"{frame.size()} for a window of {d.player.frameGeometry().size()}",
        )

        return image

    def over(self, d, framed, window):
        """framed (a window shot of the player) with what is on the screen
        inside its frame now: window, a menu or a dialog over it, which a
        window shot leaves out."""

        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QImage, QPainter

        player = d.player
        frame = _opaque_rect(framed)
        on_screen = player.frameGeometry().topLeft() - frame.topLeft()

        area = self._take(
            d,
            "ScreenshotArea",
            on_screen.x(),
            on_screen.y(),
            framed.width(),
            framed.height(),
            False,
        )

        inside = window.frameGeometry()
        client = player.geometry().translated(-on_screen)
        d.check(
            f"the {type(window).__name__} is inside the window",
            player.geometry().contains(inside),
            f"{inside} in {player.geometry()}",
        )

        image = framed.convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        # the frame as the window shot has it: the player's, focused
        painter.setClipRect(QRect(client))
        painter.drawImage(0, 0, area)
        painter.end()

        return image

    def _take(self, d, method, *args):
        from PyQt6.QtGui import QImage

        self._taken += 1
        # GNOME Shell puts a relative one in ~/Pictures
        path = (d.out / f"desktop-{self._taken}.png").resolve()

        reply = self._shell.call(method, *args, str(path))
        ok = bool(reply.arguments()) and reply.arguments()[0] is True

        if not ok:
            raise RuntimeError(f"{method}: {reply.errorMessage() or reply.arguments()}")

        return QImage(str(path))


def _opaque_rect(image):
    """Where the window is in a window shot: what is not its shadow."""

    from PyQt6.QtCore import QRect

    def opaque(x, y):
        return image.pixelColor(x, y).alpha() == 255

    w, h = image.width(), image.height()
    mid_x, mid_y = w // 2, h // 2

    left = next(x for x in range(w) if opaque(x, mid_y))
    right = next(x for x in reversed(range(w)) if opaque(x, mid_y))
    top = next(y for y in range(h) if opaque(mid_x, y))
    bottom = next(y for y in reversed(range(h)) if opaque(mid_x, y))

    return QRect(left, top, right - left + 1, bottom - top + 1)
