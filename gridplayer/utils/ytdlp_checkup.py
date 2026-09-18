"""What yt-dlp can do from here, tried rather than taken on trust.

A link that will not play says "Failed to resolve URL" whichever of half a
dozen things went wrong: yt-dlp too old for what the site serves now, no
JavaScript runtime to run the player's own code with, cookies that lapsed
or were never sent, an address the site has stopped answering for. One
message covers all of them, so the only way to tell them apart is to walk
the steps one at a time and report which one gave way.

The jar is handed in rather than read out of the store, so the settings
page can try the cookies it is showing instead of the ones last saved.
Nothing here writes to the store, and the checks work on a copy of the
jar: asking a jar what it would send prunes what has lapsed out of it.

Cookies are credentials. What comes back names hosts and counts, the same
as the settings page, and never a value.
"""

import dataclasses
import logging
import re
import shutil
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from streamlink import Streamlink
from yt_dlp import DownloadError, YoutubeDL
from yt_dlp.globals import supported_js_runtimes
from yt_dlp.version import __version__ as YT_DLP_VERSION

from gridplayer.utils.checkup import Check, CheckResult, CheckStatus, Checkup
from gridplayer.utils.cookies import RewindingBuffer, merged_with
from gridplayer.utils.js_runtime import configured_dir, ytdl_js_runtimes
from gridplayer.utils.network import (
    apply_to_streamlink,
    fetch_capped,
    ytdl_network_opts,
)
from gridplayer.utils.qt import translate

TRANSLATION_CONTEXT = "yt-dlp Checkup"

# Blender's own upload: old enough to be a fixture, still published in the
# full modern ladder, so resolving it exercises the signature and manifest
# path a present-day stream goes through rather than a legacy shortcut.
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

YOUTUBE_HOME_URL = "https://www.youtube.com/"

# how yt-dlp's own guidance is best summarised, for the hints that cannot
# say enough by themselves
COOKIES_WIKI_URL = (
    "https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
)
# GridPlayer ships no JavaScript engine of its own -- the smallest one
# going costs seconds per link, and the quick ones are the size of the
# whole player -- so the runtime is something the viewer installs, and
# this is where it says which and how
JS_RUNTIME_HELP_URL = "https://github.com/vzhd1701/gridplayer#javascript-runtime"

# yt-dlp is released about weekly and YouTube changes under it constantly;
# a build older than this is the first thing to suspect
STALE_VERSION_DAYS = 90

VERSION_DATE_PATTERN = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})")

# where a yt-dlp error stops saying what went wrong and starts telling a
# command line user what to type and what to read
CLI_ADVICE_PATTERN = re.compile(r"\s(?:Use --|See https?://|Also see\s)")

# the colours yt-dlp wraps its errors in. Asking it not to is the first
# line of defence, but a message can reach here from a yt-dlp nobody
# passed that to, and half an escape sequence in a dialog reads as
# nonsense rather than as an error somebody can act on
TERMINAL_SEQUENCE_PATTERN = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# what yt-dlp waits on a socket where the network page has named nothing:
# long enough for a slow site to answer, short enough that a checkup that
# has hung is obvious rather than indistinguishable from a slow one. The
# fetches after it go through a session and take the session's own.
REQUEST_TIMEOUT = 20

# enough of the media to prove the host will serve it to us
SAMPLE_BYTES = 64 * 1024

# what the home page says about the session it served, in the config block
# the player is set up from
LOGGED_IN_MARKER = '"LOGGED_IN":true'
LOGGED_OUT_MARKER = '"LOGGED_IN":false'

# the config block sits near the top of the document, and the rest of the
# page is a megabyte of no interest here
HOME_PAGE_LIMIT = 2 * 1024 * 1024

# a cookie on any of these belongs to the YouTube session; the account
# itself lives on the Google domain and travels with it
YOUTUBE_COOKIE_SITES = ("youtube.com", "google.com")

BYTES_IN_KIB = 1024

HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403


class YouTubeCheckup(Checkup):
    """The steps a YouTube link goes through, in the order they build up.

    Each check leaves behind what the next one needs, so they are run in
    order and a step whose ground was never laid says so rather than
    failing. Nothing raises: a check that goes wrong in a way it did not
    expect is still a result.
    """

    def __init__(
        self,
        jar=None,
        are_cookies_enabled: bool = True,
        js_runtime_path: str | None = None,
        net_opts=None,
    ):
        self._log = logging.getLogger(self.__class__.__name__)

        # a copy, because asking a jar what it would send clears what has
        # lapsed out of it, and this jar is the one still on screen
        self._jar = merged_with(jar, None) if jar is not None else None

        self._are_cookies_enabled = are_cookies_enabled

        # the rest of the page, for the same reason the jar is handed in:
        # somebody who has just typed a runtime folder or a proxy and
        # pressed the button has not pressed OK, and a test that answers
        # for the stored settings answers a question nobody asked
        self._js_runtime_path = js_runtime_path
        self._net_opts = net_opts

        self._video_info = None
        self._streamlink = None

    @property
    def title(self) -> str:
        return _t("yt-dlp checkup")

    @property
    def intro(self) -> str:
        return _t(
            "Playing a YouTube link, step by step, with the cookies on the"
            " settings page as they stand now."
        )

    @property
    def checks(self) -> tuple[Check, ...]:
        return (
            Check(_t("yt-dlp version"), self.check_version),
            Check(_t("JavaScript runtime"), self.check_js_runtime),
            Check(_t("Stored YouTube cookies"), self.check_cookies),
            Check(_t("YouTube sign-in"), self.check_sign_in),
            Check(_t("Resolving a test video"), self.check_resolve),
            Check(_t("Fetching the stream"), self.check_fetch),
        )

    def check_version(self) -> CheckResult:
        released = _release_date(YT_DLP_VERSION)

        if released is None:
            return CheckResult(CheckStatus.PASSED, YT_DLP_VERSION)

        age = (datetime.now(tz=timezone.utc).date() - released).days

        summary = _t("{VERSION}, released {DAYS} days ago").format(
            VERSION=YT_DLP_VERSION, DAYS=age
        )

        if age < STALE_VERSION_DAYS:
            return CheckResult(CheckStatus.PASSED, summary)

        return CheckResult(
            CheckStatus.WARNING,
            summary,
            _t(
                "YouTube changes what it serves every few weeks, and an old"
                " yt-dlp is the most common reason a link stops resolving."
                " It ships with GridPlayer, so updating it means updating"
                " GridPlayer."
            ),
        )

    def check_js_runtime(self) -> CheckResult:
        """Whether yt-dlp has something to run YouTube's player code with.

        YouTube hands out its stream addresses scrambled by a script that
        changes daily, and unscrambling them means running that script.
        Without a runtime the addresses come back unusable, or the
        formats that need one are dropped and never offered at all.
        """

        return _with_note(
            self._js_runtime_result(), _barren_folder_note(self._js_runtime_path)
        )

    def _js_runtime_result(self) -> CheckResult:
        """What was found, before anything is said about where it was looked for."""

        # every engine yt-dlp can drive is enabled, so one that is here
        # is one it would reach for: what is installed and what is
        # wanted were two sets once and are the same set now
        installed = _installed_js_runtimes(self._js_runtime_path)

        usable = {name: info for name, info in installed.items() if info.supported}

        if usable:
            return self._js_runtime_in_use(usable)

        if installed:
            return CheckResult(
                CheckStatus.WARNING,
                _t("{RUNTIMES} is too old for yt-dlp").format(
                    RUNTIMES=_runtime_list(installed.values())
                ),
                _minimum_version_hint(installed),
            )

        return CheckResult(
            CheckStatus.WARNING,
            _t("No JavaScript runtime found"),
            _t(
                "YouTube scrambles its stream addresses with a script that"
                " has to be run to undo. GridPlayer does not ship an engine"
                " to run it with. Install Deno or Node and YouTube links"
                " will resolve to addresses that play. See {URL}"
            ).format(URL=JS_RUNTIME_HELP_URL),
        )

    def _js_runtime_in_use(self, usable: dict) -> CheckResult:
        """Which of the installed ones is the one that will actually run.

        Several can be installed at once and only ever one of them is
        used, so a list of what is on the machine does not answer the
        question somebody opens this to ask. When a link fails it is
        the engine actually running that matters, and where it is:
        "deno" on a machine with three of them says nothing about
        which three, and nothing about the one being picked up out of
        a folder they have forgotten they put it in.
        """

        chosen = self._chosen_js_runtime()

        if chosen is None:
            # the ranking could not be asked for, so name what is there
            # rather than a winner picked by guessing at the order
            return CheckResult(CheckStatus.PASSED, _runtime_list(usable.values()))

        name, info = chosen

        others = [other for key, other in usable.items() if key != name]

        if others:
            hint = _t(
                "Running {PATH}. Also installed: {OTHERS}, which yt-dlp"
                " ranks lower and will not use."
            ).format(PATH=_runtime_path(info), OTHERS=_runtime_list(others))
        else:
            hint = _t("Running {PATH}").format(PATH=_runtime_path(info))

        return CheckResult(CheckStatus.PASSED, f"{info.name} {info.version}", hint)

    def _chosen_js_runtime(self):
        """The engine yt-dlp would reach for, asked of yt-dlp itself.

        The order they are ranked in is yt-dlp's business and has
        changed before, so it is not written down again here: the
        thing that does the choosing is built the way playback builds
        it and asked what it would choose. That is a private corner of
        yt-dlp, so a checkup that cannot ask says nothing rather than
        guessing.
        """

        # imported here because it is private enough that its going
        # missing should cost this one line and not the whole checkup
        from yt_dlp.extractor.youtube.jsc._director import initialize_jsc_director

        try:
            with YoutubeDL(
                {
                    "logger": _QuietLogger(),
                    "quiet": True,
                    "js_runtimes": ytdl_js_runtimes(self._js_runtime_path),
                }
            ) as ydl:
                director = initialize_jsc_director(ydl.get_info_extractor("Youtube"))

                provider = next(iter(director._get_providers([])), None)
        except Exception as e:
            self._log.debug(f"Could not ask yt-dlp which JS runtime it would use: {e}")
            return None

        if provider is None or provider.runtime_info is None:
            return None

        return provider.JS_RUNTIME_NAME, provider.runtime_info

    def check_cookies(self) -> CheckResult:
        """What the jar holds for YouTube, and whether any of it would go."""

        domains = _youtube_domains(self._jar)

        if not domains:
            return CheckResult(
                CheckStatus.SKIPPED,
                _t("No YouTube cookies stored"),
                _t(
                    "The rest of the checkup runs as a signed-out viewer,"
                    " which YouTube increasingly asks to prove itself."
                    " Import cookies on this page to test a signed-in one."
                ),
            )

        stored = _t("{COOKIES} cookies for {DOMAINS}").format(
            COOKIES=sum(count for _, count in domains),
            DOMAINS=", ".join(domain for domain, _ in domains),
        )

        if not self._are_cookies_enabled:
            return CheckResult(
                CheckStatus.WARNING,
                _t("{STORED}, but switched off").format(STORED=stored),
                _t(
                    "The rest of the checkup runs without them, as playback"
                    ' would. Tick "Use stored cookies" to have them sent.'
                ),
            )

        if self._cookie_header is None:
            return CheckResult(
                CheckStatus.WARNING,
                _t("{STORED}, none of them still good").format(STORED=stored),
                _t(
                    "Every stored YouTube cookie has expired, so none would"
                    " be sent. Export the site again. See {URL}"
                ).format(URL=COOKIES_WIKI_URL),
            )

        return CheckResult(CheckStatus.PASSED, stored)

    def check_sign_in(self) -> CheckResult:
        """Whether YouTube itself recognises the session in those cookies.

        A jar full of cookies proves nothing: what settles it is what the
        site says when they are sent. Its home page is built out of a
        config block that names the session it was served to.
        """

        if self._cookie_header is None:
            return CheckResult(CheckStatus.SKIPPED, _t("No cookies to sign in with"))

        try:
            page = self._fetch_home_page()
        except OSError as e:
            return CheckResult(
                CheckStatus.FAILED,
                _t("Could not reach YouTube: {ERROR}").format(ERROR=e),
            )

        if LOGGED_IN_MARKER in page:
            return CheckResult(
                CheckStatus.PASSED, _t("YouTube answered as a signed-in viewer")
            )

        if LOGGED_OUT_MARKER in page:
            return CheckResult(
                CheckStatus.WARNING,
                _t("YouTube answered as a signed-out viewer"),
                _t(
                    "The cookies reached the site but no longer name a"
                    " session. Exporting from a tab you keep browsing goes"
                    " stale within hours; export from a private window and"
                    " close it without logging out. See {URL}"
                ).format(URL=COOKIES_WIKI_URL),
            )

        return CheckResult(
            CheckStatus.WARNING,
            _t("YouTube did not say either way"),
            _t(
                "The page came back in a shape this check does not know."
                " The steps below still say whether playback works."
            ),
        )

    def check_resolve(self) -> CheckResult:
        """The step playback itself starts with, run on a known-good link."""

        logger = _CollectingLogger(self._log)

        try:
            self._video_info = self._extract_info(logger)
        except DownloadError as e:
            return _resolve_failure(_last_line(str(e)))
        except Exception as e:
            self._log.exception("yt-dlp checkup - resolve failed")
            return CheckResult(CheckStatus.FAILED, str(e))

        formats = self._video_info.get("formats") or []

        summary = _t('{FORMATS} formats for "{TITLE}"').format(
            FORMATS=len(formats), TITLE=self._video_info.get("title") or TEST_VIDEO_URL
        )

        if logger.warnings:
            return CheckResult(
                CheckStatus.WARNING,
                _t("{SUMMARY}, with warnings").format(SUMMARY=summary),
                "\n".join(logger.warnings),
            )

        return CheckResult(CheckStatus.PASSED, summary)

    def check_fetch(self) -> CheckResult:
        """Whether the address that came back actually serves media.

        Resolving and playing fail apart from each other: an address the
        site will not honour is handed over as readily as one it will,
        and the difference only shows on the first request for the bytes.
        """

        if self._video_info is None:
            return CheckResult(CheckStatus.SKIPPED, _t("Nothing was resolved to fetch"))

        sample_format = _sample_format(self._video_info)

        if sample_format is None:
            return CheckResult(
                CheckStatus.FAILED,
                _t("No format came back with an address to fetch"),
            )

        try:
            status, read = self._fetch_sample(sample_format)
        except OSError as e:
            return CheckResult(
                CheckStatus.FAILED,
                _t("Could not reach the stream: {ERROR}").format(ERROR=e),
            )

        if status >= HTTP_BAD_REQUEST:
            return _fetch_failure(status, sample_format)

        if not read:
            return CheckResult(
                CheckStatus.FAILED,
                _t("The stream answered {STATUS} but sent nothing").format(
                    STATUS=status
                ),
            )

        return CheckResult(
            CheckStatus.PASSED,
            _t("HTTP {STATUS}, {KIB} KiB from format {FORMAT}").format(
                KIB=read // BYTES_IN_KIB or 1,
                FORMAT=_format_name(sample_format),
                STATUS=status,
            ),
        )

    @property
    def _jar_in_use(self):
        """The jar as the rest of the checkup sees it, the setting applied."""

        return self._jar if self._are_cookies_enabled else None

    @property
    def _cookie_header(self) -> str | None:
        """What would be sent to YouTube, where anything would be.

        The jar is asked rather than read: it knows about paths, secure
        flags and expiry, and answers the question playback will ask.
        """

        jar = self._jar_in_use

        if jar is None:
            return None

        request = urllib.request.Request(YOUTUBE_HOME_URL)

        jar.add_cookie_header(request)

        return request.get_header("Cookie")

    def _extract_info(self, logger):
        """Resolve the test link the way the resolver would.

        yt-dlp saves its jar back on the way out, so it is handed a buffer
        rather than a file: this is a checkup, and nothing it does should
        leave a mark on what is stored.
        """

        # the network page last, so a timeout set there is the one used
        options = {
            "logger": logger,
            "socket_timeout": REQUEST_TIMEOUT,
            "js_runtimes": ytdl_js_runtimes(self._js_runtime_path),
            # what it says goes into a dialog, and yt-dlp decides to
            # colour it by looking at streams a windowed app does not
            # have in the state it expects
            "no_color": True,
            **ytdl_network_opts(self._net_opts),
        }

        jar = self._jar_in_use

        if jar is not None:
            options["cookiefile"] = RewindingBuffer(jar.dump())

        with YoutubeDL(options) as ydl:
            return ydl.extract_info(TEST_VIDEO_URL, download=False)

    def _fetch_home_page(self) -> str:
        page = self._fetch(YOUTUBE_HOME_URL, limit=HOME_PAGE_LIMIT)[1]

        return page.decode("utf-8", errors="replace")

    def _fetch_sample(self, sample_format) -> tuple[int, int]:
        headers = {
            **(sample_format.get("http_headers") or {}),
            "Range": f"bytes=0-{SAMPLE_BYTES - 1}",
        }

        status, sample = self._fetch(
            sample_format["url"], limit=SAMPLE_BYTES, headers=headers
        )

        return status, len(sample)

    def _fetch(self, url: str, limit: int, headers=None) -> tuple[int, bytes]:
        return fetch_capped(self._session(), url, limit, headers=headers)

    def _session(self) -> Streamlink:
        """A session configured the way the one behind playback is.

        Made once and kept, so every request in a run goes out the same
        way and a cookie a site sets along the way is still there for
        the next one.

        The network settings only. The cookies are put on by hand
        because the jar being tried is the checkup's own copy of what
        the settings page is showing, which is not what is stored.
        """

        if self._streamlink is None:
            self._streamlink = Streamlink()

            apply_to_streamlink(self._streamlink, self._net_opts)

            jar = self._jar_in_use

            if jar is not None:
                self._streamlink.http.cookies.update(jar)

        return self._streamlink


class _CollectingLogger:
    """A yt-dlp logger that keeps its warnings where they can be shown.

    yt-dlp says why a format went missing in a warning and then carries
    on, which is exactly the half-failure this checkup exists to surface.
    """

    def __init__(self, log):
        self._log = log
        self.warnings = []

    def debug(self, message):
        self._log.debug(message)

    def info(self, message):
        self._log.debug(message)

    def warning(self, message):
        self.warnings.append(_clean_message(message))
        self._log.warning(message)

    def error(self, message):
        self._log.error(message)


def _t(text: str) -> str:
    return translate(TRANSLATION_CONTEXT, text)


def _release_date(version: str):
    """When this yt-dlp was cut, which is what its version number is."""

    dated = VERSION_DATE_PATTERN.match(version)

    if dated is None:
        return None

    try:
        return date(*(int(part) for part in dated.groups()))
    except ValueError:
        return None


def _installed_js_runtimes(js_runtime_path: str | None = None) -> dict:
    """Every runtime yt-dlp knows of that is actually on this machine.

    Looked for where playback looks, rather than on PATH alone. Inside
    a snap or a flatpak those are not the same set of places at all,
    and a checkup that searched the smaller one would report nothing
    installed while the pane beside it played.
    """

    enabled = ytdl_js_runtimes(js_runtime_path)

    found = {}

    for name, runtime_class in supported_js_runtimes.value.items():
        info = runtime_class(path=enabled.get(name, {}).get("path")).info

        if info is not None:
            found[name] = info

    return found


class _QuietLogger:
    """Somewhere for yt-dlp to talk that is not the console."""

    def debug(self, message):
        """Nothing here is worth a line of its own."""

    info = warning = error = debug


def _with_note(check_result: CheckResult, note: str) -> CheckResult:
    """The same result with something added to the end of its hint."""

    if not note:
        return check_result

    hint = " ".join(part for part in (check_result.hint, note) if part)

    return dataclasses.replace(check_result, hint=hint)


def _barren_folder_note(js_runtime_path: str | None = None) -> str:
    """Whether a folder was named on the settings page and answered for nothing.

    Naming one is the last resort, reached when an engine is somewhere
    nothing else looks, so a name that turns out to hold none of them
    is almost always a typo or the wrong folder. Without this the page
    is simply ignored: a runtime found elsewhere hides the mistake, and
    where there is none the report says nothing was found anywhere,
    which is true and says nothing about the one thing that was asked
    for by hand.

    A folder is only looked for by the names the engines ship under, so
    a binary renamed to something else is the other way to land here.
    """

    named = configured_dir(js_runtime_path)

    if named is None:
        return ""

    answered_here = any(
        Path(config["path"]).parent == named
        for config in ytdl_js_runtimes(js_runtime_path).values()
        if config
    )

    if answered_here:
        return ""

    return _t(
        "Nothing named deno, node, qjs or bun is in {FOLDER}, which this"
        " page is pointing at."
    ).format(FOLDER=named)


def _runtime_path(info) -> str:
    """Where the engine actually is, spelled out.

    Off Windows, yt-dlp leaves a runtime it expects to find on PATH as
    the bare name it will call, because that is all exec needs. It is
    not all a person needs: the reason for printing the path at all is
    to settle which of several copies is the one running, and "deno"
    settles nothing.
    """

    path = str(info.path)

    if Path(path).is_absolute():
        return path

    return shutil.which(path) or path


def _runtime_list(infos) -> str:
    return ", ".join(f"{info.name} {info.version}" for info in infos)


def _minimum_version_hint(too_old: dict) -> str:
    wanted = ", ".join(
        f"{name} {_version_text(supported_js_runtimes.value[name])}" for name in too_old
    )

    return _t("yt-dlp needs {WANTED} or newer.").format(WANTED=wanted)


def _version_text(runtime_class) -> str:
    return ".".join(str(part) for part in runtime_class.MIN_SUPPORTED_VERSION)


def _youtube_domains(jar) -> list[tuple[str, int]]:
    """The hosts in the jar that belong to YouTube, and how many each has."""

    counts = {}

    for cookie in jar or ():
        if _is_youtube_domain(cookie.domain):
            counts[cookie.domain] = counts.get(cookie.domain, 0) + 1

    return sorted(counts.items())


def _is_youtube_domain(domain: str) -> bool:
    host = domain.lstrip(".")

    return any(
        host == site or host.endswith(f".{site}") for site in YOUTUBE_COOKIE_SITES
    )


def _sample_format(video_info):
    """The cheapest format worth proving the site will serve.

    A plain file is what the fetch is meant to test; a playlist address
    answers with text and says nothing about the media behind it. The
    smallest one going is enough, and costs the least to ask for.
    """

    candidates = [
        fmt
        for fmt in video_info.get("formats") or []
        if fmt.get("url") and fmt.get("protocol") in {"http", "https"}
    ]

    if not candidates:
        return None

    return min(candidates, key=lambda fmt: fmt.get("tbr") or float("inf"))


def _format_name(sample_format) -> str:
    return sample_format.get("format_id") or sample_format.get("ext") or "?"


def _resolve_failure(message: str) -> CheckResult:
    """Say what a yt-dlp error means where its wording is a known one."""

    if "not a bot" in message or "Sign in to confirm" in message:
        return CheckResult(
            CheckStatus.FAILED,
            message,
            _t(
                "YouTube wants a signed-in session from this address."
                " Import YouTube cookies on this page, exported from a"
                " private window. See {URL}"
            ).format(URL=COOKIES_WIKI_URL),
        )

    if "Video unavailable" in message or "Private video" in message:
        return CheckResult(
            CheckStatus.FAILED,
            message,
            _t(
                "The video this checkup uses may have been taken down or"
                " blocked where you are, which says nothing about your"
                " own links."
            ),
        )

    return CheckResult(CheckStatus.FAILED, message)


def _fetch_failure(status: int, sample_format) -> CheckResult:
    summary = _t("The stream answered HTTP {STATUS} for {FORMAT}").format(
        STATUS=status, FORMAT=_format_name(sample_format)
    )

    if status != HTTP_FORBIDDEN:
        return CheckResult(CheckStatus.FAILED, summary)

    return CheckResult(
        CheckStatus.FAILED,
        summary,
        _t(
            "The address resolved but the site refused to serve it. That is"
            " usually an address signed by a player script that could not be"
            " run, or cookies belonging to a different address than the one"
            " asking. Check the JavaScript runtime above."
        ),
    )


def _last_line(message: str) -> str:
    """The part of a yt-dlp error that says what happened.

    It prefixes its errors with ERROR: and the extractor that raised
    them, and follows the sentence that matters with command line flags
    to pass and pages to go and read. None of that is any use in a
    dialog that has a hint of its own underneath, and a paragraph of it
    buries the one sentence somebody needs to see.
    """

    line = _clean_message(message.strip().splitlines()[-1])
    line = line.removeprefix("ERROR:").strip()

    said = CLI_ADVICE_PATTERN.split(line, maxsplit=1)[0].strip()

    return said or line


def _clean_message(message: str) -> str:
    plain = TERMINAL_SEQUENCE_PATTERN.sub("", str(message))

    return re.sub(r"\s+", " ", plain).strip()
