import re
from dataclasses import dataclass
from types import MappingProxyType

from gridplayer.models.chapter import Chapter
from gridplayer.models.stream import Streams

YOUTUBE_MATCH = re.compile(r"^(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)")

PLUGIN_URLS = MappingProxyType(
    {
        "streamlink": "https://streamlink.github.io/plugins.html",
        "yt-dlp": "https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md",
    }
)


class BadURLException(Exception):
    """Exception for bad URLs"""


class NoResolverPlugin(Exception):
    """Exception for no resolver plugin"""


class StreamOfflineError(Exception):
    """Exception for offline streams"""


@dataclass
class ResolvedVideo:
    title: str
    is_live: bool
    streams: Streams
    # the chapters the site lists, for a video whose file carries none
    chapters: tuple[Chapter, ...] = ()
    # how long the site says the video is, 0 where it does not say
    duration_ms: int = 0
