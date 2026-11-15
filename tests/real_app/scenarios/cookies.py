"""Links of a server that wants a cookie for everything, the cookie in the app's
cookies.txt: a file and an HLS stream with its sound apart play, every request of
theirs having it. The proxy fetches them, as no player can be told a cookie."""

import threading

from gridplayer.utils.cookies import cookie_store
from tests.real_app.driver import QuietHandler, RangesHandler

SETTINGS = {
    # yt-dlp reads each rendition, and hands the sound over apart
    "streaming/resolver_priority": "yt_dlp",
}

COOKIE = "gp_test=yes"

# Netscape's format; every test server is on this address, whatever its port
COOKIES_TXT = (
    "# Netscape HTTP Cookie File\n127.0.0.1\tFALSE\t/\tFALSE\t0\tgp_test\tyes\n"
)

_refused: list[str] = []
_had_it: list[str] = []
_lock = threading.Lock()


def _with_cookie(handler):
    class _Handler(handler):
        def do_GET(self):
            name = self.path.partition("?")[0]
            cookies = self.headers.get("Cookie") or ""

            with _lock:
                if COOKIE not in cookies.split("; "):
                    _refused.append(name)
                    self.send_error(403)
                    return

                _had_it.append(name)

            super().do_GET()

    return _Handler


def scenario(d):
    cookie_store().path.write_text(COOKIES_TXT, encoding="utf-8")

    d.open(f"{d.serve_with_ranges(d.media.folder, _with_cookie(RangesHandler))}/a.mp4")
    file_cell = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: file_cell.time > 2000, "the file plays on")

    d.open(f"{d.serve(d.media.dubs, _with_cookie(QuietHandler))}/master.m3u8")
    stream_cell = d.wait_for_cell("master.m3u8")
    d.wait_until(lambda: stream_cell.time > 2000, "the stream plays on")
    d.wait_until(
        lambda: stream_cell.video_driver.media.cur_audio_track is not None,
        "with its sound",
    )

    with _lock:
        refused, had_it = list(_refused), list(_had_it)

    d.check("nothing asked for without the cookie", not refused, refused)
    d.check(
        "the stream's sound fetched with it",
        any(name.startswith(("/venglish/", "/vspanish/")) for name in had_it),
        had_it,
    )
    d.check("the stream's segments too", any(name.endswith(".ts") for name in had_it))
