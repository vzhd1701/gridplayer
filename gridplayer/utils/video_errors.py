"""Why a video would not play, as its cell says it and its Details window
tells it in full: from what a resolver raised finding it behind its link,
what the stream proxy was answered fetching it, what mpv said opening it,
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

# an HTTP status in what mpv said, fetching a link itself: "HTTP 404",
# "HTTP/1.1 403 Forbidden", "status 410"
_PLAYER_HTTP_STATUS = re.compile(
    r"\b(?:HTTP(?:/\d(?:\.\d)?)?|status)\D{0,12}([45]\d\d)\b"
)

# how many of the errors under the one raised are told in the details
_CHAIN_TOLD = 6

# answered the same however soon they are asked again
_LASTING_STATUSES = frozenset(
    {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.METHOD_NOT_ALLOWED,
        HTTPStatus.GONE,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS,
    }
)
_LASTING_KINDS = frozenset(
    {
        ReadErrorKind.BLOCKED,
        ReadErrorKind.GONE,
        ReadErrorKind.EMPTY,
        ReadErrorKind.NOT_A_LIST,
        ReadErrorKind.MISSING,
        ReadErrorKind.NO_ACCESS,
    }
)


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
    # as raised, and what mpv said
    raw: str = ""
    is_network: bool = False
    # whether a reload might be answered otherwise: not for a video gone,
    # refused or with nothing there to play
    is_retryable: bool = True
    # a site turning requests away, too many or from a bot: the next video
    # asked of it is likely to be too
    is_refused: bool = False
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


def is_refused_read(read: ReadError) -> bool:
    if read.kind is ReadErrorKind.HTTP:
        return read.status == HTTPStatus.TOO_MANY_REQUESTS

    return read.kind is ReadErrorKind.BLOCKED


def is_retryable_read(read: ReadError) -> bool:
    if read.kind is ReadErrorKind.HTTP:
        return read.status not in _LASTING_STATUSES

    return read.kind not in _LASTING_KINDS


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
        is_retryable=is_retryable_read(read),
        is_refused=is_refused_read(read),
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
        is_retryable=False,
    )


def unresolved_error(url: str) -> ShownError:
    return ShownError(
        title=translate("Video Error", "Couldn't find the video"),
        about=translate("Video Error", "No resolver could open this link."),
        where=where_link_txt(),
        code=translate("Video Error", "Unsupported"),
        host=host_of(url),
        is_retryable=False,
    )


def empty_link_list_error(url: str) -> ShownError:
    return ShownError(
        title=translate("Video Error", "This link is a playlist"),
        about=translate("Video Error", "There's nothing on it to play."),
        where=where_link_txt(),
        code=translate("Video Error", "Empty"),
        host=host_of(url),
        is_retryable=False,
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


def proxy_error(
    failure: ProxyFailure, player_lines: tuple[str, ...] = ()
) -> ShownError:
    host = host_of(failure.url)

    raw_lines = [f"{failure.url}"]

    if failure.status is not None:
        raw_lines.append(http_code_full_txt(failure.status, failure.reason))

    if failure.error:
        raw_lines.append(failure.error)

    raw_lines.extend(_player_said_lines(player_lines))

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


def _player_said_lines(player_lines: tuple[str, ...]) -> list[str]:
    """What mpv said, set apart under the rest of the raw text."""

    if not player_lines:
        return []

    return ["", translate("Video Error", "mpv errors:"), *player_lines]


def player_error(
    message: str, player_lines: tuple[str, ...] = (), url: str = ""
) -> ShownError:
    """mpv could not play it, by what it said: an HTTP status where it
    fetched a link itself and was turned away."""

    raw = "\n".join((message, *_player_said_lines(player_lines)))

    status = _player_http_status(player_lines)

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
            is_retryable=status not in _LASTING_STATUSES,
            is_refused=status == HTTPStatus.TOO_MANY_REQUESTS,
        )

    return ShownError(
        title=message,
        about=_first_player_line(player_lines),
        where=where_player_txt(),
        code="mpv",
        host=host_of(url),
        raw=raw,
    )


def _player_http_status(player_lines: tuple[str, ...]) -> int | None:
    for line in player_lines:
        found = _PLAYER_HTTP_STATUS.search(line)

        if found is not None:
            return int(found.group(1))

    return None


def _first_player_line(player_lines: tuple[str, ...]) -> str:
    """The first thing mpv said, without the module it said it in."""

    for line in player_lines:
        _, _, said = line.partition(": ")
        said = (said or line).strip()

        if said:
            return said

    return ""
