"""Network settings shared by everything in here that reaches out.

Three clients fetch on the app's behalf and none of them agrees with the
others about how it is configured: yt-dlp takes a dict of options,
Streamlink takes a session to mutate, and VLC takes command line flags.
This module reads the settings once and hands each of them what it
understands, so a proxy is set in one place rather than three.

VLC is the odd one out. A user agent is the end of what it will honour
from here: it finds a proxy for itself and cannot be told not to, and it
has no notion of an address family or of whose certificates to trust. So
a setting VLC cannot carry out is answered the way a cookie already is --
the link stops being handed to VLC and goes through the stream proxy
instead, which fetches with the same session as everything else. See
needs_relay.
"""

import contextlib
import socket
import urllib.parse
from dataclasses import dataclass

from streamlink.exceptions import StreamlinkError

from gridplayer.params.static import ProxyMode
from gridplayer.settings import Settings
from gridplayer.utils.cookies import apply_to_streamlink as apply_cookies
from gridplayer.utils.cookies import cookies_stamp, has_cookies_for

# What anything here calls itself where the user has not said otherwise:
# a browser, because a bare Python user agent is turned away by enough
# sites to be worth not being one.
#
# Taken from the range yt-dlp draws its own from, which it keeps to the
# last few Chrome releases because sites read the version and an old one
# is treated as an old browser. It cannot be matched exactly -- yt-dlp
# rolls a fresh one every run -- and does not need to be: a link it
# resolved carries its user agent in the format headers, and those are
# what the relay fetches with. This one is for the links nothing else
# had an opinion about. Worth raising when it starts to look old.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

# the relay is an HTTP server; rtmp, mms and the rest cannot take the long
# way round however much a setting might want them to
RELAYABLE_SCHEMES = frozenset({"http", "https"})

# what a client binds to in order to be held to IPv4. Binding to the
# any-address of a family is how yt-dlp is told which one to use
IPV4_SOURCE_ADDRESS = "0.0.0.0"

# how much of a response is taken off the wire at a time while it is
# being read up to a cap
CHUNK_BYTES = 16 * 1024

# where what a session held before this module first wrote to it is
# remembered, so that clearing a setting hands that back rather than
# leaving the last thing we wrote standing
_ORIGINAL_USER_AGENT = "_gp_network_user_agent"
_ORIGINAL_TIMEOUT = "_gp_network_timeout"


@dataclass(frozen=True)
class NetworkOpts:
    """The network settings, as one thing that can be compared and hashed.

    Frozen because it doubles as the answer to "have the settings changed
    since": a session that outlives the settings dialog keeps the one it
    was built with and compares.
    """

    proxy_mode: ProxyMode
    # the proxy to fetch through, empty where there is none to use
    proxy: str
    # empty leaves every client on the user agent it came with
    user_agent: str
    # skip IPv6 and go out over IPv4 only
    force_ipv4: bool
    # zero leaves every client on the timeout it came with
    timeout: int
    verify_tls: bool

    @property
    def use_env(self) -> bool:
        """Whether the machine's own proxy settings are what we go by."""

        return self.proxy_mode is ProxyMode.SYSTEM

    @property
    def is_relay_required(self) -> bool:
        """Whether a link VLC could open by itself has to take the long way.

        A user agent is the one thing here VLC will honour, and a timeout
        is nobody's business but the client's. Everything else is
        something VLC cannot be told, so a link handed to it would be the
        one request in the session that ignored the setting.

        Refusing the machine's proxy counts. It is the only way to
        promise that nothing goes through one: VLC finds a proxy for
        itself, out of the environment on every platform and out of the
        registry on Windows, and there is no flag that stops it looking.
        """

        return (
            self.proxy_mode is not ProxyMode.SYSTEM
            or self.force_ipv4
            or not self.verify_tls
        )


def network_opts() -> NetworkOpts:
    """The network settings as the clients need them.

    Read afresh each time rather than kept: the settings dialog writes
    them with nothing to announce that it has, and everything downstream
    either holds on to the result or asks once per request.
    """

    settings = Settings()

    return opts_for(
        proxy_mode=settings.get("network/proxy_mode"),
        proxy_url=settings.get("network/proxy_url"),
        user_agent=settings.get("network/user_agent"),
        force_ipv4=settings.get("network/force_ipv4"),
        timeout=settings.get("network/timeout"),
        verify_tls=settings.get("network/verify_tls"),
    )


def opts_for(
    *,
    proxy_mode: ProxyMode,
    proxy_url: str,
    user_agent: str,
    force_ipv4: bool,
    timeout: int,
    verify_tls: bool,
) -> NetworkOpts:
    """What the settings come to, wherever they were read from.

    Stored is the usual answer, but not the only one: the settings page
    builds these out of its own widgets so that a checkup tries what is
    on screen rather than what was last saved.
    """

    return NetworkOpts(
        proxy_mode=proxy_mode,
        # Custom with nothing filled in is read as no proxy rather than
        # as the machine's: the user has said they want one of their
        # own, and falling back to the one they were moving away from
        # would be answering a half-finished form with the opposite of
        # what it says.
        proxy=proxy_url.strip() if proxy_mode is ProxyMode.CUSTOM else "",
        user_agent=user_agent.strip(),
        force_ipv4=force_ipv4,
        timeout=timeout,
        verify_tls=verify_tls,
    )


def needs_relay(url: str) -> bool:
    """Whether this URL has to go through the proxy rather than to VLC.

    A cookie is the long-standing reason; a network setting VLC cannot be
    told is the other. Either way what comes back is the same decision the
    resolvers have always made, asked in one place.
    """

    if urllib.parse.urlparse(url).scheme.lower() not in RELAYABLE_SCHEMES:
        return False

    return network_opts().is_relay_required or has_cookies_for(url)


def session_stamp() -> tuple:
    """What a configured session depends on, for comparing against later.

    A session made once and kept for the length of a run has to notice a
    login or a proxy that was edited since. Both pages answer for
    themselves; this is the pair of them, as one thing to compare.
    """

    return cookies_stamp(), network_opts()


def configure_session(session, opts: NetworkOpts | None = None) -> None:
    """Everything a Streamlink session needs before anything is fetched with it.

    Two pages of settings and one session, and every place that makes one
    needs both. Pairing them here means a new place that reaches out
    cannot pick up the cookies and forget the proxy.

    Safe to call again on a session that has been in use, so it is also
    how a session that outlives the settings dialog catches up.
    """

    apply_cookies(session)
    apply_to_streamlink(session, opts)


def apply_to_streamlink(session, opts: NetworkOpts | None = None) -> None:
    """Give a Streamlink session the network settings, and only those.

    Safe to call again on a session that is already running: the headers
    this put on last time are lifted off first, so a header the user has
    since deleted goes with them, and one that was laid over a value the
    session came with gives that value back.

    Settings other than the stored ones can be passed in, which is how a
    checkup tries what the settings page is showing.
    """

    if opts is None:
        opts = network_opts()

    # trust_env covers rather more than proxies -- a CA bundle and a
    # netrc named in the environment go the same way -- but there is no
    # separate switch for the proxies alone, and a machine set up to
    # reach out through a proxy is the case this is for
    session.http.trust_env = opts.use_env

    session.http.proxies = (
        {"http": opts.proxy, "https": opts.proxy} if opts.proxy else {}
    )

    session.http.verify = opts.verify_tls

    _apply_timeout(session, opts.timeout)
    _apply_user_agent(session, opts.user_agent)

    session.set_option("ipv4", opts.force_ipv4)

    # and the half of it that will not do. Streamlink's ipv4 option only
    # ever turns the restriction on: set to False on a session that
    # never had it on, it leaves whatever the last session turned on
    # still standing. And what stands is a urllib3 global rather than
    # anything this session owns, so not forcing it has to be said
    # outright or it means "whatever was asked for last".
    session.http.set_address_family(socket.AF_INET if opts.force_ipv4 else None)


def fetch_capped(session, url: str, limit: int, **kwargs) -> tuple[int, bytes]:
    """Fetch as much of something as is worth looking at, and no more.

    The checkups fetch to find out what happens rather than to play
    anything, so a refusal is answered like any other response: what a
    host said no with is as much of a result as what it said yes with.

    What went wrong on the way still raises, but as itself. Streamlink
    wraps it in a PluginError with a sentence about the URL in front,
    which is right for a plugin and wrong here: a checkup tells a proxy
    that refused us from a certificate nothing trusts by the type of
    what was raised.
    """

    try:
        response = session.http.get(url, stream=True, raise_for_status=False, **kwargs)
    except StreamlinkError as e:
        raise (getattr(e, "err", None) or e) from None

    with contextlib.closing(response):
        return response.status_code, _read_capped(response, limit)


def ytdl_network_opts() -> dict:
    """Network options for a YoutubeDL, leaving out what is not set.

    A key it is not given is one it decides for itself, which is what
    every setting left alone here should come to.
    """

    opts = network_opts()

    ydl_opts = {}

    if not opts.use_env:
        # an empty string reads as "no proxy at all", where None would
        # leave it to find one in the environment for itself
        ydl_opts["proxy"] = opts.proxy

    if opts.user_agent:
        ydl_opts["http_headers"] = {"User-Agent": opts.user_agent}

    if opts.force_ipv4:
        ydl_opts["source_address"] = IPV4_SOURCE_ADDRESS

    if not opts.verify_tls:
        ydl_opts["nocheckcertificate"] = True

    if opts.timeout:
        ydl_opts["socket_timeout"] = opts.timeout

    return ydl_opts


def vlc_user_agent() -> str:
    """What VLC calls itself, for the links that still go straight to it."""

    return network_opts().user_agent or DEFAULT_USER_AGENT


def _read_capped(response, limit: int) -> bytes:
    """As much of a response as was asked for, taken a chunk at a time.

    A checkup only ever wants the first slice of what it fetched -- a
    config block near the top of a page, enough of a stream to prove the
    host will serve it -- and reading the rest costs bandwidth to throw
    away.
    """

    read = bytearray()

    for chunk in response.iter_content(CHUNK_BYTES):
        read += chunk

        if len(read) >= limit:
            break

    return bytes(read[:limit])


def _apply_timeout(session, timeout: int) -> None:
    original = _original(session, _ORIGINAL_TIMEOUT, session.http.timeout)

    session.http.timeout = float(timeout) if timeout else original


def _apply_user_agent(session, user_agent: str) -> None:
    headers = session.http.headers

    original = _original(session, _ORIGINAL_USER_AGENT, headers.get("User-Agent"))

    wanted = user_agent or original

    if wanted is None:
        headers.pop("User-Agent", None)
    else:
        headers["User-Agent"] = wanted


def _original(session, name: str, current):
    """What the session held before this module first wrote to it.

    Kept on the session itself, because a setting cleared again has to
    hand back the value the session was made with rather than whatever
    this module last put there. Read once and kept: a format's own
    header goes on after us, and that is not ours to remember.
    """

    if not hasattr(session, name):
        setattr(session, name, current)

    return getattr(session, name)
