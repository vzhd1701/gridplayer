"""The network settings, as each client that fetches has to be told them.

Nothing here reaches out. What is being pinned is the translation: one
page of settings into yt-dlp's dict, Streamlink's session and VLC's one
usable flag, plus the decision that follows from a setting VLC cannot be
told at all.
"""

import pytest

from gridplayer.params.static import IPVersion, ProxyMode
from gridplayer.utils import cookies as cookies_module
from gridplayer.utils import network as network_module
from gridplayer.utils.network import (
    DEFAULT_USER_AGENT,
    apply_to_streamlink,
    configure_session,
    needs_relay,
    network_opts,
    vlc_user_agent,
    ytdl_network_opts,
)
from tests.conftest import DEFAULT_TIMEOUT_SEC, FakeSettings
from tests.conftest import FakeStreamlinkSession as _FakeSession

PROXY_URL = "socks5h://127.0.0.1:1080"

VIDEO_URL = "https://example.com/v.mp4"


@pytest.fixture
def settings(monkeypatch):
    """The page as it comes out of the box, for a test to edit."""

    values = {
        "network/proxy_mode": ProxyMode.SYSTEM,
        "network/proxy_url": "",
        "network/user_agent": "",
        "network/ip_version": IPVersion.AUTO,
        "network/timeout": 0,
        "network/verify_tls": True,
    }

    monkeypatch.setattr(network_module, "Settings", lambda: FakeSettings(values))

    return values


@pytest.fixture
def no_cookies(monkeypatch):
    """No stored login, so the relay is only ever the settings' doing."""

    monkeypatch.setattr(network_module, "has_cookies_for", lambda url: False)


def _custom_proxy(settings, url=PROXY_URL):
    settings["network/proxy_mode"] = ProxyMode.CUSTOM
    settings["network/proxy_url"] = url


class TestReadingThePage:
    def test_out_of_the_box_it_asks_for_nothing(self, settings):
        assert network_opts() == network_module.NetworkOpts(
            proxy_mode=ProxyMode.SYSTEM,
            proxy="",
            user_agent="",
            ip_version=IPVersion.AUTO,
            timeout=0,
            verify_tls=True,
        )

    def test_a_proxy_of_the_users_own_is_used_and_the_machines_is_not(self, settings):
        _custom_proxy(settings)

        opts = network_opts()

        assert opts.proxy == PROXY_URL
        assert opts.use_env is False

    def test_refusing_a_proxy_is_not_the_same_as_having_none_configured(self, settings):
        settings["network/proxy_mode"] = ProxyMode.NONE

        opts = network_opts()

        assert opts.proxy == ""
        assert opts.use_env is False

    def test_a_custom_proxy_left_blank_is_read_as_refusing_one(self, settings):
        """Half a form is not an instruction to go back to the machine's."""

        _custom_proxy(settings, url="   ")

        opts = network_opts()

        assert opts.proxy == ""
        assert opts.use_env is False

    def test_the_machines_proxy_is_not_read_here(self, settings):
        """It is each client's own business to find it, and they differ."""

        assert network_opts().proxy == ""

    def test_it_can_be_compared_against_the_settings_as_they_were(self, settings):
        """A session that outlives the dialog keeps one and asks again."""

        before = network_opts()

        assert network_opts() == before

        _custom_proxy(settings)

        assert network_opts() != before

    def test_it_can_be_used_as_a_key(self, settings):
        assert hash(network_opts()) == hash(network_opts())


class TestWhetherALinkCanStillGoStraightToVlc:
    """VLC honours a user agent and nothing else on this page.

    So every other setting turns a link it could have opened itself into
    one the proxy has to fetch, the way a stored cookie already does.
    """

    def test_out_of_the_box_it_is_handed_over_as_it_was(self, settings, no_cookies):
        assert not needs_relay(VIDEO_URL)

    def test_a_proxy_of_the_users_own(self, settings, no_cookies):
        _custom_proxy(settings)

        assert needs_relay(VIDEO_URL)

    def test_refusing_the_machines_proxy(self, settings, no_cookies):
        """VLC looks for one whatever we do, so it has to be kept away."""

        settings["network/proxy_mode"] = ProxyMode.NONE

        assert needs_relay(VIDEO_URL)

    def test_an_address_family(self, settings, no_cookies):
        settings["network/ip_version"] = IPVersion.V4

        assert needs_relay(VIDEO_URL)

    def test_certificates_going_unchecked(self, settings, no_cookies):
        settings["network/verify_tls"] = False

        assert needs_relay(VIDEO_URL)

    def test_a_user_agent_on_its_own_does_not(self, settings, no_cookies):
        """It is the one thing VLC can be told, so it is told it."""

        settings["network/user_agent"] = "Mozilla/5.0 (test)"

        assert not needs_relay(VIDEO_URL)

    def test_a_timeout_on_its_own_does_not(self, settings, no_cookies):
        """Nothing about how long we wait changes where the bytes come from."""

        settings["network/timeout"] = 5

        assert not needs_relay(VIDEO_URL)

    def test_a_stored_login_still_speaks_for_itself(self, settings, monkeypatch):
        monkeypatch.setattr(network_module, "has_cookies_for", lambda url: True)

        assert needs_relay(VIDEO_URL)

    @pytest.mark.parametrize("url", ["rtmp://host/live", "rtsp://host/live", "/tmp/v"])
    def test_what_the_relay_could_not_carry_is_left_alone(
        self, settings, no_cookies, url
    ):
        """The relay is an HTTP server, whatever the settings ask for."""

        _custom_proxy(settings)

        assert not needs_relay(url)


class TestHandingThemToYtDlp:
    def test_out_of_the_box_it_is_told_nothing(self, settings):
        """Every key left out is one yt-dlp decides for itself."""

        assert ytdl_network_opts() == {}

    def test_a_proxy_of_the_users_own(self, settings):
        _custom_proxy(settings)

        assert ytdl_network_opts()["proxy"] == PROXY_URL

    def test_refusing_a_proxy_is_said_out_loud(self, settings):
        """Empty reads as no proxy at all; leaving it out reads as find one."""

        settings["network/proxy_mode"] = ProxyMode.NONE

        assert ytdl_network_opts()["proxy"] == ""

    def test_going_by_the_machine_leaves_it_to_look(self, settings):
        assert "proxy" not in ytdl_network_opts()

    def test_an_address_family_is_a_source_address(self, settings):
        settings["network/ip_version"] = IPVersion.V4

        assert ytdl_network_opts()["source_address"] == "0.0.0.0"

    def test_the_other_address_family(self, settings):
        settings["network/ip_version"] = IPVersion.V6

        assert ytdl_network_opts()["source_address"] == "::"

    def test_the_user_agent_goes_as_a_header(self, settings):
        settings["network/user_agent"] = "Mozilla/5.0 (test)"

        assert ytdl_network_opts()["http_headers"] == {
            "User-Agent": "Mozilla/5.0 (test)"
        }

    def test_certificates_going_unchecked(self, settings):
        settings["network/verify_tls"] = False

        assert ytdl_network_opts()["nocheckcertificate"] is True

    def test_a_timeout(self, settings):
        settings["network/timeout"] = 5

        assert ytdl_network_opts()["socket_timeout"] == 5


class TestHandingThemToStreamlink:
    def test_out_of_the_box_the_session_is_left_as_it_was(self, settings):
        session = _FakeSession({"User-Agent": "Streamlink/1.0"})

        apply_to_streamlink(session)

        assert session.http.headers == {"User-Agent": "Streamlink/1.0"}
        assert session.http.proxies == {}
        assert session.http.trust_env is True
        assert session.http.verify is True
        assert session.http.timeout == DEFAULT_TIMEOUT_SEC

    def test_a_proxy_of_the_users_own_covers_both_schemes(self, settings):
        _custom_proxy(settings)
        session = _FakeSession()

        apply_to_streamlink(session)

        assert session.http.proxies == {"http": PROXY_URL, "https": PROXY_URL}
        assert session.http.trust_env is False

    def test_refusing_a_proxy_stops_it_reading_the_environment(self, settings):
        settings["network/proxy_mode"] = ProxyMode.NONE
        session = _FakeSession()

        apply_to_streamlink(session)

        assert session.http.proxies == {}
        assert session.http.trust_env is False

    def test_an_address_family(self, settings):
        settings["network/ip_version"] = IPVersion.V4
        session = _FakeSession()

        apply_to_streamlink(session)

        assert session.options == {"ipv4": True, "ipv6": False}

    def test_certificates_going_unchecked(self, settings):
        settings["network/verify_tls"] = False
        session = _FakeSession()

        apply_to_streamlink(session)

        assert session.http.verify is False

    def test_a_timeout(self, settings):
        settings["network/timeout"] = 5
        session = _FakeSession()

        apply_to_streamlink(session)

        assert session.http.timeout == 5.0


class TestApplyingThemAgainToASessionAlreadyRunning:
    """One is made per service and kept for as long as the proxy runs.

    So what it was handed when it was made is not the last word on it,
    and a second telling has to leave it as though it were the first.
    """

    def test_what_the_header_was_laid_over_is_given_back(self, settings):
        """A format's own user agent is not ours to throw away."""

        session = _FakeSession({"User-Agent": "Streamlink/1.0"})
        settings["network/user_agent"] = "Mozilla/5.0 (test)"
        apply_to_streamlink(session)

        settings["network/user_agent"] = ""
        apply_to_streamlink(session)

        assert session.http.headers["User-Agent"] == "Streamlink/1.0"

    def test_a_header_the_session_picked_up_elsewhere_is_left_alone(self, settings):
        session = _FakeSession()
        apply_to_streamlink(session)

        session.http.headers["X-Site"] = "whatever the resolver said"
        apply_to_streamlink(session)

        assert session.http.headers["X-Site"] == "whatever the resolver said"

    def test_a_timeout_taken_off_the_page_gives_the_old_one_back(self, settings):
        settings["network/timeout"] = 5
        session = _FakeSession()
        apply_to_streamlink(session)

        settings["network/timeout"] = 0
        apply_to_streamlink(session)

        assert session.http.timeout == DEFAULT_TIMEOUT_SEC

    def test_a_proxy_switched_off_since_stops_being_used(self, settings):
        _custom_proxy(settings)
        session = _FakeSession()
        apply_to_streamlink(session)

        settings["network/proxy_mode"] = ProxyMode.SYSTEM
        apply_to_streamlink(session)

        assert session.http.proxies == {}
        assert session.http.trust_env is True


class TestGettingASessionReadyToFetchWith:
    """Both pages of settings land on it, from the one call."""

    @pytest.fixture
    def stored_login(self, tmp_path, monkeypatch):
        path = tmp_path / "cookies.txt"
        path.write_text(
            "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tabc\n",
            encoding="utf-8",
        )

        store = cookies_module.CookieStore(path)

        monkeypatch.setattr(cookies_module, "cookie_store", lambda: store)
        monkeypatch.setattr(
            cookies_module,
            "Settings",
            lambda: FakeSettings(
                {"cookies/enabled": True, "cookies/allow_update": False}
            ),
        )

        return store

    def test_the_cookies_go_on(self, settings, stored_login):
        session = _FakeSession()

        configure_session(session)

        assert session.http.cookies.get("SID") == "abc"

    def test_the_network_settings_go_on(self, settings, stored_login):
        _custom_proxy(settings)
        session = _FakeSession()

        configure_session(session)

        assert session.http.proxies == {"http": PROXY_URL, "https": PROXY_URL}

    def test_a_session_already_in_use_catches_up(self, settings, stored_login):
        session = _FakeSession()
        configure_session(session)

        _custom_proxy(settings)
        configure_session(session)

        assert session.http.proxies == {"http": PROXY_URL, "https": PROXY_URL}
        assert session.http.cookies.get("SID") == "abc"


class TestWhatVlcIsCalled:
    def test_out_of_the_box_it_is_what_it_has_always_been(self, settings):
        assert vlc_user_agent() == DEFAULT_USER_AGENT

    def test_one_the_user_set_is_used_instead(self, settings):
        settings["network/user_agent"] = "Mozilla/5.0 (test)"

        assert vlc_user_agent() == "Mozilla/5.0 (test)"

    def test_nothing_but_spaces_is_nothing(self, settings):
        settings["network/user_agent"] = "   "

        assert vlc_user_agent() == DEFAULT_USER_AGENT
