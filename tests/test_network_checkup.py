"""What the network checkup says, for each way a connection can fail.

The point of it is to tell apart failures that all look the same from
outside, so what matters is not that a step runs but that it comes back
with the one answer that sends somebody to the right place.

Nothing here goes out to the internet. The steps are pointed at servers
running on this machine, and the ones that cannot be staged locally --
a name that will not resolve, an address nothing listens on -- are
staged out of addresses reserved for exactly that.
"""

import socket
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from urllib3.util import connection

from gridplayer.params.static import ProxyMode
from gridplayer.utils import network_checkup
from gridplayer.utils.checkup import CheckStatus
from gridplayer.utils.network import opts_for
from gridplayer.utils.network_checkup import NetworkCheckup

PAGE = b"User-agent: *\nDisallow:\n"

# reserved for documentation, so nothing is ever listening on it and
# nothing is inconvenienced by being knocked on
UNROUTABLE_HOST = "192.0.2.1"

# reserved to never resolve
UNRESOLVABLE_HOST = "nothing.invalid"

# a literal with no IPv4 form at all, so asking for one is refused whether
# or not this machine has IPv6 of its own
IPV6_ONLY_HOST = "::1"

# short enough that a step which is meant to give up has given up before
# the test runner starts wondering
TIMEOUT_SEC = 1


class PageHandler(BaseHTTPRequestHandler):
    """The host the test page is on."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.seen.append(self.path)

        self.send_response(self.server.status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, format, *args):
        """Quiet, the test is not interested"""


@pytest.fixture
def site(serving, monkeypatch):
    """A host standing in for the one the checkup is pointed at."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
    server.seen = []
    server.status = HTTPStatus.OK

    serving(server)

    monkeypatch.setattr(network_checkup, "TEST_URL", _url_of(server))

    return server


@pytest.fixture
def forwarding_proxy(serving):
    """An HTTP proxy, which is to say a host given the whole URL.

    Comes back as its address and the list of URLs it was asked for,
    which is the whole of what a test needs to know it was used.
    """

    seen = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            seen.append(self.path)

            with urllib.request.urlopen(self.path, timeout=TIMEOUT_SEC) as answer:
                body = answer.read()
                status = answer.status

            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            """Quiet, the test is not interested"""

    server = serving(ThreadingHTTPServer(("127.0.0.1", 0), Handler))

    return f"http://127.0.0.1:{server.server_address[1]}", seen


@pytest.fixture
def listening():
    """A port with something on it that never says anything back.

    Enough to be connected to, which is all the connection step asks.
    """

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    yield f"http://127.0.0.1:{server.getsockname()[1]}"

    server.close()


def _url_of(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/robots.txt"


def _checkup(**kwargs) -> NetworkCheckup:
    return NetworkCheckup(
        opts_for(
            proxy_mode=kwargs.get("proxy_mode", ProxyMode.SYSTEM),
            proxy_url=kwargs.get("proxy_url", ""),
            user_agent=kwargs.get("user_agent", ""),
            force_ipv4=kwargs.get("force_ipv4", False),
            timeout=kwargs.get("timeout", TIMEOUT_SEC),
            verify_tls=kwargs.get("verify_tls", True),
        )
    )


def _up_to(checkup, title: str) -> dict:
    """The steps as far as one of them, in order, keyed by their titles.

    In order because they are written to build on each other, and no
    further than asked because the steps past the one being read about
    are the slow ones: a connection that has to time out to fail takes
    as long as it was told to wait.
    """

    ran = {}

    for check in checkup.checks:
        ran[check.title] = check.run()

        if check.title == title:
            break

    return ran


def _run(checkup) -> dict:
    """Every step, for when what is being read about is the whole run."""

    return _up_to(checkup, checkup.checks[-1].title)


def _step(checkup, title: str):
    """One row, with every step it builds on run first."""

    return _up_to(checkup, title)[title]


def _statuses(ran: dict) -> list:
    return [check_result.status for check_result in ran.values()]


class TestNothingIsConfigured:
    def test_every_step_passes(self, site):
        ran = _run(_checkup())

        assert ran["Proxy address"].status is CheckStatus.SKIPPED
        assert ran["Fetching a page"].status is CheckStatus.PASSED

    def test_the_page_really_was_fetched(self, site):
        _run(_checkup())

        assert site.seen == ["/robots.txt"]

    def test_the_settings_are_reported_before_anything_is_tried(self, site):
        said = _step(_checkup(), "Settings in use")

        assert said.status is CheckStatus.PASSED
        assert "Force IPv4: No" in said.hint

    def test_nothing_says_the_player_is_being_cut_out(self, site):
        """No setting the player cannot be given, so no relaying."""

        said = _step(_checkup(), "Settings in use").hint

        assert "go through GridPlayer" not in said


class TestAProxyThatWorks:
    def test_the_page_comes_back_through_it(self, site, forwarding_proxy):
        ran = _run(_checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url=forwarding_proxy[0]))

        assert ran["Fetching a page"].status is CheckStatus.PASSED
        assert forwarding_proxy[1] == [network_checkup.TEST_URL]

    def test_the_address_is_read_back_with_its_port(self, site, forwarding_proxy):
        said = _run(
            _checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url=forwarding_proxy[0])
        )

        assert said["Proxy address"].status is CheckStatus.PASSED
        assert "http proxy at 127.0.0.1" in said["Proxy address"].summary

    def test_the_connection_is_made_to_the_proxy_not_the_site(
        self, site, forwarding_proxy
    ):
        said = _run(
            _checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url=forwarding_proxy[0])
        )

        assert "the proxy at" in said["Opening a connection"].summary


class TestAnAddressThatCannotBeUsed:
    @pytest.mark.parametrize(
        ("proxy_url", "said"),
        [
            ("127.0.0.1:1080", "what kind of proxy"),
            ("ftp://host:21", "not a kind of proxy"),
            ("http://", "no host"),
        ],
    )
    def test_it_is_named_rather_than_tried(self, site, proxy_url, said):
        read = _step(
            _checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url=proxy_url), "Proxy address"
        )

        assert read.status is CheckStatus.FAILED
        assert said in read.summary

    def test_nothing_after_it_is_tried_against_the_site_instead(self, site):
        """Reporting on a connection nobody asked for is worse than nothing."""

        ran = _run(_checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url="ftp://host:21"))

        assert _statuses(ran)[2:] == [CheckStatus.SKIPPED] * 3
        assert site.seen == []

    def test_a_missing_port_is_pointed_out_rather_than_refused(self, site):
        ran = _up_to(
            _checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url="socks5h://127.0.0.1"),
            "Proxy address",
        )

        assert ran["Proxy address"].status is CheckStatus.WARNING
        assert "1080" in ran["Proxy address"].hint

    def test_the_socks_that_resolves_names_here_says_which_one_does_not(self, site):
        ran = _up_to(
            _checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url="socks5://127.0.0.1:1080"),
            "Proxy address",
        )

        assert "socks5h" in ran["Proxy address"].hint


class TestCustomWithNothingInIt:
    def test_it_is_pointed_out_as_meaning_no_proxy(self, site):
        """The settings say a proxy is wanted and none is going to be used."""

        ran = _up_to(_checkup(proxy_mode=ProxyMode.CUSTOM), "Settings in use")

        assert ran["Settings in use"].status is CheckStatus.WARNING

    def test_the_rest_of_the_run_carries_on_without_one(self, site):
        ran = _run(_checkup(proxy_mode=ProxyMode.CUSTOM))

        assert ran["Fetching a page"].status is CheckStatus.PASSED


class TestWhenSomethingIsInTheWay:
    def test_a_name_that_does_not_resolve_stops_at_the_lookup(self, site):
        ran = _run(
            _checkup(
                proxy_mode=ProxyMode.CUSTOM,
                proxy_url=f"http://{UNRESOLVABLE_HOST}:8080",
            )
        )

        assert ran["Looking up the address"].status is CheckStatus.FAILED
        assert ran["Opening a connection"].status is CheckStatus.SKIPPED

    def test_an_address_nothing_answers_on_stops_at_the_connection(self, site):
        ran = _run(
            _checkup(
                proxy_mode=ProxyMode.CUSTOM,
                proxy_url=f"http://{UNROUTABLE_HOST}:8080",
            )
        )

        assert ran["Looking up the address"].status is CheckStatus.PASSED
        assert ran["Opening a connection"].status is CheckStatus.FAILED

    def test_the_fetch_does_not_say_it_all_again_in_worse_words(self, site):
        ran = _run(
            _checkup(
                proxy_mode=ProxyMode.CUSTOM,
                proxy_url=f"http://{UNROUTABLE_HOST}:8080",
            )
        )

        assert ran["Fetching a page"].status is CheckStatus.SKIPPED
        assert UNROUTABLE_HOST in ran["Fetching a page"].summary

    def test_a_proxy_that_answers_and_says_nothing_fails_at_the_fetch(
        self, site, listening
    ):
        """Reachable is not the same as working, which is why both are asked."""

        ran = _run(_checkup(proxy_mode=ProxyMode.CUSTOM, proxy_url=listening))

        assert ran["Opening a connection"].status is CheckStatus.PASSED
        assert ran["Fetching a page"].status is CheckStatus.FAILED


class TestWhatTheHostSaysBack:
    def test_a_refusal_is_the_host_s_business_rather_than_a_broken_setting(self, site):
        site.status = HTTPStatus.FORBIDDEN

        said = _run(_checkup())["Fetching a page"]

        assert said.status is CheckStatus.WARNING
        assert "403" in said.summary


class TestWhatTheSettingsAreReportedAs:
    def test_a_password_in_the_proxy_address_is_not_written_down(self, site):
        """A report is written to be pasted somewhere public."""

        said = _step(
            _checkup(
                proxy_mode=ProxyMode.CUSTOM,
                proxy_url="http://user:hunter2@127.0.0.1:1",
            ),
            "Settings in use",
        )

        assert "hunter2" not in said.summary
        assert "user" in said.summary

    def test_a_password_survives_an_address_that_will_not_parse(self, site):
        """The one that cannot be taken apart is the one to be careful with."""

        said = _step(
            _checkup(
                proxy_mode=ProxyMode.CUSTOM,
                proxy_url="http://user:hunter2@127.0.0.1:notaport",
            ),
            "Settings in use",
        )

        assert "hunter2" not in said.summary

    def test_settings_the_player_cannot_be_given_say_so(self, site):
        said = _step(_checkup(verify_tls=False), "Settings in use")

        assert "go through GridPlayer" in said.hint

    @pytest.mark.parametrize(
        ("kwargs", "said"),
        [
            ({"force_ipv4": True}, "Force IPv4: Yes"),
            ({"timeout": 30}, "Timeout: 30 sec"),
            (
                {"user_agent": "Mozilla/5.0 (test)"},
                "User agent: Mozilla/5.0 (test)",
            ),
            ({"verify_tls": False}, "Verify TLS certificates: No"),
        ],
    )
    def test_each_setting_is_read_back(self, site, kwargs, said):
        assert said in _step(_checkup(**kwargs), "Settings in use").hint


class TestForcingIPv4:
    """The one thing it costs, and the thing it must not leave behind."""

    def test_a_host_that_is_only_reachable_over_ipv6_says_so(self, site):
        said = _step(
            _checkup(
                proxy_mode=ProxyMode.CUSTOM,
                proxy_url=f"http://[{IPV6_ONLY_HOST}]:8080",
                force_ipv4=True,
            ),
            "Looking up the address",
        )

        assert said.status is CheckStatus.FAILED
        assert "Force IPv4" in said.hint

    def test_the_same_host_is_found_with_it_off(self, site):
        """So the failure above is the setting, not the host being wrong."""

        said = _step(
            _checkup(
                proxy_mode=ProxyMode.CUSTOM,
                proxy_url=f"http://[{IPV6_ONLY_HOST}]:8080",
            ),
            "Looking up the address",
        )

        assert said.status is CheckStatus.PASSED

    def test_the_family_used_is_reported(self, site):
        said = _step(_checkup(force_ipv4=True), "Looking up the address")

        assert "IPv4" in said.summary

    def test_the_process_is_left_as_it_was_found(self, site):
        """It is a urllib3 global, and videos are playing behind the dialog."""

        before = connection.allowed_gai_family()

        _run(_checkup(force_ipv4=True))

        assert connection.allowed_gai_family() == before
