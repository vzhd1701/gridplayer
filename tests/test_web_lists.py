"""Lists a site keeps behind a link, read for what is on them."""

import contextlib
import itertools
import subprocess
import sys

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.media_list import ListItem
from gridplayer.params.static import ListSourceKind
from gridplayer.utils.list_progress import ReadingEnough
from gridplayer.utils.url_resolve.static import PlaylistURLError, ResolvedList
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolverWorker
from gridplayer.utils.web_lists import (
    is_web_list_url,
    item_details,
    read_web_list,
    thumbnail_of,
    video_in_list,
    web_list_items,
    without_list,
)

RESOLVE_URL = "gridplayer.utils.url_resolve.url_resolve.resolve_url"


def _entry(video_id, **fields):
    return {
        "_type": "url",
        "ie_key": "Youtube",
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": f"Video {video_id}",
        "duration": 61,
        **fields,
    }


def _playlist(*entries, title="List"):
    return {"_type": "playlist", "id": "PL", "title": title, "entries": list(entries)}


CHANNEL_ID = "UCLA_DiR1FfKNvjuUpBHmylQ"


def _channel_tab(*entries, title="NASA - Videos"):
    """A tab of a channel's page, as yt-dlp reads it: the list is the
    channel's own, and its videos do not say whose they are."""

    return {
        **_playlist(*entries, title=title),
        "id": CHANNEL_ID,
        "channel_id": CHANNEL_ID,
        "channel": "NASA",
        "uploader": "NASA",
    }


def _channel_page(*tabs):
    """A link to a channel's page: its tabs, each a list of its own."""

    return {
        **_playlist(*tabs, title="NASA"),
        "id": "@NASA",
        "channel_id": CHANNEL_ID,
        "channel": "NASA",
    }


class TestLinksThatLookLikeLists:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/playlist?list=PL123",
            "https://www.youtube.com/watch?v=abc&list=PL123&index=2",
            "https://youtu.be/abc?list=PL123",
            "https://m.youtube.com/watch?v=abc&list=PL123",
            "https://music.youtube.com/playlist?list=OLAK5",
            "https://www.youtube.com/@NASA",
            "https://www.youtube.com/@NASA/videos",
            "https://www.youtube.com/channel/UCLA_DiR1FfKNvjuUpBHmylQ",
            "https://www.youtube.com/c/Something",
            "https://www.youtube.com/user/Someone",
        ],
    )
    def test_youtube_playlists_and_channels(self, url):
        assert is_web_list_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=abc",
            "https://youtu.be/abc",
            "https://www.youtube.com/shorts/abc",
            "https://vimeo.com/showcase/1",
            "https://notyoutube.com/playlist?list=1",
            "/local/file.mp4",
        ],
    )
    def test_not_others(self, url):
        assert not is_web_list_url(url)


class TestAVideoOpenedFromAPlaylist:
    @pytest.mark.parametrize(
        ("url", "video_id"),
        [
            ("https://www.youtube.com/watch?v=abc&list=PL1", "abc"),
            ("https://youtu.be/abc?list=PL1", "abc"),
            ("https://www.youtube.com/watch?v=abc", None),
            ("https://www.youtube.com/playlist?list=PL1", None),
        ],
    )
    def test_is_told_by_its_link(self, url, video_id):
        assert video_in_list(url) == video_id

    def test_alone_keeps_where_it_starts(self):
        url = "https://www.youtube.com/watch?v=abc&list=PL1&index=3&t=42&pp=x"

        assert without_list(url) == "https://www.youtube.com/watch?v=abc&t=42"

    def test_a_short_link_alone(self):
        assert without_list("https://youtu.be/abc?list=PL1") == (
            "https://www.youtube.com/watch?v=abc"
        )


class TestWhatIsOnAList:
    def test_each_video_with_its_name_and_length(self):
        (item,) = web_list_items(_playlist(_entry("a")))

        assert item.uri == "https://www.youtube.com/watch?v=a"
        assert item.title == "Video a"
        assert item.duration_ms == 61000

    @pytest.mark.parametrize(
        "fields",
        [
            {"title": "[Private video]"},
            {"title": "[Deleted video]"},
            {"availability": "private"},
            {"live_status": "is_upcoming"},
        ],
    )
    def test_not_one_that_cannot_be_played(self, fields):
        items = web_list_items(_playlist(_entry("a", **fields), _entry("b")))

        assert [item.title for item in items] == ["Video b"]

    def test_a_live_one_has_no_length(self):
        (item,) = web_list_items(_playlist(_entry("a", duration=None)))

        assert item.duration_ms is None

    def test_a_channels_videos_are_its_first_tab(self):
        channel = _playlist(
            _playlist(_entry("v1"), _entry("v2"), title="Videos"),
            _playlist(_entry("s1"), title="Shorts"),
        )

        assert [item.title for item in web_list_items(channel)] == [
            "Video v1",
            "Video v2",
        ]

    def test_a_channels_videos_are_its_own(self):
        items = web_list_items(_channel_tab(_entry("a"), _entry("b")))

        assert [item.details.channel for item in items] == ["NASA", "NASA"]

    def test_a_channels_first_tab_its_own_too(self):
        page = _channel_page(_channel_tab(_entry("a")), _channel_tab(_entry("s")))

        (item,) = web_list_items(page)

        assert item.details.channel == "NASA"

    def test_a_video_saying_whose_it_is_left_so(self):
        (item,) = web_list_items(_channel_tab(_entry("a", channel="NASA Johnson")))

        assert item.details.channel == "NASA Johnson"

    def test_a_playlists_videos_not_taken_for_its_owners(self):
        playlist = {
            **_playlist(_entry("a")),
            "channel_id": CHANNEL_ID,
            "channel": "NASA",
        }

        (item,) = web_list_items(playlist)

        assert item.details is None or item.details.channel is None

    def test_an_entry_with_no_link_is_left_out(self):
        items = web_list_items(_playlist(_entry("a", url=None), None, _entry("b")))

        assert [item.title for item in items] == ["Video b"]


class TestWhatTheListSaysOfEachVideo:
    def test_its_channel_views_date_and_picture(self):
        (item,) = web_list_items(
            _playlist(
                _entry("a", channel="Workshop", view_count=19000, timestamp=1286582400)
            )
        )

        assert item.details.channel == "Workshop"
        assert item.details.view_count == 19000
        assert item.details.published == 1286582400
        assert item.details.thumbnail == "https://i.ytimg.com/vi/a/mqdefault.jpg"

    def test_the_date_only_as_near_as_the_page_says_it(self):
        (item,) = web_list_items(_playlist(_entry("a", timestamp=1286582400)))

        assert not item.details.is_published_exact

    def test_the_uploader_where_no_channel_is_named(self):
        (item,) = web_list_items(_playlist(_entry("a", uploader="Someone")))

        assert item.details.channel == "Someone"

    def test_none_said_is_none(self):
        info = {"url": "https://example.com/v/1", "title": "One", "duration": 5}

        assert item_details(info, is_exact=False) is None

    def test_a_day_where_that_is_all_there_is(self):
        details = item_details({"upload_date": "20100508"}, is_exact=True)

        assert details.published == 1273276800
        assert details.is_published_exact

    def test_no_date_is_not_an_exact_one(self):
        details = item_details({"view_count": 5}, is_exact=True)

        assert details.published is None
        assert not details.is_published_exact

    def test_no_views_is_not_a_count(self):
        assert (
            item_details({"view_count": None, "channel": "C"}, False).view_count is None
        )
        assert item_details({"view_count": 0, "channel": "C"}, False).view_count == 0


class TestAVideosPicture:
    def test_youtubes_16_9_one_by_its_id(self):
        info = {
            "ie_key": "Youtube",
            "id": "abc",
            "thumbnails": [{"url": "https://i.ytimg.com/vi/abc/hqdefault.jpg?sqp=x"}],
        }

        assert thumbnail_of(info) == "https://i.ytimg.com/vi/abc/mqdefault.jpg"

    def test_elsewhere_the_narrowest_one_wide_enough(self):
        info = {
            "ie_key": "Vimeo",
            "thumbnails": [
                {"url": "https://cdn/100.jpg", "width": 100},
                {"url": "https://cdn/640.jpg", "width": 640},
                {"url": "https://cdn/200.jpg", "width": 200},
            ],
        }

        assert thumbnail_of(info) == "https://cdn/200.jpg"

    def test_or_the_best_one_where_none_says_how_wide(self):
        info = {
            "thumbnails": [
                {"url": "https://cdn/worse.jpg"},
                {"url": "https://cdn/best.jpg"},
            ]
        }

        assert thumbnail_of(info) == "https://cdn/best.jpg"

    def test_or_the_one_there_is(self):
        assert (
            thumbnail_of({"thumbnail": "https://cdn/one.jpg"}) == "https://cdn/one.jpg"
        )

    def test_none_that_is_not_a_link(self):
        assert thumbnail_of({"thumbnails": [{"url": "nothing"}]}) is None


class _FakeYDL:
    """yt-dlp answering with what a test says: the list, or by link where
    one leads on to another; a list's videos read as yt-dlp reads them, one
    after another as far as it is set to."""

    def __init__(self, info):
        self.info = info
        self.answers = {}
        self.asked = []
        self.opts = None

    def __call__(self, opts):
        self.opts = opts
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False, process=True, ie_key=None):
        assert not download
        assert not process

        self.asked.append(url)

        return self.answers.get(url, self.info)

    def process_ie_result(self, info, download=False):
        assert not download

        entries = itertools.islice(info["entries"], self.opts.get("playlistend"))

        # a list on the list read too, as yt-dlp reads each tab of a page
        return {
            **info,
            "entries": [
                self.process_ie_result(entry)
                if isinstance(entry, dict) and entry.get("_type") == "playlist"
                else entry
                for entry in entries
            ],
        }


class TestReadingAList:
    @pytest.fixture
    def ydl(self, mocker):
        fake = _FakeYDL(_playlist(_entry("a"), _entry("b"), _entry("c")))

        import yt_dlp

        mocker.patch.object(yt_dlp, "YoutubeDL", fake)
        mocker.patch(
            "gridplayer.utils.cookies.ytdl_cookies",
            return_value=contextlib.nullcontext({}),
        )
        mocker.patch("gridplayer.utils.network.ytdl_network_opts", return_value={})
        mocker.patch("gridplayer.utils.js_runtime.ytdl_js_runtimes", return_value=None)

        return fake

    def test_for_what_is_on_it_and_no_more(self, ydl):
        read = read_web_list("https://www.youtube.com/playlist?list=PL", max_items=7)

        assert ydl.opts["extract_flat"] == "in_playlist"
        assert ydl.opts["playlistend"] == 7
        # when each was put up, as near as the list page says it
        assert ydl.opts["extractor_args"] == {"youtubetab": {"approximate_date": [""]}}
        assert read.name == "List"
        assert len(read.items) == 3
        assert read.source.kind is ListSourceKind.URL
        assert read.start == 0

    def test_from_the_video_it_was_opened_from(self, ydl):
        read = read_web_list("https://www.youtube.com/watch?v=b&list=PL")

        assert read.start == 1

    def test_one_video_after_all(self, ydl):
        ydl.info = {"_type": "video", "id": "a", "title": "Just one"}

        read = read_web_list("https://www.youtube.com/@one")

        assert isinstance(read, ListItem)
        assert read.title == "Just one"

    def test_one_with_nothing_to_play_could_not_be_read(self, ydl):
        ydl.info = _playlist(_entry("a", title="[Private video]"))

        with pytest.raises(ValueError, match="nothing"):
            read_web_list("https://www.youtube.com/playlist?list=PL")

    def test_found_where_a_link_leads_on_to_it(self, ydl):
        playlist = "https://www.youtube.com/playlist?list=PL"
        ydl.answers["https://youtu.be/b?list=PL"] = {
            "_type": "url",
            "url": playlist,
            "ie_key": "YoutubeTab",
        }

        read = read_web_list("https://youtu.be/b?list=PL")

        assert ydl.asked == ["https://youtu.be/b?list=PL", playlist]
        assert len(read.items) == 3


class TestReadingAChannelsPage:
    @pytest.fixture
    def ydl(self, mocker):
        shorts_read = []

        def shorts():
            shorts_read.append(True)
            yield _entry("s")

        fake = _FakeYDL(
            _channel_page(
                _channel_tab(_entry("a"), _entry("b"), _entry("c")),
                _channel_tab(title="NASA - Shorts") | {"entries": shorts()},
            )
        )
        fake.shorts_read = shorts_read

        import yt_dlp

        mocker.patch.object(yt_dlp, "YoutubeDL", fake)
        mocker.patch(
            "gridplayer.utils.cookies.ytdl_cookies",
            return_value=contextlib.nullcontext({}),
        )
        mocker.patch("gridplayer.utils.network.ytdl_network_opts", return_value={})
        mocker.patch("gridplayer.utils.js_runtime.ytdl_js_runtimes", return_value=None)

        return fake

    def test_its_videos_by_the_channels_name(self, ydl):
        read = read_web_list("https://www.youtube.com/@NASA")

        assert read.name == "NASA"
        assert [item.title for item in read.items] == ["Video a", "Video b", "Video c"]
        assert {item.details.channel for item in read.items} == {"NASA"}

    def test_its_other_tabs_not_read(self, ydl):
        read_web_list("https://www.youtube.com/@NASA")

        assert ydl.shorts_read == []

    def test_its_videos_counted_as_they_come(self, ydl):
        told = []

        read_web_list(
            "https://www.youtube.com/@NASA",
            progress=lambda what, count, of=None: told.append(count),
        )

        assert told == [1, 2, 3]


class TestHowFarReadingAListHasGot:
    @pytest.fixture
    def ydl(self, mocker):
        fake = _FakeYDL(_playlist(_entry("a"), _entry("b"), _entry("c")))

        import yt_dlp

        mocker.patch.object(yt_dlp, "YoutubeDL", fake)
        mocker.patch(
            "gridplayer.utils.cookies.ytdl_cookies",
            return_value=contextlib.nullcontext({}),
        )
        mocker.patch("gridplayer.utils.network.ytdl_network_opts", return_value={})
        mocker.patch("gridplayer.utils.js_runtime.ytdl_js_runtimes", return_value=None)

        return fake

    def test_told_as_each_video_comes(self, ydl):
        told = []

        read_web_list(
            "https://www.youtube.com/playlist?list=PL",
            progress=lambda what, count, of=None: told.append((what, count)),
        )

        assert told == [("items", 1), ("items", 2), ("items", 3)]

    def test_told_no_further_than_it_is_read(self, ydl):
        told = []

        read_web_list(
            "https://www.youtube.com/playlist?list=PL",
            max_items=2,
            progress=lambda what, count, of=None: told.append(count),
        )

        assert told == [1, 2]

    def test_ended_with_the_videos_read_by_then(self, ydl):
        def progress(what, count, of=None):
            if count == 3:
                raise ReadingEnough

        read = read_web_list(
            "https://www.youtube.com/playlist?list=PL", progress=progress
        )

        assert [item.title for item in read.items] == ["Video a", "Video b"]


@pytest.fixture(scope="module")
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.usefixtures("_qapp")
class TestALinkThatTurnsOutToBeAList:
    def _worker(self):
        worker = VideoURLResolverWorker()
        worker.lists = []
        worker.errors = []
        worker.list_resolved.connect(worker.lists.append)
        worker.error.connect(lambda: worker.errors.append(True))
        return worker

    def test_is_handed_over_as_the_list(self, mocker):
        mocker.patch(
            RESOLVE_URL,
            side_effect=PlaylistURLError(
                _playlist(_entry("a"), _entry("b"), title="T")
            ),
        )
        worker = self._worker()

        worker.resolve("https://site/list")

        (resolved,) = worker.lists
        assert isinstance(resolved, ResolvedList)
        assert resolved.title == "T"
        assert [item.title for item in resolved.items] == ["Video a", "Video b"]
        assert worker.errors == []

    def test_with_nothing_on_it_is_an_error(self, mocker):
        mocker.patch(RESOLVE_URL, side_effect=PlaylistURLError(_playlist()))
        worker = self._worker()

        worker.resolve("https://site/list")

        assert worker.lists == []
        assert worker.errors == [True]


def test_telling_a_list_link_does_not_load_yt_dlp():
    """Asked on the interface thread for every link added, where loading
    yt-dlp would hold it up for a good third of a second."""

    code = """
import sys
from gridplayer.utils.web_lists import is_web_list_url
is_web_list_url("https://www.youtube.com/playlist?list=PL")
print("yt_dlp" in sys.modules)
"""

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "False"
