"""What is known of the files and links put on a list by hand, looked up: which
of them can be, and what each lookup makes of what it is told."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from gridplayer.models.media_list import ItemDetails, ListItem
from gridplayer.utils import item_info
from gridplayer.utils.item_info import (
    Found,
    NotFound,
    Refused,
    look_up_link,
    look_up_youtube,
    may_be_looked_up,
    needs_info,
    plan,
    youtube_id,
)
from gridplayer.utils.media_import import ListInput

VIDEO = "dQw4w9WgXcQ"
WATCH = f"https://www.youtube.com/watch?v={VIDEO}"
SITE = "https://vimeo.com/76979871"
STREAM = "http://iptv.example:8080/live/user/pass/1234.ts"


class TestYouTubeIds:
    @pytest.mark.parametrize(
        "url",
        [
            WATCH,
            f"https://youtube.com/watch?v={VIDEO}&list=PL123&index=3",
            f"https://m.youtube.com/watch?v={VIDEO}",
            f"https://music.youtube.com/watch?v={VIDEO}",
            f"https://youtu.be/{VIDEO}?t=42",
            f"https://www.youtube.com/shorts/{VIDEO}",
            f"https://www.youtube.com/live/{VIDEO}",
            f"https://www.youtube.com/embed/{VIDEO}",
        ],
    )
    def test_the_video_a_link_is_to(self, url):
        assert youtube_id(url) == VIDEO

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/playlist?list=PL123",
            "https://www.youtube.com/@channel",
            "https://www.youtube.com/watch?v=short",
            "https://www.youtube.com/watch",
            SITE,
            STREAM,
        ],
    )
    def test_none_for_any_other(self, url):
        assert youtube_id(url) is None

    def test_none_for_a_file(self):
        assert youtube_id(Path("D:/a.mp4")) is None


class TestWhatNeedsLookingUp:
    def test_a_file_with_no_length(self):
        assert needs_info(ListItem(uri=Path("D:/a.mp4")))
        assert not needs_info(ListItem(uri=Path("D:/a.mp4"), duration_ms=1000))

    def test_a_link_with_nothing_said_of_it(self):
        assert needs_info(ListItem(uri=WATCH))
        assert needs_info(ListItem(uri=WATCH, title="Named", duration_ms=1000))
        assert not needs_info(ListItem(uri=WATCH, details=ItemDetails(channel="A")))

    def test_files_and_links_may_be_looked_up(self):
        assert may_be_looked_up(ListItem(uri=Path("D:/a.mp4")))
        assert may_be_looked_up(ListItem(uri=WATCH))
        assert not may_be_looked_up(ListItem(uri="rtsp://camera/stream"))


class TestPlanned:
    def items(self):
        return [
            ListItem(uri=Path("D:/a.mp4")),
            ListItem(uri=Path("D:/b.mp4"), duration_ms=1000),
            ListItem(uri=WATCH),
            ListItem(uri=WATCH, details=ItemDetails(channel="A")),
            ListItem(uri=SITE),
            ListItem(uri=STREAM),
        ]

    def test_files_youtube_and_sites_apart(self):
        items = self.items()

        planned = plan(items, False, is_site_link=lambda url: url == SITE)

        assert planned.files == (items[0], items[1])
        assert planned.youtube == (items[2], items[3])
        assert planned.links == (items[4],)
        assert planned.count == 5

    def test_the_missing_alone(self):
        items = self.items()

        planned = plan(items, True, is_site_link=lambda url: url == SITE)

        assert planned.files == (items[0],)
        assert planned.youtube == (items[2],)
        assert planned.links == (items[4],)


class TestSiteLinks:
    @pytest.fixture(autouse=True)
    def no_hosts_known(self, mocker):
        mocker.patch.object(item_info, "_site_hosts", {})

    def test_a_site_yt_dlp_knows(self):
        assert item_info.is_site_video_link(SITE)

    def test_a_host_it_does_not(self):
        assert not item_info.is_site_video_link("http://iptv.example:8080/1234")

    def test_a_stream_never_looked_at(self, mocker):
        asked = mocker.patch.object(item_info, "_has_extractor", return_value=True)

        assert not item_info.is_site_video_link(STREAM)
        assert not item_info.is_site_video_link("https://cdn.example/a/index.m3u8")

        asked.assert_not_called()

    def test_each_host_looked_at_once(self, mocker):
        asked = mocker.patch.object(item_info, "_has_extractor", return_value=False)

        for n in range(100):
            item_info.is_site_video_link(f"http://iptv.example:8080/user/pass/{n}")

        asked.assert_called_once()


def _video_list(*items):
    return ListInput(name="List", items=tuple(items))


class TestYouTubesListOfThem:
    def test_each_found_by_its_id(self, mocker):
        details = ItemDetails(channel="Rick Astley", thumbnail="pic")
        read = mocker.patch.object(
            item_info,
            "read_web_list",
            return_value=_video_list(
                ListItem(uri=WATCH, title="Never", duration_ms=213_000, details=details)
            ),
        )

        found = look_up_youtube([VIDEO, "AAAAAAAAAAA"])

        assert found == {
            VIDEO: Found(title="Never", duration_ms=213_000, details=details)
        }
        assert read.call_args.args[0] == (
            "https://www.youtube.com/watch_videos?video_ids=dQw4w9WgXcQ,AAAAAAAAAAA"
        )

    def test_turned_away(self, mocker):
        mocker.patch.object(
            item_info,
            "read_web_list",
            side_effect=Exception("HTTP Error 429: Too Many Requests"),
        )

        with pytest.raises(Refused) as refused:
            look_up_youtube([VIDEO])

        assert refused.value.site == "YouTube"

    def test_not_read_is_nothing_found(self, mocker):
        mocker.patch.object(
            item_info, "read_web_list", side_effect=ValueError("nothing on the list")
        )

        assert look_up_youtube([VIDEO]) == {}


class _FakeYoutubeDL:
    """yt-dlp answering with what a test says, by link."""

    answers: dict = {}
    opts: list = []

    def __init__(self, opts):
        _FakeYoutubeDL.opts.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True, process=True, ie_key=None):
        assert not download
        assert not process

        answer = self.answers[url]

        if isinstance(answer, Exception):
            raise answer

        return answer


@pytest.fixture
def ytdl(mocker):
    import yt_dlp

    _FakeYoutubeDL.answers = {}
    _FakeYoutubeDL.opts = []
    mocker.patch.object(yt_dlp, "YoutubeDL", _FakeYoutubeDL)

    return _FakeYoutubeDL


class TestAVideoOnItsOwn:
    def test_all_said_of_it(self, ytdl):
        ytdl.answers[WATCH] = {
            "id": VIDEO,
            "ie_key": "Youtube",
            "title": "Never Gonna",
            "duration": 213,
            "channel": "Rick Astley",
            "view_count": 1_800_000_000,
            "timestamp": 1_256_453_853,
        }

        found = look_up_link(WATCH)

        assert found.title == "Never Gonna"
        assert found.duration_ms == 213_000
        assert found.details == ItemDetails(
            channel="Rick Astley",
            view_count=1_800_000_000,
            published=1_256_453_853,
            is_published_exact=True,
            thumbnail=f"https://i.ytimg.com/vi/{VIDEO}/mqdefault.jpg",
        )

    def test_looked_up_as_to_be_played(self, ytdl):
        # YouTube without its player's script says a video is unavailable
        ytdl.answers[WATCH] = {"title": "A"}

        look_up_link(WATCH)

        (opts,) = ytdl.opts
        assert "js_runtimes" in opts
        assert "extractor_args" not in opts

    def test_a_link_leading_on_to_it(self, ytdl):
        ytdl.answers[SITE] = {"_type": "url", "url": "https://player/1", "ie_key": "X"}
        ytdl.answers["https://player/1"] = {"title": "B", "duration": 2.5}

        assert look_up_link(SITE) == Found(title="B", duration_ms=2500)

    def test_turned_away(self, ytdl):
        # as YouTube says it, with a typographic apostrophe
        ytdl.answers[WATCH] = Exception("Sign in to confirm you\u2019re not a bot")
        ytdl.answers[SITE] = Exception("HTTP Error 429: Too Many Requests")

        with pytest.raises(Refused) as youtube:
            look_up_link(WATCH)
        with pytest.raises(Refused) as site:
            look_up_link(SITE)

        assert youtube.value.site == "YouTube"
        assert site.value.site == "vimeo.com"

    def test_gone(self, ytdl):
        ytdl.answers[WATCH] = Exception("Video unavailable")

        with pytest.raises(NotFound):
            look_up_link(WATCH)

    def test_a_list_is_no_video(self, ytdl):
        ytdl.answers[SITE] = {"_type": "playlist", "entries": []}

        with pytest.raises(NotFound):
            look_up_link(SITE)


class _Media:
    def __init__(self, statuses, duration):
        self._statuses = list(statuses)
        self._duration = duration
        self.released = False

    def parse_with_options(self, flag, timeout):
        pass

    def get_parsed_status(self):
        if len(self._statuses) > 1:
            return self._statuses.pop(0)
        return self._statuses[0]

    def get_duration(self):
        return self._duration

    def release(self):
        self.released = True


def _vlc(media):
    return SimpleNamespace(
        MediaParseFlag=SimpleNamespace(local=0),
    ), SimpleNamespace(media_new_path=lambda path: media)


class TestAFilesLength:
    def test_once_read(self):
        media = _Media([0, 0, SimpleNamespace(value=4)], 61_000)
        vlc, instance = _vlc(media)

        assert item_info._length_of(vlc, instance, "a.mp4") == 61_000
        assert media.released

    @pytest.mark.parametrize("status", [1, 2, 3])
    def test_none_where_it_could_not_be(self, status):
        vlc, instance = _vlc(_Media([status], 61_000))

        assert item_info._length_of(vlc, instance, "a.mp4") is None

    def test_none_where_vlc_knows_none(self):
        vlc, instance = _vlc(_Media([4], -1))

        assert item_info._length_of(vlc, instance, "a.mp4") is None
