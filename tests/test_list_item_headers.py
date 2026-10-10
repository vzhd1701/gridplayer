"""What a channel list says to fetch a channel with: a user agent and a
referrer, on their way to whatever does the fetching."""

import contextlib

import pytest

from gridplayer.models.media_list import HttpHeaders, ListItem
from gridplayer.models.stream import HashableDict, StreamOrigin
from gridplayer.params.static import URLResolver
from gridplayer.utils.stream_proxy.server import ProxyRequestHandler, StreamProxyServer
from gridplayer.utils.url_resolve import resolver_base, resolver_yt_dlp, url_resolve
from gridplayer.utils.url_resolve.resolver_base import DirectResolver
from gridplayer.utils.url_resolve.resolver_streamlink import StreamlinkResolver
from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver
from gridplayer.vlc_player.player_base import _http_header_options

URL = "http://iptv.example/live/1.ts"

HEADERS = {"User-Agent": "Box/1.0", "Referer": "https://portal.example/"}


class TestTheHeaders:
    def test_give_the_user_agent_and_referrer_as_headers(self):
        headers = HttpHeaders(user_agent="Box/1.0", referrer="https://portal.example/")

        assert headers.as_dict() == HEADERS

    def test_give_none_they_were_not_given(self):
        assert HttpHeaders(user_agent="Box/1.0").as_dict() == {"User-Agent": "Box/1.0"}

    def test_items_read_back_with_the_same_share_them(self):
        one = ListItem(uri=URL, http_headers={"user_agent": "Box/1.0"})
        two = ListItem.model_validate(
            {"uri": URL, "http_headers": {"user_agent": "Box/1.0"}}
        )

        assert one.http_headers is two.http_headers


class TestVLC:
    def test_is_handed_the_two_it_takes_as_input_options(self):
        options = _http_header_options({**HEADERS, "Cookie": "a=b"})

        assert options == [
            ":http-user-agent=Box/1.0",
            ":http-referrer=https://portal.example/",
        ]

    def test_whatever_they_are_spelled(self):
        assert _http_header_options({"user-agent": "Box"}) == [":http-user-agent=Box"]


class TestResolving:
    def test_hands_them_to_the_resolver(self, mocker):
        made = []

        class _Resolver:
            def __init__(self, url, headers=None, progress=None):
                made.append((url, headers))

            def resolve(self):
                return "resolved"

        mocker.patch.object(
            url_resolve, "_pick_resolvers", return_value={URLResolver.DIRECT: _Resolver}
        )

        assert url_resolve.resolve_url(URL, headers=HEADERS) == "resolved"
        assert made == [(URL, HEADERS)]

    def test_a_link_played_as_it_is_is_looked_at_with_them(self, mocker):
        probe = mocker.patch.object(
            resolver_base, "is_http_live_stream", return_value=True
        )

        assert DirectResolver(URL, headers=HEADERS).is_live

        assert probe.call_args.kwargs["session_headers"] == HEADERS

    def test_a_relayed_link_is_relayed_with_them(self, mocker):
        mocker.patch.object(resolver_base, "needs_relay", return_value=True)

        stream = DirectResolver(URL, headers=HEADERS).streams["generic"]

        assert stream.protocol == "http"
        assert stream.session.session_headers == HEADERS

    def test_streamlink_fetches_with_them(self):
        resolver = StreamlinkResolver("http://iptv.example/live.m3u8", headers=HEADERS)

        assert resolver._session.http.headers["User-Agent"] == "Box/1.0"
        assert resolver._session.http.headers["Referer"] == "https://portal.example/"

    @pytest.fixture
    def ydl_opts(self, mocker):
        """What yt-dlp is set up with, the settings giving a user agent."""

        opts = {}

        class _YoutubeDL:
            def __init__(self, params):
                opts.update(params)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"_type": "video", "id": "1", "title": "Channel"}

        mocker.patch.object(resolver_yt_dlp, "YoutubeDL", _YoutubeDL)
        mocker.patch.object(
            resolver_yt_dlp, "ytdl_cookies", return_value=contextlib.nullcontext({})
        )
        mocker.patch.object(resolver_yt_dlp, "ytdl_js_runtimes", return_value=None)
        mocker.patch.object(
            resolver_yt_dlp,
            "ytdl_network_opts",
            return_value={"http_headers": {"User-Agent": "Settings", "X-A": "1"}},
        )

        return opts

    def test_yt_dlp_fetches_with_them_over_the_settings(self, ydl_opts):
        info = YoutubeDLResolver(URL, headers=HEADERS)._video_info

        assert info["title"] == "Channel"
        assert ydl_opts["http_headers"] == {**HEADERS, "X-A": "1"}

    def test_yt_dlp_left_to_the_settings_without_them(self, ydl_opts):
        info = YoutubeDLResolver(URL)._video_info

        assert info["title"] == "Channel"
        assert ydl_opts["http_headers"] == {"User-Agent": "Settings", "X-A": "1"}


@pytest.fixture
def proxy():
    made = []

    def _make(resolve_source):
        server = StreamProxyServer(
            ("127.0.0.1", 0), ProxyRequestHandler, resolve_source=resolve_source
        )
        made.append(server)
        return server

    yield _make

    for server in made:
        server.server_close()


class TestTheProxyRenewingAStream:
    def test_resolves_the_page_again_with_them(self, proxy):
        calls = []

        def resolve_source(url, headers=None):
            calls.append((url, headers))

        server = proxy(resolve_source)

        server._refresh_source(
            StreamOrigin(url=URL, quality="best", headers=HashableDict(HEADERS))
        )

        assert calls == [(URL, HEADERS)]

    def test_as_ever_without_them(self, proxy):
        calls = []

        def resolve_source(url, headers=None):
            calls.append((url, headers))

        server = proxy(resolve_source)

        server._refresh_source(StreamOrigin(url=URL, quality="best"))

        assert calls == [(URL, None)]
