"""A stream that stops partway through, which neither player says: its link refused from
then on, VLC tries again once a minute and MPV plays out what it has, the picture held.
Stopped, it's loaded again from where it was: within 10 s of the proxy being turned away,
else after the buffering timeout. VLC with a file whose connection was cut asks for no
more of it, and crept on, 1.8 s in two minutes. Refused for good, the cell says why.

A file the proxy fetches for the player, as of a site. Asked for all of it at once, it's
sent no faster than a few times as it plays, or the player would have it all before
anything went wrong."""

import threading
import time
from pathlib import Path

from gridplayer.models.stream import (
    STREAM_QUALITY_BEST,
    HashableDict,
    Stream,
    Streams,
    StreamSessionOpts,
)
from tests.real_app.driver import RangesHandler

SETTINGS = {
    "video_defaults/network_retry_mode": "times",
    "video_defaults/network_retry_times": 1,
    # for the reload of a link refused for good
    "player/video_init_timeout": 10,
    # for VLC, which the proxy has no word from
    "network/buffering_timeout": 15,
}

FILE = "feature.mkv"
FILE_LENGTH_S = 60

# how much faster than it plays the whole file is sent
SENT_FASTER = 3

PLAYED_BEFORE_MS = 6_000

# from it being seen to stop: the buffering timeout, less the time that took
STALL_TOLD_IN_S = 20
# what a player has, sent faster than it plays, at most, from where it plays
PLAYED_OUT_S = 30

HANGING_TIMEOUT_S = 8


class _Link:
    """What the server is doing with the link: serving, refusing or hanging."""

    SERVING, REFUSING, HANGING = "serving", "refusing", "hanging"

    def __init__(self, files: Path, length_s: float):
        self.state = self.SERVING
        self.refused = 0
        self.bytes_per_s = (files / FILE).stat().st_size / length_s


class _Server(RangesHandler):
    link: _Link

    def do_GET(self):
        link = self.link

        if link.state == _Link.HANGING:
            while link.state == _Link.HANGING:
                time.sleep(0.1)

        if link.state == _Link.REFUSING:
            link.refused += 1
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # paced for this one only: the connection is kept for the next
        raw = self.wfile

        try:
            super().do_GET()
        finally:
            self.wfile = raw

    def end_headers(self):
        super().end_headers()

        # the whole of it asked for: sent at a pace, and cut off as the link goes
        if (self.headers.get("Range") or "bytes=0-").endswith("-"):
            self.wfile = _Paced(self.wfile, self.link, self.link.bytes_per_s)


class _Paced:
    CHUNK = 16384

    def __init__(self, raw, link: _Link, bytes_per_s: float):
        self._raw = raw
        self._link = link
        self._wait_s = self.CHUNK / (bytes_per_s * SENT_FASTER)

    def write(self, data):
        for at in range(0, len(data), self.CHUNK):
            if self._link.state != _Link.SERVING:
                raise ConnectionAbortedError("the link went")

            self._raw.write(data[at : at + self.CHUNK])
            time.sleep(self._wait_s)

        return len(data)

    def __getattr__(self, name):
        return getattr(self._raw, name)


def scenario(d):
    files = d.media.feature.parent
    length_s = FILE_LENGTH_S

    link = _Link(files, length_s)
    base = d.serve_with_ranges(files, type("_ThisServer", (_Server,), {"link": link}))

    d.open(f"{base}/{FILE}")
    cell = d.wait_for_cell(FILE)

    _play_as_a_site_file(d, cell, base, length_s)

    _stops(d, cell, link, _Link.REFUSING)
    d.check(
        "refused for good, it says why",
        d.wait_until(lambda: cell.is_error, "the error", timeout=STALL_TOLD_IN_S + 10)
        and cell.status.last_error is not None
        and cell.status.last_error.title == "Access denied",
        cell.status.last_error,
    )
    d.shot("refused")

    link.state = _Link.SERVING
    _play_as_a_site_file(d, cell, base, length_s)

    # Waited for from the refusal: the proxy can tell of it before the player has
    # played out what it had, and the reload can come and go before it's seen to stop.
    link.state = _Link.REFUSING
    d.note("the link is refusing", cell)

    # where it had got to before the reload, which may start it over
    played_to = [cell.time]

    def is_loaded_again():
        if cell.recovery.retries > 0:
            return True

        played_to[0] = max(played_to[0], cell.time or 0)
        return False

    d.check(
        "stopped, it's loaded again",
        d.wait_until(
            is_loaded_again,
            "loaded again",
            timeout=PLAYED_OUT_S + STALL_TOLD_IN_S,
        ),
    )
    stopped_at = played_to[0]
    d.note(f"stopped at {stopped_at}")

    # the link renewed as it's loaded again, as a YouTube one that ran out is. It's
    # the link the cell was opened with, the server's own, that's played.
    link.state = _Link.SERVING
    d.check(
        "and plays on from there",
        d.wait_until(
            lambda: cell.is_playable and cell.time > stopped_at + 2000,
            "plays on",
            timeout=60,
        )
        and not cell.is_error,
        cell.time,
    )

    # hanging, with nothing to say why: the buffering timeout
    d.change_setting("network/buffering_timeout", HANGING_TIMEOUT_S)

    hung_at = time.monotonic()
    _stops(d, cell, link, _Link.HANGING)
    d.check(
        "hanging, it's loaded again after the buffering timeout",
        d.wait_until(
            lambda: cell.recovery.retries > 0 or cell.is_error,
            "loaded again",
            timeout=60,
        ),
        f"{time.monotonic() - hung_at:.0f} s after the link hung",
    )

    # let go of the requests still hanging
    link.state = _Link.REFUSING
    threading.Event().wait(0.5)

    d.note("end", cell)


def _play_as_a_site_file(d, cell, base: str, length_s: float) -> None:
    cell.streams = Streams(
        {
            "best": Stream(
                url=f"{base}/{FILE}",
                protocol="http",
                session=StreamSessionOpts(
                    service="here", session_headers=HashableDict({"User-Agent": "here"})
                ),
                duration=length_s,
            )
        }
    )
    cell.reset(is_link_kept=True)
    cell.stream.load_quality(STREAM_QUALITY_BEST)

    d.wait_until(
        lambda: cell.is_playable and cell.time > PLAYED_BEFORE_MS,
        "plays a while",
        timeout=60,
    )


def _stops(d, cell, link: _Link, state: str) -> int:
    """Where it was once it stopped moving, the link gone this way."""

    link.state = state
    d.note(f"the link is {state}", cell)

    last = [cell.time, time.monotonic()]

    def has_stopped():
        if cell.time != last[0]:
            last[:] = [cell.time, time.monotonic()]

        return time.monotonic() - last[1] > 2

    d.wait_until(has_stopped, "it stops", timeout=120)
    d.note("stopped", cell)

    return last[0]
