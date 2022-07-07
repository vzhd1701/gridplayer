import itertools
import logging
import re
import traceback
from functools import cached_property
from typing import Optional, Tuple

from yt_dlp import DownloadError, YoutubeDL
from yt_dlp.utils import UnsupportedError

from gridplayer.models.stream import HashableDict, Stream, Streams, StreamSessionOpts
from gridplayer.models.video import VideoURL
from gridplayer.settings import Settings
from gridplayer.utils.url_resolve.resolver_base import ResolverBase
from gridplayer.utils.url_resolve.static import (
    BadURLException,
    NoResolverPlugin,
    StreamOfflineError,
)
from gridplayer.utils.url_resolve.stream_detect import (
    is_hls_live_stream,
    is_http_live_stream,
)


class YoutubeDLResolver(ResolverBase):
    @property
    def title(self) -> str:
        return self._video_info.get("title") or self.url

    @cached_property
    def is_live(self) -> bool:
        if self._video_info.get("is_live") is not None:
            return self._video_info["is_live"]

        test_stream = self._raw_streams_main[-1]

        if "m3u8" in test_stream["protocol"]:
            return is_hls_live_stream(
                url=test_stream["url"],
                session_headers=test_stream.get("http_headers"),
            )

        if "http" in test_stream["protocol"]:
            return is_http_live_stream(
                url=test_stream["url"],
                session_headers=test_stream.get("http_headers"),
            )

        return False

    @property
    def streams(self) -> Streams:
        return self._get_streams(
            raw_streams_main=self._raw_streams_main,
            raw_streams_audio=self._raw_streams_audio,
            is_live=self.is_live,
        )

    @staticmethod
    def is_able_to_handle(url: VideoURL) -> bool:  # noqa: WPS602
        logger = logging.getLogger("YoutubeDLResolver")
        with YoutubeDL({"logger": logger}) as ydl:
            ies = ydl._ies  # noqa: WPS437
            return any(ie.suitable(url) for ie in ies.values())

    @cached_property
    def _video_info(self):
        with YoutubeDL({"logger": self._log}) as ydl:
            try:
                return ydl.extract_info(self.url, download=False)
            except DownloadError as e:
                if e.exc_info[0] is UnsupportedError:
                    raise NoResolverPlugin

                if "offline" in str(e):
                    raise StreamOfflineError

                self._log.debug(f"yt-dlp error:\n{traceback.format_exc()}")
                raise NoResolverPlugin

    @cached_property
    def _raw_streams(self):
        http_streams = [
            fmt
            for fmt in self._video_info.get("formats", [])
            if fmt.get("url", "").startswith("http")
        ]

        audio_streams = [
            fmt
            for fmt in http_streams
            if fmt.get("vcodec") == "none" and fmt.get("acodec") != "none"
        ]

        streams_with_video = [
            fmt for fmt in http_streams if fmt.get("vcodec") != "none"
        ]

        # keeping only muxed streams or m3u8 streams (which can be paired with audio)
        streams_with_video = [
            fmt
            for fmt in streams_with_video
            if fmt.get("acodec") != "none" or "m3u8" in fmt.get("protocol", "")
        ]

        # getting all streams if no combined streams are available
        if streams_with_video:
            streams_main = streams_with_video
        else:
            streams_main = http_streams
            audio_streams = []

        if not streams_main:
            raise BadURLException("yt-dlp - no streams found")

        self._log.debug("yt-dlp - {0} stream(s) found".format(len(streams_main)))

        return streams_main, audio_streams

    @cached_property
    def _raw_streams_main(self):
        streams, _ = self._raw_streams
        return streams

    @cached_property
    def _raw_streams_audio(self):
        _, streams = self._raw_streams
        return streams

    @property
    def _service_id(self) -> str:
        return "yt_dlp-{0}".format(self._video_info["extractor"])

    def _get_streams(  # noqa: WPS210
        self, raw_streams_main, raw_streams_audio, is_live
    ) -> Streams:
        streams = Streams()

        unknown_counter = itertools.count(1)

        audio_tracks = self._get_audio_tracks(raw_streams_audio)

        for raw_stream in raw_streams_main:
            stream = self._get_stream(raw_stream, audio_tracks, is_live)

            fmt_name = _get_fmt_name(
                stream=raw_stream,
                unknown_counter=unknown_counter,
                is_muxed=bool(stream.audio_tracks),
            )

            streams[fmt_name] = stream

        return streams

    def _get_audio_tracks(self, raw_streams_audio) -> Optional[Streams]:
        if not raw_streams_audio:
            return None

        # these will be used to pair up with m3u8 only, vlc can support only these
        audio_tracks_m3u8 = [s for s in raw_streams_audio if "m3u8" in s["protocol"]]
        return self._get_streams(audio_tracks_m3u8, [], False)

    def _get_stream(
        self, stream, audio_tracks: Optional[Streams], is_live: bool
    ) -> Stream:
        is_m3u8 = "m3u8" in stream["protocol"]

        if is_m3u8 and stream.get("acodec") == "none" and audio_tracks:
            cur_audio_tracks = audio_tracks
            is_live = False
        else:
            cur_audio_tracks = None

        url, protocol = _get_stream_url(stream, is_live)

        return Stream(
            url=url,
            protocol=protocol,
            audio_tracks=cur_audio_tracks,
            session=StreamSessionOpts(
                service=self._service_id,
                session_headers=HashableDict(stream.get("http_headers", {})),
            ),
        )


def _get_stream_url(stream, is_live) -> Tuple[str, str]:
    protocol = stream.get("protocol", "")

    if protocol in {"m3u8", "m3u8_native"}:
        protocol = "hls"
    elif protocol in {"http", "https"}:
        protocol = "http"
    else:
        protocol = "direct"

    is_via_streamlink = Settings().get("streaming/hls_via_streamlink")

    if protocol == "hls" and (not is_via_streamlink or not is_live):
        protocol = "hls_proxy"

    return stream["url"], protocol


def _get_fmt_name(stream, unknown_counter, is_muxed=False):
    fmt_name = stream.get("format_note") or stream.get("format_id")

    if not re.match(r"^\d+p", fmt_name):
        if stream.get("height"):
            if stream.get("format_id"):
                fmt_name = "{0}p [{1}]".format(stream["height"], stream["format_id"])
            else:
                fmt_name = "{0}p".format(stream["height"])
        else:
            fmt_name = stream.get("format", "Unknown {0}".format(next(unknown_counter)))

    if stream.get("acodec") == "none" and not is_muxed:
        fmt_name += " (video only)"

    if stream.get("vcodec") == "none":
        fmt_name += " (audio only)"

    return fmt_name
