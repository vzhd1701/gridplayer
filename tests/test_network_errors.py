import logging
import socket

import requests
from streamlink import PluginError, StreamError
from urllib3.connection import HTTPConnection
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError

from gridplayer.utils.network_errors import (
    failure_txt,
    log_failure,
    network_failure_txt,
)

_log = logging.getLogger("test_network_errors")


def _raised(error, cause):
    error.__cause__ = cause

    return error


def _forbidden(url):
    response = requests.Response()
    response.status_code = 403
    response.url = url

    return requests.HTTPError("403 Client Error", response=response)


def _timed_out(url):
    request = requests.Request("GET", url).prepare()

    return requests.ConnectTimeout("Max retries exceeded", request=request)


def _download_error(cause):
    from yt_dlp.networking.exceptions import TransportError
    from yt_dlp.utils import DownloadError, ExtractorError

    from gridplayer.utils.percent_re import untangle_percent_re

    # yt-dlp patches urllib3 as it is imported; see utils/percent_re.py
    untangle_percent_re()

    extractor_error = ExtractorError(
        "Unable to download webpage", cause=TransportError(cause=cause)
    )

    return DownloadError(
        "ERROR: Unable to download webpage",
        exc_info=(type(extractor_error), extractor_error, None),
    )


class TestSaid:
    def test_http_status_with_the_host_that_answered(self):
        # a redirect: the host that said 403 is the one told
        error = _raised(
            PluginError("Unable to open URL: https://jmp.example/x.m3u8"),
            _raised(OSError("Unable to open URL"), _forbidden("https://cdn.example/x")),
        )

        assert network_failure_txt(error) == "HTTP 403 Forbidden (cdn.example)"

    def test_timeout_wrapped_by_streamlink(self):
        error = _raised(
            StreamError("Unable to open URL"), _timed_out("http://cdn.example/x")
        )

        assert network_failure_txt(error) == "timed out (cdn.example)"

    def test_host_of_a_connection_kept_in_args(self):
        conn = HTTPConnection("cdn.example")
        error = ConnectTimeoutError(conn, "Connection to cdn.example timed out")
        error.__cause__ = TimeoutError()

        assert network_failure_txt(error) == "timed out (cdn.example)"

    def test_yt_dlp_name_not_resolved(self):
        conn = HTTPConnection("nothere.invalid")
        cause = NameResolutionError("nothere.invalid", conn, socket.gaierror())

        error = _download_error(cause)

        assert network_failure_txt(error) == "host not found (nothere.invalid)"

    def test_without_a_host(self):
        assert network_failure_txt(ConnectionRefusedError()) == "connection refused"

    def test_not_a_network_failure(self):
        assert network_failure_txt(ZeroDivisionError("division by zero")) is None
        assert failure_txt(ValueError("bad value")) == "bad value"


class TestLogged:
    def test_network_failure_in_one_line_at_most_a_warning(self, caplog):
        error = _timed_out("http://cdn.example/x")

        with caplog.at_level(logging.DEBUG):
            log_failure(_log, "Could not resolve", error)

        (record,) = caplog.records
        assert record.levelno == logging.WARNING
        assert record.getMessage() == "Could not resolve: timed out (cdn.example)"
        assert record.exc_info is None

    def test_network_failure_kept_below_a_warning(self, caplog):
        with caplog.at_level(logging.DEBUG):
            log_failure(_log, "yt-dlp error", ConnectionResetError(), logging.DEBUG)

        (record,) = caplog.records
        assert record.levelno == logging.DEBUG
        assert record.exc_info is None

    def test_anything_else_with_its_traceback(self, caplog):
        error = ValueError("a bug of ours")

        with caplog.at_level(logging.DEBUG):
            log_failure(_log, "Could not resolve", error)

        (record,) = caplog.records
        assert record.levelno == logging.ERROR
        assert record.getMessage() == "Could not resolve"
        assert record.exc_info[1] is error
