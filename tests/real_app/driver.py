"""The real player, driven the way a viewer drives it: through its menus.

A scenario is a function that takes a Driver; tests/real_app/run.py starts
the app in a process of its own and hands it one. Everything here runs in
that process. See AGENTS.md, "Driving the real app".
"""

import json
import logging
import os
import sys
import threading
import time
import traceback
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.real_app.media import Media

_log = logging.getLogger("real_app")

# The app's own defaults that a driven run cannot live with
DEFAULT_SETTINGS = {
    # nobody is there to answer "save the playlist?"
    "playlist/unsaved_changes": "discard",
    # Hardware video draws into an X11 window, which offscreen has none of
    "player/video_driver": "vlc_sw_sp",
    "player/one_instance": False,
}


class Driver:
    def __init__(self, app, player, media: Media, out: Path):
        self.app = app
        self.player = player
        self.ctx = player._context
        self.media = media
        self.out = out
        self.steps: list[dict] = []
        self.failures: list[str] = []
        self.errors: list[str] = []
        self._servers: list[ThreadingHTTPServer] = []

    # -- time

    def pump(self, seconds: float = 0.05) -> None:
        """Let the app run for a while: its timers, VLC's callbacks, paints."""

        from PyQt5.QtCore import QEventLoop

        deadline = time.monotonic() + seconds
        while True:
            self.app.processEvents(QEventLoop.AllEvents, 20)
            left = deadline - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(left, 0.01))

    wait = pump

    def wait_until(self, predicate, what: str, timeout: float = 20) -> bool:
        """Run the app until predicate() is true; a failure if it never is.

        An exception from the predicate counts as not yet: the cell it asks
        about may not be there, or not have loaded.
        """

        deadline = time.monotonic() + timeout
        started = time.monotonic()

        while time.monotonic() < deadline:
            try:
                if predicate():
                    self._step(f"waited {time.monotonic() - started:.1f}s: {what}")
                    return True
            except Exception:
                pass
            self.pump(0.05)

        self.fail(f"gave up after {timeout}s waiting until {what}")
        return False

    # -- cells

    def open(self, *uris) -> None:
        """Open each as a cell of its own, as from the command line."""

        self._step(f"open {', '.join(map(str, uris))}")
        self.player.process_arguments([str(uri) for uri in uris])

    @property
    def cells(self) -> list:
        return list(self.ctx.video_blocks)

    def cell(self, name: str):
        """The first cell playing something with this in its link or path,
        or reading a list with it in its path."""

        for block in self.cells:
            if name in str(block.video_params.uri) or name in str(block.media_list):
                return block

        raise LookupError(f"no cell has {name!r}")

    def wait_for_cell(self, name: str, timeout: float = 30):
        """The cell once it is playing."""

        self.wait_until(lambda: self.cell(name).is_playable, f"{name} plays", timeout)
        return self.cell(name)

    # -- doing things

    def act(self, block, action: str) -> None:
        """Choose a menu item or press its key: an action of params/actions.py,
        by its name there, for this cell."""

        self.ctx.active_block = block
        item = self.ctx.actions[action]
        self._step(f"action {action!r}", enabled=item.is_enabled)
        item.trigger()
        self.pump()

    def run(self, block, *command):
        """Run a command as the menus name it: ("active", "loop.reset")."""

        self.ctx.active_block = block
        self._step(f"command {command!r}")
        result = self.ctx.commands.resolve(command)()
        self.pump()
        return result

    def menu(self, block, generator: str) -> list[str]:
        """The titles of a menu made as it is opened, as the viewer sees it:
        "menu_generator_audio_track" and the like in ActiveBlockManager."""

        titles = [title for title, _ in self._menu(block, generator)]
        self._step(f"menu {generator}", items=titles)
        return titles

    def choose(self, block, generator: str, title: str, timeout: float = 10) -> bool:
        """Click the item of such a menu with this title, or else the first
        with it in its title.

        Waits for it to be there: tracks, sizes and languages are listed
        only once the video has loaded, and a choice of some of them
        reloads it.
        """

        deadline = time.monotonic() + timeout

        while True:
            entries = [(t, item) for t, item in self._menu(block, generator) if item]
            chosen = next((item for t, item in entries if t == title), None) or next(
                (item for t, item in entries if title in t), None
            )
            if chosen is not None or time.monotonic() > deadline:
                break
            self.pump(0.1)

        if chosen is None:
            self.fail(f"no {title!r} in {generator}: {[t for t, _ in entries]}")
            return False

        self.ctx.active_block = block
        self._step(f"choose {title!r} in {generator}")
        self.ctx.commands.resolve(chosen["func"])()
        self.pump()
        return True

    def _menu(self, block, generator):
        self.ctx.active_block = block

        for template in self.ctx.commands.resolve(generator)():
            if not isinstance(template, dict):
                yield str(template), None
                continue
            title = template.get("title")
            if isinstance(title, tuple):
                title = title[0]
            yield str(title), template if template.get("func") else None

    def windows(self) -> list:
        """The windows open besides the player."""

        from PyQt5.QtWidgets import QApplication

        return [
            w
            for w in QApplication.topLevelWidgets()
            if w.isVisible() and w is not self.player and w.isWindow()
        ]

    def through_modal(self, open_it, name: str, inspect=None) -> None:
        """Open a window that holds everything until it is closed, such as an
        error's Details: look at it (a screenshot, then inspect(window)) and
        close it from inside, since open_it only returns once it is."""

        from PyQt5.QtCore import QTimer

        seen = []

        def look():
            windows = self.windows()
            if not windows:
                QTimer.singleShot(100, look)
                return
            window = windows[-1]
            seen.append(type(window).__name__)
            self.shot(name, window)
            if inspect is not None:
                try:
                    inspect(window)
                except Exception:
                    self.error(*sys.exc_info())
            window.close()

        QTimer.singleShot(500, look)
        open_it()
        # one that does not hold everything has returned already
        self.wait_until(lambda: seen, f"{name} is open", timeout=10)
        self._step(f"window {name}", windows=seen)

    # -- looking

    def state(self, block) -> dict:
        """What a viewer could tell of a cell, and a little more."""

        return {key: _read(block, read) for key, read in STATE.items()}

    def note(self, label: str, block=None) -> dict:
        """Write down a cell's state, or every cell's, as a step."""

        if block is not None:
            state = self.state(block)
            self._step(label, state=state)
            return state

        cells = [self.state(b) for b in self.cells]
        self._step(label, cells=cells)
        return cells

    def shot(self, name: str, widget=None) -> Path:
        path = self.out / f"{name}.png"
        (widget or self.player).grab().save(str(path))
        self._step(f"screenshot {path.name}")
        return path

    # -- judging

    def check(self, what: str, ok, detail=None) -> bool:
        """A soft assert: the run goes on, and fails at the end."""

        self._step(f"check {what}", ok=bool(ok), detail=detail)
        if not ok:
            self.fail(f"{what}" + (f": {detail}" if detail is not None else ""))
        return bool(ok)

    def fail(self, message: str) -> None:
        self.failures.append(message)
        self._step(f"FAILED {message}")

    def error(self, kind, value, tb) -> None:
        text = "".join(traceback.format_exception(kind, value, tb))
        self.errors.append(text)
        self._step(f"ERROR {kind.__name__}: {value}")

    # -- what a run needs from outside

    def serve(self, directory: Path) -> str:
        """Serve a folder over HTTP on a port of its own; the base URL."""

        handler = partial(_QuietHandler, directory=str(directory))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self._servers.append(server)

        return f"http://127.0.0.1:{server.server_address[1]}"

    def fake_sponsorblock(self, block, segments, video_id="aaaaaaaaaaa") -> None:
        """Have SponsorBlock answer for this cell, with these segments.

        Asking it takes a YouTube video and the internet; this makes the
        cell's video one, with a made-up id, and answers the lookup here.
        """

        import gridplayer.utils.sponsorblock as sponsorblock

        sponsorblock.fetch_segments = lambda _id, _length: tuple(segments)

        block._youtube_id = video_id
        block._site_length_ms = block.video_driver.length
        self._step(f"fake SponsorBlock: {len(segments)} segment(s)")
        block.sponsorblock.look_up()
        self.pump()

    # -- the record

    def _step(self, label: str, **details) -> None:
        entry = {"t": round(time.monotonic() - _STARTED, 2), "step": label, **details}
        self.steps.append(entry)
        print(json.dumps(entry, default=str), flush=True)

    def report(self) -> dict:
        return {
            "ok": not self.failures and not self.errors,
            "failures": self.failures,
            "errors": self.errors,
            "steps": self.steps,
        }

    def close(self) -> None:
        for server in self._servers:
            server.shutdown()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _read(block, read):
    try:
        value = read(block)
    except Exception as e:
        return f"<{type(e).__name__}: {e}>"

    if isinstance(value, (bool, int, float, str, type(None))):
        return value
    if isinstance(value, Path):
        return value.name
    if isinstance(value, (list, tuple)) and all(isinstance(v, Path) for v in value):
        return [v.name for v in value]
    return str(value)


def _title_of(error):
    return None if error is None else error.title


STATE = {
    "uri": lambda b: str(b.video_params.uri),
    "title": lambda b: b.title,
    "playable": lambda b: b.is_playable,
    "paused": lambda b: b.video_params.is_paused,
    "time": lambda b: b.time,
    "length": lambda b: b.video_driver.length,
    "error": lambda b: b.is_error,
    "last_error": lambda b: _title_of(b.status.last_error),
    "stage": lambda b: b.status.load_stage,
    "retries": lambda b: b.recovery.retries,
    "loop": lambda b: (b.loop_start, b.loop_end),
    "list_place": lambda b: b.navigation.list_place_txt,
    "muted": lambda b: b.video_params.is_muted,
    "volume": lambda b: b.video_params.volume,
    "scale": lambda b: b.video_params.scale,
    "chapter": lambda b: b.chapters.playing,
    "audio_playing": lambda b: b.audio.track_playing,
    "audio_delay_ms": lambda b: b.video_params.audio_delay_ms,
    "external_audio": lambda b: list(b.video_params.external_audio),
    "subtitle_showing": lambda b: b.subtitles.track_showing,
    "subtitle_delay_ms": lambda b: b.video_params.subtitle_delay_ms,
    "streams": lambda b: len(b.streams),
    "quality": lambda b: b.stream.quality_playing,
    "languages": lambda b: b.stream.audio_language_options,
    "language": lambda b: b.stream.audio_language_playing,
}

_STARTED = time.monotonic()


def start(media: Media, out: Path, settings: dict) -> Driver:
    """The app, as run.py starts it: offscreen, with settings and data of its
    own under out, and these settings over the defaults above."""

    home = out / "home"
    os.environ["GP_USER_DATA_DIR"] = str(home / "data")
    os.environ["XDG_DATA_HOME"] = str(home / "data")
    os.environ["XDG_CONFIG_HOME"] = str(home / "config")
    os.environ["XDG_CACHE_HOME"] = str(home / "cache")
    os.environ["XDG_RUNTIME_DIR"] = str(home / "runtime")
    Path(os.environ["XDG_RUNTIME_DIR"]).mkdir(parents=True, mode=0o700)
    # no desktop to talk to: no media keys, no dark mode portal waits
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/nonexistent/gridplayer-run"

    logging.basicConfig(
        filename=out / "app.log",
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from gridplayer.main.init_app import init_app
    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.params import env
    from gridplayer.settings import Settings
    from gridplayer.utils.libvlc import init_vlc

    # the app picks xcb itself whenever there is no Wayland, whatever
    # QT_QPA_PLATFORM says
    env.QT_PLATFORM = "offscreen"

    init_app_env()
    app = init_app()
    env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()

    store = Settings()
    for key, value in {
        **DEFAULT_SETTINGS,
        "screenshots/dir": str(out / "screenshots"),
        **settings,
    }.items():
        store.set(key, _setting_value(key, value))

    from gridplayer.player import Player

    player = Player()
    app.installEventFilter(player)
    player.resize(1280, 720)
    player.show()

    return Driver(app, player, media, out)


def _setting_value(key, value):
    """A setting as the app keeps it: an enum's member from its value, so a
    scenario can say "discard" rather than import UnsavedChangesMode."""

    from enum import Enum

    from gridplayer.settings import _default_settings

    default = _default_settings.get(key)

    if isinstance(default, Enum) and not isinstance(value, Enum):
        return type(default)(value)

    return value
