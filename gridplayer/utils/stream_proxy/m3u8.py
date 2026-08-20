from streamlink.stream.hls import M3U8, ByteRange, HLSSegment

LIVESTREAM_EDGE = 16


def m3u8_to_str(hls_playlist: M3U8):
    res = ["#EXTM3U"]
    res += [f"#EXT-X-VERSION:{hls_playlist.version}"]
    if hls_playlist.playlist_type:
        res += [f"#EXT-X-PLAYLIST-TYPE:{hls_playlist.playlist_type}"]
    if hls_playlist.media_sequence:
        res += [f"#EXT-X-MEDIA-SEQUENCE:{hls_playlist.media_sequence}"]
    res += [f"#EXT-X-TARGETDURATION:{hls_playlist.targetduration}"]

    # grab only the edge if it's a livestream
    if hls_playlist.media_sequence:
        segments = hls_playlist.segments[-LIVESTREAM_EDGE:]
    else:
        segments = hls_playlist.segments

    s_map = None
    for s in segments:
        if s.map is not None and s.map != s_map:
            s_map = s.map

            res += _segment_to_str(s, add_map=True)
        else:
            res += _segment_to_str(s)

    if hls_playlist.is_endlist:
        res += ["#EXT-X-ENDLIST"]

    return "\n".join(res)


def _segment_to_str(segment: HLSSegment, add_map=False) -> list[str]:
    res = []

    if segment.date:
        timestamp = segment.date.isoformat(timespec="seconds")
        timestamp = timestamp.replace("+00:00", "Z")
        res += [f"#EXT-X-PROGRAM-DATE-TIME:{timestamp}"]
    if segment.discontinuity:
        res += ["#EXT-X-DISCONTINUITY"]
    if segment.byterange:
        res += [f"#EXT-X-BYTERANGE:{_byterange_to_str(segment.byterange)}"]
    if segment.map and add_map:
        res += [
            '#EXT-X-MAP:URI="{}"{}'.format(
                segment.map.uri,
                f',BYTERANGE="{_byterange_to_str(segment.map.byterange)}"'
                if segment.map.byterange
                else "",
            )
        ]

    res += [
        "#EXTINF:{},{}".format(segment.duration, segment.title if segment.title else "")
    ]

    res += [segment.uri]

    return res


def _byterange_to_str(byterange: ByteRange) -> str:
    offset_txt = f"@{byterange.offset}" if byterange.offset else ""
    return f"{byterange.range}{offset_txt}"
