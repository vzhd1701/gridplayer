import re
from dataclasses import dataclass
from types import MappingProxyType

from gridplayer.models.chapter import Chapter
from gridplayer.models.media_list import ItemDetails
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


class PlaylistURLError(Exception):
    """A link to a list of videos rather than to one"""

    def __init__(self, info: dict | None = None):
        super().__init__("Link to a list of videos")

        # what yt-dlp read of the list, for what is on it
        self.info = info or {}


@dataclass
class ResolvedList:
    """A link that leads to a list of videos, with what is on it."""

    title: str
    # ListItem each, in the order the site lists them
    items: tuple


@dataclass
class ResolvedVideo:
    title: str
    is_live: bool
    streams: Streams
    # the chapters the site lists, for a video whose file carries none
    chapters: tuple[Chapter, ...] = ()
    # how long the site says the video is, 0 where it does not say
    duration_ms: int = 0
    # the ID of a YouTube video that is not live, which is what SponsorBlock
    # is asked about; None for anything else
    youtube_id: str | None = None
    # what the site says of the video, for a list it is on to show
    details: ItemDetails | None = None
