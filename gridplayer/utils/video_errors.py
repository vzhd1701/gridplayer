"""Why a video would not play, as its cell says it and its Details window
tells it in full: from what a resolver raised finding it behind its link,
what the stream proxy was answered fetching it, what VLC said opening it,
or the file itself gone. A list that could not be read is told the same
way in the List window.
"""

import dataclasses
import re
import time
from dataclasses import dataclass, field
from http import HTTPStatus

from gridplayer.models.media_list import ListSource
from gridplayer.params.static import ListSourceKind
from gridplayer.utils.error_txts import (
    error_tag,
    http_code_txt,
    http_error_txts,
    read_error_txts,
    where_link_txt,
    where_player_txt,
    where_server_txt,
)
from gridplayer.utils.list_errors import (
    ReadError,
    ReadErrorKind,
    error_chain,
    host_of,
    read_error_of,
)
from gridplayer.utils.qt import translate

# an HTTP status in what VLC said, fetching a link itself: "HTTP 404",
# "HTTP/1.1 403 Forbidden", "status 410"
_VLC_HTTP_STATUS = re.compile(r"\b(?:HTTP(?:/\d(?:\.\d)?)?|status)\D{0,12}([45]\d\d)\b")

# how many of the errors under the one raised are told in the details
_CHAIN_TOLD = 6


@dataclass(frozen=True)
class ShownError:
    """What went wrong, as it is shown: a few words, a line on what that
    means, where it broke and its code for the tag, and in full for the
    Details window."""

    title: str
    about: str = ""
    where: str = ""
    code: str = ""
    # the code in full, with the server's words: "HTTP 429 Too Many Requests"
    code_full: str = ""
    host: str = ""
    # as raised, and what VLC said
    raw: str = ""
    is_network: bool = False
    # when, not what: the same thing gone wrong again is the same error
    at: float = field(default_factory=time.time, compare=False)

    @property
    def icon(self) -> str:
        return "network-error" if self.is_network else "error"


def http_code_full_txt(status: int, reason: str = "") -> str:
    if not reason:
        try:
            reason = HTTPStatus(status).phrase
        except ValueError:
            reason = ""

    return f"{http_code_txt(status)} {reason}".strip()


def read_code_full_txt(read: ReadError) -> str:
    """Its code as the Details window says it: an HTTP status with what it
    means."""

    if read.kind is ReadErrorKind.HTTP and read.status is not None:
        return http_code_full_txt(read.status)

    return error_tag(read)[1]


def shown_read_error(
    read: ReadError, raw: str | None = None, is_video: bool = True
) -> ShownError:
    """Why a video behind a link, or a list, could not be read; told in full
    as raised, unless what to tell is given."""

    title, about = read_error_txts(read, is_video=is_video)
    where, code = error_tag(read)

    return ShownError(
        title=title,
        about=about,
        where=where,
        code=code,
        code_full=read_code_full_txt(read),
        host=read.host,
        raw=read.raw if raw is None else raw,
        is_network=read.is_network,
    )


def chain_txt(error: BaseException) -> str:
    """The error raised and the ones under it, each on its line."""

    lines = []

    for each in error_chain(error)[:_CHAIN_TOLD]:
        said = str(each).strip()
        name = type(each).__name__

        line = f"{name}: {said}" if said else name

        if line not in lines:
            lines.append(line)

    return "\n".join(lines)


def resolve_error(error: BaseException, url: str) -> ShownError:
    """A resolver could not find the video behind the link."""

    read = read_error_of(error, ListSource(kind=ListSourceKind.URL, location=url))

    return shown_read_error(read, chain_txt(error))


def stream_offline_error(url: str) -> ShownError:
    return ShownError(
        title=translate("Video Error", "Stream is offline"),
        about=translate("Video Error", "Nothing is streaming right now."),
        where=where_server_txt(),
        code=translate("Video Error", "Offline"),
        host=host_of(url),
    )


def unresolved_error(url: str) -> ShownError:
    return ShownError(
        title=translate("Video Error", "Couldn't find the video"),
        about=translate("Video Error", "No resolver could open this link."),
        where=where_link_txt(),
        code=translate("Video Error", "Unsupported"),
        host=host_of(url),
    )


def empty_link_list_error(url: str) -> ShownError:
    return ShownError(
        title=translate("Video Error", "This link is a playlist"),
        about=translate("Video Error", "There's nothing on it to play."),
        where=where_link_txt(),
        code=translate("Video Error", "Empty"),
        host=host_of(url),
    )


def file_error(kind: ReadErrorKind, path) -> ShownError:
    """The file gone, or not to be opened."""

    read = ReadError(kind=kind, raw=str(path), source_kind=ListSourceKind.FILE)

    return shown_read_error(read, str(path))


@dataclass(frozen=True)
class ProxyFailure:
    """What the stream proxy ran into fetching a stream for VLC: the
    server's answer, or what broke on the way to it."""

    url: str
    status: int | None = None
    reason: str = ""
    error: str = ""
    kind: ReadErrorKind | None = None
    at: float = field(default_factory=time.monotonic)


def proxy_error(failure: ProxyFailure, vlc_lines: tuple[str, ...] = ()) -> ShownError:
    host = host_of(failure.url)

    raw_lines = [f"{failure.url}"]

    if failure.status is not None:
        raw_lines.append(http_code_full_txt(failure.status, failure.reason))

    if failure.error:
        raw_lines.append(failure.error)

    raw_lines.extend(_vlc_said_lines(vlc_lines))

    raw = "\n".join(raw_lines)

    if failure.status is not None:
        read = ReadError(kind=ReadErrorKind.HTTP, raw=raw, status=failure.status)
        return dataclasses.replace(
            shown_read_error(read, raw),
            host=host,
            code_full=http_code_full_txt(failure.status, failure.reason),
        )

    read = ReadError(
        kind=failure.kind or ReadErrorKind.CONNECTION,
        raw=failure.error,
        source_kind=ListSourceKind.URL,
        host=host,
    )

    return shown_read_error(read, raw)


def _vlc_said_lines(vlc_lines: tuple[str, ...]) -> list[str]:
    """What VLC said, set apart under the rest of the raw text."""

    if not vlc_lines:
        return []

    return ["", translate("Video Error", "VLC errors:"), *vlc_lines]


def player_error(
    message: str, vlc_lines: tuple[str, ...] = (), url: str = ""
) -> ShownError:
    """VLC could not play it, by what it said: an HTTP status where it
    fetched a link itself and was turned away."""

    raw = "\n".join((message, *_vlc_said_lines(vlc_lines)))

    status = _vlc_http_status(vlc_lines)

    if status is not None:
        title, about = http_error_txts(status)

        return ShownError(
            title=title,
            about=about,
            where=where_server_txt(),
            code=http_code_txt(status),
            code_full=http_code_full_txt(status),
            host=host_of(url),
            raw=raw,
        )

    return ShownError(
        title=message,
        about=_first_vlc_line(vlc_lines),
        where=where_player_txt(),
        code="VLC",
        host=host_of(url),
        raw=raw,
    )


def _vlc_http_status(vlc_lines: tuple[str, ...]) -> int | None:
    for line in vlc_lines:
        found = _VLC_HTTP_STATUS.search(line)

        if found is not None:
            return int(found.group(1))

    return None


def _first_vlc_line(vlc_lines: tuple[str, ...]) -> str:
    """The first thing VLC said, without the module it said it in."""

    for line in vlc_lines:
        _, _, said = line.partition(": ")
        said = (said or line).strip()

        if said:
            return said

    return ""
