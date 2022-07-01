from typing import List

from streamlink.stream.hls_playlist import M3U8, ByteRange, Segment

LIVESTREAM_EDGE = 16


def m3u8_to_str(hls_playlist: M3U8):
    res = ["#EXTM3U"]
    res += [f"#EXT-X-VERSION:{hls_playlist.version}"]
    res += [f"#EXT-X-TARGETDURATION:{hls_playlist.target_duration}"]
    if hls_playlist.playlist_type:
        res += [f"#EXT-X-PLAYLIST-TYPE:{hls_playlist.playlist_type}"]
    res += [f"#EXT-X-MEDIA-SEQUENCE:{hls_playlist.media_sequence}"]

    # grab only the edge if it's a livestream
    if hls_playlist.media_sequence:
        segments = hls_playlist.segments[-LIVESTREAM_EDGE:]
    else:
        segments = hls_playlist.segments

    res += sum([_segment_to_str(s) for s in segments], [])

    if hls_playlist.is_endlist:
        res += ["#EXT-X-ENDLIST"]

    return "\n".join(res)


def _segment_to_str(segment: Segment) -> List[str]:
    res = []

    if segment.date:
        timestamp = segment.date.isoformat(timespec="seconds")
        timestamp = timestamp.replace("+00:00", "Z")
        res += [f"#EXT-X-PROGRAM-DATE-TIME:{timestamp}"]
    if segment.discontinuity:
        res += ["#EXT-X-DISCONTINUITY"]
    if segment.byterange:
        res += ["#EXT-X-BYTERANGE:{0}".format(_byterange_to_str(segment.byterange))]
    if segment.map:
        res += [
            '#EXT-X-MAP:URI="{0}"{1}'.format(
                segment.map.uri,
                ',BYTERANGE="{0}"'.format(_byterange_to_str(segment.map.byterange))
                if segment.map.byterange
                else "",
            )
        ]

    res += [
        "#EXTINF:{0},{1}".format(
            segment.duration, segment.title if segment.title else ""
        )
    ]

    res += [segment.uri]

    return res


def _byterange_to_str(byterange: ByteRange) -> str:
    offset_txt = f"@{byterange.offset}" if byterange.offset else ""
    return f"{byterange.range}{offset_txt}"
