from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from streamlink import Streamlink

from gridplayer.utils.url_resolve.stream_detect import is_dash_live_stream


def _manifest(mpd_attributes: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" {mpd_attributes}'
        ' profiles="urn:mpeg:dash:profile:isoff-live:2011">\n'
        '  <Period id="0" start="PT0S">\n'
        '    <AdaptationSet mimeType="video/mp4" segmentAlignment="true"/>\n'
        "  </Period>\n"
        "</MPD>\n"
    )


@pytest.fixture
def manifest_url(serving):
    served = {}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            body = served["manifest"].encode("utf-8")

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            """Quiet, the test is not interested"""

    server = serving(ThreadingHTTPServer(("127.0.0.1", 0), Handler))
    address, port = server.server_address

    def _serve(manifest: str) -> str:
        served["manifest"] = manifest
        return f"http://{address}:{port}/manifest.mpd"

    return _serve


def _is_live(manifest_url, manifest: str) -> bool:
    return is_dash_live_stream(manifest_url(manifest), session=Streamlink())


@pytest.mark.parametrize(
    "attributes",
    [
        'type="dynamic" minimumUpdatePeriod="PT2S"',
        'type = "dynamic"',
    ],
)
def test_a_dynamic_manifest_is_live(manifest_url, attributes):
    assert _is_live(manifest_url, _manifest(attributes))


@pytest.mark.parametrize(
    "attributes",
    [
        'type="static" mediaPresentationDuration="PT60S"',
        # static is what a manifest that names no type is
        'mediaPresentationDuration="PT60S"',
    ],
)
def test_a_static_manifest_is_not_live(manifest_url, attributes):
    assert not _is_live(manifest_url, _manifest(attributes))


def test_a_type_ending_another_name_says_nothing(manifest_url):
    """Only the type attribute itself: not one whose name ends with it."""

    assert not _is_live(manifest_url, _manifest('contenttype="dynamic"'))
