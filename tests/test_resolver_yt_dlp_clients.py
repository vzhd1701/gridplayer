"""Which of YouTube's players yt-dlp asks as. Signed in, its first is the embedded
player, whose links stop a minute in: the TV app's go first."""

import contextlib

import pytest

from gridplayer.utils.url_resolve import resolver_yt_dlp
from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver

URL = "https://www.youtube.com/watch?v=a"


@pytest.fixture
def opened_with(mocker):
    """What yt-dlp is opened with, the cookies being the test's to set."""

    params = {}

    class _FakeYoutubeDL:
        def __init__(self, opts):
            params.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False, ie_key=None):
            return {"_type": "video", "id": "a", "formats": [{"url": "x"}]}

    def with_cookies(cookie_opts):
        mocker.patch.object(
            resolver_yt_dlp,
            "ytdl_cookies",
            return_value=contextlib.nullcontext(cookie_opts),
        )

        assert YoutubeDLResolver(URL)._video_info

        return params

    mocker.patch.object(resolver_yt_dlp, "YoutubeDL", _FakeYoutubeDL)
    mocker.patch.object(resolver_yt_dlp, "ytdl_network_opts", return_value={})
    mocker.patch.object(resolver_yt_dlp, "ytdl_js_runtimes", return_value=None)

    return with_cookies


def test_signed_in_the_tv_app_is_asked_first(opened_with):
    params = opened_with({"cookiefile": "jar"})

    assert params["extractor_args"]["youtube"]["player_client"] == [
        "tv_samsung",
        "default",
    ]


def test_with_no_cookies_yt_dlp_chooses(opened_with):
    params = opened_with({})

    assert "extractor_args" not in params
