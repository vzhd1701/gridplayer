"""A stream with separate sound, for a driver that opens the two apart, and what the
proxy does for a response with no length."""

import time
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from requests import Response
from streamlink import StreamError

from gridplayer.models.stream import Stream, StreamOrigin, Streams
from gridplayer.utils.stream_proxy.server import ProxyRequestHandler
from gridplayer.utils.video_errors import ProxyFailure
from gridplayer.widgets.video_block_stream import StreamControl
from gridplayer.widgets.video_frame_mpv import VideoFrameMpv
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC

_AUDIO = Stream(url="http://a/high", protocol="http", is_audio_only=True, language="de")


def _with_sound(**fields):
    return Stream(
        url="http://v",
        protocol="hls_proxy",
        audio_tracks=Streams({"Audio 128k": _AUDIO}),
        **fields,
    )


def test_apart_the_picture_has_no_sound_left():
    video, name, audio = _with_sound().apart()

    assert video.audio_tracks is None
    assert video.url == "http://v"
    assert name == "Audio 128k"
    assert audio == _AUDIO


def test_apart_the_sound_can_be_found_again_once_renewed():
    origin = StreamOrigin(url="http://page", quality="720p")

    video, _name, audio = _with_sound(origin=origin).apart()

    assert video.origin == origin
    assert audio.origin.audio_track == "Audio 128k"
    assert audio.origin.quality == "720p"


@pytest.mark.parametrize(
    ("video", "sound", "has_one"),
    [
        ("http_hls", "http_hls", True),
        ("hls_proxy", "http_hls", True),
        ("http_hls", "hls_proxy", True),
        ("hls_proxy", "hls_proxy", False),
    ],
)
def test_a_file_in_fragments_is_told_whichever_half_it_is(video, sound, has_one):
    stream = Stream(
        url="http://v",
        protocol=video,
        audio_tracks=Streams({"A": Stream(url="http://a", protocol=sound)}),
    )

    assert stream.has_fragmented_file == has_one


def test_a_stream_with_no_separate_sound_has_only_itself_to_go_by():
    assert Stream(url="http://v", protocol="http_hls").has_fragmented_file
    assert not Stream(url="http://v", protocol="hls_proxy").has_fragmented_file


@pytest.fixture
def control(mocker):
    mocker.patch("gridplayer.widgets.video_block_stream.QTimer")

    block = MagicMock()
    block._ctx.commands.add_stream.side_effect = lambda stream: f"proxy/{stream.url}"

    return StreamControl(block)


@pytest.fixture
def apart(control):
    """On a driver that opens a stream as it comes, the sound apart."""

    control._block.driver_class = VideoFrameMpv

    return control


@pytest.fixture
def together(control):
    control._block.driver_class = VideoFrameVLC

    return control


def _given(control):
    return [
        call.args[0] for call in control._block._ctx.commands.add_stream.call_args_list
    ]


def test_a_driver_that_opens_them_apart_gets_two_links(apart):
    url, stream_audio = apart._add_to_proxy(_with_sound())

    assert url == "proxy/http://v"
    assert stream_audio.uri == "proxy/http://a/high"
    assert stream_audio.title == "Audio 128k"
    assert stream_audio.language == "de"


def test_the_rest_get_the_one_playlist(together):
    url, stream_audio = together._add_to_proxy(_with_sound())

    assert url == "proxy/http://v"
    assert stream_audio is None
    together._block._ctx.commands.add_stream.assert_called_once()


def test_a_driver_that_takes_them_as_they_are_is_given_files_not_playlists(apart):
    audio = Stream(url="http://a", protocol="http_hls", is_audio_only=True)
    stream = Stream(
        url="http://v", protocol="http_hls", audio_tracks=Streams({"A": audio})
    )

    apart._add_to_proxy(stream)

    assert [stream.protocol for stream in _given(apart)] == ["http", "http"]


def test_the_rest_are_given_the_playlist_made_of_a_file(together):
    together._add_to_proxy(Stream(url="http://v", protocol="http_hls"))

    assert [stream.protocol for stream in _given(together)] == ["http_hls"]


@pytest.mark.parametrize("protocol", ["hls_proxy", "hls", "dash", "http"])
def test_only_a_file_in_fragments_is_made_a_file(protocol):
    assert Stream(url="http://v", protocol=protocol).as_file().protocol == protocol


def test_a_stream_with_no_separate_sound_is_one_link_on_any_driver(apart):
    _url, stream_audio = apart._add_to_proxy(Stream(url="http://v", protocol="hls"))

    assert stream_audio is None


def _failure(status, at):
    return ProxyFailure(url="http://cdn", status=status, reason="", at=at)


@pytest.fixture
def loaded_apart(apart):
    """Its two links, loaded a while ago."""

    apart._add_to_proxy(_with_sound())
    apart._loaded_at = time.monotonic() - 10

    return apart


def test_what_went_wrong_with_either_is_told(loaded_apart):
    failures = {"proxy/http://a/high": _failure(403, time.monotonic())}
    loaded_apart._block._ctx.commands.stream_failure.side_effect = failures.get

    assert loaded_apart.proxy_failure().status == 403


def test_the_last_to_go_wrong_is_the_one_told(loaded_apart):
    now = time.monotonic()
    failures = {
        "proxy/http://v": _failure(404, now - 2),
        "proxy/http://a/high": _failure(403, now - 1),
    }
    loaded_apart._block._ctx.commands.stream_failure.side_effect = failures.get

    assert loaded_apart.proxy_failure().status == 403


def _handler():
    handler = ProxyRequestHandler.__new__(ProxyRequestHandler)

    handler._is_response_started = False
    handler.request_version = "HTTP/1.1"
    handler.requestline = "GET / HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)
    handler.close_connection = False
    handler.wfile = BytesIO()
    handler._log = MagicMock()

    return handler


def _response(**headers):
    response = Response()
    response.status_code = 200
    response.reason = "OK"
    response.headers.update(headers)
    response._content = b"data"

    return response


def test_a_response_of_no_length_ends_by_closing():
    # a live stream's: it's all a player has to know that it's over
    handler = _handler()

    handler._relay_response(_response(), [b"data"])

    assert handler.close_connection
    assert b"Connection: close" in handler.wfile.getvalue()


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Length": "4"},
        {"content-length": "4"},
        {"Transfer-Encoding": "chunked"},
    ],
)
def test_a_response_that_says_where_it_ends_keeps_its_connection(headers):
    handler = _handler()

    handler._relay_response(_response(**headers), [b"data"])

    assert not handler.close_connection
    assert b"Connection: close" not in handler.wfile.getvalue()


def test_a_stream_error_with_no_answer_behind_it_is_a_failure_all_the_same():
    # raised by the proxy's own reader, which has no request to say anything of
    failure = _handler()._failure_from_error(StreamError("No data returned"))

    assert failure.response is None
    assert isinstance(failure.error, StreamError)


def test_a_stream_error_with_an_answer_behind_it_relays_that():
    from requests import HTTPError

    answer = _response()
    answer.status_code = 403

    err = StreamError("Unable to open URL")
    err.err = HTTPError(response=answer)

    assert _handler()._failure_from_error(err).response is answer
