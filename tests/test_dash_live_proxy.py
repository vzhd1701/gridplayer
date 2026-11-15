"""The proxy serving a live DASH manifest to mpv as live HLS: what it can't read is
a failure of the stream, the manifest is fetched once for the picture's playlist and
the sound's, every language is offered, and a server's clock read whatever its Date
says of the zone."""

from email.utils import format_datetime
from unittest.mock import MagicMock

import pytest
from requests import Response
from streamlink import StreamError

from gridplayer.models.stream import HashableDict, Stream, StreamSessionOpts
from gridplayer.utils.stream_proxy import dash_live, wrappers
from gridplayer.utils.stream_proxy.wrappers import DASHLiveHLS
from tests.test_dash_live import NUMBERED, STARTED

MANIFEST_URL = "https://cdn.example/live/manifest.mpd"

AT_21_S = format_datetime(STARTED.replace(second=21), usegmt=True)


@pytest.fixture(autouse=True)
def _forget():
    wrappers._live_manifests.clear()
    dash_live._numbers_given.clear()


def _response(text: str, date: str = AT_21_S) -> Response:
    response = Response()
    response.status_code = 200
    response._content = text.encode()
    response.url = MANIFEST_URL
    response.headers["Date"] = date
    return response


def _proxy(mocker, text, date=AT_21_S, **stream):
    server = MagicMock()
    server.add_stream.side_effect = lambda s: f"proxy/{s.rendition or s.url}"

    proxy = DASHLiveHLS(
        server=server,
        session_opts=StreamSessionOpts(service="here", session_headers=HashableDict()),
        session_=MagicMock(),
        url=MANIFEST_URL,
        stream=Stream(url=MANIFEST_URL, protocol="dash_live", **stream),
    )
    fetch = mocker.patch.object(proxy, "_fetch", return_value=_response(text, date))

    return proxy, fetch


def test_what_is_no_manifest_fails_as_the_stream(mocker):
    proxy, _ = _proxy(mocker, "<html><body>Sorry</body></html>")

    with pytest.raises(StreamError):
        proxy.open()


def test_its_playlist_of_what_is_out(mocker):
    proxy, _ = _proxy(mocker, NUMBERED, rendition="video", max_height=800)

    proxy.open()

    body = proxy.response.text

    assert "#EXT-X-MEDIA-SEQUENCE:6" in body
    assert "proxy/https://cdn.example/live/v720/00010.m4s" in body


def test_a_date_that_says_no_zone(mocker):
    proxy, _ = _proxy(
        mocker,
        NUMBERED,
        date="Sun, 15 Nov 2026 12:00:21 -0000",
        rendition="video",
        max_height=800,
    )

    proxy.open()

    assert "v720/00010.m4s" in proxy.response.text


def test_the_manifest_is_fetched_once_for_the_picture_and_the_sound(mocker):
    video, video_fetch = _proxy(mocker, NUMBERED, rendition="video", max_height=800)
    sound, sound_fetch = _proxy(mocker, NUMBERED, rendition="audio:en")

    video.open()
    sound.open()

    assert video_fetch.call_count + sound_fetch.call_count == 1
    assert "a_en_hi/6.m4s" in sound.response.text


def test_every_language_offered_the_one_asked_for_first(mocker):
    proxy, _ = _proxy(mocker, NUMBERED, languages_asked="es")

    proxy.open()

    body = proxy.response.text

    assert 'LANGUAGE="es",DEFAULT=YES,AUTOSELECT=YES,URI="proxy/audio:es"' in body
    assert 'LANGUAGE="en",DEFAULT=NO,AUTOSELECT=YES,URI="proxy/audio:en"' in body
    assert body.endswith("proxy/video")


def test_a_manifest_read_a_while_ago_is_let_go_of(mocker):
    wrappers._live_manifests[("old", None)] = (0.0, "", "", STARTED)

    proxy, _ = _proxy(mocker, NUMBERED, rendition="video")
    proxy.open()

    assert ("old", None) not in wrappers._live_manifests
