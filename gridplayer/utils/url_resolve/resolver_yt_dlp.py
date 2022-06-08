import itertools
import logging
import re
from typing import Optional

from yt_dlp import DownloadError, YoutubeDL
from yt_dlp.utils import UnsupportedError

from gridplayer.utils.url_resolve.static import (
    BadURLException,
    NoResolverPlugin,
    ResolvedVideo,
)
from gridplayer.utils.url_resolve.stream_detect import is_http_live_stream
from gridplayer.video import VideoURL

logger = logging.getLogger(__name__)


def resolve_youtube_dl(url: VideoURL) -> Optional[ResolvedVideo]:
    with YoutubeDL({"logger": logger}) as ydl:
        try:
            video_info = ydl.extract_info(url, download=False)
        except DownloadError as e:
            if e.exc_info[0] is UnsupportedError:
                raise NoResolverPlugin
            raise

    streams = _get_streams(video_info)

    stream_urls = _get_stream_urls(streams)

    if video_info.get("is_live") is None:
        is_live = is_http_live_stream(list(stream_urls.values())[-1])
    else:
        is_live = video_info["is_live"]

    return ResolvedVideo(
        title=video_info["title"],
        urls=stream_urls,
        is_live=is_live,
    )


def _get_streams(video_info):
    streams = [
        fmt
        for fmt in video_info["formats"]
        if fmt.get("vcodec") != "none" and fmt.get("acodec") != "none"
    ]

    # getting all streams if no combined stream is available
    if not streams:
        streams = video_info["formats"]

    if not streams:
        raise BadURLException("No streams found")

    return streams


def _get_stream_urls(streams):
    stream_urls = {}

    unknown_counter = itertools.count(1)

    for stream in streams:
        fmt_name = _get_fmt_name(stream, unknown_counter)

        stream_urls[fmt_name] = stream["url"]

    return stream_urls


def _get_fmt_name(stream, unknown_counter):
    fmt_name = stream.get("format_note") or stream.get("format_id")

    if not re.match(r"^\d+p", fmt_name):
        if stream.get("height"):
            if stream.get("format_id"):
                fmt_name = "{0}p [{1}]".format(stream["height"], stream["format_id"])
            else:
                fmt_name = "{0}p".format(stream["height"])
        else:
            fmt_name = stream.get("format", "Unknown {0}".format(next(unknown_counter)))

    if stream.get("acodec") == "none":
        fmt_name += " (video only)"

    if stream.get("vcodec") == "none":
        fmt_name += " (audio only)"

    return fmt_name
