import contextlib
import itertools
import re
from typing import Dict, Optional

from streamlink import Streamlink
from streamlink.stream import HTTPStream

from gridplayer.utils.url_resolve.static import BadURLException


def is_hls_live_stream(
    url: str,
    session: Optional[Streamlink] = None,
    session_headers: Optional[Dict[str, str]] = None,
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


def is_http_live_stream(
    url: str,
    session: Optional[Streamlink] = None,
    session_headers: Optional[Dict[str, str]] = None,
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
