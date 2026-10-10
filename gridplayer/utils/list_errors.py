"""Why a list could not be read from its source, told apart for the List
window to say plainly: what the server answered, what went wrong on the
way to it, or what came back.

What is raised comes from the app's own downloads (requests, under a
Streamlink session) or from yt-dlp, each wrapping what went wrong in
errors of its own; the one that says what happened is found by walking
down to it, by the names of its types, so that neither has to be imported
to be told apart.
"""

import urllib.parse
from dataclasses import dataclass
from enum import Enum, auto

from gridplayer.models.media_list import ListSource
from gridplayer.params.static import ListSourceKind

# what a site says when it will not answer for now, rather than that what
# was asked for is not there: too many asked for too quickly
SITE_REFUSALS = (
    "HTTP Error 429",
    "Too Many Requests",
    "Sign in to confirm",
    "The page needs to be reloaded",
)

# what a site says of a list it will not show at all
_SITE_GONE = (
    "does not exist",
    "is private",
    "private playlist",
    "unavailable",
    "no longer available",
    "has been removed",
    "has been terminated",
)

# the most errors looked at down from the one raised
_MOST_LOOKED_AT = 32

# how much of an error nothing better is known of is said
_RAW_SAID_CHARS = 150


class ReadErrorKind(Enum):
    HTTP = auto()
    PROXY = auto()
    CERTIFICATE = auto()
    SECURE = auto()
    DNS = auto()
    TIMEOUT = auto()
    REFUSED = auto()
    LOST = auto()
    CONNECTION = auto()
    BLOCKED = auto()
    GONE = auto()
    NOT_A_LIST = auto()
    TOO_LARGE = auto()
    EMPTY = auto()
    MISSING = auto()
    NO_ACCESS = auto()
    OTHER = auto()


NETWORK_KINDS = frozenset(
    (
        ReadErrorKind.PROXY,
        ReadErrorKind.CERTIFICATE,
        ReadErrorKind.SECURE,
        ReadErrorKind.DNS,
        ReadErrorKind.TIMEOUT,
        ReadErrorKind.REFUSED,
        ReadErrorKind.LOST,
        ReadErrorKind.CONNECTION,
    )
)

# by the names of the types an error is of, first found first: a proxy
# that could not be reached is the proxy's to say, a timed-out connection
# is a connection error too. Not by urllib3's ConnectTimeoutError: every
# connection it could not open is one, refused or not found.
_KINDS_BY_TYPE = (
    (ReadErrorKind.PROXY, {"ProxyError"}),
    (
        ReadErrorKind.CERTIFICATE,
        {"SSLCertVerificationError", "CertificateVerifyError"},
    ),
    (ReadErrorKind.SECURE, {"SSLError"}),
    (ReadErrorKind.DNS, {"gaierror", "NameResolutionError"}),
    (ReadErrorKind.REFUSED, {"ConnectionRefusedError"}),
    (ReadErrorKind.TIMEOUT, {"TimeoutError", "Timeout", "ReadTimeoutError"}),
    (
        ReadErrorKind.LOST,
        {
            "ConnectionResetError",
            "ConnectionAbortedError",
            "BrokenPipeError",
            "RemoteDisconnected",
            "IncompleteRead",
            "ProtocolError",
            "ChunkedEncodingError",
        },
    ),
    (
        ReadErrorKind.CONNECTION,
        {"ConnectionError", "NewConnectionError", "TransportError"},
    ),
    (ReadErrorKind.TOO_LARGE, {"ListTooLargeError"}),
    (ReadErrorKind.EMPTY, {"EmptyListError"}),
    (
        ReadErrorKind.NOT_A_LIST,
        {"NoListThereError", "NotAListError", "UnsupportedError"},
    ),
)

_LOCAL_KINDS_BY_TYPE = (
    (ReadErrorKind.MISSING, {"FileNotFoundError", "NotADirectoryError"}),
    (ReadErrorKind.NO_ACCESS, {"PermissionError"}),
)

_HTTP_ERROR_TYPES = frozenset(("HTTPStatusError", "HTTPError"))
_SITE_ERROR_TYPES = frozenset(("DownloadError", "ExtractorError"))


@dataclass(frozen=True)
class ReadError:
    """What a list could not be read for: its kind, what is needed to say
    it (the HTTP status, the host, the size it was over), and the error
    itself as it was raised."""

    kind: ReadErrorKind
    raw: str
    source_kind: ListSourceKind | None = None
    status: int | None = None
    host: str = ""
    limit_mb: int | None = None

    @property
    def is_network(self) -> bool:
        return self.kind in NETWORK_KINDS

    @property
    def raw_said(self) -> str:
        """The error as raised, cut short to say where nothing better is
        known of it: its first line."""

        first = self.raw.strip().splitlines()[0] if self.raw.strip() else ""

        if len(first) > _RAW_SAID_CHARS:
            return f"{first[:_RAW_SAID_CHARS].rstrip()}…"

        return first


def is_site_refusal(error: str) -> bool:
    return any(refusal in error for refusal in SITE_REFUSALS)


def read_error_of(error: BaseException, source: ListSource | None) -> ReadError:
    """What the list could not be read for, from what was raised reading it
    from its source."""

    chain = _chain(error)
    raw = str(error)

    source_kind = None if source is None else source.kind
    host = _host_of(source)

    def found(kind, **fields):
        return ReadError(
            kind=kind, raw=raw, source_kind=source_kind, host=host, **fields
        )

    for each in chain:
        status = getattr(each, "status", None)

        if _type_names(each) & _HTTP_ERROR_TYPES and isinstance(status, int):
            return found(ReadErrorKind.HTTP, status=status)

    said = " ".join(str(each) for each in chain)

    if is_site_refusal(said):
        return found(ReadErrorKind.BLOCKED)

    names = set().union(*(_type_names(each) for each in chain))

    if source_kind in (ListSourceKind.FILE, ListSourceKind.FOLDER):
        for kind, kind_names in _LOCAL_KINDS_BY_TYPE:
            if names & kind_names:
                return found(kind)

    for kind, kind_names in _KINDS_BY_TYPE:
        if names & kind_names:
            if kind is ReadErrorKind.TOO_LARGE:
                return found(kind, limit_mb=_limit_mb(chain))

            return found(kind)

    if names & _SITE_ERROR_TYPES and any(gone in said for gone in _SITE_GONE):
        return found(ReadErrorKind.GONE)

    return found(ReadErrorKind.OTHER)


def site_name(host: str) -> str:
    """A host as its site is called: YouTube, or the host itself."""

    from gridplayer.utils.web_lists import YOUTUBE_HOSTS

    if host in YOUTUBE_HOSTS:
        return "YouTube"

    return host.removeprefix("www.")


def _chain(error: BaseException) -> list[BaseException]:
    """The error raised and the ones under it: what it was raised from,
    and what yt-dlp, requests and urllib3 keep of what they wrap."""

    chain = []
    seen = set()
    waiting = [error]

    while waiting and len(chain) < _MOST_LOOKED_AT:
        each = waiting.pop(0)

        if not isinstance(each, BaseException) or id(each) in seen:
            continue

        seen.add(id(each))
        chain.append(each)

        waiting.extend(
            (
                each.__cause__,
                each.__context__,
                getattr(each, "cause", None),
                getattr(each, "reason", None),
            )
        )

        exc_info = getattr(each, "exc_info", None)
        if isinstance(exc_info, tuple) and len(exc_info) > 1:
            waiting.append(exc_info[1])

        waiting.extend(arg for arg in each.args if isinstance(arg, BaseException))

    return chain


def _type_names(error: BaseException) -> set[str]:
    return {cls.__name__ for cls in type(error).__mro__}


def _host_of(source: ListSource | None) -> str:
    if source is None or source.kind != ListSourceKind.URL:
        return ""

    return urllib.parse.urlsplit(str(source.location)).hostname or ""


def _limit_mb(chain) -> int | None:
    for each in chain:
        max_bytes = getattr(each, "max_bytes", None)

        if isinstance(max_bytes, int):
            return max_bytes // 2**20

    return None
