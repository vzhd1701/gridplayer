"""How a link that won't play is told, and a list going on past it, whichever driver:
a file that's no video, one that can't be read for want of a server that can seek, a
list's own headers reaching the server, and the next item of a list."""

import time
from pathlib import Path

from gridplayer.params.static import ListFailAction
from tests.real_app.driver import RangesHandler

SETTINGS = {
    "video_defaults/network_retry_mode": "times",
    "video_defaults/network_retry_times": 1,
    # for the link that never answers the player
    "player/video_init_timeout": 6,
}

AGENT = "Box/1.0"
REFERRER = "http://ref.example/"

NO_ANSWER_FOR_S = 30

NO_VIDEO = b"not a video " * 5000


class _Server(RangesHandler):
    def do_GET(self):
        name = self.path.partition("?")[0]

        agent = self.headers.get("User-Agent", "")

        if name == "/garbage.mp4":
            self._answer_all(NO_VIDEO)
            return

        if name == "/missing.mp4":
            self.send_error(404)
            return

        if name == "/no_seeking.mp4":
            self._answer_all((Path(self.directory) / "a.mp4").read_bytes())
            return

        if name == "/headers.mp4" and (
            agent != AGENT or self.headers.get("Referer") != REFERRER
        ):
            self.send_error(403)
            return

        if name == "/no_answer.mp4" and _is_a_player(agent):
            time.sleep(NO_ANSWER_FOR_S)
            self.send_error(504)
            return

        self.path = "/a.mp4"
        super().do_GET()

    def _answer_all(self, body: bytes) -> None:
        """All of it and only ever that: there's no asking for any more of it."""

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _is_a_player(agent: str) -> bool:
    """As opposed to the app, finding out what the link is first."""

    return "VLC" in agent or "libmpv" in agent or "Lavf" in agent


def _failed(d, link, what):
    """Open it in a cell of its own, and what it says once it gives up."""

    cells = len(d.cells)
    d.open(link)
    d.wait_until(lambda: len(d.cells) > cells, "a cell for it")
    cell = d.cells[-1]
    d.wait_until(lambda: cell.is_error, f"{what} gives up", timeout=40)

    return cell, cell.status.last_error


def _list(d, name, *lines):
    path = d.out / name
    path.write_text("\n".join(("#EXTM3U", *lines)) + "\n", encoding="utf-8")

    d.open(path)
    d.wait(0.5)

    return d.cells[-1]


def scenario(d):
    base = d.serve_with_ranges(d.media.folder, handler=_Server)

    garbage = d.out / "garbage.mp4"
    garbage.write_bytes(NO_VIDEO)

    cell, error = _failed(d, garbage, "a file that's no video")
    d.check("it says the player", error.where == "Player", error.where)
    d.check("it says what it said", bool(error.about), error.about)
    d.check("it's not left paused", not cell.video_params.is_paused)
    d.shot("no_video")

    _, error = _failed(d, f"{base}/garbage.mp4", "a link that's no video")
    d.check("it says the player", error.where == "Player", error.where)

    # an mp4 with its index at the end, and a server that can't go there
    cell, error = _failed(
        d, f"{base}/no_seeking.mp4", "a file it can't get the index of"
    )
    d.check(
        "it says it never started",
        error.title == "Video stopped before initialization",
        error.title,
    )
    d.check("it's not left paused", not cell.video_params.is_paused)

    _, error = _failed(
        d, f"{base}/no_answer.mp4", "a link that never answers the player"
    )
    d.check("it says the player", error.where == "Player", error.where)

    told = _list(
        d,
        "headers.m3u",
        "#EXTINF:-1,With headers",
        f"#EXTVLCOPT:http-user-agent={AGENT}",
        f"#EXTVLCOPT:http-referrer={REFERRER}",
        f"{base}/headers.mp4",
    )
    d.wait_until(lambda: told.is_playable, "a link that takes a list's headers plays")

    onward = _list(
        d,
        "onward.m3u",
        "#EXTINF:-1,Missing",
        f"{base}/missing.mp4",
        "#EXTINF:-1,No video",
        f"{base}/garbage.mp4",
        "#EXTINF:-1,Good",
        f"{base}/good.mp4",
    )
    d.check(
        "a list goes on by default",
        onward.video_params.list_fail_action == ListFailAction.PLAY_NEXT,
    )
    onward.recovery.set_fail_wait(0)
    d.wait_until(
        lambda: onward.is_playable and onward.navigation.list_place_txt == "3/3",
        "the list gets past both to one that plays",
        timeout=60,
    )
    d.check("titled from the list", onward.title == "Good", onward.title)
    d.shot("end")

    d.note("end", onward)
