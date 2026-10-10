"""Which resolved videos SponsorBlock can be asked about."""

from gridplayer.utils.url_resolve.resolver_base import DirectResolver
from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver

VIDEO_ID = "dQw4w9WgXcQ"


def _resolver(**video_info):
    resolver = YoutubeDLResolver(f"https://www.youtube.com/watch?v={VIDEO_ID}")
    resolver.__dict__["_video_info"] = {
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "id": VIDEO_ID,
        "title": "test",
        "is_live": False,
        **video_info,
    }
    return resolver


def test_a_youtube_video_is_known_by_its_id():
    assert _resolver().youtube_id == VIDEO_ID


def test_a_live_one_has_nothing_to_skip():
    assert _resolver(is_live=True).youtube_id is None


def test_another_site_is_not_youtube():
    assert _resolver(extractor="vimeo", extractor_key="Vimeo").youtube_id is None


def test_a_link_played_as_it_is_is_nobodys():
    assert DirectResolver("https://cdn/video.mp4").youtube_id is None


class TestWhatTheSiteSaysOfTheVideo:
    def test_when_it_was_put_up_to_the_second(self):
        details = _resolver(
            channel="Channel", view_count=92789, timestamp=1273312425
        ).details

        assert details.channel == "Channel"
        assert details.view_count == 92789
        assert details.published == 1273312425
        assert details.is_published_exact

    def test_its_picture(self):
        assert _resolver().details.thumbnail == (
            f"https://i.ytimg.com/vi/{VIDEO_ID}/mqdefault.jpg"
        )

    def test_nothing_from_a_link_played_as_it_is(self):
        assert DirectResolver("https://cdn/video.mp4").details is None
