"""What is known of the files and links put on a list by hand, looked up:
a file's length, and a video's title, length, channel, views, when it was
put up and its picture, from the site it is on.

All of it is slow -- a site answers in a second or two a video, and asked
too often, stops answering -- so it is looked up off the interface thread;
see player/managers/list_info.py for how.

A YouTube video is looked up twice. YouTube makes a list of up to 50
videos named in a link, read the way a playlist is, all at once: their
titles, lengths, channels and pictures in a few seconds. Views and when
each was put up are not on such a list, and need each video looked up on
its own, which is what YouTube turns away first.
"""

import logging
import threading
import time
import urllib.parse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path

from gridplayer.models.media_list import ItemDetails, ListItem
from gridplayer.utils.list_errors import is_site_refusal, site_name
from gridplayer.utils.web_lists import (
    LINK_RESULT_TYPES,
    LIST_RESULT_TYPES,
    YOUTUBE_HOSTS,
    duration_ms_of,
    item_details,
    read_web_list,
    ytdl,
)

_log = logging.getLogger(__name__)

# how many YouTube videos the list YouTube makes of them takes at most
YOUTUBE_LIST_MAX = 50
YOUTUBE_LIST_URL = "https://www.youtube.com/watch_videos?video_ids={IDS}"

# how long a file is looked at for its length at most, in ms
FILE_PARSE_TIMEOUT_MS = 5000

# the ends of a link's path that are a stream or a file, never a page of a
# site: a channel list's links
_STREAM_ENDS = (
    ".m3u8",
    ".m3u",
    ".mpd",
    ".ts",
    ".mp4",
    ".mkv",
    ".webm",
    ".flv",
    ".avi",
    ".mov",
    ".mp3",
    ".aac",
    ".m4a",
    ".ogg",
)

_YOUTUBE_ID_LENGTH = 11
_YOUTUBE_ID_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)

# whether yt-dlp knows the site of a host, by host: a channel list's links
# are all on a few hosts, which are looked at once each
_site_hosts: dict[str, bool] = {}
_site_hosts_lock = threading.Lock()


@dataclass(frozen=True)
class Found:
    """What was learned of an item; None for what was not."""

    title: str | None = None
    duration_ms: int | None = None
    details: ItemDetails | None = None


class NotFound(Exception):
    """Nothing to be had of it: gone, private, or no video at all."""


class Refused(Exception):
    """The site turned it away for now, having been asked too often."""

    def __init__(self, site: str):
        super().__init__(site)
        self.site = site


@dataclass(frozen=True)
class Planned:
    """What of the items is looked up, and how."""

    files: tuple[ListItem, ...] = ()
    youtube: tuple[ListItem, ...] = ()
    links: tuple[ListItem, ...] = ()

    @property
    def count(self) -> int:
        return len(self.files) + len(self.youtube) + len(self.links)


def plan(items, is_missing_only: bool, is_site_link=None) -> Planned:
    """The items that can be looked up: files, and links to a video on a
    site yt-dlp knows; those with nothing known of them yet alone, where
    is_missing_only says so."""

    is_site_link = is_site_link or is_site_video_link

    files, youtube, links = [], [], []

    for item in items:
        if is_missing_only and not needs_info(item):
            continue

        if isinstance(item.uri, Path):
            files.append(item)
        elif youtube_id(item.uri) is not None:
            youtube.append(item)
        elif is_site_link(item.uri):
            links.append(item)

    return Planned(files=tuple(files), youtube=tuple(youtube), links=tuple(links))


def needs_info(item: ListItem) -> bool:
    """Whether nothing has been learned of an item yet: a file's length, or
    what a site says of a video."""

    if isinstance(item.uri, Path):
        return item.duration_ms is None

    return item.details is None


def may_be_looked_up(item: ListItem) -> bool:
    """Whether an item is a file or a link, to offer looking it up: which
    links are to a site's video is told once it is."""

    return isinstance(item.uri, Path) or item.uri.startswith(("http://", "https://"))


def youtube_id(url) -> str | None:
    """The video a YouTube link is to, None for any other link."""

    if not isinstance(url, str):
        return None

    parts = urllib.parse.urlsplit(url)

    if parts.netloc.lower() not in YOUTUBE_HOSTS:
        return None

    path = parts.path

    if parts.netloc.lower() == "youtu.be":
        video_id = path.strip("/").split("/")[0]
    elif path == "/watch":
        video_id = (urllib.parse.parse_qs(parts.query).get("v") or [""])[0]
    elif path.startswith(("/shorts/", "/live/", "/embed/", "/v/")):
        video_id = path.split("/")[2]
    else:
        return None

    if len(video_id) != _YOUTUBE_ID_LENGTH or not set(video_id) <= _YOUTUBE_ID_CHARS:
        return None

    return video_id


def is_site_video_link(url: str) -> bool:
    """Whether a link is to a page of a site yt-dlp knows, rather than to a
    stream or a file: told by its host, once for each host."""

    parts = urllib.parse.urlsplit(url)
    host = parts.netloc.lower()

    if parts.scheme not in {"http", "https"} or not host:
        return False

    if parts.path.lower().endswith(_STREAM_ENDS):
        return False

    with _site_hosts_lock:
        known = _site_hosts.get(host)

    if known is None:
        known = _has_extractor(url)

        with _site_hosts_lock:
            _site_hosts[host] = known

    return known


def _has_extractor(url: str) -> bool:
    from yt_dlp.extractor import gen_extractor_classes

    from gridplayer.utils.percent_re import untangle_percent_re

    # yt-dlp patches urllib3 as it is imported; see utils/percent_re.py
    untangle_percent_re()

    return any(
        extractor.suitable(url)
        for extractor in gen_extractor_classes()
        if extractor.ie_key() != "Generic"
    )


def look_up_youtube(ids: list[str]) -> dict[str, Found]:
    """What the list YouTube makes of the videos says of each, by its id:
    its title, length, channel and picture. The ones not on it, gone or
    private, are left out."""

    if not ids:
        return {}

    url = YOUTUBE_LIST_URL.format(IDS=",".join(ids[:YOUTUBE_LIST_MAX]))

    try:
        read = read_web_list(url)
    except Exception as e:
        if is_site_refusal(str(e)):
            raise Refused("YouTube") from e

        _log.debug(f"YouTube list of {len(ids)} videos not read: {e}")
        return {}

    found = {}

    for item in getattr(read, "items", ()):
        video_id = youtube_id(item.uri)

        if video_id is not None:
            found[video_id] = Found(
                title=item.title, duration_ms=item.duration_ms, details=item.details
            )

    return found


def look_up_link(url: str) -> Found:
    """What a site says of a video, the video looked up on its own: when it
    was put up to the second, and its views as they are now."""

    # as a video is looked up to be played, though nothing of it is: YouTube
    # without its player's script says a video is unavailable, or that the
    # page needs to be reloaded
    opts = {"noplaylist": True, "extract_flat": "in_playlist"}

    try:
        with ytdl(_log, opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)

            # a link that leads on to the video's own
            if info.get("_type") in LINK_RESULT_TYPES:
                info = ydl.extract_info(
                    info["url"],
                    download=False,
                    process=False,
                    ie_key=info.get("ie_key"),
                )
    except Exception as e:
        if is_site_refusal(str(e)):
            host = urllib.parse.urlsplit(url).netloc.lower()
            raise Refused(site_name(host)) from e

        raise NotFound(str(e)) from e

    if info.get("_type") in LIST_RESULT_TYPES:
        raise NotFound("a list, not a video")

    title = info.get("title")

    return Found(
        title=title if isinstance(title, str) and title.strip() else None,
        duration_ms=duration_ms_of(info),
        details=item_details(info, is_exact=True),
    )


class FileLengths:
    """How long files are, as VLC reads them: in a process of its own, for
    a file VLC chokes on to take that down rather than the player. Started
    when first asked, and let go of once there is nothing more to ask."""

    def __init__(self):
        self._pool: ProcessPoolExecutor | None = None
        self._lock = threading.Lock()

    def lengths(self, paths: list[Path]) -> list[int | None]:
        """Each file's length in ms, None for one that could not be read."""

        with self._lock:
            if self._pool is None:
                self._pool = ProcessPoolExecutor(
                    max_workers=1, mp_context=get_context("spawn")
                )
            pool = self._pool

        try:
            return pool.submit(lengths_in_process, [str(p) for p in paths]).result()
        except Exception as e:
            # the process gone: these not read, and a new one next time
            _log.warning(f"File lengths not read: {e}")
            self.release()
            return [None] * len(paths)

    def release(self):
        with self._lock:
            pool, self._pool = self._pool, None

        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)


_vlc_instance = None


def lengths_in_process(paths: list[str]) -> list[int | None]:
    """Run in the process FileLengths keeps: each file read by VLC, as far
    as to tell how long it is, nothing of it played."""

    global _vlc_instance

    from gridplayer.vlc_player.libvlc import vlc

    if _vlc_instance is None:
        _vlc_instance = vlc.Instance(
            [
                "--intf=dummy",
                "--quiet",
                "--no-video",
                "--no-audio",
                "--no-lua",
                "--no-interact",
                "--no-sub-autodetect-file",
            ]
        )

    return [_length_of(vlc, _vlc_instance, path) for path in paths]


def _length_of(vlc, instance, path: str) -> int | None:
    media = instance.media_new_path(path)

    try:
        media.parse_with_options(vlc.MediaParseFlag.local, FILE_PARSE_TIMEOUT_MS)

        deadline = time.monotonic() + FILE_PARSE_TIMEOUT_MS / 1000 + 1

        while _parse_status(media) not in _PARSE_ENDED and time.monotonic() < deadline:
            time.sleep(0.005)

        if _parse_status(media) != _PARSE_DONE:
            return None

        length = media.get_duration()

        return length if length and length > 0 else None
    finally:
        media.release()


def _parse_status(media) -> int:
    status = media.get_parsed_status()

    return getattr(status, "value", status)


# VLC's MediaParsedStatus: skipped, failed, timeout, done; 0 while parsing
_PARSE_DONE = 4
_PARSE_ENDED = frozenset((1, 2, 3, _PARSE_DONE))
