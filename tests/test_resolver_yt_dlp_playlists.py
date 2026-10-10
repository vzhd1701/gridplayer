"""Links to a list of videos, and videos opened from one."""

import contextlib

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.extractor.common import InfoExtractor

from gridplayer.utils.list_progress import ReadingStopped
from gridplayer.utils.url_resolve import resolver_yt_dlp
from gridplayer.utils.url_resolve.resolver_yt_dlp import (
    MAX_LIST_NESTING,
    YoutubeDLResolver,
    _video_of,
)
from gridplayer.utils.url_resolve.static import PlaylistURLError
from gridplayer.utils.url_resolve.url_resolve import _is_match_youtube

VIDEO = {"_type": "video", "id": "v1", "title": "one", "formats": [{"url": "x"}]}


class _FakeYDL:
    """Answers a look-up of a link on a list with the video it leads to."""

    def __init__(self, videos=None):
        self.videos = videos or {}
        self.looked_up = []

    def extract_info(self, url, download=False, ie_key=None):
        self.looked_up.append((url, ie_key))
        return self.videos[url]


def _flat_entry(url, ie_key="Youtube"):
    return {"_type": "url", "url": url, "ie_key": ie_key}


def _playlist(*entries, kind="playlist"):
    return {"_type": kind, "id": "PL", "title": "list", "entries": list(entries)}


class TestTheOneVideoAResultStandsFor:
    def test_a_video_is_itself(self):
        assert _video_of(_FakeYDL(), VIDEO) is VIDEO

    def test_a_result_that_says_nothing_of_its_kind_is_a_video(self):
        info = {"id": "v1", "formats": []}

        assert _video_of(_FakeYDL(), info) is info

    def test_a_list_of_one_link_is_the_video_it_leads_to(self):
        ydl = _FakeYDL({"https://site/v1": VIDEO})

        info = _video_of(ydl, _playlist(_flat_entry("https://site/v1")))

        assert info is VIDEO
        assert ydl.looked_up == [("https://site/v1", "Youtube")]

    def test_a_list_of_one_video_read_in_full_is_that_video(self):
        ydl = _FakeYDL()

        assert _video_of(ydl, _playlist(VIDEO)) is VIDEO
        assert ydl.looked_up == []

    def test_several_videos_shown_as_one_are_a_list_as_well(self):
        assert _video_of(_FakeYDL(), _playlist(VIDEO, kind="multi_video")) is VIDEO

    def test_entries_left_empty_by_the_site_are_not_counted(self):
        assert _video_of(_FakeYDL(), _playlist(None, VIDEO, {})) is VIDEO

    def test_a_list_of_several_is_no_one_video(self):
        with pytest.raises(PlaylistURLError):
            _video_of(_FakeYDL(), _playlist(VIDEO, dict(VIDEO, id="v2")))

    def test_an_empty_list_is_no_video_at_all(self):
        with pytest.raises(PlaylistURLError):
            _video_of(_FakeYDL(), _playlist())

    def test_a_list_with_no_entries_said_is_no_video_either(self):
        with pytest.raises(PlaylistURLError):
            _video_of(_FakeYDL(), {"_type": "playlist", "id": "PL"})

    def test_lists_of_one_inside_each_other_are_looked_into(self):
        nested = VIDEO
        for _ in range(MAX_LIST_NESTING):
            nested = _playlist(nested)

        assert _video_of(_FakeYDL(), nested) is VIDEO

    def test_but_not_for_ever(self):
        nested = VIDEO
        for _ in range(MAX_LIST_NESTING + 1):
            nested = _playlist(nested)

        with pytest.raises(PlaylistURLError):
            _video_of(_FakeYDL(), nested)


class TestWhatYtDlpIsAskedFor:
    @pytest.fixture
    def opened_with(self, mocker):
        params = {}

        class _FakeYoutubeDL:
            def __init__(self, opts):
                params.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False, ie_key=None):
                return dict(VIDEO)

        mocker.patch.object(resolver_yt_dlp, "YoutubeDL", _FakeYoutubeDL)
        mocker.patch.object(
            resolver_yt_dlp, "ytdl_cookies", return_value=contextlib.nullcontext({})
        )
        mocker.patch.object(resolver_yt_dlp, "ytdl_network_opts", return_value={})
        mocker.patch.object(resolver_yt_dlp, "ytdl_js_runtimes", return_value=None)

        return params

    def test_only_the_video_of_a_link_into_a_playlist(self, opened_with):
        assert YoutubeDLResolver(
            "https://www.youtube.com/watch?v=a&list=PL"
        )._video_info

        assert opened_with["noplaylist"] is True

    def test_a_list_only_for_what_is_on_it(self, opened_with):
        assert YoutubeDLResolver("https://www.youtube.com/playlist?list=PL")._video_info

        assert opened_with["extract_flat"] == "in_playlist"

    def test_a_list_of_several_is_reported_for_what_it_is(self, mocker, opened_with):
        mocker.patch.object(
            resolver_yt_dlp.YoutubeDL,
            "extract_info",
            return_value=_playlist(VIDEO, dict(VIDEO, id="v2")),
        )

        resolver = YoutubeDLResolver("https://www.youtube.com/playlist?list=PL")

        with pytest.raises(PlaylistURLError):
            _ = resolver._video_info


class TestYouTubeLinksGoStraightToYtDlp:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=qIP9kb_RPd4",
            # issue #130: opened from a playlist, the link carries it along
            "https://www.youtube.com/watch?v=qIP9kb_RPd4&list=PL-rKCNLqzCwuMOiq4gIShHodFOGYgAixQ&index=1&pp=iAQB",
            "https://youtu.be/qIP9kb_RPd4?list=PL-rKCNLqzCwuMOiq4gIShHodFOGYgAixQ",
            "https://www.youtube.com/playlist?list=PL-rKCNLqzCwuMOiq4gIShHodFOGYgAixQ",
            "https://www.youtube.com/@NASA",
            "https://www.youtube.com/@NASA/videos",
        ],
    )
    def test_videos_playlists_and_channels(self, url):
        assert _is_match_youtube(url)

    def test_another_site_is_left_to_the_resolver_order(self):
        assert not _is_match_youtube("https://vimeo.com/76979871")


class _ListIE(InfoExtractor):
    """A site whose lists are read a video at a time: list.test/N is a list
    of N videos."""

    _VALID_URL = r"https?://list\.test/(?P<id>\d+)"

    def _real_extract(self, url):
        count = int(self._match_id(url))

        def entries():
            for n in range(count):
                yield self.url_result(
                    f"https://video.test/{n}", _VideoIE, str(n), f"Video {n}"
                )

        return self.playlist_result(entries(), "list", "A list")


class _VideoIE(InfoExtractor):
    _VALID_URL = r"https?://video\.test/(?P<id>\d+)"

    def _real_extract(self, url):
        video_id = self._match_id(url)

        return {
            "id": video_id,
            "title": f"Video {video_id}",
            "formats": [{"url": f"https://video.test/{video_id}.mp4", "ext": "mp4"}],
        }


def _test_sites(params, **kwargs):
    ydl = YoutubeDL({**params, "quiet": True}, auto_init=False)
    ydl.add_info_extractor(_ListIE())
    ydl.add_info_extractor(_VideoIE())
    return ydl


class TestHowFarALinkFoundToBeAListIsRead:
    @pytest.fixture(autouse=True)
    def test_sites(self, mocker):
        mocker.patch.object(resolver_yt_dlp, "YoutubeDL", _test_sites)
        mocker.patch.object(
            resolver_yt_dlp, "ytdl_cookies", return_value=contextlib.nullcontext({})
        )
        mocker.patch.object(resolver_yt_dlp, "ytdl_network_opts", return_value={})
        mocker.patch.object(resolver_yt_dlp, "ytdl_js_runtimes", return_value={})

    def _read(self, url, progress):
        with pytest.raises(PlaylistURLError) as raised:
            _ = YoutubeDLResolver(url, progress=progress)._video_info

        return raised.value.info

    def test_told_each_video_as_it_is_read(self):
        told = []

        self._read("https://list.test/3", lambda *said: told.append(said))

        assert told == [("items", 1), ("items", 2), ("items", 3)]

    def test_all_of_it_read_as_ever(self):
        info = self._read("https://list.test/3", lambda *said: None)

        assert [entry["url"] for entry in info["entries"]] == [
            f"https://video.test/{n}" for n in range(3)
        ]

    def test_no_more_than_a_list_read_before_it_is_put_in_a_cell(self, mocker):
        mocker.patch.object(resolver_yt_dlp, "MAX_WEB_LIST_ITEMS", 2)

        info = self._read("https://list.test/5", lambda *said: None)

        assert len(info["entries"]) == 2

    def test_nothing_told_of_a_video(self):
        told = []

        resolver = YoutubeDLResolver(
            "https://video.test/7", progress=lambda *said: told.append(said)
        )

        assert resolver._video_info["title"] == "Video 7"
        assert told == []

    def test_a_list_of_one_still_its_video(self):
        resolver = YoutubeDLResolver("https://list.test/1", progress=lambda *said: None)

        assert resolver._video_info["title"] == "Video 0"

    def test_stopped_part_way(self):
        read = []

        def progress(what, count):
            read.append(count)
            if count == 2:
                raise ReadingStopped

        with pytest.raises(ReadingStopped):
            _ = YoutubeDLResolver("https://list.test/50", progress=progress)._video_info

        assert read == [1, 2]
