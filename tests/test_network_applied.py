"""Every place that reaches out, and whether it was told the settings.

The settings themselves are pinned next door in test_network_opts. What
is pinned here is that each client actually gets them: a proxy nobody
passed on is a proxy that quietly is not used, and the only sign of it
is traffic going somewhere the user said it should not.
"""

import socket

import pytest

from gridplayer.models.stream import HashableDict, Stream, StreamSessionOpts
from gridplayer.params.static import ProxyMode
from gridplayer.utils import network as network_module
from gridplayer.utils import ytdlp_checkup
from gridplayer.utils.stream_proxy import session as proxy_session
from gridplayer.utils.url_resolve import (
    resolver_streamlink,
    resolver_yt_dlp,
    stream_detect,
)
from gridplayer.utils.url_resolve.resolver_base import DirectResolver
from gridplayer.utils.url_resolve.resolver_yt_dlp import _manifest_protocol
from gridplayer.vlc_player import instance as vlc_instance
from tests.conftest import FakeSettings
from tests.conftest import FakeStreamlinkSession as _FakeSession

PROXY_URL = "http://127.0.0.1:8080"

CUSTOM_USER_AGENT = "Mozilla/5.0 (test)"


class _FakeYoutubeDL:
    """A YoutubeDL that only remembers what it was asked for."""

    opened_with = {}

    def __init__(self, params):
        type(self).opened_with = dict(params)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return {"title": "t", "extractor": "generic", "formats": []}


@pytest.fixture
def proxy_set(monkeypatch):
    """A page filled in enough that every client has something to show."""

    opts = network_module.NetworkOpts(
        proxy_mode=ProxyMode.CUSTOM,
        proxy=PROXY_URL,
        user_agent=CUSTOM_USER_AGENT,
        force_ipv4=True,
        timeout=0,
        verify_tls=True,
    )

    _answer_with(monkeypatch, opts)

    return opts


def _answer_with(monkeypatch, opts):
    """Make every reader of the page see this one.

    One patch reaches all of them: nothing reads the settings for
    itself, they all ask the network module, and it resolves the reader
    out of its own globals when they do.
    """

    monkeypatch.setattr(network_module, "network_opts", lambda: opts)


def _nothing_set():
    return network_module.NetworkOpts(
        proxy_mode=ProxyMode.SYSTEM,
        proxy="",
        user_agent="",
        force_ipv4=False,
        timeout=0,
        verify_tls=True,
    )


@pytest.fixture
def no_cookies(monkeypatch):
    """Nothing stored, so a session only ever shows the network settings."""

    monkeypatch.setattr(network_module, "apply_cookies", lambda session: None)
    monkeypatch.setattr(network_module, "cookies_stamp", lambda: None)


def _relayed(session_headers=None):
    return StreamSessionOpts(
        service="yt_dlp-youtube",
        session_headers=HashableDict(session_headers or {}),
    )


class TestTheStreamlinkSide:
    def test_the_resolver(self, mocker, proxy_set, no_cookies):
        mocker.patch.object(resolver_streamlink, "Streamlink", _FakeSession)

        session = resolver_streamlink.StreamlinkResolver("http://host/v")._session

        assert session.http.proxies == {"http": PROXY_URL, "https": PROXY_URL}
        assert session.http.headers["User-Agent"] == CUSTOM_USER_AGENT
        assert session.options == {"ipv4": True}

    def test_the_probes_that_tell_live_from_recorded(
        self, mocker, proxy_set, no_cookies
    ):
        mocker.patch.object(stream_detect, "Streamlink", _FakeSession)

        session = stream_detect._session_for(None, None)

        assert session.http.proxies == {"http": PROXY_URL, "https": PROXY_URL}

    def test_the_proxy_that_fetches_the_segments(self, mocker, proxy_set, no_cookies):
        mocker.patch.object(proxy_session, "Streamlink", _FakeSession)

        relay = proxy_session.StreamSession(stream_session=_relayed(), server=None)

        assert relay._session.http.proxies == {"http": PROXY_URL, "https": PROXY_URL}
        assert relay._session.http.headers["User-Agent"] == CUSTOM_USER_AGENT


class TestWhoseUserAgentWins:
    """A shared default, and a format that came with one of its own.

    A site signs an address for the user agent that asked it for one, so
    the format's is the last word wherever there is one. Where there is
    not, the shared one stands.
    """

    def test_a_format_that_brought_its_own_keeps_it(
        self, mocker, proxy_set, no_cookies
    ):
        mocker.patch.object(proxy_session, "Streamlink", _FakeSession)

        relay = proxy_session.StreamSession(
            stream_session=_relayed({"User-Agent": "com.google.android.youtube/1.0"}),
            server=None,
        )

        assert (
            relay._session.http.headers["User-Agent"]
            == "com.google.android.youtube/1.0"
        )

    def test_a_format_that_did_not_takes_the_shared_one(
        self, mocker, proxy_set, no_cookies
    ):
        mocker.patch.object(proxy_session, "Streamlink", _FakeSession)

        relay = proxy_session.StreamSession(stream_session=_relayed(), server=None)

        assert relay._session.http.headers["User-Agent"] == CUSTOM_USER_AGENT

    def test_it_still_keeps_it_after_the_settings_are_edited(
        self, mocker, proxy_set, no_cookies, monkeypatch
    ):
        """The catch-up re-applies the page; it must not win on the way."""

        mocker.patch.object(proxy_session, "Streamlink", _FakeSession)

        relay = proxy_session.StreamSession(
            stream_session=_relayed({"User-Agent": "com.google.android.youtube/1.0"}),
            server=None,
        )

        _answer_with(monkeypatch, _nothing_set())

        relay.get_stream(Stream(url="http://host/v.mp4", protocol="http"))

        assert (
            relay._session.http.headers["User-Agent"]
            == "com.google.android.youtube/1.0"
        )
        assert relay._session.http.proxies == {}

    def test_the_probes_leave_a_formats_own_alone(self, mocker, proxy_set, no_cookies):
        mocker.patch.object(stream_detect, "Streamlink", _FakeSession)

        session = stream_detect._session_for(
            None, {"User-Agent": "com.google.android.youtube/1.0"}
        )

        assert session.http.headers["User-Agent"] == "com.google.android.youtube/1.0"


class TestTheYtDlpSide:
    def test_the_resolver(self, mocker, proxy_set, no_cookies):
        mocker.patch.object(resolver_yt_dlp, "YoutubeDL", _FakeYoutubeDL)

        assert resolver_yt_dlp.YoutubeDLResolver("http://host/v")._video_info

        assert _FakeYoutubeDL.opened_with["proxy"] == PROXY_URL
        assert _FakeYoutubeDL.opened_with["source_address"] == "0.0.0.0"
        assert _FakeYoutubeDL.opened_with["http_headers"] == {
            "User-Agent": CUSTOM_USER_AGENT
        }

    def test_the_checkup_tries_what_playback_would(self, mocker, proxy_set, no_cookies):
        """A checkup on a connection playback would not make says nothing."""

        mocker.patch.object(ytdlp_checkup, "YoutubeDL", _FakeYoutubeDL)

        ytdlp_checkup.YouTubeCheckup()._extract_info(logger=None)

        assert _FakeYoutubeDL.opened_with["proxy"] == PROXY_URL

    def test_the_checkups_own_requests_go_through_it_too(
        self, mocker, proxy_set, no_cookies
    ):
        mocker.patch.object(ytdlp_checkup, "Streamlink", _FakeSession)

        session = ytdlp_checkup.YouTubeCheckup()._session()

        assert session.http.proxies == {"http": PROXY_URL, "https": PROXY_URL}

    def test_a_socks_proxy_is_no_longer_beyond_them(
        self, mocker, monkeypatch, no_cookies
    ):
        """They used to be made with urllib, which cannot speak SOCKS.

        Going around the proxy instead would have reported on a
        connection playback was never going to make.
        """

        socks = "socks5h://127.0.0.1:1080"

        _answer_with(
            monkeypatch,
            network_module.NetworkOpts(
                proxy_mode=ProxyMode.CUSTOM,
                proxy=socks,
                user_agent="",
                force_ipv4=False,
                timeout=0,
                verify_tls=True,
            ),
        )
        mocker.patch.object(ytdlp_checkup, "Streamlink", _FakeSession)

        session = ytdlp_checkup.YouTubeCheckup()._session()

        assert session.http.proxies == {"http": socks, "https": socks}


class TestTheAddressFamily:
    """Not the session's to keep, whatever it looks like.

    Streamlink holds the restriction in a urllib3 global and its ipv4
    and ipv6 options only ever turn one on: set to False on a session
    that never had them on, they leave the last one turned on standing.
    So a session set back to Auto has to say so outright, or whoever
    forced a family last speaks for every session made after them.
    """

    def test_forcing_one_says_which(self, proxy_set, no_cookies):
        session = _FakeSession()

        network_module.apply_to_streamlink(session)

        assert session.address_family is socket.AF_INET

    def test_auto_clears_it_even_on_a_session_that_never_set_it(
        self, monkeypatch, no_cookies
    ):
        _answer_with(monkeypatch, _nothing_set())

        session = _FakeSession()

        network_module.apply_to_streamlink(session)

        assert session.address_family is None


class TestTheVlcSide:
    """The one setting VLC can be told, for the links still handed to it."""

    def test_it_is_told_the_user_agent(self, mocker, monkeypatch):
        monkeypatch.setattr(
            vlc_instance,
            "vlc_user_agent",
            lambda: CUSTOM_USER_AGENT,
        )
        monkeypatch.setattr(
            vlc_instance.Settings,
            "__call__",
            lambda self: FakeSettings({"misc/vlc_options": ""}),
            raising=False,
        )

        created = mocker.patch.object(vlc_instance.vlc, "Instance")

        player = vlc_instance.InstanceVLC(vlc_log_level=0, vlc_options=[])
        mocker.patch.object(player, "init_logger")

        player.init_instance()

        created.return_value.set_user_agent.assert_called_once_with(
            vlc_instance.VLC_USER_AGENT_NAME, CUSTOM_USER_AGENT
        )


class TestALinkThatWouldHaveGoneStraightToVlc:
    """Who fetches it, now that a cookie is not the only reason to relay.

    Which settings count is pinned in test_network_opts; what is pinned
    here is that the resolvers ask, and act on the answer.
    """

    def test_a_plain_link_is_relayed_once_a_proxy_is_set(self, proxy_set):
        stream = DirectResolver("https://example.com/v.mp4").streams["generic"]

        assert stream.protocol == "http"
        assert stream.session.service == "direct"

    def test_a_plain_link_is_handed_over_as_it_was_when_nothing_is_set(self):
        """The relay costs a hop, so it stays out of the way."""

        stream = DirectResolver("https://example.com/v.mp4").streams["generic"]

        assert stream.protocol == "direct"
        assert stream.session is None

    def test_a_live_manifest_is_fetched_for_vlc_once_a_proxy_is_set(self, proxy_set):
        """VLC follows such a manifest itself, and would miss the proxy."""

        assert _manifest_protocol({"url": "https://example.com/live.mpd"}) == (
            "dash_proxy"
        )

    def test_a_live_manifest_is_left_to_vlc_when_nothing_is_set(self):
        assert _manifest_protocol({"url": "https://example.com/live.mpd"}) == "direct"

    @pytest.mark.parametrize(
        "url", ["rtmp://example.com/live", "rtsp://example.com/live"]
    )
    def test_what_the_relay_could_not_carry_stays_with_vlc(self, monkeypatch, url):
        """The relay is an HTTP server, whatever the page asks for."""

        _answer_with(
            monkeypatch,
            network_module.NetworkOpts(
                proxy_mode=ProxyMode.CUSTOM,
                proxy=PROXY_URL,
                user_agent="",
                force_ipv4=False,
                timeout=0,
                verify_tls=True,
            ),
        )

        assert DirectResolver(url).streams["generic"].protocol == "direct"

    def test_a_file_on_disk_is_never_relayed(self, proxy_set):
        """A proxy has nothing to do with a path, and could not serve one."""

        stream = DirectResolver(r"C:\videos\v.mp4").streams["generic"]

        assert stream.protocol == "direct"
