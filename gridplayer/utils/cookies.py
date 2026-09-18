"""Cookies handed to the URL resolvers and to the stream proxy.

A single Netscape cookies.txt kept next to settings.ini is the only place
cookies live. Both yt-dlp and Streamlink read that format natively, so one
jar covers the resolvers, the probes that tell a live stream from a
recorded one, and the proxy that fetches the segments.

Cookies are credentials: nothing in here ever logs a value, only how many
there are and which hosts they belong to.
"""

import contextlib
import io
import json
import logging
import os
import re
import threading
import time
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from http.cookiejar import (
    HTTPONLY_ATTR,
    HTTPONLY_PREFIX,
    Cookie,
    MozillaCookieJar,
)
from pathlib import Path

from gridplayer.settings import Settings
from gridplayer.utils.app_dir import get_app_data_dir

COOKIE_FILE_NAME = "cookies.txt"

_log = logging.getLogger(__name__)

_STORE = None
_STORE_LOCK = threading.Lock()

NETSCAPE_MAGIC = "# Netscape HTTP Cookie File"

NETSCAPE_HEADER = (
    f"{NETSCAPE_MAGIC}\n"
    "# Written by GridPlayer. Anything here is a login; treat it as one.\n"
    "\n"
)

# what a jar read out of a string calls itself when it will not parse
TEXT_SOURCE_NAME = "<text>"

# domain, include subdomains, path, secure, expires, name, value
NETSCAPE_FIELDS = 7

# what a session cookie's expiry looks like on the way out; the stdlib
# leaves the field empty, everything else in the ecosystem writes 0
SESSION_EXPIRY = "0"

EXPIRY_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?")

# how many URLs are worth remembering the answer for; one source being
# resolved asks about a handful, and a grid asks about one source at a time
CACHED_COOKIE_ANSWERS = 128

# what an exported cookie may call the moment it lapses
EXPIRY_KEYS = ("expirationDate", "expires", "expiry")


class CookieImportError(Exception):
    """Text handed in that no cookie format can be made of."""


@dataclass(frozen=True)
class DomainRow:
    """One host's worth of cookies, as the settings page lists them."""

    domain: str
    count: int
    # the span over which the cookies here that are still good will lapse,
    # both None where none of them is
    expires_from: int | None = None
    expires_to: int | None = None
    # nothing here is any use any more: every dated cookie is in the past
    # and there is no session cookie to fall back on
    is_expired: bool = False


class RewindingBuffer(io.StringIO):
    """A text buffer yt-dlp can save its jar back into.

    Its jar truncates before writing but never seeks, so a plain StringIO
    leaves the space the old contents took up padded with NULs and what
    comes back out no longer parses. Nothing here is ours: this exists
    for any buffer handed to a YoutubeDL as its cookiefile.
    """

    def truncate(self, size=None):
        if size == 0:
            self.seek(0)

        return super().truncate(size)


class CookieJar(MozillaCookieJar):
    """A Netscape jar that can be read from and written to text as well.

    The stdlib jar only goes by filename, and these are credentials: the
    way round that is not to leave a copy of them in a temp directory.

    Reading stays with the stdlib parser, which has had decades of strange
    cookie files thrown at it. Only the writing is ours, and seven
    tab-separated fields have nowhere much to go wrong. Both ways keep
    session and lapsed cookies, which the stdlib defaults would drop.
    """

    def load_text(self, text: str) -> None:
        """Read cookies out of Netscape text, keeping what is already here.

        A line that makes no sense is dropped rather than taken as reason
        to throw the whole file away. Exports carry the odd broken entry,
        and the cookies around it are still worth having. A file that is
        not a cookie file at all still fails, on the header.
        """

        readable = io.StringIO("".join(_usable_lines(text)))

        self._really_load(
            readable,
            TEXT_SOURCE_NAME,
            ignore_discard=True,
            ignore_expires=True,
        )

        self._adopt_zero_expiry()

    def _adopt_zero_expiry(self) -> None:
        """Read a zero expiry as a session cookie rather than one from 1970.

        Browsers and their add-ons write 0 where the stdlib writes an empty
        field, and the stdlib reads that 0 as a date long past. Left alone,
        every library we hand the jar to would drop those as expired and
        never send them, which is how a login quietly fails.
        """

        for cookie in self:
            if cookie.expires == 0:
                cookie.expires = None
                cookie.discard = True

    def load_path(self, path: Path) -> None:
        """Read a jar off the disk, as UTF-8 rather than whatever the locale says."""

        self.load_text(path.read_text(encoding="utf-8"))

    def dump(self) -> str:
        """The whole jar as Netscape text."""

        buffer = io.StringIO()

        self._write_to(buffer)

        return buffer.getvalue()

    def save_path(self, path: Path) -> None:
        """Write the jar out, readable by its owner and nobody else."""

        opened = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)

        with os.fdopen(opened, "w", encoding="utf-8") as jar_file:
            self._write_to(jar_file)

    def _write_to(self, jar_file) -> None:
        jar_file.write(NETSCAPE_HEADER)

        for cookie in self:
            jar_file.write(_netscape_line(cookie))


class CookieStore:
    """The jar on disk, and the only thing allowed to write to it."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._jar = None
        self._stamp = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def jar(self) -> CookieJar | None:
        """The cookies on disk, or None where there are none to be had."""

        with self._lock:
            self._refresh()

            return self._jar

    @property
    def is_empty(self) -> bool:
        return jar_or_none(self.jar) is None

    def dump(self) -> str:
        """The jar as Netscape text, to hand to a library that wants its own."""

        with self._lock:
            jar = self.jar

            if jar is None:
                return ""

            return jar.dump()

    def merge(self, dumped: str) -> int:
        """Take new values for cookies already held here, and nothing else.

        yt-dlp hands back the whole jar it was given, so a plain merge would
        restore a domain that was deleted while a resolve was in flight, and
        would let any host it followed on the way deposit cookies of its own
        in a file full of logins. Only what is already here gets refreshed.

        Returns how many cookies changed.
        """

        incoming = {_cookie_key(c): c for c in _cookies_from_dump(dumped)}

        if not incoming:
            return 0

        with self._lock:
            jar = self.jar

            if jar is None:
                return 0

            refreshed = [cookie for cookie in jar if _refresh_cookie(cookie, incoming)]

            if not refreshed:
                return 0

            self._write(jar)

            _log.debug(
                f"Refreshed {len(refreshed)} cookie(s)"
                f" for {len(_domains(refreshed))} domain(s)"
            )

            return len(refreshed)

    def save(self, jar: CookieJar) -> None:
        """Replace what is stored with this jar."""

        with self._lock:
            self._write(jar)

    def clear(self) -> None:
        """Take the jar off the disk entirely, rather than leaving it empty."""

        with self._lock:
            with contextlib.suppress(OSError):
                self._path.unlink(missing_ok=True)

            self._jar = None
            self._stamp = None

    def _write(self, jar: CookieJar) -> None:
        tmp_path = self._path.with_name(f"{self._path.name}.tmp")

        self._path.parent.mkdir(parents=True, exist_ok=True)

        jar.save_path(tmp_path)

        tmp_path.replace(self._path)

        # a write of our own is never missed, whatever the clock says
        self._jar = jar
        self._stamp = _file_stamp(self._path)

    def _refresh(self) -> None:
        """Pick up a file somebody changed behind our back.

        Writes made here keep the cache current by themselves, so this only
        has to notice the file being edited or replaced from outside.
        """

        stamp = _file_stamp(self._path)

        if stamp is not None and stamp == self._stamp:
            return

        self._stamp = stamp
        self._jar = _load(self._path) if stamp is not None else None


def cookie_store() -> CookieStore:
    global _STORE

    with _STORE_LOCK:
        if _STORE is None:
            _STORE = CookieStore(get_app_data_dir() / COOKIE_FILE_NAME)

    return _STORE


def jar_or_none(jar) -> CookieJar | None:
    """An empty jar and no jar at all come to the same thing."""

    return jar if jar is not None and len(jar) else None


def cookie_jar() -> CookieJar | None:
    """The cookies to play with, where there are any and they are switched on."""

    if not Settings().get("cookies/enabled"):
        return None

    return jar_or_none(cookie_store().jar)


def has_cookies_for(url: str) -> bool:
    """Whether the jar holds anything that would be sent to this URL.

    Asked once per format while a source is being resolved, so the
    answer is kept until the store changes underneath it: walking a jar
    exported out of a browser costs a millisecond or so, and a grid of
    videos would pay it a few hundred times over for nothing.
    """

    return _has_cookies_for(cookies_stamp(), url)


@lru_cache(maxsize=CACHED_COOKIE_ANSWERS)
def _has_cookies_for(stamp, url: str) -> bool:
    """Whether a jar in this state would send anything to this URL.

    The stamp is what the answer is good for rather than anything this
    needs: a jar written to, switched off or swapped out is a different
    jar, and answers for itself.
    """

    jar = cookie_jar()

    if jar is None:
        return False

    request = urllib.request.Request(url)

    jar.add_cookie_header(request)

    return request.get_header("Cookie") is not None


def apply_to_streamlink(session) -> None:
    """Give a Streamlink session the stored cookies, and only those.

    What the session held is cleared first, so applying this again once
    the store has been edited leaves the session with what is stored now
    rather than the union of that and what was stored before. A cookie
    the host set along the way goes too, and is set again by the next
    response that cares.

    Streamlink reads cookies and never writes them: there is no save
    counterpart to set_cookies_from_file, so whatever a site sets during a
    session stays in that session's jar and goes when it does. Only the
    yt-dlp side can put anything back, see ytdl_cookies.
    """

    session.http.cookies.clear()

    jar = cookie_jar()

    if jar is None:
        return

    session.http.cookies.update(jar)


def cookies_stamp() -> tuple | None:
    """Which jar is in use and what state it is in.

    Cheap enough to ask before every request: a stat of the file, where
    it is, and the setting that decides whether any of it counts. None
    where the cookies would not be used at all, so switching them off
    reads as a change like any other.
    """

    if not Settings().get("cookies/enabled"):
        return None

    path = cookie_store().path

    return str(path), _file_stamp(path)


@contextlib.contextmanager
def ytdl_cookies():
    """Cookie options for a YoutubeDL, keeping what it refreshes.

    yt-dlp saves its jar back on close, so it is handed a buffer rather than
    the file itself: nothing it does can damage the store, and what comes
    back out is merged in on our terms, or dropped when the setting says so.
    """

    jar = cookie_jar()

    if jar is None:
        yield {}
        return

    buffer = RewindingBuffer(cookie_store().dump())

    try:
        yield {"cookiefile": buffer}
    finally:
        if Settings().get("cookies/allow_update"):
            cookie_store().merge(buffer.getvalue())


def domain_summary(jar, now: float | None = None) -> list[DomainRow]:
    """The jar as one row per host, in an order that keeps kin together.

    Sorting on the labels backwards puts google.com next to
    accounts.google.com, which is as close to grouping a login as can be
    managed without a public suffix list to say where a site begins.
    """

    by_domain = {}

    for cookie in jar or ():
        by_domain.setdefault(cookie.domain, []).append(cookie)

    now = time.time() if now is None else now

    rows = [
        _domain_row(domain, domain_cookies, now)
        for domain, domain_cookies in by_domain.items()
    ]

    return sorted(rows, key=lambda row: _domain_sort_key(row.domain))


def parse_cookies(text: str) -> CookieJar:
    """Read cookies out of whatever was handed over.

    A cookies.txt and what a browser extension copies to the clipboard are
    the two things people actually have, so both are taken.
    """

    text = text.strip()

    if not text:
        raise CookieImportError("There is nothing there to import")

    jar = _parse_json(text) if text[0] in {"[", "{"} else _parse_netscape(text)

    if not len(jar):
        raise CookieImportError("No cookies could be read out of that")

    return jar


def same_cookies(jar, other) -> bool:
    """Whether two jars hold the same cookies, values and all.

    Saving is skipped when they do, so that closing the settings dialog
    does not rewrite a file full of logins for no reason.
    """

    return _fingerprint(jar) == _fingerprint(other)


def merged_with(jar, incoming) -> CookieJar:
    """Add one jar to another, so several sites can be built up over time."""

    merged = CookieJar()

    for cookie in jar or ():
        merged.set_cookie(cookie)

    for cookie in incoming or ():
        merged.set_cookie(cookie)

    return merged


def without_domains(jar, domains) -> CookieJar:
    """The jar with these hosts taken out of it."""

    unwanted = set(domains)
    kept = CookieJar()

    for cookie in jar or ():
        if cookie.domain not in unwanted:
            kept.set_cookie(cookie)

    return kept


def _load(path: Path) -> CookieJar | None:
    jar = CookieJar()

    try:
        jar.load_path(path)
    except Exception as e:
        _log.warning(f"Could not read cookies from {path}: {e}")
        return None

    _log.debug(f"Loaded {len(jar)} cookie(s) for {len(_domains(jar))} domain(s)")

    return jar


def _cookies_from_dump(dumped: str) -> tuple:
    if not dumped.strip():
        return ()

    jar = CookieJar()

    try:
        jar.load_text(dumped)
    except Exception as e:
        _log.warning(f"Could not read back cookies: {e}")
        return ()

    return tuple(jar)


def _refresh_cookie(cookie, incoming: dict) -> bool:
    """Bring one cookie up to date, saying whether that changed anything."""

    fresh = incoming.get(_cookie_key(cookie))

    if fresh is None:
        return False

    if (fresh.value, fresh.expires) == (cookie.value, cookie.expires):
        return False

    cookie.value = fresh.value
    cookie.expires = fresh.expires

    return True


def _parse_netscape(text: str) -> CookieJar:
    # The stdlib parser wants the line naming the format first and will take
    # nothing else, while text off the clipboard usually has no header at all
    # and an export often leads with a comment of its own. Putting one in
    # front unconditionally covers both: a header already there is only a
    # comment on the line below, which the parser skips.
    jar = CookieJar()

    try:
        jar.load_text(f"{NETSCAPE_MAGIC}\n{text}\n")
    except Exception as e:
        raise CookieImportError(f"That is not a cookies.txt file: {e}") from e

    return jar


def _parse_json(text: str) -> CookieJar:
    try:
        parsed = json.loads(text)
    except ValueError as e:
        raise CookieImportError(f"That is not valid JSON: {e}") from e

    if isinstance(parsed, dict):
        parsed = parsed.get("cookies", [])

    if not isinstance(parsed, list):
        raise CookieImportError("That JSON does not hold a list of cookies")

    jar = CookieJar()

    for entry in parsed:
        cookie = _cookie_from_mapping(entry)

        if cookie is not None:
            jar.set_cookie(cookie)

    return jar


def _cookie_from_mapping(entry) -> Cookie | None:
    """One cookie out of what a browser extension exports, where it has one."""

    if not isinstance(entry, dict):
        return None

    domain = str(entry.get("domain") or "").strip()
    name = entry.get("name")

    if not domain or not name:
        return None

    expires = _expiry_of(entry)
    has_dot = domain.startswith(".")

    return Cookie(
        version=0,
        name=str(name),
        value=str(entry.get("value") or ""),
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=has_dot,
        domain_initial_dot=has_dot,
        path=str(entry.get("path") or "/"),
        path_specified=True,
        secure=bool(entry.get("secure")),
        expires=expires,
        discard=expires is None,
        comment=None,
        comment_url=None,
        rest={},
    )


def _expiry_of(entry) -> int | None:
    for key in EXPIRY_KEYS:
        with contextlib.suppress(TypeError, ValueError):
            if entry.get(key):
                return int(float(entry[key]))

    return None


def _domain_row(domain: str, cookies, now: float) -> DomainRow:
    """Sum up one host's cookies by when the good ones run out.

    Only the ones still standing are counted. A browser export routinely
    carries a few that lapsed minutes before it was taken, and going by
    those would report a login dead the moment it was saved.
    """

    live = sorted(
        cookie.expires for cookie in cookies if cookie.expires and cookie.expires > now
    )

    if live:
        return DomainRow(
            domain=domain,
            count=len(cookies),
            expires_from=live[0],
            expires_to=live[-1],
        )

    # a session cookie has no date to be past, so it is still worth something
    has_session = any(not cookie.expires for cookie in cookies)

    return DomainRow(domain=domain, count=len(cookies), is_expired=not has_session)


def _domain_sort_key(domain: str) -> tuple:
    return tuple(reversed(domain.lstrip(".").split(".")))


def _fingerprint(jar) -> set:
    return {(*_cookie_key(c), c.value, c.expires) for c in jar or ()}


def _usable_lines(text: str):
    """The lines of a cookie file that stand a chance of parsing.

    The stdlib parser gives up on the whole file at the first line it
    cannot split, so the broken ones are held back from it here. What was
    on a dropped line is never logged: it is somebody's login.
    """

    for line in io.StringIO(text):
        if _is_usable_line(line):
            yield line
        else:
            _log.debug("Skipping a cookie file line that does not parse")


def _is_usable_line(line: str) -> bool:
    body = line.removeprefix(HTTPONLY_PREFIX)

    # comments and blank lines are the parser's business, not ours
    if body.startswith("#") or not body.strip():
        return True

    fields = body.rstrip("\n").split("\t")

    if len(fields) != NETSCAPE_FIELDS:
        return False

    expires = fields[4]

    return not expires or bool(EXPIRY_PATTERN.fullmatch(expires))


def _netscape_line(cookie) -> str:
    """One cookie as the seven tab-separated fields the format asks for."""

    domain = cookie.domain

    if cookie.has_nonstandard_attr(HTTPONLY_ATTR):
        domain = HTTPONLY_PREFIX + domain

    name, value = cookie.name, cookie.value

    # the file format reads "Set-Cookie: foo" as a cookie with no name,
    # where http.cookiejar reads it as one with no value
    if value is None:
        name, value = "", cookie.name

    fields = (
        domain,
        _true_or_false(cookie.domain.startswith(".")),
        cookie.path,
        _true_or_false(cookie.secure),
        SESSION_EXPIRY if cookie.expires is None else str(cookie.expires),
        name,
        value,
    )

    return "\t".join(fields) + "\n"


def _true_or_false(flag) -> str:
    return "TRUE" if flag else "FALSE"


def _cookie_key(cookie) -> tuple:
    return cookie.domain, cookie.path, cookie.name


def _domains(cookies) -> set:
    return {cookie.domain for cookie in cookies}


def _file_stamp(path: Path) -> tuple | None:
    try:
        file_stat = path.stat()
    except OSError:
        return None

    return file_stat.st_mtime_ns, file_stat.st_size
