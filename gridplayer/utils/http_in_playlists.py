"""Plain http links inside a playlist that was fetched over https.

Streamlink refuses them outright, as a downgrade. VLC, mpv and ffmpeg
follow them, and some IPTV hosts serve the playlist over https and the
streams it lists over http, so whether to follow them is left to the
user: network/allow_http_in_playlists.

Streamlink has no option for it. The check sits in M3U8Parser.uri, which
every HLS playlist goes through -- the resolver's, the stream proxy's and
those of plugins with a parser of their own -- so that is where it is let
through. Anything else the check stops, a file:// link above all, it
still stops.
"""

from urllib.parse import urlparse

from streamlink.stream.hls.m3u8 import M3U8Parser

from gridplayer.settings import Settings

_streamlink_uri = M3U8Parser.uri


def allow_http_in_playlists() -> None:
    """Put the setting in front of Streamlink's check. Safe to call again."""

    M3U8Parser.uri = _uri


def _uri(self, uri: str) -> str:
    # the setting is read only when it matters, and afresh each time, so
    # a change on the settings page holds for the next playlist fetched
    if (
        uri
        and self._scheme == "https"
        and urlparse(uri).scheme == "http"
        and Settings().get("network/allow_http_in_playlists")
    ):
        return uri

    return _streamlink_uri(self, uri)
