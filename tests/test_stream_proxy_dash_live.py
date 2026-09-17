"""A live DASH stream fetched through the proxy.

VLC follows a live manifest itself, so the proxy cannot hand it the
segments: it hands over the manifest with every URL in it pointing back
here, and answers for whatever VLC's own templates come to.
"""

import xml.etree.ElementTree as ET
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from gridplayer.models.stream import HashableDict, Stream, StreamSessionOpts
from gridplayer.utils.stream_proxy.mpd import MPD_NS
from gridplayer.utils.stream_proxy.server import ProxyRequestHandler, StreamProxyServer
from tests.conftest import LOGIN

# a manifest the host answers for somewhere else
MOVED_MANIFEST = "/moved/Manifest.mpd"

SEGMENT = b"\x00\x00\x00\x18ftypiso6" + bytes(range(64))

MANIFEST = (
    '<?xml version="1.0"?>'
    f'<MPD xmlns="{MPD_NS}" type="dynamic" minimumUpdatePeriod="PT2S">'
    "<Period>"
    "<AdaptationSet>"
    '<SegmentTemplate media="$RepresentationID$/$Number$.m4s"'
    ' initialization="$RepresentationID$/init.mp4" />'
    '<Representation id="V300" bandwidth="300000" />'
    "</AdaptationSet>"
    "</Period>"
    "</MPD>"
)

SESSION = StreamSessionOpts(service="test", session_headers=HashableDict({}))


class LiveHandler(BaseHTTPRequestHandler):
    """A host that serves a live manifest, and only to whoever is logged in."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get("Cookie")))

        if self.headers.get("Cookie") != LOGIN:
            self._send(HTTPStatus.FORBIDDEN, b"", "text/plain")
            return

        if self.path == MOVED_MANIFEST:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/live/Manifest.mpd")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self.path.endswith(".mpd"):
            self._send(HTTPStatus.OK, MANIFEST.encode("utf-8"), "application/dash+xml")
            return

        self._send(HTTPStatus.OK, SEGMENT, "video/mp4")

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Quiet, the test is not interested"""


@pytest.fixture
def upstream(serving):
    server = ThreadingHTTPServer(("127.0.0.1", 0), LiveHandler)
    server.seen = []

    return serving(server)


@pytest.fixture
def proxy(serving):
    return serving(StreamProxyServer(("127.0.0.1", 0), ProxyRequestHandler))


@pytest.fixture
def relay(upstream, proxy):
    """What VLC would be given for a manifest on the upstream host."""

    address, port = upstream.server_address

    def _relay(path: str = "/live/Manifest.mpd") -> str:
        return proxy.add_stream(
            Stream(
                url=f"http://{address}:{port}{path}",
                protocol="dash_proxy",
                session=SESSION,
            )
        )

    return _relay


@pytest.fixture
def manifest_url(relay):
    return relay()


def _base_url(manifest: str) -> str:
    return next(ET.fromstring(manifest).iter(f"{{{MPD_NS}}}BaseURL")).text


class TestTheManifest:
    def test_it_is_fetched_with_the_login_attached(
        self, local_login, upstream, manifest_url
    ):
        response = requests.get(manifest_url, timeout=5)

        assert response.status_code == 200
        assert upstream.seen == [("/live/Manifest.mpd", LOGIN)]

    def test_it_comes_back_pointing_at_the_proxy(
        self, local_login, proxy, manifest_url
    ):
        """VLC resolves the templates against this, so it has to be ours."""

        manifest = requests.get(manifest_url, timeout=5).text

        assert _base_url(manifest).startswith(f"{proxy.base_url}/dash/")

    def test_the_templates_are_left_for_vlc_to_fill_in(self, local_login, manifest_url):
        manifest = requests.get(manifest_url, timeout=5).text
        template = next(ET.fromstring(manifest).iter(f"{{{MPD_NS}}}SegmentTemplate"))

        assert template.get("media") == "$RepresentationID$/$Number$.m4s"

    def test_a_redirected_manifest_takes_its_segments_with_it(
        self, local_login, upstream, relay
    ):
        """Hosts move manifests about, and what is in them moves too.

        The templates are relative, so they hang off wherever the
        manifest was actually served, not off where it was asked for.
        """

        manifest = requests.get(relay(MOVED_MANIFEST), timeout=5).text

        requests.get(f"{_base_url(manifest)}V300/0.m4s", timeout=5)

        assert upstream.seen[-1] == ("/live/V300/0.m4s", LOGIN)


class TestTheSegmentsUnderIt:
    def test_a_filled_in_template_reaches_the_right_upstream_url(
        self, local_login, upstream, manifest_url
    ):
        """This is the request VLC makes once it has expanded the template."""

        base = _base_url(requests.get(manifest_url, timeout=5).text)

        response = requests.get(f"{base}V300/0.m4s", timeout=5)

        assert response.status_code == 200
        assert response.content == SEGMENT
        assert upstream.seen[-1] == ("/live/V300/0.m4s", LOGIN)

    def test_a_query_the_host_signs_with_survives_the_trip(
        self, local_login, upstream, manifest_url
    ):
        """Templates carry one, and a segment fetched without it is refused."""

        base = _base_url(requests.get(manifest_url, timeout=5).text)

        requests.get(f"{base}V300/0.m4s?token=xyz", timeout=5)

        assert upstream.seen[-1] == ("/live/V300/0.m4s?token=xyz", LOGIN)

    def test_a_base_nobody_handed_out_is_not_served(self, local_login, proxy):
        """The relay answers for what it registered, not for any URL asked of it."""

        response = requests.get(f"{proxy.base_url}/dash/made-up/V300/0.m4s", timeout=5)

        assert response.status_code == 404

    def test_a_base_nobody_handed_out_is_said_to_be_missing(self, proxy):
        """404 either way, but only one of them says what was not found.

        Falling through to the query the rest of the proxy uses would
        report a session that was never asked for.
        """

        with pytest.raises(LookupError, match="made-up"):
            proxy.dash_query("/dash/made-up/V300/0.m4s")

    def test_a_request_that_is_not_a_relayed_segment_is_left_alone(self, proxy):
        assert proxy.dash_query("/?url=http%3A%2F%2Fhost%2Fv.mp4") is None

    def test_the_rest_of_the_proxy_is_untouched(self, local_login, proxy, upstream):
        """A plain relayed stream still goes through the query it always did."""

        address, port = upstream.server_address

        url = proxy.add_stream(
            Stream(
                url=f"http://{address}:{port}/live/V300/0.m4s",
                protocol="http",
                session=SESSION,
            )
        )

        assert requests.get(url, timeout=5).content == SEGMENT
