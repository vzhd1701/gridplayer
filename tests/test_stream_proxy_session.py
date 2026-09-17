"""Which wrapper a protocol is served by.

Every stream the proxy serves arrives as a protocol name and has to be
matched to the one wrapper that knows how to fetch it. Getting that
mapping wrong serves the right bytes the wrong way, or nothing at all.
"""

from unittest.mock import MagicMock

import pytest

from gridplayer.models.stream import (
    HashableDict,
    Stream,
    Streams,
    StreamSessionOpts,
)
from gridplayer.utils.stream_proxy.session import StreamSession
from gridplayer.utils.stream_proxy.wrappers import (
    DASHManifestProxy,
    DASHPlaylistStream,
    HLSMuxedStream,
    HLSProxy,
    HLSProxyLive,
    HTTPPlaylistStream,
    HTTPStreamProxy,
)

SESSION = StreamSessionOpts(service="test", session_headers=HashableDict({}))


@pytest.fixture
def session():
    return StreamSession(stream_session=SESSION, server=MagicMock())


def _stream(protocol, **kwargs):
    return Stream(url="http://host/video", protocol=protocol, session=SESSION, **kwargs)


@pytest.mark.parametrize(
    ("protocol", "wrapper"),
    [
        ("http", HTTPStreamProxy),
        ("hls_proxy", HLSProxy),
        ("dash_proxy", DASHManifestProxy),
        ("http_hls", HTTPPlaylistStream),
        ("dash", DASHPlaylistStream),
        ("hls", HLSProxyLive),
    ],
)
def test_a_protocol_is_served_by_its_own_wrapper(session, protocol, wrapper):
    assert isinstance(session.get_stream(_stream(protocol)), wrapper)


def test_a_stream_with_separate_audio_is_paired_whatever_its_protocol(session):
    """VLC can only be given both through a playlist, so that comes first."""

    with_audio = _stream(
        "http", audio_tracks=Streams({"best": _stream("http", is_audio_only=True)})
    )

    assert isinstance(session.get_stream(with_audio), HLSMuxedStream)


def test_a_protocol_nobody_handles_is_refused(session):
    """Better than serving it with whichever wrapper happens to be last."""

    with pytest.raises(RuntimeError, match="rtmp"):
        session.get_stream(_stream("rtmp"))
