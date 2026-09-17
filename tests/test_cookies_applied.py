import io

import pytest
from requests.cookies import RequestsCookieJar
from yt_dlp.cookies import YoutubeDLCookieJar

from gridplayer.models.stream import HashableDict, Stream, StreamSessionOpts
from gridplayer.utils import cookies as cookies_module
from gridplayer.utils.cookies import (
    CookieStore,
    apply_to_streamlink,
    parse_cookies,
    ytdl_cookies,
)
from gridplayer.utils.stream_proxy import session as proxy_session
from gridplayer.utils.url_resolve import (
    resolver_streamlink,
    resolver_yt_dlp,
    stream_detect,
)
from gridplayer.utils.url_resolve.resolver_base import DirectResolver

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"

COOKIE_LINE = ".youtube.com\tTRUE\t/\tFALSE\t0\tSID\tabc\n"


class _FakeSettings:
    def __init__(self, values):
        self._values = values

    def get(self, key):
        return self._values[key]


class _FakeSession:
    """Enough of a Streamlink session for cookies and headers to land on.

    And for a stream to be built against, which asks it to vet the
    arguments the request will be made with.
    """

    def __init__(self):
        self.http = type("_Http", (), {})()
        self.http.cookies = RequestsCookieJar()
        self.http.headers = {}
        self.http.valid_request_args = dict


@pytest.fixture
def settings(monkeypatch):
    values = {"cookies/enabled": True, "cookies/allow_update": True}

    monkeypatch.setattr(cookies_module, "Settings", lambda: _FakeSettings(values))

    return values


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "cookies.txt"
    path.write_text(NETSCAPE_HEADER + COOKIE_LINE, encoding="utf-8")

    store = CookieStore(path)
    monkeypatch.setattr(cookies_module, "cookie_store", lambda: store)

    return store


@pytest.fixture
def empty_store(tmp_path, monkeypatch):
    store = CookieStore(tmp_path / "cookies.txt")
    monkeypatch.setattr(cookies_module, "cookie_store", lambda: store)

    return store


def _values(jar):
    return {(c.domain, c.name): c.value for c in jar}


def _read_back(cookie_opts):
    """Load the options the way yt-dlp itself would."""

    jar = YoutubeDLCookieJar(cookie_opts["cookiefile"])
    jar.load(ignore_discard=True, ignore_expires=True)

    return jar


class TestHandingThemToYtDlp:
    def test_they_arrive_as_something_it_can_load(self, settings, store):
        with ytdl_cookies() as cookie_opts:
            assert _values(_read_back(cookie_opts)) == {(".youtube.com", "SID"): "abc"}

    def test_an_empty_store_hands_it_nothing_at_all(self, settings, empty_store):
        """An empty cookiefile is a load error, which would fail the resolve."""

        with ytdl_cookies() as cookie_opts:
            assert cookie_opts == {}

    def test_the_switch_being_off_hands_it_nothing(self, settings, store):
        settings["cookies/enabled"] = False

        with ytdl_cookies() as cookie_opts:
            assert cookie_opts == {}

    def test_what_it_refreshes_is_kept(self, settings, store):
        with ytdl_cookies() as cookie_opts:
            _refresh_like_yt_dlp(cookie_opts, "refreshed")

        assert _values(store.jar) == {(".youtube.com", "SID"): "refreshed"}

    def test_what_it_refreshes_is_dropped_when_told_to(self, settings, store):
        settings["cookies/allow_update"] = False

        with ytdl_cookies() as cookie_opts:
            _refresh_like_yt_dlp(cookie_opts, "refreshed")

        assert _values(store.jar) == {(".youtube.com", "SID"): "abc"}

    def test_a_resolve_that_blew_up_still_keeps_the_refresh(self, settings, store):
        """yt-dlp saves its jar on the way out however the extraction ended."""

        with pytest.raises(RuntimeError):
            with ytdl_cookies() as cookie_opts:
                _refresh_like_yt_dlp(cookie_opts, "refreshed")
                raise RuntimeError("extractor blew up")

        assert _values(store.jar) == {(".youtube.com", "SID"): "refreshed"}


class TestHandingThemToStreamlink:
    def test_a_session_gets_them(self, settings, store):
        session = _FakeSession()

        apply_to_streamlink(session)

        assert session.http.cookies.get("SID") == "abc"

    def test_the_switch_being_off_leaves_the_session_alone(self, settings, store):
        settings["cookies/enabled"] = False
        session = _FakeSession()

        apply_to_streamlink(session)

        assert not len(session.http.cookies)

    def test_an_empty_store_leaves_the_session_alone(self, settings, empty_store):
        session = _FakeSession()

        apply_to_streamlink(session)

        assert not len(session.http.cookies)


class TestEveryPlaceThatReachesOut:
    """Each of them has to be given the cookies, not just the resolvers."""

    def test_the_yt_dlp_resolver(self, mocker, settings, store):
        opened_with = {}

        class _FakeYoutubeDL:
            def __init__(self, params):
                opened_with.update(params)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"title": "t", "extractor": "generic"}

        mocker.patch.object(resolver_yt_dlp, "YoutubeDL", _FakeYoutubeDL)

        resolver_yt_dlp.YoutubeDLResolver("http://host/v")._video_info

        assert _values(_read_back(opened_with)) == {(".youtube.com", "SID"): "abc"}

    def test_the_streamlink_resolver(self, mocker, settings, store):
        mocker.patch.object(resolver_streamlink, "Streamlink", _FakeSession)

        session = resolver_streamlink.StreamlinkResolver("http://host/v")._session

        assert session.http.cookies.get("SID") == "abc"

    def test_the_probes_that_tell_live_from_recorded(self, mocker, settings, store):
        mocker.patch.object(stream_detect, "Streamlink", _FakeSession)

        session = stream_detect._session_for(None, {"Referer": "http://host/"})

        assert session.http.cookies.get("SID") == "abc"
        assert session.http.headers == {"Referer": "http://host/"}

    def test_a_session_the_caller_brought_is_left_as_it_is(
        self, mocker, settings, store
    ):
        """It came from a resolver, so it carries the cookies already."""

        mocker.patch.object(stream_detect, "Streamlink", _FakeSession)
        brought = _FakeSession()

        assert stream_detect._session_for(brought, None) is brought
        assert not len(brought.http.cookies)

    def test_the_proxy_that_fetches_the_segments(self, mocker, settings, store):
        mocker.patch.object(proxy_session, "Streamlink", _FakeSession)

        proxy = proxy_session.StreamSession(
            stream_session=StreamSessionOpts(
                service="yt_dlp-youtube", session_headers=HashableDict({})
            ),
            server=None,
        )

        assert proxy._session.http.cookies.get("SID") == "abc"


class TestAUrlThatWouldGoStraightToVlc:
    """VLC cannot be told a cookie, so one that needs it takes the long way.

    Nothing here asks the resolver to reach out: which protocol a URL
    comes back with is decided by the jar alone.
    """

    def test_one_there_is_a_login_for_is_relayed_instead(self, settings, store):
        stream = DirectResolver("https://www.youtube.com/v.mp4").streams["generic"]

        assert stream.protocol == "http"
        assert stream.session.service == "direct"

    def test_one_there_is_nothing_for_is_handed_over_as_it_was(self, settings, store):
        """The relay costs something, so it stays out of the way."""

        stream = DirectResolver("https://example.com/v.mp4").streams["generic"]

        assert stream.protocol == "direct"
        assert stream.session is None

    def test_a_host_that_merely_reads_like_the_one_stored(self, settings, store):
        """Which cookies a URL gets is the jar's question, not a string match."""

        stream = DirectResolver("https://youtube.com.elsewhere.net/v.mp4").streams[
            "generic"
        ]

        assert stream.protocol == "direct"

    def test_the_switch_being_off_hands_it_over_as_it_was(self, settings, store):
        settings["cookies/enabled"] = False

        stream = DirectResolver("https://www.youtube.com/v.mp4").streams["generic"]

        assert stream.protocol == "direct"

    def test_an_empty_store_hands_it_over_as_it_was(self, settings, empty_store):
        stream = DirectResolver("https://www.youtube.com/v.mp4").streams["generic"]

        assert stream.protocol == "direct"


class TestCookiesEditedWhileTheProxyIsRunning:
    """A proxy session outlives the settings dialog and has to notice.

    One is made per service and kept for as long as the proxy runs, so
    what it was handed when it was made is not the last word on it.
    """

    @pytest.fixture
    def proxy(self, mocker, settings, store):
        mocker.patch.object(proxy_session, "Streamlink", _FakeSession)

        return proxy_session.StreamSession(
            stream_session=StreamSessionOpts(
                service="yt_dlp-youtube", session_headers=HashableDict({})
            ),
            server=None,
        )

    def test_a_login_changed_since_is_picked_up(self, proxy, store):
        _store(store, ".youtube.com", "SID", "changed")

        _request(proxy)

        assert proxy._session.http.cookies.get("SID") == "changed"

    def test_one_taken_out_of_the_store_stops_being_sent(self, proxy, store):
        store.clear()

        _request(proxy)

        assert not len(proxy._session.http.cookies)

    def test_switching_them_off_stops_them_being_sent(self, proxy, settings):
        settings["cookies/enabled"] = False

        _request(proxy)

        assert not len(proxy._session.http.cookies)

    def test_an_untouched_store_leaves_the_session_as_it_is(self, proxy, store):
        """A cookie the host set along the way is not thrown out every request."""

        proxy._session.http.cookies.set("CDN", "xyz")

        _request(proxy)

        assert proxy._session.http.cookies.get("CDN") == "xyz"

    def test_an_edit_does_take_the_hosts_own_cookie_with_it(self, proxy, store):
        """The price of a deleted login not lingering in a running session.

        What the host set is set again by the next response that cares,
        where a login nobody could see any more would just keep going out.
        """

        proxy._session.http.cookies.set("CDN", "xyz")

        _store(store, ".youtube.com", "SID", "changed")
        _request(proxy)

        assert proxy._session.http.cookies.get("CDN") is None


def _store(store, domain, name, value):
    line = f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n"

    store.save(parse_cookies(NETSCAPE_HEADER + line))


def _request(proxy):
    """Ask the session for a stream, the way serving a request does."""

    proxy.get_stream(Stream(url="http://host/v.mp4", protocol="http"))


def _refresh_like_yt_dlp(cookie_opts, value):
    """What YoutubeDL.close does: update the jar, then save it back."""

    buffer = cookie_opts["cookiefile"]

    jar = YoutubeDLCookieJar(buffer)
    jar.load(ignore_discard=True, ignore_expires=True)

    for cookie in jar:
        cookie.value = value

    jar.save()

    assert "\x00" not in buffer.getvalue()

    return io.StringIO(buffer.getvalue())
