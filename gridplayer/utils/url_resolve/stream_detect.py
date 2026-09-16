import contextlib
import itertools
import re

from streamlink import Streamlink
from streamlink.stream.http import HTTPStream

from gridplayer.utils.stream_proxy.mp4 import is_fragmented
from gridplayer.utils.url_resolve.static import BadURLException

MANIFEST_HEAD = 4096
FILE_HEAD = 64 * 1024


def is_hls_live_stream(
    url: str,
    session: Streamlink | None = None,
    session_headers: dict[str, str] | None = None,
) -> bool:
    if session is None:
        session = Streamlink()

        if session_headers:
            session.http.headers.update(session_headers)

    http_stream = HTTPStream(session, url, buffered=False)
    with contextlib.closing(http_stream.open()) as stream:
        first_lines = 20
        playlist_header = "".join(
            line.decode("utf-8") for line in itertools.islice(stream, first_lines)
        )

    if "#EXT-X-TWITCH-LIVE-SEQUENCE" in playlist_header:
        return True

    if "#EXT-X-PLAYLIST-TYPE:VOD" in playlist_header:
        return False

    if re.search("#EXT-X-MEDIA-SEQUENCE:0$", playlist_header, re.M):
        return False

    return bool(re.search(r"#EXT-X-MEDIA-SEQUENCE:[\d.]+$", playlist_header, re.M))


def is_dash_live_stream(
    url: str,
    session: Streamlink | None = None,
    session_headers: dict[str, str] | None = None,
) -> bool:
    """A DASH manifest is live when it declares itself dynamic."""

    if session is None:
        session = Streamlink()

        if session_headers:
            session.http.headers.update(session_headers)

    manifest = session.http.get(url).text

    return bool(re.search(r'type\s*=\s*"dynamic"', manifest[:MANIFEST_HEAD]))


def is_fragmented_stream(
    url: str,
    session: Streamlink | None = None,
    session_headers: dict[str, str] | None = None,
) -> bool:
    """Whether a plain file is fragmented, and so can be cut into segments."""

    if session is None:
        session = Streamlink()

        if session_headers:
            session.http.headers.update(session_headers)

    with session.http.get(
        url, headers={"Range": f"bytes=0-{FILE_HEAD - 1}"}, stream=True
    ) as response:
        return is_fragmented(next(response.iter_content(FILE_HEAD), b""))


def is_http_live_stream(
    url: str,
    session: Streamlink | None = None,
    session_headers: dict[str, str] | None = None,
) -> bool:
    """if there is a content-length header, it not a stream"""

    if session is None:
        session = Streamlink()

        if session_headers:
            session.http.headers.update(session_headers)

    # not using HEAD because some servers will return bad code
    with session.http.request("GET", url, stream=True) as response:
        if "text/html" in response.headers.get("Content-Type", ""):
            raise BadURLException(f"URL returned html page {url}")
        size = int(response.headers.get("Content-Length", 0))

    return size == 0
