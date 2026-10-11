"""Plain http links in a playlist fetched over https, as the setting says.

Streamlink refuses them on its own; the setting lets them through and
nothing else. Nothing here reaches out: the playlists are parsed as text.
"""

import pytest
from streamlink.stream.hls import parse_m3u8

from gridplayer.utils import http_in_playlists as module
from gridplayer.utils.http_in_playlists import allow_http_in_playlists
from tests.conftest import FakeSettings

MASTER_URL = "https://example.com/index.m3u8"

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=921124,RESOLUTION=720x480
{variant}
"""

MEDIA = """#EXTM3U
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
{segment}
"""


@pytest.fixture
def settings(monkeypatch):
    values = {"network/allow_http_in_playlists": True}

    monkeypatch.setattr(module, "Settings", lambda: FakeSettings(values))

    allow_http_in_playlists()

    return values


def _variant(url: str, base: str = MASTER_URL) -> str:
    playlist = parse_m3u8(MASTER.format(variant=url), base)

    return playlist.playlists[0].uri


def _segment(url: str, base: str = MASTER_URL) -> str:
    playlist = parse_m3u8(MEDIA.format(segment=url), base)

    return playlist.segments[0].uri


class TestAllowed:
    def test_an_http_variant(self, settings):
        url = "http://cdn.example.net/720/index.m3u8"

        assert _variant(url) == url

    def test_an_http_segment(self, settings):
        url = "http://cdn.example.net/720/0.ts"

        assert _segment(url) == url

    def test_https_and_relative_links_are_as_before(self, settings):
        assert _variant("https://cdn.example.net/a.m3u8") == (
            "https://cdn.example.net/a.m3u8"
        )
        assert _segment("0.ts") == "https://example.com/0.ts"

    def test_a_file_link_is_still_refused(self, settings):
        with pytest.raises(ValueError, match="insecure"):
            _variant("file:///etc/passwd")


class TestRefused:
    def test_an_http_variant(self, settings):
        settings["network/allow_http_in_playlists"] = False

        with pytest.raises(ValueError, match="insecure"):
            _variant("http://cdn.example.net/720/index.m3u8")

    def test_an_http_segment(self, settings):
        settings["network/allow_http_in_playlists"] = False

        with pytest.raises(ValueError, match="insecure"):
            _segment("http://cdn.example.net/720/0.ts")

    def test_an_http_playlist_is_not_affected(self, settings):
        settings["network/allow_http_in_playlists"] = False

        url = "http://cdn.example.net/720/index.m3u8"

        assert _variant(url, base="http://example.com/index.m3u8") == url
