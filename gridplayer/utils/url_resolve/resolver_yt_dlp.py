import dataclasses
import itertools
import logging
import re
import traceback
from collections import Counter
from functools import cached_property
from types import MappingProxyType
from urllib.parse import urljoin

from yt_dlp import DownloadError, YoutubeDL
from yt_dlp.utils import UnsupportedError

from gridplayer.models.stream import (
    HashableDict,
    Stream,
    StreamFragment,
    Streams,
    StreamSessionOpts,
)
from gridplayer.settings import Settings
from gridplayer.utils.cookies import ytdl_cookies
from gridplayer.utils.js_runtime import ytdl_js_runtimes
from gridplayer.utils.network import needs_relay, ytdl_network_opts
from gridplayer.utils.percent_re import untangle_percent_re
from gridplayer.utils.track_language import language_name
from gridplayer.utils.url_resolve.resolver_base import ResolverBase
from gridplayer.utils.url_resolve.static import (
    BadURLException,
    NoResolverPlugin,
    StreamOfflineError,
)
from gridplayer.utils.url_resolve.stream_detect import (
    is_dash_live_stream,
    is_fragmented_stream,
    is_hls_live_stream,
    is_http_live_stream,
)

# yt-dlp patches urllib3 as it is imported; see utils/percent_re.py
untangle_percent_re()

# VLC can only pair separate audio & video through HLS, so a stream that
# has to carry an extra audio track must be servable as a playlist
PLAYLIST_PROTOCOLS = MappingProxyType(
    {
        "hls": "hls_proxy",
        "hls_proxy": "hls_proxy",
        "dash": "dash",
        "http": "http_hls",
        "http_hls": "http_hls",
    }
)

# a stream whose URL is a manifest that decides for itself what plays,
# whether VLC opens it or the proxy hands it over rewritten
MANIFEST_PROTOCOLS = frozenset({"direct", "dash_proxy"})

# what the one rung is called when a whole ladder turns out to be the same
# manifest; naming it after any one representation would promise a size
# that VLC is under no obligation to pick
ADAPTIVE_FMT_NAME = "Adaptive"
ADAPTIVE_AUDIO_FMT_NAME = "Audio"

# VLC refuses to demux anything but mp4 & mpegts out of a playlist we build,
# WebM segments make it bail out before the first frame
HLS_SEGMENT_EXTENSIONS = frozenset({"mp4", "m4a", "m4v", "mov", "ts", "mts", "m2ts"})

# a whole file carries no segment list to state its length, so the duration
# has to travel with it; "http" is in here because such a stream can still be
# turned into "http_hls" later on, taking the duration with it
FILE_PROTOCOLS = frozenset({"http", "http_hls"})

# yt-dlp promises bitrates in kbit/s, but some extractors pass on the raw
# bits/s they read off the site, inflating every number by 1000. Such a value
# gives itself away by making the file out to be a fraction of a second long.
BITRATE_KEYS = ("tbr", "vbr", "abr")
MIN_PLAUSIBLE_DURATION = 1.0

# what yt-dlp scores the sound a video was made with, above every dub of it
ORIGINAL_LANGUAGE_PREFERENCE = 10


class YoutubeDLResolver(ResolverBase):
    @property
    def title(self) -> str:
        return self._video_info.get("title") or self.url

    @cached_property
    def is_live(self) -> bool:
        if self._video_info.get("is_live") is not None:
            return self._video_info["is_live"]

        test_stream = self._raw_streams_main[-1]

        if test_stream["protocol"] == "http_dash_segments":
            return is_dash_live_stream(
                url=test_stream["url"],
                session_headers=test_stream.get("http_headers"),
            )

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
    def is_able_to_handle(url: str) -> bool:
        logger = logging.getLogger("YoutubeDLResolver")
        with YoutubeDL({"logger": logger}) as ydl:
            ies = ydl._ies
            return any(ie.suitable(url) for ie in ies.values())

    @cached_property
    def _video_info(self):
        with (
            ytdl_cookies() as cookie_opts,
            YoutubeDL(
                {
                    "logger": self._log,
                    "js_runtimes": ytdl_js_runtimes(),
                    **cookie_opts,
                    **ytdl_network_opts(),
                }
            ) as ydl,
        ):
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
        if self._video_info.get("direct"):
            self._log.debug("yt-dlp reports direct link, passing it to DirectResolver")
            raise NoResolverPlugin

        http_streams = [
            fmt
            for fmt in self._video_info.get("formats", [])
            if fmt.get("url", "").startswith("http")
        ]

        # yt-dlp would fetch these posing as a browser, but VLC and the
        # proxy cannot, so the host would turn them away on the first request
        fetchable = [fmt for fmt in http_streams if not _needs_impersonation(fmt)]
        if len(fetchable) < len(http_streams):
            self._log.debug(
                f"yt-dlp - skipping {len(http_streams) - len(fetchable)} stream(s)"
                " that can only be fetched with browser impersonation"
            )

            if not fetchable:
                raise BadURLException(
                    "yt-dlp - all streams need browser impersonation to be fetched"
                )

            http_streams = fetchable

        _fix_bitrate_units(http_streams)

        audio_streams = [
            fmt
            for fmt in http_streams
            if fmt.get("vcodec") == "none" and fmt.get("acodec") != "none"
        ]

        streams_with_video = [
            fmt for fmt in http_streams if fmt.get("vcodec") != "none"
        ]

        has_audio_tracks = any(self._is_playlist_capable(fmt) for fmt in audio_streams)

        # a silent stream is only worth offering if audio can be paired with it
        streams_with_video = [
            fmt
            for fmt in streams_with_video
            if fmt.get("acodec") != "none"
            or (has_audio_tracks and self._is_playlist_capable(fmt))
        ]

        # getting all streams if no combined streams are available
        if streams_with_video:
            streams_main = streams_with_video
        else:
            streams_main = http_streams
            audio_streams = []

        if not streams_main:
            raise BadURLException("yt-dlp - no streams found")

        self._log.debug(f"yt-dlp - {len(streams_main)} stream(s) found")

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
        return f"yt_dlp-{self._video_info['extractor']}"

    def _get_streams(self, raw_streams_main, raw_streams_audio, is_live) -> Streams:
        streams = Streams()

        unknown_counter = itertools.count(1)

        audio_tracks = self._get_audio_tracks(raw_streams_audio, is_live)

        is_multilingual = _is_multilingual(raw_streams_main)

        manifests_with_sound = {raw_stream["url"] for raw_stream in raw_streams_audio}

        for raw_stream in raw_streams_main + raw_streams_audio:
            stream = self._get_stream(raw_stream, audio_tracks, is_live)

            fmt_name = _get_fmt_name(
                stream=raw_stream,
                unknown_counter=unknown_counter,
                is_muxed=bool(stream.audio_tracks)
                or _carries_its_own_sound(stream, manifests_with_sound),
                is_multilingual=is_multilingual,
            )

            streams[_unique_name(streams, fmt_name)] = stream

        return _collapse_manifest_rungs(streams)

    def _get_audio_tracks(self, raw_streams_audio, is_live) -> Streams | None:
        """Audio tracks that can be attached to a video-only stream.

        They are served as HLS renditions, so anything that cannot be
        turned into a playlist is of no use here.
        """

        if not raw_streams_audio:
            return None

        audio_tracks = Streams()

        for raw_stream in raw_streams_audio:
            stream = self._get_stream(raw_stream, audio_tracks=None, is_live=is_live)

            playlist_protocol = self._playlist_protocol(raw_stream, stream.protocol)
            if playlist_protocol is None:
                continue

            fmt_name = _get_audio_fmt_name(raw_stream)

            # the duration set above rides along, a playlist may still need it
            audio_tracks[_unique_name(audio_tracks, fmt_name)] = dataclasses.replace(
                stream, protocol=playlist_protocol
            )

        return audio_tracks or None

    def _get_stream(
        self, stream, audio_tracks: Streams | None, is_live: bool
    ) -> Stream:
        protocol = _get_stream_protocol(stream, is_live)

        is_audio_only = _is_audio_only(stream)

        is_silent = stream.get("acodec") == "none" and not is_audio_only

        cur_audio_tracks = None
        if is_silent and audio_tracks:
            playlist_protocol = self._playlist_protocol(stream, protocol)

            if playlist_protocol is not None:
                protocol = playlist_protocol
                cur_audio_tracks = audio_tracks

        init_fragment, fragments = _get_fragments(stream, protocol)

        return Stream(
            url=stream["url"],
            protocol=protocol,
            is_audio_only=is_audio_only,
            video_codec=_get_video_codec(stream),
            language=_get_language(stream),
            is_original_language=_is_original_language(stream),
            audio_tracks=cur_audio_tracks,
            fragments=fragments,
            init_fragment=init_fragment,
            duration=self._duration if protocol in FILE_PROTOCOLS else 0,
            session=StreamSessionOpts(
                service=self._service_id,
                session_headers=HashableDict(stream.get("http_headers", {})),
            ),
        )

    @property
    def _duration(self) -> float:
        """Duration is needed to build a playlist for an unsegmented file."""

        return float(self._video_info.get("duration") or 0)

    def _playlist_protocol(self, stream, protocol: str) -> str | None:
        """Protocol to use when this stream has to be served as an HLS playlist."""

        if protocol == "http" and not self._is_segmentable_file(stream):
            return None

        return PLAYLIST_PROTOCOLS.get(protocol)

    def _is_playlist_capable(self, stream) -> bool:
        protocol = _get_stream_protocol(stream, is_live=False)

        return bool(self._playlist_protocol(stream, protocol))

    def _is_segmentable_file(self, stream) -> bool:
        if not _is_hls_segmentable(stream):
            return False

        # yt-dlp labels the containers it knows are published for DASH,
        # the rest have to be looked at
        return _is_dash_container(stream) or self._is_fragmented_source

    @cached_property
    def _is_fragmented_source(self) -> bool:
        """Whether plain files from this site are fragmented.

        A site serves every format out of the same packager, so one probe
        settles it for all of them.
        """

        probe = next(
            (
                fmt
                for fmt in reversed(self._video_info.get("formats", []))
                if fmt.get("protocol") in {"http", "https"}
                and fmt.get("acodec") == "none"
                and _is_hls_segmentable(fmt)
            ),
            None,
        )

        if probe is None:
            return False

        try:
            is_source_fragmented = is_fragmented_stream(
                url=probe["url"],
                session_headers=probe.get("http_headers"),
            )
        except Exception as e:
            self._log.debug(f"Failed to probe stream for fragments: {e}")
            return False

        self._log.debug(f"yt-dlp - source is fragmented: {is_source_fragmented}")

        return is_source_fragmented


def _get_stream_protocol(stream, is_live) -> str:
    protocol = stream.get("protocol", "")

    if protocol in {"m3u8", "m3u8_native"}:
        protocol = "hls"
    elif protocol == "http_dash_segments":
        # a live manifest keeps moving and the segment list we got is only a
        # snapshot of it, so VLC has to follow such a manifest itself
        is_expandable = not is_live and _is_hls_segmentable(stream)
        protocol = "dash" if is_expandable else _manifest_protocol(stream)
    elif protocol in {"http", "https"}:
        protocol = "http"
    else:
        protocol = "direct"

    is_via_streamlink = Settings().get("streaming/hls_via_streamlink")

    if protocol == "hls" and (not is_via_streamlink or not is_live):
        protocol = "hls_proxy"

    return protocol


def _manifest_protocol(stream) -> str:
    """Who fetches a manifest that VLC has to follow for itself.

    VLC cannot be told a cookie, nor a proxy it will honour for every
    access module, so a manifest whose segments need either is fetched by
    the proxy and handed over pointing back at it. Where nothing is
    asked of the connection that VLC cannot do itself, VLC is left to
    it: the relay would buy nothing and cost a hop on every segment.
    """

    return "dash_proxy" if needs_relay(stream.get("url", "")) else "direct"


def _needs_impersonation(stream) -> bool:
    """Whether yt-dlp would only fetch this stream posing as a browser.

    Read the way yt-dlp reads it: True or an empty string takes any
    target, a target or a list of them asks for those, and anything else
    empty means plain requests will do.
    """

    impersonate = stream.get("impersonate")

    return impersonate == "" or bool(impersonate)


def _is_dash_container(stream) -> bool:
    return str(stream.get("container") or "").endswith("_dash")


def _is_hls_segmentable(stream) -> bool:
    extensions = {
        str(stream.get("ext") or "").lower(),
        str(stream.get("container") or "").lower().removesuffix("_dash"),
    }

    return bool(extensions & HLS_SEGMENT_EXTENSIONS)


def _get_fragments(
    stream, protocol: str
) -> tuple[StreamFragment | None, tuple[StreamFragment, ...]]:
    """Expand yt-dlp fragment references into absolute segment URLs."""

    if protocol != "dash":
        return None, ()

    base_url = stream.get("fragment_base_url") or stream.get("url") or ""

    init_fragment = None
    fragments = []

    for fragment in stream.get("fragments") or []:
        url = fragment.get("url") or urljoin(base_url, fragment.get("path", ""))
        duration = fragment.get("duration")

        # the leading entry without a duration is the initialization segment
        if duration is None and not fragments and init_fragment is None:
            init_fragment = StreamFragment(url=url)
            continue

        fragments.append(StreamFragment(url=url, duration=duration or 0))

    return init_fragment, tuple(fragments)


def _is_multilingual(raw_streams) -> bool:
    """Whether these streams are the same video in more than one language."""

    languages = {_get_language(stream) for stream in raw_streams}

    return len(languages - {None}) > 1


def _unique_name(streams: Streams, fmt_name: str) -> str:
    """Keep one format from taking over another one's place in the list."""

    if fmt_name not in streams:
        return fmt_name

    for counter in itertools.count(2):
        candidate = f"{fmt_name} #{counter}"

        if candidate not in streams:
            return candidate


def _collapse_manifest_rungs(streams: Streams) -> Streams:
    """One rung per manifest, where a whole ladder is the same manifest.

    A live DASH source comes back as one format per representation, and
    every one of them carries the manifest URL rather than its own,
    because a live manifest has to be followed by VLC rather than
    expanded here. VLC then picks a representation by itself, so the
    ladder offers a choice that nothing downstream can honour: every rung
    loads the same URL. "Auto" takes the offer at face value and reloads
    the video on each change of pane size to arrive back where it was.
    """

    sizes = Counter(_manifest_key(stream) for _, stream in streams.items())

    collapsed = Streams()

    for name, stream in streams.items():
        key = _manifest_key(stream)

        if key is None or sizes[key] < 2:
            collapsed[name] = stream
            continue

        rung = ADAPTIVE_AUDIO_FMT_NAME if stream.is_audio_only else ADAPTIVE_FMT_NAME

        # the first one stands for the rest: they differ only in what they
        # say about a representation that VLC has yet to choose
        if rung not in collapsed:
            collapsed[_unique_name(collapsed, rung)] = stream

    return collapsed


def _carries_its_own_sound(stream: Stream, manifests_with_sound: set) -> bool:
    """Whether a rung that is silent by itself is still played with sound.

    A manifest is handed over whole, and VLC takes the audio out of it as
    readily as the video. The representation the format described is
    silent; what ends up playing is not, so calling the rung video only
    would be telling the viewer something they can hear is untrue.
    """

    return stream.protocol in MANIFEST_PROTOCOLS and stream.url in manifests_with_sound


def _manifest_key(stream: Stream) -> tuple | None:
    """What makes two rungs the same manifest handed over twice.

    Only a stream VLC opens for itself can be one. Anything the proxy
    serves carries its own segment list and is a rung in its own right,
    even where the URL next to it is the manifest they all came from.
    """

    if stream.protocol not in MANIFEST_PROTOCOLS:
        return None

    return stream.url, stream.is_audio_only


def _is_audio_only(stream) -> bool:
    return stream.get("vcodec") == "none" or (
        stream.get("video_ext") in {"none", None}
        and stream.get("resolution") in {"none", None}
        and stream.get("width") in {"none", None}
    )


def _get_fmt_name(stream, unknown_counter, is_muxed=False, is_multilingual=False):
    if _is_audio_only(stream):
        return _get_audio_fmt_name(stream)

    fmt_name = _get_video_fmt_name(stream, unknown_counter)

    # a dubbed video comes back as the whole ladder once per language, and
    # nothing but the language tells one copy of a rung from another
    if is_multilingual:
        language = _get_language(stream)

        if language:
            fmt_name = f"{fmt_name} ({language_name(language) or language})"

    # a site usually offers the same resolution in several codecs, so the
    # size alone does not say which one of them this is
    details = _get_codec_info(stream) or stream.get("format_id")
    if details:
        fmt_name = f"{fmt_name} [{details}]"

    if stream.get("acodec") == "none" and not is_muxed:
        fmt_name += " (video only)"

    return fmt_name


def _get_video_fmt_name(stream, unknown_counter) -> str:
    """Name a video stream by its size, however the site chose to state it."""

    fmt_name = stream.get("format_note") or stream.get("format_id") or ""

    if re.match(r"^\d+p", fmt_name):
        return fmt_name

    if stream.get("height"):
        return f"{stream['height']}p"

    return stream.get("format") or f"Unknown {next(unknown_counter)}"


def _get_language(stream) -> str | None:
    """The language of this stream's audio, where the site names one.

    A silent stream has no language of its own, whatever the site says:
    it borrows one from whichever audio track it ends up paired with.
    """

    if stream.get("acodec") == "none":
        return None

    language = stream.get("language")

    return language if language and language != "none" else None


def _is_original_language(stream) -> bool:
    """Whether this is the language the video was made in.

    yt-dlp scores a dub below the sound it was dubbed from, and reserves
    the top of that scale for the original.
    """

    return stream.get("language_preference") == ORIGINAL_LANGUAGE_PREFERENCE


def _get_audio_fmt_name(stream) -> str:
    """Name an audio-only stream by what tells it apart from the others.

    The format id yt-dlp falls back to is an internal number that means
    nothing outside the site it came from.
    """

    fmt_name = "Audio"

    language = stream.get("language")
    if language and language != "none":
        fmt_name = f"{fmt_name} ({language})"

    codec_info = _get_codec_info(stream)
    if codec_info:
        fmt_name = f"{fmt_name} [{codec_info}]"

    return fmt_name


def _fix_bitrate_units(streams) -> None:
    """Bring a ladder's bitrates back to the kbit/s that yt-dlp promises.

    Rewrites the format dicts in place, since every consumer shares them.
    """

    if not _is_bitrate_in_bits(streams):
        return

    for fmt in streams:
        for key in BITRATE_KEYS:
            if fmt.get(key):
                fmt[key] = fmt[key] / 1000


def _is_bitrate_in_bits(streams) -> bool:
    """Whether a ladder states its bitrates in bits/s instead of kbit/s.

    A known file size pins the bitrate against the duration it implies. No
    format in a quality ladder is a fraction of a second long, so a reading
    that says otherwise is off by the factor that separates the two units.
    """

    implied_durations = [
        fmt["filesize"] * 8 / (fmt["tbr"] * 1000)
        for fmt in streams
        if fmt.get("filesize") and fmt.get("tbr")
    ]

    if not implied_durations:
        return False

    return all(duration < MIN_PLAUSIBLE_DURATION for duration in implied_durations)


def _get_video_codec(stream) -> str | None:
    """The codec family, as both yt-dlp and VLC spell it (avc1, av01, vp09)."""

    vcodec = stream.get("vcodec")

    if vcodec in {None, "none"}:
        return None

    return vcodec.split(".")[0]


def _get_codec_info(stream):
    codec = ""

    if stream.get("vcodec") not in {None, "none"}:
        codec = _get_video_codec(stream)
    elif stream.get("acodec") not in {None, "none"}:
        codec = stream.get("acodec").split(".")[0]

    if stream.get("tbr") not in {None, 0}:
        tbr = int(stream.get("tbr"))
        codec += f" {tbr}kbps"

    return codec.strip()
