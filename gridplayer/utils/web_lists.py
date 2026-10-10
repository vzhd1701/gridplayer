"""Lists a site keeps behind a link: a YouTube playlist or channel, and the
like on the other sites yt-dlp knows.

Only read for what is on them -- each video's link, name and length, and
what the list page says of it: its channel, views, how long ago it was put
up and its picture -- the way yt-dlp reads a list without looking up every
video on it; each one is looked up when it comes to be played, its stream
links being good for a few hours at most.
"""

import calendar
import contextlib
import logging
import time
import urllib.parse
from pathlib import Path

from gridplayer.models.media_list import ItemDetails, ListItem, ListSource
from gridplayer.params.static import ListSourceKind
from gridplayer.utils.list_progress import ReadingEnough
from gridplayer.utils.misc import is_url

_log = logging.getLogger(__name__)

# results that are a list of videos rather than one
LIST_RESULT_TYPES = frozenset(("playlist", "multi_video"))

# how many videos of a list are read at most: a channel can have tens of
# thousands, a page of a hundred at a time
MAX_WEB_LIST_ITEMS = 5000

# how wide a video's picture is wanted: the List window shows it 80 px
# wide, which is 160 on a screen of twice the pixels
THUMBNAIL_WIDTH = 160

# a YouTube video's picture of the width wanted and no wider, 320 x 180,
# 16:9 with no bars: the ones yt-dlp lists are 4:3 with bars, or carry a
# signature of a hundred characters
YOUTUBE_THUMBNAIL = "https://i.ytimg.com/vi/{ID}/mqdefault.jpg"

# results that lead on to another link, to be read in their place
LINK_RESULT_TYPES = frozenset(("url", "url_transparent"))

# how many links on from the one added a list may be found at: a video
# opened from a playlist leads to the playlist
_MOST_LINKS_ON = 3

# what yt-dlp calls a video on a list that cannot be played
_UNPLAYABLE_TITLES = frozenset(("[Private video]", "[Deleted video]"))
_UNPLAYABLE_AVAILABILITY = frozenset(("private",))
_UNPLAYABLE_LIVE_STATUS = frozenset(("is_upcoming",))


class EmptyListError(ValueError):
    """A list read whole, with nothing on it that can be played."""


YOUTUBE_HOSTS = frozenset(
    (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    )
)

# the pages of a YouTube channel, and of a playlist
_YOUTUBE_LIST_PATHS = ("/playlist", "/@", "/c/", "/channel/", "/user/")


def is_web_list_url(url: str) -> bool:
    """Whether a link looks like one to a list on a site, told by its look
    alone, without asking the site or loading yt-dlp: a YouTube playlist, a
    channel, or a video opened from a playlist, which carries the playlist
    along in its link.

    What it leads to is only known once it is read, and a look that was
    wrong comes out as the one video it is. A list behind a link of any
    other look is found out once the link is played; see
    VideoBlock._link_was_a_list.
    """

    if not is_url(url):
        return False

    parsed = urllib.parse.urlparse(url)

    if parsed.hostname is None or parsed.hostname.lower() not in YOUTUBE_HOSTS:
        return False

    if urllib.parse.parse_qs(parsed.query).get("list"):
        return True

    return parsed.path.startswith(_YOUTUBE_LIST_PATHS)


def video_in_list(url: str) -> str | None:
    """The video a link opened from a playlist leads to, None for a link
    that is not one: watch?v=ID&list=LIST, youtu.be/ID?list=LIST."""

    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    if not query.get("list"):
        return None

    if query.get("v"):
        return query["v"][0]

    if parsed.netloc.lower().endswith("youtu.be"):
        return parsed.path.strip("/") or None

    return None


def without_list(url: str) -> str:
    """A link opened from a playlist as a link to the video alone."""

    parsed = urllib.parse.urlparse(url)

    if parsed.netloc.lower().endswith("youtu.be"):
        video_id = parsed.path.strip("/")
        return f"https://www.youtube.com/watch?v={video_id}"

    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"list", "index", "pp", "start_radio"}
    ]

    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def read_web_list(url: str, max_items: int = MAX_WEB_LIST_ITEMS, progress=None):
    """The list behind a link, as yt-dlp reads it: its name and the videos
    on it, in order, as many as there may be; or the one video it turns
    out to be.

    progress is told how many videos are read so far, as each page of them
    comes: ("items", count); where it raises ReadingEnough, the list is the
    videos read by then.
    """

    from gridplayer.utils.media_import import ListInput

    with ytdl(
        _log,
        {
            "extract_flat": "in_playlist",
            "playlistend": max_items,
            # when each video was put up, as near as the list page says:
            # "3 years ago"
            "extractor_args": {"youtubetab": {"approximate_date": [""]}},
        },
    ) as ydl:
        info = _list_info(ydl, url)

        # it looked like a list, and is one video
        if info.get("_type") not in LIST_RESULT_TYPES:
            return ListItem(uri=url, title=info.get("title") or None)

        name = info.get("title")

        # a channel's page lists its tabs, and its videos are the first of
        # them: its shorts and live streams are not read after them
        info = _first_tab(info) or info

        # read as it would have been all at once, the videos counted as
        # they come
        info = ydl.process_ie_result(counted_entries(info, progress), download=False)

    items = web_list_items(info)

    if not items:
        raise EmptyListError("nothing on the list to play")

    return ListInput(
        name=name or _name_of(url),
        items=items,
        source=ListSource(kind=ListSourceKind.URL, location=url),
        start=_place_of(items, video_in_list(url)),
    )


@contextlib.contextmanager
def ytdl(log: logging.Logger, opts: dict):
    """A yt-dlp to look things up with, reaching out the way the rest of
    the app does: with the cookies, the script runtimes and the network
    settings asked for; and these options of the caller's."""

    from yt_dlp import YoutubeDL

    from gridplayer.utils.cookies import ytdl_cookies
    from gridplayer.utils.js_runtime import ytdl_js_runtimes
    from gridplayer.utils.network import ytdl_network_opts
    from gridplayer.utils.percent_re import untangle_percent_re

    # yt-dlp patches urllib3 as it is imported; see utils/percent_re.py
    untangle_percent_re()

    with (
        ytdl_cookies() as cookie_opts,
        YoutubeDL(
            {
                "logger": log,
                "js_runtimes": ytdl_js_runtimes(),
                **opts,
                **cookie_opts,
                **ytdl_network_opts(),
            }
        ) as ydl,
    ):
        yield ydl


def duration_ms_of(info: dict) -> int | None:
    """How long a video is, as yt-dlp says, in milliseconds; None where it
    does not say."""

    duration = info.get("duration")

    if isinstance(duration, (int, float)) and duration > 0:
        return round(duration * 1000)

    return None


def _list_info(ydl, url: str) -> dict:
    """What a link leads to, as its site says it, the list's videos yet to
    be read from it; followed on where it leads to another link."""

    info = ydl.extract_info(url, download=False, process=False)

    for _ in range(_MOST_LINKS_ON):
        if info.get("_type") not in LINK_RESULT_TYPES:
            break

        info = ydl.extract_info(
            info["url"], download=False, process=False, ie_key=info.get("ie_key")
        )

    return info


def counted_entries(info: dict, progress) -> dict:
    """A list whose videos tell progress how many have been read, as yt-dlp
    reads them a page at a time, and end where it says it is enough."""

    from yt_dlp.utils import PagedList

    entries = info.get("entries")

    # a list read a page at a time by number is read only as far as it is
    # asked for, not from its start to its end
    if progress is None or entries is None or isinstance(entries, PagedList):
        return info

    def told():
        count = 0

        try:
            for entry in entries:
                count += 1
                progress("items", count)

                yield entry
        except ReadingEnough:
            return

    return {**info, "entries": told()}


def web_list_items(info: dict) -> tuple[ListItem, ...]:
    """The videos on a list as yt-dlp read it, those that cannot be played
    left out: private, deleted, or still to come."""

    # a channel's page lists its tabs, and its videos are the first of them
    info = _first_tab(info) or info

    entries = [entry for entry in info.get("entries") or () if entry]
    channel = _channel_of(info)

    items = []

    for entry in entries:
        if entry.get("_type") == "playlist" or _is_unplayable(entry):
            continue

        if channel is not None and not (entry.get("channel") or entry.get("uploader")):
            entry = {**entry, "channel": channel}

        url = entry.get("url") or entry.get("webpage_url")

        if not isinstance(url, str) or not is_url(url):
            continue

        items.append(
            ListItem(
                uri=url,
                title=entry.get("title") or None,
                duration_ms=duration_ms_of(entry),
                details=item_details(entry, is_exact=False),
            )
        )

    return tuple(items)


def _first_tab(info: dict) -> dict | None:
    """The first of the tabs a channel's page lists, each a list of its own;
    None for a list of videos.

    Tabs come read already, as a list: videos come as they are read, and
    are not looked at here, which would read them."""

    entries = info.get("entries")

    if not isinstance(entries, list):
        return None

    tabs = [entry for entry in entries if entry]

    if tabs and all(tab.get("_type") == "playlist" for tab in tabs):
        return tabs[0]

    return None


def _channel_of(info: dict) -> str | None:
    """The channel whose own list this is, its videos or another of its
    tabs: the videos on it do not say whose they are, as the videos on a
    playlist do. None for any other list."""

    channel_id = info.get("channel_id")

    if not channel_id or info.get("id") != channel_id:
        return None

    channel = info.get("channel") or info.get("uploader")

    return channel if isinstance(channel, str) and channel.strip() else None


def item_details(info: dict, is_exact: bool) -> ItemDetails | None:
    """What yt-dlp read of a video, of what the List window shows of it;
    None where it read none of it.

    is_exact says whether when it was put up is known to the second, as it
    is once the video itself is looked up, or only as near as a list page
    says it.
    """

    view_count = info.get("view_count")
    if not isinstance(view_count, int) or view_count < 0:
        view_count = None

    channel = info.get("channel") or info.get("uploader")
    if not isinstance(channel, str) or not channel.strip():
        channel = None

    published = _published_of(info)

    details = ItemDetails(
        channel=channel,
        view_count=view_count,
        published=published,
        is_published_exact=is_exact and published is not None,
        thumbnail=thumbnail_of(info),
    )

    return None if details == ItemDetails() else details


def thumbnail_of(info: dict) -> str | None:
    """A link to a video's picture, about as wide as it is shown."""

    video_id = info.get("id")
    is_youtube = "Youtube" in (info.get("ie_key"), info.get("extractor_key"))

    if is_youtube and isinstance(video_id, str) and video_id:
        return YOUTUBE_THUMBNAIL.format(ID=video_id)

    thumbnails = [
        thumbnail
        for thumbnail in info.get("thumbnails") or ()
        if isinstance(thumbnail, dict) and is_url(thumbnail.get("url") or "")
    ]

    wide_enough = [
        thumbnail
        for thumbnail in thumbnails
        if (thumbnail.get("width") or 0) >= THUMBNAIL_WIDTH
    ]

    if wide_enough:
        return min(wide_enough, key=lambda thumbnail: thumbnail["width"])["url"]

    # listed worst first
    if thumbnails:
        return thumbnails[-1]["url"]

    thumbnail = info.get("thumbnail")

    return thumbnail if isinstance(thumbnail, str) and is_url(thumbnail) else None


def _published_of(info: dict) -> int | None:
    for field in ("timestamp", "release_timestamp"):
        value = info.get(field)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)

    # a day, YYYYMMDD, where that is all there is
    upload_date = info.get("upload_date")

    if isinstance(upload_date, str) and len(upload_date) == 8:
        try:
            return calendar.timegm(time.strptime(upload_date, "%Y%m%d"))
        except ValueError:
            return None

    return None


def _is_unplayable(entry: dict) -> bool:
    return (
        entry.get("title") in _UNPLAYABLE_TITLES
        or entry.get("availability") in _UNPLAYABLE_AVAILABILITY
        or entry.get("live_status") in _UNPLAYABLE_LIVE_STATUS
    )


def _place_of(items, video_id: str | None) -> int:
    if video_id is None:
        return 0

    for index, item in enumerate(items):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(item.uri).query)

        if video_id in query.get("v", ()) or item.uri.rstrip("/").endswith(
            f"/{video_id}"
        ):
            return index

    return 0


def _name_of(url: str) -> str:
    parsed = urllib.parse.urlparse(url)

    return Path(parsed.path).name or parsed.netloc or url
