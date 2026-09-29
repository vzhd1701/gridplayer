"""The chapters a site lists, as they come out of yt-dlp."""

import pytest

from gridplayer.models.chapter import Chapter
from gridplayer.models.stream import Stream, Streams
from gridplayer.utils.url_resolve.resolver_base import ResolverBase
from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver

STREAMS = Streams({"720p": Stream(url="https://cdn/720.mp4", protocol="direct")})


def _resolver(**video_info):
    resolver = YoutubeDLResolver("https://site/watch?v=1")
    resolver.__dict__["_video_info"] = {
        "extractor": "generic",
        "title": "test",
        **video_info,
    }
    return resolver


def _chapters(*raw_chapters):
    return _resolver(chapters=list(raw_chapters)).chapters


class TestChapters:
    def test_seconds_come_out_as_milliseconds_under_their_names(self):
        chapters = _chapters(
            {"start_time": 0, "end_time": 101, "title": "Intro"},
            {"start_time": 101.5, "end_time": 230, "title": "Building the Frame"},
        )

        assert chapters == (Chapter(0, "Intro"), Chapter(101500, "Building the Frame"))

    def test_what_yt_dlp_calls_an_untitled_one_is_no_name(self):
        chapters = _chapters(
            {"start_time": 0, "title": "Intro"},
            {"start_time": 60, "title": "<Untitled Chapter 2>"},
        )

        assert chapters == (Chapter(0, "Intro"), Chapter(60000, None))

    def test_the_one_yt_dlp_puts_in_front_of_the_list_goes(self):
        # what yt-dlp makes of a list whose first chapter starts 30s in
        chapters = _chapters(
            {"start_time": 0, "end_time": 30, "title": "<Untitled Chapter 1>"},
            {"start_time": 30, "end_time": 90, "title": "Opening"},
            {"start_time": 90, "end_time": 120, "title": "Main"},
        )

        assert chapters == (Chapter(30000, "Opening"), Chapter(90000, "Main"))

    def test_a_list_with_no_names_at_all_is_kept_whole(self):
        chapters = _chapters(
            {"start_time": 0, "title": "<Untitled Chapter 1>"},
            {"start_time": 30, "title": "<Untitled Chapter 2>"},
        )

        assert chapters == (Chapter(0, None), Chapter(30000, None))

    @pytest.mark.parametrize("video_info", [{}, {"chapters": None}, {"chapters": []}])
    def test_a_site_that_lists_none_gives_none(self, video_info):
        assert _resolver(**video_info).chapters == ()

    @pytest.mark.parametrize("start", [None, "soon", float("nan")])
    def test_one_with_no_start_to_go_by_is_passed_over(self, start):
        chapters = _chapters(
            {"start_time": 0, "title": "Intro"},
            {"start_time": start, "title": "Broken"},
            {"start_time": 60, "title": "Main"},
        )

        assert chapters == (Chapter(0, "Intro"), Chapter(60000, "Main"))


class TestLength:
    def test_the_sites_duration_comes_out_in_milliseconds(self):
        assert _resolver(duration=596.4).duration_ms == 596400

    def test_a_site_that_gives_none_leaves_it_at_zero(self):
        assert _resolver().duration_ms == 0


class TestResolved:
    def test_they_come_along_with_the_streams(self, mocker):
        mocker.patch.object(YoutubeDLResolver, "streams", STREAMS)
        mocker.patch.object(YoutubeDLResolver, "is_live", False)

        resolved = _resolver(
            duration=120, chapters=[{"start_time": 0, "title": "Intro"}]
        ).resolve()

        assert resolved.chapters == (Chapter(0, "Intro"),)
        assert resolved.duration_ms == 120000

    def test_a_resolver_that_cannot_tell_gives_none(self):
        class _Plain(ResolverBase):
            title = "test"
            is_live = False
            streams = STREAMS

            @staticmethod
            def is_able_to_handle(url):
                return True

        resolved = _Plain("https://site/live").resolve()

        assert resolved.chapters == ()
        assert resolved.duration_ms == 0
