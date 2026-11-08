"""A stream with its sound apart on MPV: it's opened as two, and to the menus its sound is
the video's own. Behind one demuxer every seek on a YouTube video took 5.6-6 s, and as two
0.25-0.8 s. A stream from this machine takes under a second either way, so that's not
something this can tell: only that it's opened as two, and that seeks and sync hold up.

A file in fragments, as YouTube serves them, is opened as that file. As the playlist made of
it for VLC, on 0.40 with FFmpeg 7.1, most seeks past what's been read went back to the start.
"""

from gridplayer.models.stream import (
    STREAM_QUALITY_BEST,
    HashableDict,
    Stream,
    Streams,
    StreamSessionOpts,
)

SETTINGS = {
    "player/video_driver": "mpv_hw",
    # Streamlink takes only the default audio of an HLS stream; yt-dlp
    # reads each rendition and its language
    "streaming/resolver_priority": "yt_dlp",
}


def scenario(d):
    d.open(f"{d.serve(d.media.dubs)}/master.m3u8")
    cell = d.wait_for_cell("master.m3u8")

    media = cell.video_driver.media
    player = cell.video_driver.video_driver._player

    d.check("the sound was opened apart", player.media_input.stream_audio is not None)
    d.check("as the video's own", media.external_audio_ids == (), media.audio_tracks)
    d.check("one track of sound", len(media.audio_tracks) == 1, media.audio_tracks)
    d.check(
        "named as the stream names it",
        media.cur_audio_track.description == player.media_input.stream_audio.title,
        media.cur_audio_track,
    )
    d.check(
        "in its language",
        media.cur_audio_track.language == player.media_input.stream_audio.language,
        media.cur_audio_track,
    )
    d.check("no retries for a seek", not cell.stream.is_adaptive)

    d.wait_until(lambda: player.mpv.audio_params is not None, "the sound is playing")

    for target in (20000, 5000, 15000):
        cell.seek(target)
        d.wait_until(
            lambda t=target: t + 500 < cell.time < t + 5000, f"plays on from {target}"
        )

    d.wait_until(lambda: player.mpv.avsync is not None, "there's sound to go by")
    d.wait(1)
    d.check(
        "picture and sound together", abs(player.mpv.avsync) < 0.1, player.mpv.avsync
    )

    _files_in_fragments(d, cell)

    d.note("end", cell)


def _files_in_fragments(d, cell):
    """Given to the cell as a resolver gives them: no link of a test server's says it's this."""

    base = d.serve_with_ranges(d.media.fragmented)
    session = StreamSessionOpts(
        service="here", session_headers=HashableDict({"User-Agent": "here"})
    )
    length_s = d.media.FRAGMENTED_LENGTH_S

    cell.streams = Streams(
        {
            "best": Stream(
                url=f"{base}/video.mp4",
                protocol="http_hls",
                session=session,
                duration=length_s,
                audio_tracks=Streams(
                    {
                        "Sound": Stream(
                            url=f"{base}/audio.mp4",
                            protocol="http_hls",
                            session=session,
                            duration=length_s,
                            is_audio_only=True,
                        )
                    }
                ),
            )
        }
    )
    cell.reset(is_link_kept=True)
    cell.stream.load_quality(STREAM_QUALITY_BEST)

    d.wait_until(
        lambda: cell.is_playable and cell.video_driver.length > 60000, "the file plays"
    )

    player = cell.video_driver.video_driver._player

    d.check(
        "as the file it is", player.mpv.file_format != "hls", player.mpv.file_format
    )
    d.check("with its sound", cell.video_driver.media.cur_audio_track is not None)
    cache_seeks = player.mpv.demuxer_seekable_cache
    d.check("not sought in through its cache", cache_seeks is False, cache_seeks)

    # past what's been read, and back again
    for target in (200000, 250000, 40000, 280000, 80000, 10000):
        cell.seek(target)
        d.wait_until(
            lambda t=target: t + 500 < cell.time < t + 15000, f"plays on from {target}"
        )
        # a stream of another shape has a good 0.5 s or more of this, and takes 6 s over it
        d.check(
            f"picture and sound together at {target}",
            abs(player.mpv.avsync) < 0.1,
            player.mpv.avsync,
        )
