"""The proxy serving a live DASH manifest to mpv as live HLS: what it can't read is
a failure of the stream, and the manifest is fetched once for the picture's playlist
and the sound's."""

from email.utils import format_datetime
from unittest.mock import MagicMock

import pytest
from requests import Response
from streamlink import StreamError

from gridplayer.models.stream import HashableDict, Stream, StreamSessionOpts
from gridplayer.utils.stream_proxy import wrappers
from gridplayer.utils.stream_proxy.wrappers import DASHLiveHLS
from tests.test_dash_live import NUMBERED, STARTED

MANIFEST_URL = "https://cdn.example/live/manifest.mpd"


@pytest.fixture(autouse=True)
def _forget():
    wrappers._live_manifests.clear()


def _response(text: str) -> Response:
    response = Response()
    response.status_code = 200
    response._content = text.encode()
    response.url = MANIFEST_URL
    response.headers["Date"] = format_datetime(STARTED.replace(second=21), usegmt=True)
    return response


def _proxy(mocker, text, representation=None):
    server = MagicMock()
    server.add_stream.side_effect = lambda stream: f"proxy/{stream.url}"

    proxy = DASHLiveHLS(
        server=server,
        session_opts=StreamSessionOpts(service="here", session_headers=HashableDict()),
        session_=MagicMock(),
        url=MANIFEST_URL,
        stream=Stream(
            url=MANIFEST_URL, protocol="dash_live", representation=representation
        ),
    )
    fetch = mocker.patch.object(proxy, "_fetch", return_value=_response(text))

    return proxy, fetch


def test_what_is_no_manifest_fails_as_the_stream(mocker):
    proxy, _ = _proxy(mocker, "<html><body>Sorry</body>")

    with pytest.raises(StreamError):
        proxy.open()


def test_its_playlist_of_what_is_out(mocker):
    proxy, _ = _proxy(mocker, NUMBERED, representation="v720")

    proxy.open()

    body = proxy.response.text

    assert "#EXT-X-MEDIA-SEQUENCE:6" in body
    assert "proxy/https://cdn.example/live/v720/00010.m4s" in body


def test_the_manifest_is_fetched_once_for_the_picture_and_the_sound(mocker):
    video, video_fetch = _proxy(mocker, NUMBERED, representation="v720")
    sound, sound_fetch = _proxy(mocker, NUMBERED, representation="a_en")

    video.open()
    sound.open()

    assert video_fetch.call_count + sound_fetch.call_count == 1
    assert "a_en/6.m4s" in sound.response.text
