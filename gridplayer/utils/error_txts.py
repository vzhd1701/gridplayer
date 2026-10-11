"""What went wrong reading a list or opening a video, said plainly: a few
words, a line on what that means or what to do, and a tag of two parts,
where it broke (the server, the network, the file) and its code, for the
viewer to tell an HTTP error from a connection that never got there.

Shared by the List window and the cells, so that the same thing gone wrong
is said the same way in both.
"""

from gridplayer.params.static import ListSourceKind
from gridplayer.utils.list_errors import ReadError, ReadErrorKind, site_name
from gridplayer.utils.qt import translate

HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_THERE = frozenset((404, 410))
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERRORS = (500, 600)


def where_server_txt() -> str:
    return translate("Video Error", "Server")


def where_network_txt() -> str:
    return translate("Video Error", "Network")


def where_file_txt() -> str:
    return translate("Video Error", "File")


def where_player_txt() -> str:
    return translate("Video Error", "Player")


def where_list_txt() -> str:
    return translate("Video Error", "List")


def where_link_txt() -> str:
    return translate("Video Error", "Link")


def http_code_txt(status: int) -> str:
    return f"HTTP {status}"


def error_tag(error: ReadError) -> tuple[str, str]:
    """Where it broke, and its code."""

    kind = error.kind

    if kind is ReadErrorKind.HTTP:
        return where_server_txt(), http_code_txt(error.status)

    network_codes = {
        ReadErrorKind.PROXY: translate("Video Error", "Proxy"),
        ReadErrorKind.CERTIFICATE: translate("Video Error", "Certificate"),
        ReadErrorKind.SECURE: "TLS",
        ReadErrorKind.DNS: "DNS",
        ReadErrorKind.TIMEOUT: translate("Video Error", "Timeout"),
        ReadErrorKind.REFUSED: translate("Video Error", "Refused"),
        ReadErrorKind.LOST: translate("Video Error", "Reset"),
        ReadErrorKind.CONNECTION: translate("Video Error", "No connection"),
    }

    if kind in network_codes:
        return where_network_txt(), network_codes[kind]

    if kind is ReadErrorKind.BLOCKED:
        return where_server_txt(), translate("Video Error", "Blocked")

    if kind is ReadErrorKind.GONE:
        return where_server_txt(), translate("Video Error", "Unavailable")

    if kind is ReadErrorKind.MISSING:
        return where_file_txt(), translate("Video Error", "Missing")

    if kind is ReadErrorKind.NO_ACCESS:
        return where_file_txt(), translate("Video Error", "No access")

    list_codes = {
        ReadErrorKind.NOT_A_LIST: translate("Video Error", "Not a list"),
        ReadErrorKind.TOO_LARGE: translate("Video Error", "Too big"),
        ReadErrorKind.EMPTY: translate("Video Error", "Empty"),
    }

    if kind in list_codes:
        return where_list_txt(), list_codes[kind]

    if error.source_kind in (ListSourceKind.FILE, ListSourceKind.FOLDER):
        return where_file_txt(), translate("Video Error", "Error")

    return where_link_txt(), translate("Video Error", "Error")


def read_error_txts(error: ReadError, is_video: bool = False) -> tuple[str, str]:
    """What the list could not be read from its source for, or the video
    found behind a link: a few words, and a line on what that means or what
    to do. The code is the tag's to say, see error_tag."""

    kind = error.kind
    host = error.host

    if kind is ReadErrorKind.HTTP:
        return http_error_txts(error.status)

    if kind is ReadErrorKind.PROXY:
        return (
            translate("Dialog - List", "Proxy error"),
            translate(
                "Dialog - List", "Couldn't connect through the proxy set in Settings."
            ),
        )

    if kind is ReadErrorKind.CERTIFICATE:
        return (
            translate("Dialog - List", "Secure connection failed"),
            translate("Dialog - List", "The site's certificate isn't trusted."),
        )

    if kind is ReadErrorKind.SECURE:
        return (
            translate("Dialog - List", "Secure connection failed"),
            translate(
                "Dialog - List", "Couldn't make a secure connection to {HOST}."
            ).format(HOST=host),
        )

    if kind is ReadErrorKind.DNS:
        return (
            translate("Dialog - List", "Server not found"),
            translate(
                "Dialog - List",
                "Couldn't find {HOST}. Check the link and your internet connection.",
            ).format(HOST=host),
        )

    if kind is ReadErrorKind.TIMEOUT:
        return (
            translate("Dialog - List", "Timed out"),
            translate("Dialog - List", "{HOST} took too long to answer.").format(
                HOST=host
            ),
        )

    if kind is ReadErrorKind.REFUSED:
        return (
            translate("Dialog - List", "Connection refused"),
            translate("Dialog - List", "{HOST} isn't accepting connections.").format(
                HOST=host
            ),
        )

    if kind is ReadErrorKind.LOST:
        return (
            translate("Dialog - List", "Connection lost"),
            translate("Dialog - List", "The connection to {HOST} was cut off.").format(
                HOST=host
            ),
        )

    if kind is ReadErrorKind.CONNECTION:
        return (
            translate("Dialog - List", "Couldn't connect"),
            translate(
                "Dialog - List",
                "Couldn't reach {HOST}. Check your internet connection.",
            ).format(HOST=host),
        )

    if kind is ReadErrorKind.BLOCKED:
        return (
            translate("Dialog - List", "{SITE} is blocking requests").format(
                SITE=site_name(host)
            ),
            translate(
                "Dialog - List", "Try again later, or set up cookies in Settings."
            ),
        )

    if kind is ReadErrorKind.GONE:
        return (
            translate("Dialog - List", "Not found"),
            translate("Dialog - List", "It may be private or deleted."),
        )

    if kind is ReadErrorKind.NOT_A_LIST:
        if error.source_kind == ListSourceKind.FILE:
            about = translate("Dialog - List", "The file isn't a playlist.")
        else:
            about = translate("Dialog - List", "The link didn't return a playlist.")

        return translate("Dialog - List", "Not a playlist"), about

    if kind is ReadErrorKind.TOO_LARGE:
        return (
            translate("Dialog - List", "Playlist too big"),
            translate(
                "Dialog - List",
                "It's over the M3U size limit ({SIZE} MB). You can raise it in"
                " Settings.",
            ).format(SIZE=error.limit_mb),
        )

    if kind is ReadErrorKind.EMPTY:
        return (
            translate("Dialog - List", "Empty playlist"),
            translate("Dialog - List", "The source has nothing to play right now."),
        )

    if kind is ReadErrorKind.MISSING:
        if error.source_kind == ListSourceKind.FOLDER:
            title = translate("Dialog - List", "Folder not found")
        else:
            title = translate("Dialog - List", "File not found")

        return title, translate(
            "Dialog - List", "It may have been moved, renamed or deleted."
        )

    if kind is ReadErrorKind.NO_ACCESS:
        return (
            translate("Dialog - List", "Access denied"),
            translate("Dialog - List", "You don't have permission to open it."),
        )

    if is_video:
        title = translate("Video Error", "Couldn't find the video")
    elif error.source_kind == ListSourceKind.URL:
        title = translate("Dialog - List", "Couldn't download the list")
    else:
        title = translate("Dialog - List", "Couldn't read the list")

    return title, error.raw_said


def http_error_txts(status: int) -> tuple[str, str]:
    if status == HTTP_UNAUTHORIZED:
        return (
            translate("Video Error", "Login needed"),
            translate("Dialog - List", "The server wants a username and password."),
        )

    if status == HTTP_FORBIDDEN:
        return (
            translate("Video Error", "Access denied"),
            translate(
                "Dialog - List", "The server refused. The link may have expired."
            ),
        )

    if status in HTTP_NOT_THERE:
        return (
            translate("Video Error", "Not found"),
            translate("Dialog - List", "The server has nothing at this link."),
        )

    if status == HTTP_TOO_MANY_REQUESTS:
        return (
            translate("Video Error", "Too many requests"),
            translate(
                "Dialog - List",
                "The server is limiting requests. Try again later.",
            ),
        )

    if HTTP_SERVER_ERRORS[0] <= status < HTTP_SERVER_ERRORS[1]:
        return (
            translate("Video Error", "Server error"),
            translate(
                "Dialog - List",
                "The problem is on the server's side. Try again later.",
            ),
        )

    return (
        translate("Video Error", "Request refused"),
        translate("Dialog - List", "The server didn't accept the request."),
    )
