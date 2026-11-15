import math
from collections.abc import Sequence
from dataclasses import dataclass

from streamlink.stream.hls import M3U8, ByteRange, HLSSegment, Key, Map

from gridplayer.models.stream import StreamFragment

LIVESTREAM_EDGE = 16


def m3u8_to_str(hls_playlist: M3U8):
    # grab only the edge if it's a livestream
    if _is_live_window(hls_playlist):
        segments = hls_playlist.segments[-LIVESTREAM_EDGE:]
    else:
        segments = hls_playlist.segments

    # the edge starts further along than the window did, and a segment
    # encrypted without an IV of its own is decrypted with its number
    media_sequence = segments[0].num if segments else hls_playlist.media_sequence

    res = ["#EXTM3U"]
    if hls_playlist.version:
        res += [f"#EXT-X-VERSION:{hls_playlist.version}"]
    if hls_playlist.playlist_type:
        res += [f"#EXT-X-PLAYLIST-TYPE:{hls_playlist.playlist_type}"]
    if media_sequence:
        res += [f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}"]
    res += [f"#EXT-X-TARGETDURATION:{hls_playlist.targetduration}"]

    s_map = None
    s_key = None
    for s in segments:
        # the key in effect where the map was declared is the one it is
        # encrypted with, which need not be the segment's own
        if s.map is not None and s.map != s_map:
            s_map = s.map

            res += _key_change(s_key, s.map.key)
            s_key = _key_in_effect(s.map.key)

            res += [_map_to_str(s.map)]

        res += _key_change(s_key, s.key)
        s_key = _key_in_effect(s.key)

        res += _segment_to_str(s)

    if hls_playlist.is_endlist:
        res += ["#EXT-X-ENDLIST"]

    return "\n".join(res)


def _is_live_window(hls_playlist: M3U8) -> bool:
    """Whether a playlist is a window sliding along a live stream.

    A window has moved on from its first segment, so it numbers them from
    somewhere past zero. That alone does not make it live: some hosts
    number a finished video from one, and cutting such a playlist down
    to its edge leaves only the last minute of it to play.
    """

    is_finished = hls_playlist.is_endlist or hls_playlist.playlist_type == "VOD"

    return bool(hls_playlist.media_sequence) and not is_finished


def _key_in_effect(key: Key | None) -> Key | None:
    """The key segments are decrypted with, or nothing when they are not."""

    if key is None or key.method == "NONE":
        return None

    return key


def _key_change(in_effect: Key | None, key: Key | None) -> list[str]:
    """What has to be said for `key` to take over from the one in effect.

    A key stays in effect for every segment after it, so it is only
    written out where it changes, and a playlist that stops encrypting
    part way through has to say so.
    """

    key = _key_in_effect(key)

    if key == in_effect:
        return []

    if key is None:
        return ["#EXT-X-KEY:METHOD=NONE"]

    return [_key_to_str(key)]


def _key_to_str(key: Key) -> str:
    attrs = [f"METHOD={key.method}"]

    if key.uri:
        attrs += [f'URI="{key.uri}"']
    if key.iv is not None:
        attrs += [f"IV=0x{key.iv.hex().upper()}"]
    if key.key_format:
        attrs += [f'KEYFORMAT="{key.key_format}"']
    if key.key_format_versions:
        attrs += [f'KEYFORMATVERSIONS="{key.key_format_versions}"']

    return "#EXT-X-KEY:{}".format(",".join(attrs))


def _map_to_str(segment_map: Map) -> str:
    byterange = (
        f',BYTERANGE="{_byterange_to_str(segment_map.byterange)}"'
        if segment_map.byterange
        else ""
    )

    return f'#EXT-X-MAP:URI="{segment_map.uri}"{byterange}'


def _segment_to_str(segment: HLSSegment) -> list[str]:
    res = []

    if segment.date:
        timestamp = segment.date.isoformat(timespec="seconds")
        timestamp = timestamp.replace("+00:00", "Z")
        res += [f"#EXT-X-PROGRAM-DATE-TIME:{timestamp}"]
    if segment.discontinuity:
        res += ["#EXT-X-DISCONTINUITY"]
    if segment.byterange:
        res += [f"#EXT-X-BYTERANGE:{_byterange_to_str(segment.byterange)}"]

    res += [
        "#EXTINF:{},{}".format(segment.duration, segment.title if segment.title else "")
    ]

    res += [segment.uri]

    return res


def _byterange_to_str(byterange: ByteRange) -> str:
    offset_txt = f"@{byterange.offset}" if byterange.offset else ""
    return f"{byterange.range}{offset_txt}"


def build_media_playlist(
    segments: Sequence[StreamFragment],
    init_segment: StreamFragment | None = None,
) -> str:
    """Render a VOD media playlist out of plain segment references.

    Used to expose non-HLS sources (DASH representations, single fMP4 files)
    to VLC, which only knows how to pair separate audio & video through HLS.
    """

    target_duration = max((s.duration for s in segments), default=0)

    res = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        f"#EXT-X-TARGETDURATION:{math.ceil(target_duration)}",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]

    if init_segment is not None:
        byterange = (
            f',BYTERANGE="{init_segment.byterange}"' if init_segment.byterange else ""
        )
        res += [f'#EXT-X-MAP:URI="{init_segment.url}"{byterange}']

    for segment in segments:
        res += [f"#EXTINF:{segment.duration:.3f},"]
        if segment.byterange:
            res += [f"#EXT-X-BYTERANGE:{segment.byterange}"]
        res += [segment.url]

    res += ["#EXT-X-ENDLIST"]

    return "\n".join(res)


@dataclass(frozen=True)
class LiveEntry:
    url: str
    duration: float
    # "length@offset", where it's a piece of a file
    byterange: str | None = None
    init_url: str | None = None
    init_byterange: str | None = None
    # its times start anew
    is_discontinuity: bool = False


def build_live_media_playlist(
    entries: Sequence[LiveEntry], first_sequence: int, is_over: bool = False
) -> str:
    """A live media playlist: what's out now, to be asked for again; the first
    numbered as it was the last time it was listed. An init segment is said
    again wherever it changes."""

    target_duration = max((entry.duration for entry in entries), default=1)

    res = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        f"#EXT-X-TARGETDURATION:{math.ceil(target_duration)}",
        f"#EXT-X-MEDIA-SEQUENCE:{first_sequence}",
    ]

    init = None

    for entry in entries:
        if entry.is_discontinuity:
            res += ["#EXT-X-DISCONTINUITY"]

        if (
            entry.init_url is not None
            and (entry.init_url, entry.init_byterange) != init
        ):
            init = (entry.init_url, entry.init_byterange)
            byterange = (
                f',BYTERANGE="{entry.init_byterange}"' if entry.init_byterange else ""
            )
            res += [f'#EXT-X-MAP:URI="{entry.init_url}"{byterange}']

        res += [f"#EXTINF:{entry.duration:.3f},"]

        if entry.byterange:
            res += [f"#EXT-X-BYTERANGE:{entry.byterange}"]

        res += [entry.url]

    if is_over:
        res += ["#EXT-X-ENDLIST"]

    return "\n".join(res)


def build_rendition_master_playlist(
    video_url: str | None, sounds: Sequence[tuple[str, str, bool]]
) -> str:
    """A master playlist of the picture and its sound in every language there
    is, (url, language, is_default) each, so that the player can switch; or of
    the sound alone, the default one."""

    if video_url is None:
        default = next((url for url, _, is_default in sounds if is_default), None)
        return build_variant_playlist(default or sounds[0][0])

    if not sounds:
        return build_variant_playlist(video_url)

    res = ["#EXTM3U", "#EXT-X-INDEPENDENT-SEGMENTS"]

    for url, language, is_default in sounds:
        name = _escape_attr(language or "Audio")
        spoken = f'LANGUAGE="{_escape_attr(language)}",' if language else ""
        default = "YES" if is_default else "NO"
        res += [
            (
                '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
                f'NAME="{name}",{spoken}'
                f'DEFAULT={default},AUTOSELECT=YES,URI="{url}"'
            )
        ]

    res += ['#EXT-X-STREAM-INF:BANDWIDTH=0,AUDIO="audio"', video_url]

    return "\n".join(res)


def build_variant_playlist(video_url: str) -> str:
    """A master playlist of one variant and nothing else."""

    return f"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=0\n{video_url}"


def build_master_playlist(
    video_url: str,
    audio_url: str,
    audio_name: str,
    audio_language: str | None = None,
) -> str:
    """Render a master playlist pairing a video-only rendition with audio.

    The language rides along so that VLC reports it on the track: once
    the playlist is all the player can see, it is the only thing a
    preferred-language setting has left to match against.
    """

    language = f'LANGUAGE="{_escape_attr(audio_language)}",' if audio_language else ""

    return "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-INDEPENDENT-SEGMENTS",
            (
                '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
                f'NAME="{_escape_attr(audio_name)}",{language}'
                f'DEFAULT=YES,URI="{audio_url}"'
            ),
            '#EXT-X-STREAM-INF:BANDWIDTH=0,AUDIO="audio"',
            video_url,
        ]
    )


def _escape_attr(value: str) -> str:
    return value.replace('"', "'")
