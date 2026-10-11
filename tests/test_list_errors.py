import socket
import ssl

import pytest
import requests

from gridplayer.models.media_list import ListSource
from gridplayer.params.static import ListSourceKind
from gridplayer.utils.error_txts import error_tag, read_error_txts
from gridplayer.utils.list_errors import (
    ReadError,
    ReadErrorKind,
    read_error_of,
    site_name,
)
from gridplayer.utils.list_files import (
    ListTooLargeError,
    NoListThereError,
    NotAListError,
)
from gridplayer.utils.network import HTTPStatusError
from gridplayer.utils.web_lists import EmptyListError

LINK = ListSource(
    kind=ListSourceKind.URL, location="http://provider.example:8080/get.php?u=1"
)
YOUTUBE = ListSource(
    kind=ListSourceKind.URL, location="https://www.youtube.com/playlist?list=PL1"
)
FOLDER = ListSource(kind=ListSourceKind.FOLDER, location="D:/Videos")
FILE = ListSource(kind=ListSourceKind.FILE, location="D:/Videos/tv.m3u")


# named as yt-dlp's and urllib3's are: told apart by the names of the types
class HTTPError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP Error {status}")
        self.status = status


class ProxyError(ConnectionError):
    pass


class NewConnectionError(Exception):
    pass


class ConnectTimeoutError(Exception):
    pass


class RefusedLikeUrllib3(NewConnectionError, ConnectTimeoutError):
    pass


def _raised(error, cause):
    """The error as raised from another, the way the libraries chain
    theirs."""

    error.__cause__ = cause

    return error


def _download_error(message, cause=None):
    from yt_dlp.utils import DownloadError, ExtractorError

    extractor_error = ExtractorError(message, cause=cause, expected=True)

    return DownloadError(
        f"ERROR: {message}", exc_info=(type(extractor_error), extractor_error, None)
    )


class TestKinds:
    def test_http_status_of_its_own_download(self):
        error = read_error_of(HTTPStatusError(404), LINK)

        assert error.kind is ReadErrorKind.HTTP
        assert error.status == 404
        assert error.host == "provider.example"
        assert error.raw == "HTTP 404"

    def test_http_status_from_yt_dlp(self):
        error = read_error_of(
            _download_error("Unable to download webpage", HTTPError(503)), LINK
        )

        assert error.kind is ReadErrorKind.HTTP
        assert error.status == 503

    def test_refused(self):
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            port = free.getsockname()[1]

        with pytest.raises(requests.exceptions.ConnectionError) as raised:
            requests.get(f"http://127.0.0.1:{port}/list.m3u", timeout=5)

        assert read_error_of(raised.value, LINK).kind is ReadErrorKind.REFUSED

    def test_refused_is_not_a_timeout_though_urllib3_says_so(self):
        error = _raised(
            RefusedLikeUrllib3("could not connect"),
            ConnectionRefusedError("refused"),
        )

        assert read_error_of(error, LINK).kind is ReadErrorKind.REFUSED

    def test_server_name_not_found(self):
        error = _raised(ConnectionError("pool"), socket.gaierror(11001, "failed"))

        assert read_error_of(error, LINK).kind is ReadErrorKind.DNS

    def test_timed_out(self):
        error = _raised(ConnectionError("pool"), TimeoutError("timed out"))

        assert read_error_of(error, LINK).kind is ReadErrorKind.TIMEOUT

    def test_cut_off(self):
        error = _raised(ConnectionError("aborted"), ConnectionResetError("reset"))

        assert read_error_of(error, LINK).kind is ReadErrorKind.LOST

    def test_certificate(self):
        error = _raised(
            ConnectionError("pool"), ssl.SSLCertVerificationError("not trusted")
        )

        assert read_error_of(error, LINK).kind is ReadErrorKind.CERTIFICATE

    def test_secure_connection(self):
        error = _raised(ConnectionError("pool"), ssl.SSLError("wrong version"))

        assert read_error_of(error, LINK).kind is ReadErrorKind.SECURE

    def test_proxy_before_what_the_proxy_ran_into(self):
        error = _raised(ProxyError("proxy"), ConnectionRefusedError("refused"))

        assert read_error_of(error, LINK).kind is ReadErrorKind.PROXY

    def test_any_other_connection_trouble(self):
        assert read_error_of(ConnectionError("x"), LINK).kind is (
            ReadErrorKind.CONNECTION
        )

    def test_site_refusing(self):
        error = _download_error(
            "[youtube:tab] PL1: Sign in to confirm you're not a bot"
        )

        read = read_error_of(error, YOUTUBE)

        assert read.kind is ReadErrorKind.BLOCKED
        assert site_name(read.host) == "YouTube"

    def test_site_429_is_an_http_status(self):
        error = _download_error("HTTP Error 429: Too Many Requests", HTTPError(429))

        assert read_error_of(error, YOUTUBE).kind is ReadErrorKind.HTTP

    def test_list_gone_from_the_site(self):
        error = _download_error("[youtube:tab] PL1: The playlist does not exist.")

        assert read_error_of(error, YOUTUBE).kind is ReadErrorKind.GONE

    @pytest.mark.parametrize(
        "error",
        [
            NoListThereError("Not a list: http://x"),
            NotAListError(),
        ],
    )
    def test_not_a_list(self, error):
        assert read_error_of(error, LINK).kind is ReadErrorKind.NOT_A_LIST

    def test_site_link_that_is_no_list(self):
        from yt_dlp.utils import DownloadError, UnsupportedError

        unsupported = UnsupportedError("http://x/page")
        error = DownloadError(
            "ERROR: Unsupported URL", exc_info=(UnsupportedError, unsupported, None)
        )

        assert read_error_of(error, LINK).kind is ReadErrorKind.NOT_A_LIST

    def test_too_large(self):
        error = read_error_of(ListTooLargeError(512 * 2**20), LINK)

        assert error.kind is ReadErrorKind.TOO_LARGE
        assert error.limit_mb == 512

    def test_empty(self):
        error = EmptyListError("nothing on the list to play")

        assert read_error_of(error, YOUTUBE).kind is ReadErrorKind.EMPTY

    @pytest.mark.parametrize("source", [FOLDER, FILE])
    def test_local_gone(self, source):
        error = read_error_of(FileNotFoundError("Folder not found"), source)

        assert error.kind is ReadErrorKind.MISSING
        assert error.source_kind is source.kind
        assert error.host == ""

    def test_local_no_access(self):
        error = PermissionError("denied")

        assert read_error_of(error, FILE).kind is ReadErrorKind.NO_ACCESS

    def test_anything_else(self):
        error = read_error_of(ValueError("Not an XSPF list: junk"), FILE)

        assert error.kind is ReadErrorKind.OTHER
        assert error.raw_said == "Not an XSPF list: junk"

    def test_network_kinds(self):
        assert read_error_of(TimeoutError(), LINK).is_network
        assert not read_error_of(HTTPStatusError(500), LINK).is_network


class TestRawSaid:
    def test_first_line(self):
        error = ReadError(kind=ReadErrorKind.OTHER, raw="first\nsecond")

        assert error.raw_said == "first"

    def test_cut_short(self):
        error = ReadError(kind=ReadErrorKind.OTHER, raw="x" * 400)

        assert len(error.raw_said) == 151
        assert error.raw_said.endswith("…")

    def test_nothing(self):
        assert ReadError(kind=ReadErrorKind.OTHER, raw="").raw_said == ""


class TestTexts:
    @pytest.mark.parametrize(
        ("status", "title"),
        [
            (401, "Login needed"),
            (403, "Access denied"),
            (404, "Not found"),
            (410, "Not found"),
            (429, "Too many requests"),
            (500, "Server error"),
            (503, "Server error"),
            (418, "Request refused"),
        ],
    )
    def test_http(self, status, title):
        """The code is the tag's to say."""

        error = ReadError(kind=ReadErrorKind.HTTP, raw="", status=status)

        assert read_error_txts(error)[0] == title
        assert error_tag(error) == ("Server", f"HTTP {status}")

    @pytest.mark.parametrize(
        ("kind", "tag"),
        [
            (ReadErrorKind.DNS, ("Network", "DNS")),
            (ReadErrorKind.TIMEOUT, ("Network", "Timeout")),
            (ReadErrorKind.REFUSED, ("Network", "Refused")),
            (ReadErrorKind.LOST, ("Network", "Reset")),
            (ReadErrorKind.PROXY, ("Network", "Proxy")),
            (ReadErrorKind.SECURE, ("Network", "TLS")),
            (ReadErrorKind.BLOCKED, ("Server", "Blocked")),
            (ReadErrorKind.MISSING, ("File", "Missing")),
            (ReadErrorKind.NO_ACCESS, ("File", "No access")),
            (ReadErrorKind.TOO_LARGE, ("List", "Too big")),
        ],
    )
    def test_tag_tells_where_it_broke(self, kind, tag):
        assert error_tag(ReadError(kind=kind, raw="")) == tag

    @pytest.mark.parametrize("kind", list(ReadErrorKind))
    def test_every_kind_tagged(self, kind):
        where, code = error_tag(ReadError(kind=kind, raw="", status=404))

        assert where
        assert code

    def test_a_video_behind_a_link_said_as_one(self):
        error = ReadError(
            kind=ReadErrorKind.OTHER, raw="boom", source_kind=ListSourceKind.URL
        )

        assert read_error_txts(error, is_video=True) == (
            "Couldn't find the video",
            "boom",
        )

    @pytest.mark.parametrize("kind", list(ReadErrorKind))
    def test_every_kind_said(self, kind):
        error = ReadError(
            kind=kind,
            raw="what went wrong",
            source_kind=ListSourceKind.URL,
            status=404,
            host="provider.example",
            limit_mb=512,
        )

        title, about = read_error_txts(error)

        assert title
        assert about
        assert "{" not in title
        assert "{" not in about

    def test_host_named(self):
        error = ReadError(kind=ReadErrorKind.DNS, raw="", host="provider.example")

        assert "provider.example" in read_error_txts(error)[1]

    def test_size_limit_named(self):
        error = ReadError(kind=ReadErrorKind.TOO_LARGE, raw="", limit_mb=512)

        assert "512 MB" in read_error_txts(error)[1]

    def test_site_named(self):
        error = ReadError(kind=ReadErrorKind.BLOCKED, raw="", host="www.youtube.com")

        assert read_error_txts(error)[0] == "YouTube is blocking requests"

    def test_folder_or_file(self):
        folder = ReadError(
            kind=ReadErrorKind.MISSING, raw="", source_kind=ListSourceKind.FOLDER
        )
        file = ReadError(
            kind=ReadErrorKind.MISSING, raw="", source_kind=ListSourceKind.FILE
        )

        assert read_error_txts(folder)[0] == "Folder not found"
        assert read_error_txts(file)[0] == "File not found"

    def test_anything_else_says_the_error(self):
        error = ReadError(
            kind=ReadErrorKind.OTHER,
            raw="Not an XSPF list: junk",
            source_kind=ListSourceKind.URL,
        )

        assert read_error_txts(error) == (
            "Couldn't download the list",
            "Not an XSPF list: junk",
        )
