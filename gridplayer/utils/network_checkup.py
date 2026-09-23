"""What the network settings actually do, tried rather than taken on trust.

A proxy that is typed in wrong fails the same way as one that is typed in
right and refuses us: the video does not play. So do a name that will not
resolve, an address family the route does not carry, and a certificate
nothing here trusts. The settings page cannot tell those apart, and
neither can the one line a failed video shows.

So the steps a request goes through are walked one at a time -- the
address is read, then looked up, then connected to, then fetched from --
and the one that gave way is named. Each step leaves behind what the next
one needs, so a step whose ground was never laid says so rather than
failing.

Nothing here sends cookies. The point is the connection, and a checkup is
no reason to put a login on the wire.
"""

import re
import socket
import time
import urllib.parse
import urllib.request
from types import MappingProxyType

import requests
from streamlink import Streamlink

from gridplayer.params.static import ProxyMode
from gridplayer.utils.checkup import Check, CheckResult, CheckStatus, Checkup
from gridplayer.utils.network import (
    NetworkOpts,
    apply_to_streamlink,
    fetch_capped,
    network_opts,
)
from gridplayer.utils.qt import translate

TRANSLATION_CONTEXT = "Network Checkup"

# A page whose whole job is to be fetched by something that is not a
# browser, on the site this player is pointed at more than any other. It
# is small, it is never personalised, and asking for it is the least
# interesting thing anybody does to that host all day.
TEST_URL = "https://www.youtube.com/robots.txt"

# what requests can be pointed at, and so what an address here may say
PROXY_SCHEMES = MappingProxyType(
    {
        "http": 8080,
        "https": 8080,
        "socks4": 1080,
        "socks4a": 1080,
        "socks5": 1080,
        "socks5h": 1080,
    }
)

# whatever an address puts in front of the host, which is a user name
# and as likely as not a password with it
CREDENTIALS_PATTERN = re.compile(r"//[^/@]*@")

# the ones that hand the name to the proxy rather than resolving it here,
# which is the difference that decides whether a name only the far side
# knows about can be reached at all
REMOTE_DNS_SCHEMES = frozenset({"socks4a", "socks5h"})

FAMILY_NAMES = MappingProxyType(
    {
        socket.AF_INET: "IPv4",
        socket.AF_INET6: "IPv6",
    }
)

# what a URL means when it does not say
SCHEME_PORTS = MappingProxyType({"http": 80, "https": 443})

# what a session waits where the page has named nothing, matching what
# Streamlink came set to: long enough for a slow host, short enough that a
# checkup sitting there is obvious
DEFAULT_TIMEOUT_SEC = 20

# how many of the addresses a name resolves to are worth naming; the rest
# are counted. A big site answers with more than a line can hold
ADDRESSES_SHOWN = 2

HTTP_BAD_REQUEST = 400

BYTES_IN_KIB = 1024

# enough of the page to prove bytes are coming back
SAMPLE_BYTES = 8 * 1024


class NetworkCheckup(Checkup):
    """The network page, step by step, against a real address.

    Built from whatever settings it is handed rather than from the stored
    ones, so the settings page can try what it is showing.
    """

    def __init__(self, opts: NetworkOpts | None = None):
        self._opts = opts if opts is not None else network_opts()

        self._addresses = ()

        # what the proxy address check made of it, where there was one
        # to make anything of: nothing after it is worth trying against
        # an address that cannot be used
        self._is_proxy_usable = None

        # and whether anything turned out to be there, which the fetch
        # would only find out again in worse words
        self._is_reached = False

    @property
    def title(self) -> str:
        return _t("Network checkup")

    @property
    def intro(self) -> str:
        return _t(
            "The network settings on this page, tried against a real"
            " address. No cookies are sent."
        )

    @property
    def checks(self) -> tuple[Check, ...]:
        return (
            Check(_t("Settings in use"), self.check_settings),
            Check(_t("Proxy address"), self.check_proxy_address),
            Check(_t("Looking up the address"), self.check_lookup),
            Check(_t("Opening a connection"), self.check_connect),
            Check(_t("Fetching a page"), self.check_fetch),
        )

    def check_settings(self) -> CheckResult:
        """What is about to be tried, before anything is tried.

        Worth a row of its own because the commonest way for this page to
        do nothing is for it to be set to nothing, and because a run
        pasted into a bug report should say what it was run with. Read
        back in the page's own words, so the two can be compared without
        anybody working out which setting is being talked about.
        """

        status = CheckStatus.WARNING if self._is_proxy_missing else CheckStatus.PASSED

        return CheckResult(status, self._proxy_summary, self._settings_list)

    def check_proxy_address(self) -> CheckResult:
        """Whether the address typed in is one that can be used at all.

        A proxy is the one setting on the page written out by hand, so it
        is the one that can be wrong in ways nothing else can: a scheme
        left off, a port left off, a scheme nothing here speaks.
        """

        if not self._opts.proxy:
            return CheckResult(CheckStatus.SKIPPED, self._nothing_to_check)

        parsed = _split(self._opts.proxy)

        self._is_proxy_usable = False

        if parsed is None or not parsed.scheme:
            return CheckResult(
                CheckStatus.FAILED,
                _t("The address does not say what kind of proxy it is"),
                _t(
                    "Start it with the kind and ://, as in"
                    " http://host:port or socks5h://host:port."
                ),
            )

        if parsed.scheme not in PROXY_SCHEMES:
            return CheckResult(
                CheckStatus.FAILED,
                _t("{SCHEME} is not a kind of proxy GridPlayer can use").format(
                    SCHEME=parsed.scheme
                ),
                _t("It understands {SCHEMES}.").format(
                    SCHEMES=", ".join(PROXY_SCHEMES)
                ),
            )

        if not parsed.hostname:
            return CheckResult(
                CheckStatus.FAILED, _t("The address names no host to connect to")
            )

        self._is_proxy_usable = True

        return _proxy_address_result(parsed)

    def check_lookup(self) -> CheckResult:
        """Whether the name to be connected to resolves, and to what.

        The name is the proxy's where there is one and the site's where
        there is not, because that is the one this machine looks up
        either way. Forcing an address family is answered here: a host
        Forcing IPv4 is answered here too: a host that only has an IPv6
        address cannot be reached that way, and this is where that stops
        being mysterious.
        """

        if self._is_proxy_usable is False:
            return _no_usable_proxy()

        host, port, _ = self._endpoint

        family = socket.AF_INET if self._opts.force_ipv4 else socket.AF_UNSPEC

        try:
            found = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
        except OSError as e:
            return CheckResult(
                CheckStatus.FAILED, _lookup_error(host, e), _dns_hint(self._opts)
            )

        # family and sockaddr, which is all a connection needs of an
        # entry; the rest of what getaddrinfo answers with is protocol
        # bookkeeping this is not making a choice about
        self._addresses = tuple((entry[0], entry[4]) for entry in found)

        return CheckResult(
            CheckStatus.PASSED, _addresses_summary(host, self._addresses)
        )

    def check_connect(self) -> CheckResult:
        """Whether anything answers at the address, before asking it for a page.

        Told apart from the fetch because they fail for unrelated
        reasons: nothing listening, a firewall in the way and a route
        that does not go there all stop here, and everything to do with
        TLS, credentials and what the far side thinks of us stops later.
        """

        if self._is_proxy_usable is False:
            return _no_usable_proxy()

        if not self._addresses:
            return CheckResult(CheckStatus.SKIPPED, _t("No address to connect to"))

        started = time.monotonic()

        family, address, error = self._connect()

        if error is not None:
            return CheckResult(
                CheckStatus.FAILED,
                _t("Could not connect to {WHAT}: {ERROR}").format(
                    WHAT=self._endpoint[2], ERROR=_clipped(error)
                ),
                _connect_hint(self._opts),
            )

        self._is_reached = True

        return CheckResult(
            CheckStatus.PASSED,
            _t("Connected to {WHAT} over {FAMILY} in {SECONDS}").format(
                WHAT=_reached_text(self._endpoint[2], address),
                FAMILY=_family_name(family),
                SECONDS=_seconds(time.monotonic() - started),
            ),
        )

    def check_fetch(self) -> CheckResult:
        """A whole request, the way everything that plays a link makes one.

        The same session the relay fetches with, configured from the same
        settings, so what happens here is what happens to a video.
        """

        if self._is_proxy_usable is False:
            return _no_usable_proxy()

        if not self._is_reached:
            return CheckResult(
                CheckStatus.SKIPPED,
                _t("Not tried, {WHAT} could not be reached").format(
                    WHAT=self._endpoint[2]
                ),
            )

        started = time.monotonic()

        try:
            status, read = self._fetch()
        except requests.exceptions.SSLError as e:
            return CheckResult(CheckStatus.FAILED, _clipped(e), _tls_hint(self._opts))
        except requests.exceptions.ProxyError as e:
            return CheckResult(CheckStatus.FAILED, _clipped(e), _proxy_error_hint())
        except OSError as e:
            return CheckResult(
                CheckStatus.FAILED, _clipped(e), _connect_hint(self._opts)
            )

        summary = _t("HTTP {STATUS}, {KIB} KiB from {HOST} in {SECONDS}").format(
            STATUS=status,
            KIB=read // BYTES_IN_KIB or 1,
            HOST=_site_endpoint()[0],
            SECONDS=_seconds(time.monotonic() - started),
        )

        if status >= HTTP_BAD_REQUEST:
            return CheckResult(
                CheckStatus.WARNING,
                summary,
                _t(
                    "The connection worked and the host turned the request"
                    " down, which is between you and that host rather than"
                    " a problem with these settings."
                ),
            )

        if not read:
            return CheckResult(
                CheckStatus.WARNING,
                summary,
                _t("The host answered without sending anything."),
            )

        return CheckResult(CheckStatus.PASSED, summary)

    @property
    def _timeout(self) -> float:
        return float(self._opts.timeout or DEFAULT_TIMEOUT_SEC)

    @property
    def _endpoint(self) -> tuple[str, int, str]:
        """The host and port this machine opens a socket to, and its name.

        The proxy where there is one: everything past it is the proxy's
        business, and with a name resolved at the far side there is
        nothing here to look up anyway.

        The name comes back with it rather than being worked out again,
        so a step cannot report on one host while having tried another.
        """

        parsed = _split(self._opts.proxy) if self._opts.proxy else None

        if parsed is not None and parsed.hostname:
            return (
                parsed.hostname,
                _port_of(parsed),
                _t("the proxy at {HOST}").format(HOST=parsed.hostname),
            )

        return _site_endpoint()

    @property
    def _is_proxy_missing(self) -> bool:
        """Custom picked and the address left empty, which means no proxy."""

        return self._opts.proxy_mode is ProxyMode.CUSTOM and not self._opts.proxy

    @property
    def _nothing_to_check(self) -> str:
        if self._opts.use_env:
            return _t("No address to check, the system settings are in use")

        return _t("No address to check, no proxy is in use")

    @property
    def _proxy_summary(self) -> str:
        """The Proxy setting, and what it works out to."""

        if self._opts.proxy:
            return _t("Proxy: Custom, {PROXY}").format(
                PROXY=_redacted(self._opts.proxy)
            )

        if self._is_proxy_missing:
            return _t("Proxy: Custom, but no address filled in")

        if not self._opts.use_env:
            return _t("Proxy: None")

        from_machine = _machine_proxies()

        if not from_machine:
            return _t("Proxy: System, none set on this machine")

        return _t("Proxy: System, {PROXIES}").format(PROXIES=", ".join(from_machine))

    @property
    def _settings_list(self) -> str:
        """The rest of the page, one setting to a line, then what to do.

        The labels are the page's own, so a line here can be matched to
        the field it came from without anybody working it out.
        """

        lines = [
            _t("Force IPv4: {VALUE}").format(VALUE=_yes_or_no(self._opts.force_ipv4)),
            _t("Timeout: {VALUE}").format(VALUE=_timeout_text(self._opts.timeout)),
            _t("User agent: {VALUE}").format(VALUE=self._opts.user_agent or _t("Auto")),
            _t("Verify TLS certificates: {VALUE}").format(
                VALUE=_yes_or_no(self._opts.verify_tls)
            ),
        ]

        if self._is_proxy_missing:
            lines += [
                "",
                _t(
                    "No proxy will be used. Fill in the address, or set"
                    " Proxy to System or None."
                ),
            ]

        if self._opts.is_relay_required:
            lines += [
                "",
                _t(
                    "http and https links go through GridPlayer instead of"
                    " straight to the player, because the player cannot be"
                    " given these settings."
                ),
            ]

        return "\n".join(lines)

    def _connect(self):
        """Open a socket to the first of the addresses that takes one.

        Every one of them is tried, the way anything else connecting to a
        name would, so a host with a dead address alongside a live one is
        not reported as unreachable.
        """

        error = None

        for family, address in self._addresses:
            reached = self._try_address(family, address)

            if reached is None:
                return family, address, None

            error = reached

        return None, None, error

    def _try_address(self, family, address) -> OSError | None:
        """Nothing where the address took a connection, the reason where not."""

        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(self._timeout)
                probe.connect(address)
        except OSError as e:
            return e

        return None

    def _fetch(self) -> tuple[int, int]:
        """One whole request, and then the process put back as it was.

        An address family is a urllib3 global rather than anything a
        session owns, so trying one here reaches every video already
        playing behind this dialog. None of them asked to be tried with
        settings nobody has saved, so the stored ones go back on.
        """

        session = Streamlink()

        apply_to_streamlink(session, self._opts)

        try:
            status, page = fetch_capped(
                session, TEST_URL, SAMPLE_BYTES, timeout=self._timeout
            )
        finally:
            apply_to_streamlink(session)

        return status, len(page)


def _t(text: str) -> str:
    return translate(TRANSLATION_CONTEXT, text)


def _proxy_address_result(parsed) -> CheckResult:
    """What a well-formed proxy address is still worth saying about."""

    port = _port_of(parsed)

    summary = _t("{SCHEME} proxy at {HOST}, port {PORT}").format(
        SCHEME=parsed.scheme, HOST=parsed.hostname, PORT=port
    )

    hints = []

    if parsed.port is None:
        hints.append(_t("No port was given, so {PORT} is assumed.").format(PORT=port))

    if parsed.scheme.startswith("socks") and parsed.scheme not in REMOTE_DNS_SCHEMES:
        hints.append(
            _t(
                "{SCHEME} looks host names up on this machine. Use {REMOTE}"
                " instead to have the proxy look them up, which is what you"
                " want if the names you are after only resolve on its side."
            ).format(SCHEME=parsed.scheme, REMOTE=_remote_dns_twin(parsed.scheme))
        )

    if not hints:
        return CheckResult(CheckStatus.PASSED, summary)

    return CheckResult(CheckStatus.WARNING, summary, "\n".join(hints))


def _split(url: str):
    """A proxy address taken apart, or nothing if it will not come apart.

    An address with a bad port in it raises on the way out of urlsplit
    rather than on the way in, so it is asked for here where there is
    somewhere to say no.
    """

    try:
        parsed = urllib.parse.urlsplit(url)
        parsed.port  # noqa: B018
    except ValueError:
        return None

    # Python before 3.11 takes the 127.0.0.1 in 127.0.0.1:1080 for a
    # scheme, later ones know a scheme starts with a letter
    if parsed.scheme and not parsed.scheme[0].isalpha():
        return parsed._replace(scheme="", path=f"{parsed.scheme}:{parsed.path}")

    return parsed


def _port_of(parsed) -> int:
    if parsed.port is not None:
        return parsed.port

    return PROXY_SCHEMES.get(parsed.scheme, SCHEME_PORTS["http"])


def _site_endpoint() -> tuple[str, int, str]:
    """The host, port and name of the page this is all pointed at."""

    parsed = urllib.parse.urlsplit(TEST_URL)

    host = parsed.hostname or TEST_URL
    port = parsed.port or SCHEME_PORTS.get(parsed.scheme, SCHEME_PORTS["https"])

    return host, port, host


def _remote_dns_twin(scheme: str) -> str:
    return "socks5h" if scheme == "socks5" else "socks4a"


def _machine_proxies() -> list[str]:
    """What this machine says its proxies are, as anything here would find.

    The environment on every platform, and the registry on Windows;
    the same places every client the app drives looks, so naming them
    here says what "System" is about to come to.
    """

    found = urllib.request.getproxies()

    return [f"{scheme} via {_redacted(url)}" for scheme, url in sorted(found.items())]


def _redacted(url: str) -> str:
    """A proxy address with the password taken out of it.

    Proxies are given credentials often enough, and a report written to
    be pasted into a bug tracker should not carry one.
    """

    parsed = _split(url)

    if parsed is None:
        # it would not come apart, so there is no telling which part of
        # it is a password; whatever is in front of an @ might be
        return CREDENTIALS_PATTERN.sub("//***@", url)

    if parsed.password is None:
        return url

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""

    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            f"{parsed.username or ''}:***@{host}{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _no_usable_proxy() -> CheckResult:
    """Nothing past the proxy is worth trying until the address is right."""

    return CheckResult(
        CheckStatus.SKIPPED, _t("Not tried, the proxy address has to be right first")
    )


def _timeout_text(timeout: int) -> str:
    if timeout:
        return _t("{SECONDS} sec").format(SECONDS=timeout)

    return _t("Auto")


def _yes_or_no(flag: bool) -> str:
    return _t("Yes") if flag else _t("No")


def _addresses_summary(host: str, addresses) -> str:
    shown = ", ".join(
        _address_text(address) for _, address in addresses[:ADDRESSES_SHOWN]
    )

    families = ", ".join(dict.fromkeys(_family_name(family) for family, _ in addresses))

    rest = len(addresses) - ADDRESSES_SHOWN

    if rest > 0:
        shown = _t("{SHOWN} and {REST} more").format(SHOWN=shown, REST=rest)

    return _t("{HOST} is {SHOWN} ({FAMILIES})").format(
        HOST=host, SHOWN=shown, FAMILIES=families
    )


def _address_text(address) -> str:
    return str(address[0])


def _reached_text(name: str, address) -> str:
    """What was connected to, without saying an IP address twice.

    The name is the proxy's or the site's, and for a proxy typed in as
    an address the two are the same string.
    """

    reached = _address_text(address)

    if reached in name:
        return name

    return _t("{NAME} at {ADDRESS}").format(NAME=name, ADDRESS=reached)


def _family_name(family) -> str:
    return FAMILY_NAMES.get(family, str(family))


def _seconds(elapsed: float) -> str:
    return _t("{SECONDS} sec").format(SECONDS=f"{elapsed:.2f}")


def _lookup_error(host: str, error: OSError) -> str:
    return _t("{HOST} could not be looked up: {ERROR}").format(
        HOST=host, ERROR=_clipped(error)
    )


def _dns_hint(opts: NetworkOpts) -> str:
    if opts.force_ipv4:
        return _t(
            'The host may have no IPv4 address. Turn "Force IPv4" off and try again.'
        )

    return _t("The name did not resolve. Check the address and your DNS.")


def _connect_hint(opts: NetworkOpts) -> str:
    if opts.proxy:
        return _t(
            "Nothing answered where the proxy address says it should be."
            " Check that it is running and that the port is right."
        )

    if opts.force_ipv4:
        return _t(
            "The address resolved but would not take a connection. Try"
            ' turning "Force IPv4" off, in case the host is only reachable'
            " over IPv6."
        )

    return _t("Nothing answered at that address.")


def _tls_hint(opts: NetworkOpts) -> str:
    if opts.verify_tls:
        return _t(
            "This machine does not trust the certificate. A proxy that"
            " inspects traffic signs with its own, which is the one case"
            ' for turning "Verify TLS certificates" off.'
        )

    return _t("The secure connection failed even with certificate checks off.")


def _proxy_error_hint() -> str:
    return _t(
        "The proxy would not pass the request on. That is usually"
        " credentials it wanted, or a host it will not connect to."
    )


def _clipped(error) -> str:
    """One line of what went wrong, out of however many it came with."""

    said = " ".join(str(error).split())

    return said or type(error).__name__
