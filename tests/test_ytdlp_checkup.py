"""What the checkup says, for each way a link can fail to play.

The point of it is to tell apart failures that all look the same from
outside, so what matters is not that a step runs but that it comes back
with the one answer that sends somebody to the right place.
"""

import time
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from yt_dlp import DownloadError

from gridplayer.utils import ytdlp_checkup
from gridplayer.utils.checkup import CheckStatus
from gridplayer.utils.cookies import parse_cookies
from gridplayer.utils.ytdlp_checkup import YouTubeCheckup

MEDIA = bytes(range(256)) * 512

SIGNED_IN_PAGE = b'<html><script>ytcfg.set({"LOGGED_IN":true,"x":1});</script></html>'
SIGNED_OUT_PAGE = b'<html><script>ytcfg.set({"LOGGED_IN":false});</script></html>'
UNKNOWN_PAGE = b"<html>nothing to see here</html>"

COOKIE_LIFETIME_SEC = 10000


class Runtime:
    """Stands in for what yt-dlp reports about an installed runtime."""

    def __init__(self, name, version="1.0.0", supported=True, path=None):
        self.name = name
        self.version = version
        self.supported = supported
        self.path = path or f"/usr/bin/{name}"


class HomeHandler(BaseHTTPRequestHandler):
    """Stands in for the page a site builds out of the session it sees."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.seen.append(dict(self.headers))

        body = self.server.page

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Quiet, the test is not interested"""


class MediaHandler(BaseHTTPRequestHandler):
    """A host that serves the bytes, or refuses to."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.seen.append(dict(self.headers))

        if self.server.status != HTTPStatus.PARTIAL_CONTENT:
            self.send_response(self.server.status)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        body = MEDIA[: ytdlp_checkup.SAMPLE_BYTES]

        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Quiet, the test is not interested"""


class FakeYoutubeDL:
    """yt-dlp, answering with whatever the test says it found."""

    info = None
    error = None
    warnings = ()

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        for warning in self.warnings:
            self.options["logger"].warning(warning)

        if self.error is not None:
            raise DownloadError(self.error)

        return self.info


@pytest.fixture
def home_page(serving):
    server = ThreadingHTTPServer(("127.0.0.1", 0), HomeHandler)
    server.seen = []
    server.page = SIGNED_IN_PAGE

    return serving(server)


@pytest.fixture
def media_host(serving):
    server = ThreadingHTTPServer(("127.0.0.1", 0), MediaHandler)
    server.seen = []
    server.status = HTTPStatus.PARTIAL_CONTENT

    return serving(server)


def _url_of(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/"


def _jar(*lines):
    expires = int(time.time()) + COOKIE_LIFETIME_SEC

    return parse_cookies(
        "# Netscape HTTP Cookie File\n"
        + "".join(line.format(EXPIRES=expires) + "\n" for line in lines)
    )


def _youtube_jar():
    return _jar(".youtube.com\tTRUE\t/\tFALSE\t{EXPIRES}\tSID\tabc")


def _expired_youtube_jar():
    return _jar(".youtube.com\tTRUE\t/\tFALSE\t1\tSID\tabc")


def _local_jar():
    return _jar("127.0.0.1\tFALSE\t/\tFALSE\t{EXPIRES}\tSID\tabc")


def _resolved(url, **fmt):
    return {
        "title": "A Video",
        "formats": [{"url": url, "protocol": "http", "format_id": "18", **fmt}],
    }


class TestVersion:
    def test_a_fresh_build_passes(self, monkeypatch):
        monkeypatch.setattr(ytdlp_checkup, "YT_DLP_VERSION", _version_days_ago(days=3))

        check_result = YouTubeCheckup().check_version()

        assert check_result.status is CheckStatus.PASSED

    def test_an_old_build_is_named_as_the_first_thing_to_suspect(self, monkeypatch):
        monkeypatch.setattr(
            ytdlp_checkup,
            "YT_DLP_VERSION",
            _version_days_ago(days=ytdlp_checkup.STALE_VERSION_DAYS + 1),
        )

        check_result = YouTubeCheckup().check_version()

        assert check_result.status is CheckStatus.WARNING
        assert "updating GridPlayer" in check_result.hint

    def test_a_version_that_is_not_a_date_is_still_reported(self, monkeypatch):
        monkeypatch.setattr(ytdlp_checkup, "YT_DLP_VERSION", "from-source")

        check_result = YouTubeCheckup().check_version()

        assert check_result.status is CheckStatus.PASSED
        assert check_result.summary == "from-source"


class TestJsRuntime:
    @pytest.fixture(autouse=True)
    def _no_ranking_to_be_had(self, monkeypatch):
        """These cases are about what is installed, not which one wins.

        Asked for real it would answer with whatever this machine has,
        which is not something a test can be written against.
        """

        monkeypatch.setattr(
            ytdlp_checkup.YouTubeCheckup, "_chosen_js_runtime", lambda self: None
        )

    def test_the_runtime_yt_dlp_uses_passes(self, monkeypatch):
        _installed(monkeypatch, deno=Runtime("deno", "2.9.6"))

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.PASSED
        assert check_result.summary == "deno 2.9.6"

    def test_a_runtime_too_old_to_use_says_what_is_needed(self, monkeypatch):
        _installed(monkeypatch, deno=Runtime("deno", "1.0.0", supported=False))

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.WARNING
        assert "too old" in check_result.summary
        assert "2.3.0" in check_result.hint

    def test_no_runtime_at_all_explains_what_it_is_for(self, monkeypatch):
        _installed(monkeypatch)

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.WARNING
        assert "scrambles" in check_result.hint


class TestCookies:
    def test_an_empty_jar_is_skipped_rather_than_failed(self):
        """Signed out is a way of watching YouTube, not a broken setup."""

        check_result = YouTubeCheckup().check_cookies()

        assert check_result.status is CheckStatus.SKIPPED

    def test_a_login_is_counted_by_host(self):
        check_result = YouTubeCheckup(jar=_youtube_jar()).check_cookies()

        assert check_result.status is CheckStatus.PASSED
        assert check_result.summary == "1 cookies for .youtube.com"

    def test_cookies_switched_off_are_named_as_switched_off(self):
        checkup = YouTubeCheckup(jar=_youtube_jar(), are_cookies_enabled=False)

        check_result = checkup.check_cookies()

        assert check_result.status is CheckStatus.WARNING
        assert "switched off" in check_result.summary

    def test_a_jar_of_lapsed_cookies_is_not_a_login(self):
        check_result = YouTubeCheckup(jar=_expired_youtube_jar()).check_cookies()

        assert check_result.status is CheckStatus.WARNING
        assert "none of them still good" in check_result.summary

    def test_a_cookie_for_another_site_is_not_counted(self):
        jar = _jar(".example.com\tTRUE\t/\tFALSE\t{EXPIRES}\tSID\tabc")

        assert YouTubeCheckup(jar=jar).check_cookies().status is CheckStatus.SKIPPED

    def test_the_jar_it_was_given_is_left_alone(self):
        """Asking a jar what it would send throws out what has lapsed.

        The jar handed over is the one the settings page is showing and
        will save if the dialog is accepted, so a checkup that pruned it
        would delete cookies nobody asked to delete.
        """

        jar = _expired_youtube_jar()

        YouTubeCheckup(jar=jar).check_cookies()

        assert len(jar) == 1


class TestSignIn:
    def test_without_cookies_there_is_nothing_to_sign_in_with(self):
        assert YouTubeCheckup().check_sign_in().status is CheckStatus.SKIPPED

    def test_cookies_switched_off_are_not_sent(self, monkeypatch, home_page):
        monkeypatch.setattr(ytdlp_checkup, "YOUTUBE_HOME_URL", _url_of(home_page))

        checkup = YouTubeCheckup(jar=_local_jar(), are_cookies_enabled=False)

        assert checkup.check_sign_in().status is CheckStatus.SKIPPED
        assert not home_page.seen

    def test_a_session_the_site_recognises_passes(self, monkeypatch, home_page):
        monkeypatch.setattr(ytdlp_checkup, "YOUTUBE_HOME_URL", _url_of(home_page))

        check_result = YouTubeCheckup(jar=_local_jar()).check_sign_in()

        assert check_result.status is CheckStatus.PASSED
        assert home_page.seen[0]["Cookie"] == "SID=abc"

    def test_a_session_the_site_does_not_know_says_how_it_went_stale(
        self, monkeypatch, home_page
    ):
        monkeypatch.setattr(ytdlp_checkup, "YOUTUBE_HOME_URL", _url_of(home_page))
        home_page.page = SIGNED_OUT_PAGE

        check_result = YouTubeCheckup(jar=_local_jar()).check_sign_in()

        assert check_result.status is CheckStatus.WARNING
        assert "private window" in check_result.hint

    def test_a_page_that_says_neither_defers_to_the_steps_below(
        self, monkeypatch, home_page
    ):
        monkeypatch.setattr(ytdlp_checkup, "YOUTUBE_HOME_URL", _url_of(home_page))
        home_page.page = UNKNOWN_PAGE

        check_result = YouTubeCheckup(jar=_local_jar()).check_sign_in()

        assert check_result.status is CheckStatus.WARNING
        assert "did not say either way" in check_result.summary

    def test_a_host_that_cannot_be_reached_fails(self, monkeypatch):
        monkeypatch.setattr(
            ytdlp_checkup, "YOUTUBE_HOME_URL", "http://127.0.0.1:1/nothing"
        )

        check_result = YouTubeCheckup(jar=_local_jar()).check_sign_in()

        assert check_result.status is CheckStatus.FAILED


class TestResolve:
    def test_a_link_that_resolves_reports_what_came_back(self, monkeypatch):
        _resolving(monkeypatch, info=_resolved("http://host/media"))

        check_result = YouTubeCheckup().check_resolve()

        assert check_result.status is CheckStatus.PASSED
        assert check_result.summary == '1 formats for "A Video"'

    def test_warnings_along_the_way_are_kept_rather_than_swallowed(self, monkeypatch):
        """yt-dlp drops a format and carries on, which is half a failure."""

        _resolving(
            monkeypatch,
            info=_resolved("http://host/media"),
            warnings=["Some formats have been skipped"],
        )

        check_result = YouTubeCheckup().check_resolve()

        assert check_result.status is CheckStatus.WARNING
        assert check_result.hint == "Some formats have been skipped"

    def test_a_bot_check_is_answered_with_what_to_do_about_it(self, monkeypatch):
        _resolving(
            monkeypatch,
            error=(
                "ERROR: [youtube] xy: Sign in to confirm you are not a bot."
                " Use --cookies for the authentication."
            ),
        )

        check_result = YouTubeCheckup().check_resolve()

        assert check_result.status is CheckStatus.FAILED
        assert "Import YouTube cookies" in check_result.hint

    def test_command_line_advice_is_left_out_of_the_message(self, monkeypatch):
        """Flags to pass mean nothing here, and bury the one sentence."""

        _resolving(
            monkeypatch,
            error=(
                "ERROR: [youtube] xy: Sign in to confirm you are not a bot."
                " Use --cookies for the authentication."
                " See https://example.com/wiki for how to pass cookies"
            ),
        )

        check_result = YouTubeCheckup().check_resolve()

        assert check_result.summary == (
            "[youtube] xy: Sign in to confirm you are not a bot."
        )

    def test_a_missing_test_video_says_it_is_not_your_fault(self, monkeypatch):
        _resolving(monkeypatch, error="ERROR: [youtube] xy: Video unavailable")

        check_result = YouTubeCheckup().check_resolve()

        assert check_result.status is CheckStatus.FAILED
        assert "says nothing about your own links" in check_result.hint

    def test_the_stored_cookies_are_handed_to_yt_dlp(self, monkeypatch):
        used = _resolving(monkeypatch, info=_resolved("http://host/media"))

        YouTubeCheckup(jar=_youtube_jar()).check_resolve()

        assert "SID" in used[0].options["cookiefile"].getvalue()

    def test_cookies_switched_off_are_not_handed_over(self, monkeypatch):
        used = _resolving(monkeypatch, info=_resolved("http://host/media"))

        YouTubeCheckup(jar=_youtube_jar(), are_cookies_enabled=False).check_resolve()

        assert "cookiefile" not in used[0].options


class TestFetch:
    def test_nothing_resolved_leaves_nothing_to_fetch(self):
        assert YouTubeCheckup().check_fetch().status is CheckStatus.SKIPPED

    def test_media_that_is_served_passes(self, monkeypatch, media_host):
        checkup = _after_resolving(monkeypatch, _resolved(_url_of(media_host)))

        check_result = checkup.check_fetch()

        assert check_result.status is CheckStatus.PASSED
        assert "64 KiB" in check_result.summary

    def test_the_range_asked_for_is_only_a_sample(self, monkeypatch, media_host):
        checkup = _after_resolving(monkeypatch, _resolved(_url_of(media_host)))

        checkup.check_fetch()

        asked = ytdlp_checkup.SAMPLE_BYTES - 1
        assert media_host.seen[0]["Range"] == f"bytes=0-{asked}"

    def test_a_refused_address_is_pinned_on_the_signature(
        self, monkeypatch, media_host
    ):
        """Resolved but unplayable is the failure this step exists for."""

        media_host.status = HTTPStatus.FORBIDDEN
        checkup = _after_resolving(monkeypatch, _resolved(_url_of(media_host)))

        check_result = checkup.check_fetch()

        assert check_result.status is CheckStatus.FAILED
        assert "JavaScript runtime" in check_result.hint

    def test_a_ladder_with_no_plain_file_in_it_has_nothing_to_sample(self, monkeypatch):
        info = {
            "title": "A Video",
            "formats": [{"url": "http://host/x.m3u8", "protocol": "m3u8_native"}],
        }
        checkup = _after_resolving(monkeypatch, info)

        assert checkup.check_fetch().status is CheckStatus.FAILED

    def test_the_cheapest_format_is_the_one_sampled(self, monkeypatch, media_host):
        info = {
            "title": "A Video",
            "formats": [
                {"url": "http://host/big", "protocol": "http", "tbr": 4000},
                {
                    "url": _url_of(media_host),
                    "protocol": "http",
                    "tbr": 50,
                    "format_id": "audio",
                },
            ],
        }
        checkup = _after_resolving(monkeypatch, info)

        assert "audio" in checkup.check_fetch().summary


def _version_days_ago(days: int) -> str:
    cut = datetime.now(tz=timezone.utc).date() - timedelta(days=days)

    return cut.strftime("%Y.%m.%d")


def _installed(monkeypatch, **runtimes):
    """The runtimes on this machine, whatever folder it is asked about."""

    monkeypatch.setattr(ytdlp_checkup, "_installed_js_runtimes", lambda *_: runtimes)


def _resolving(monkeypatch, info=None, error=None, warnings=()):
    """Put a yt-dlp in place that answers with this, and keep the ones made."""

    made = []

    class _Fake(FakeYoutubeDL):
        pass

    _Fake.info = info
    _Fake.error = error
    _Fake.warnings = warnings

    def _build(options):
        ydl = _Fake(options)
        made.append(ydl)
        return ydl

    monkeypatch.setattr(ytdlp_checkup, "YoutubeDL", _build)

    return made


def _after_resolving(monkeypatch, info):
    checkup = YouTubeCheckup()

    _resolving(monkeypatch, info=info)

    checkup.check_resolve()

    return checkup


class TestWhichRuntimeWins:
    """One of them runs and the rest do not, so the line says which.

    Somebody opens this because a link failed. "deno, node" tells them
    two things are installed and nothing about what just happened.
    """

    def test_the_one_that_will_run_is_named_with_its_path(self, monkeypatch):
        _installed(monkeypatch, deno=Runtime("deno", "2.9.7", path="/opt/deno"))
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.7", path="/opt/deno"))

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.PASSED
        assert check_result.summary == "deno 2.9.7"
        assert "/opt/deno" in check_result.hint

    def test_the_ones_that_will_not_run_are_named_as_such(self, monkeypatch):
        """Installing a second one and seeing nothing change is the trap."""

        _installed(
            monkeypatch,
            deno=Runtime("deno", "2.9.7", path="/opt/deno"),
            node=Runtime("node", "24.0.0", path="/usr/bin/node"),
        )
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.7", path="/opt/deno"))

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.summary == "deno 2.9.7"
        assert "node 24.0.0" in check_result.hint
        assert "will not use" in check_result.hint

    def test_a_lone_runtime_is_not_told_it_beat_anything(self, monkeypatch):
        _installed(monkeypatch, deno=Runtime("deno", "2.9.7", path="/opt/deno"))
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.7", path="/opt/deno"))

        assert "Also installed" not in YouTubeCheckup().check_js_runtime().hint

    def test_the_winner_is_named_even_where_it_is_not_the_top_ranked(self, monkeypatch):
        """Whoever answers is the answer; the ranking is not repeated here."""

        _installed(
            monkeypatch,
            deno=Runtime("deno", "2.9.7", path="/opt/deno"),
            quickjs=Runtime("quickjs-ng", "0.16.2", path="/data/qjs"),
        )
        _chosen(
            monkeypatch, "quickjs", Runtime("quickjs-ng", "0.16.2", path="/data/qjs")
        )

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.summary == "quickjs-ng 0.16.2"
        assert "/data/qjs" in check_result.hint
        assert "deno 2.9.7" in check_result.hint

    def test_a_bare_name_is_resolved_to_where_it_actually_is(self, monkeypatch):
        """Off Windows yt-dlp leaves a PATH hit as the name it will call.

        Printing that back says nothing, and saying nothing is the one
        thing this line exists not to do.
        """

        _installed(monkeypatch, deno=Runtime("deno", "2.9.6", path="deno"))
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.6", path="deno"))
        monkeypatch.setattr(
            ytdlp_checkup.shutil, "which", lambda name: f"/usr/local/bin/{name}"
        )

        assert "/usr/local/bin/deno" in YouTubeCheckup().check_js_runtime().hint

    def test_a_name_that_resolves_to_nothing_is_printed_as_it_stands(self, monkeypatch):
        """Better the bare name than an empty space where a path goes."""

        _installed(monkeypatch, deno=Runtime("deno", "2.9.6", path="deno"))
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.6", path="deno"))
        monkeypatch.setattr(ytdlp_checkup.shutil, "which", lambda name: None)

        assert "deno" in YouTubeCheckup().check_js_runtime().hint

    def test_an_absolute_path_is_left_alone(self, monkeypatch, tmp_path):
        """Nothing to look up, and PATH could answer with a different copy.

        Built from tmp_path rather than written out, since what counts
        as an absolute path is not the same on every platform.
        """

        found = []
        absolute = str(tmp_path / "deno")

        _installed(monkeypatch, deno=Runtime("deno", "2.9.7", path=absolute))
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.7", path=absolute))
        monkeypatch.setattr(
            ytdlp_checkup.shutil, "which", lambda name: found.append(name)
        )

        assert absolute in YouTubeCheckup().check_js_runtime().hint
        assert not found

    def test_a_ranking_that_cannot_be_asked_for_still_lists_what_is_there(
        self, monkeypatch
    ):
        """A private corner of yt-dlp, so it is allowed to go missing."""

        _installed(monkeypatch, deno=Runtime("deno", "2.9.7"))
        monkeypatch.setattr(
            ytdlp_checkup.YouTubeCheckup, "_chosen_js_runtime", lambda self: None
        )

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.PASSED
        assert check_result.summary == "deno 2.9.7"
        assert not check_result.hint

    def test_it_never_raises_when_yt_dlp_moves_under_it(self, monkeypatch):
        """The checkup is a diagnosis; it does not get to fail itself."""

        _installed(monkeypatch, deno=Runtime("deno", "2.9.7"))
        monkeypatch.setattr(ytdlp_checkup, "YoutubeDL", _raising("no such director"))

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.PASSED
        assert check_result.summary == "deno 2.9.7"


def _chosen(monkeypatch, name, info):
    monkeypatch.setattr(
        ytdlp_checkup.YouTubeCheckup, "_chosen_js_runtime", lambda self: (name, info)
    )


def _raising(message):
    def _boom(*args, **kwargs):
        raise RuntimeError(message)

    return _boom


class TestColouredErrors:
    """yt-dlp writes for a terminal, and this is a dialog.

    It wraps its errors in escape sequences when it thinks something is
    watching that can render them, which a windowed app makes it think
    more often than not. Printed as they stand they turn the one
    sentence somebody needs into line noise.
    """

    COLOURED = (
        "\x1b[0;31mERROR:\x1b[0m [youtube] aqz-KE-bpKQ:"
        " Sign in to confirm you are not a bot. Use --cookies-from-browser"
    )

    def test_the_colours_do_not_reach_the_dialog(self):
        said = ytdlp_checkup._last_line(self.COLOURED)

        assert "\x1b" not in said
        assert "[0;31m" not in said

    def test_the_prefix_is_still_taken_off_behind_them(self):
        """It is only a prefix once the escape in front of it is gone."""

        assert not ytdlp_checkup._last_line(self.COLOURED).startswith("ERROR:")

    def test_what_went_wrong_survives(self):
        said = ytdlp_checkup._last_line(self.COLOURED)

        assert "Sign in to confirm you are not a bot." in said
        assert "--cookies-from-browser" not in said

    def test_the_hint_still_recognises_it(self):
        """The wording is matched on, so colour in it would hide the match."""

        check_result = ytdlp_checkup._resolve_failure(
            ytdlp_checkup._last_line(self.COLOURED)
        )

        assert check_result.status is CheckStatus.FAILED
        assert "cookies" in check_result.hint.lower()

    def test_ordinary_text_is_left_alone(self):
        """The pattern has ranges in it that plain prose is full of."""

        plain = "Video unavailable [youtube] A-Z_@~ 100% done"

        assert ytdlp_checkup._clean_message(plain) == plain

    def test_yt_dlp_is_asked_not_to_colour_in_the_first_place(self, monkeypatch):
        """Stripping is the second line of defence, not the only one."""

        made = _resolving(monkeypatch, info={"formats": [], "title": "t"})

        YouTubeCheckup().check_resolve()

        assert made[0].options["no_color"] is True


class TestAFolderThatAnswersForNothing:
    """Naming a folder is the last resort, so a wrong one is worth saying.

    Nothing else looks where that setting points, which is the whole
    reason for it. A name that holds no engine is a typo or the wrong
    folder, and without a word about it the page is simply ignored.
    """

    def test_a_folder_holding_nothing_is_called_out(self, monkeypatch, tmp_path):
        _installed(monkeypatch)
        _configured(monkeypatch, tmp_path, found=None)

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.WARNING
        assert str(tmp_path) in check_result.hint

    def test_it_is_said_even_where_something_was_found_elsewhere(
        self, monkeypatch, tmp_path
    ):
        """Playback works, but the setting is doing nothing and looks wrong."""

        _installed(monkeypatch, deno=Runtime("deno", "2.9.7", path="/usr/bin/deno"))
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.7", path="/usr/bin/deno"))
        _configured(monkeypatch, tmp_path, found="/usr/bin/deno")

        check_result = YouTubeCheckup().check_js_runtime()

        assert check_result.status is CheckStatus.PASSED
        assert str(tmp_path) in check_result.hint
        assert "/usr/bin/deno" in check_result.hint

    def test_a_folder_that_answered_is_not_complained_about(
        self, monkeypatch, tmp_path
    ):
        found = tmp_path / "deno"
        _installed(monkeypatch, deno=Runtime("deno", "2.9.7", path=str(found)))
        _chosen(monkeypatch, "deno", Runtime("deno", "2.9.7", path=str(found)))
        _configured(monkeypatch, tmp_path, found=str(found))

        # the path is in the hint either way, as the one being run, so
        # what is being checked for is the complaint rather than the path
        assert "pointing at" not in YouTubeCheckup().check_js_runtime().hint

    def test_nothing_is_said_where_no_folder_was_named(self, monkeypatch):
        """Which is how it ships, so the usual report must stay unchanged."""

        _installed(monkeypatch)
        monkeypatch.setattr(ytdlp_checkup, "configured_dir", lambda *_: None)

        check_result = YouTubeCheckup().check_js_runtime()

        assert "pointing at" not in check_result.hint


def _configured(monkeypatch, folder, found):
    """A folder named on the page, and what the search made of it."""

    monkeypatch.setattr(ytdlp_checkup, "configured_dir", lambda *_: folder)
    monkeypatch.setattr(
        ytdlp_checkup,
        "ytdl_js_runtimes",
        lambda *_: {"deno": {"path": found} if found else {}},
    )
