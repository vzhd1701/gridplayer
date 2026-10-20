"""Network failures said in one line of the log.

A connection that timed out or a site that answered 403 is the network's
doing, not the app's, and its traceback -- urllib3 under requests under
Streamlink or yt-dlp, each wrapping the one before -- says nothing that
the kind of failure and the host it came from do not. Anything else is
still logged with its traceback: that one may be a bug of ours.

Told apart the way the List window tells them apart; see list_errors.
"""

import logging
from http import HTTPStatus

from gridplayer.utils.list_errors import (
    ReadErrorKind,
    error_chain,
    host_of,
    read_error_of,
)

_SAID = {
    ReadErrorKind.PROXY: "proxy failed",
    ReadErrorKind.CERTIFICATE: "certificate not trusted",
    ReadErrorKind.SECURE: "secure connection failed",
    ReadErrorKind.DNS: "host not found",
    ReadErrorKind.TIMEOUT: "timed out",
    ReadErrorKind.REFUSED: "connection refused",
    ReadErrorKind.LOST: "connection lost",
    ReadErrorKind.CONNECTION: "could not connect",
    ReadErrorKind.BLOCKED: "turned away by the site",
}


def network_failure_txt(error: BaseException) -> str | None:
    """What went wrong on the way, and with which host, in a few words;
    None for anything that is not a network failure."""

    read = read_error_of(error, None)

    if read.kind is ReadErrorKind.HTTP:
        said = f"HTTP {read.status}"

        try:
            said = f"{said} {HTTPStatus(read.status).phrase}"
        except ValueError:
            pass

    elif read.kind in _SAID:
        said = _SAID[read.kind]

    else:
        return None

    host = _failed_host(error)

    return f"{said} ({host})" if host else said


def failure_txt(error: BaseException) -> str:
    """The error as a log line says it: a network failure in a few words,
    anything else as it was raised."""

    return network_failure_txt(error) or str(error)


def log_failure(
    log: logging.Logger, what: str, error: BaseException, level=logging.ERROR
) -> None:
    """Log what failed: a network failure in one line, at most a warning,
    anything else at this level with its traceback."""

    said = network_failure_txt(error)

    if said is None:
        log.log(level, what, exc_info=error)
    else:
        log.log(min(level, logging.WARNING), f"{what}: {said}")


def _failed_host(error: BaseException) -> str:
    """The host the failure came from: the one that answered, where one
    did, which is the one a redirect went to."""

    for each in error_chain(error):
        for held in ("response", "request"):
            host = host_of(getattr(getattr(each, held, None), "url", None))

            if host:
                return host

        # urllib3's, which keep the connection or its pool and not the URL;
        # a connection that timed out, only among what it was raised with.
        # Its pool asked for only where there is no connection: on those
        # that have one it is a deprecated name for it
        conn = getattr(each, "conn", None) or getattr(each, "pool", None)
        held = (conn, *each.args)

        for each_held in held:
            host = getattr(each_held, "host", None)

            if isinstance(host, str) and host:
                return host

    return ""
