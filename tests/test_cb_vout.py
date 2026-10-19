from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import gridplayer.vlc_player.player_base as player_base_mod
from gridplayer.params.static import (
    VideoAnchor,
    VideoCellViewMode,
    VideoCrop,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.vlc_player.libvlc import vlc
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import Media, MediaInput, VideoTrack


class _MinimalPlayer(VlcPlayerBase):
    """Concrete VlcPlayerBase with the 9 abstractmethods stubbed as no-ops."""

    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error, vlc_lines=()): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def notify_snapshot_taken(self, snapshot_path): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class _RecordingMediaPlayer:
    """Fake libvlc media player recording the three view setter calls."""

    def __init__(self):
        self.calls = []

    def video_get_size(self, num=0):
        return (640, 360)

    def video_set_aspect_ratio(self, value):
        self.calls.append(("aspect_ratio", value))

    def video_set_crop_geometry(self, value):
        self.calls.append(("crop_geometry", value))

    def video_set_scale(self, value):
        self.calls.append(("scale", value))


def _make_player(cell_view_mode=VideoCellViewMode.FILL, is_audio_only=False):
    player = _MinimalPlayer(vlc_instance=None)

    media_player = _RecordingMediaPlayer()
    player._media_player = media_player

    media = Mock()
    media.is_audio_only = is_audio_only
    player.media = media

    media_input = MediaInput(
        uri="file:///video.mp4",
        is_live=False,
        is_audio_only=is_audio_only,
        size=(640, 360),
        video=Mock(),
    )
    media_input.video.cell_view_mode = cell_view_mode
    media_input.video.scale = 1.0
    media_input.video.crop = VideoCrop(0, 0, 0, 0)
    media_input.video.anchor = VideoAnchor.CENTER
    media_input.video.shift = VideoShift(0, 0)
    media_input.video.transform = None
    media_input.video.aspect_ratio = ""
    media_input.video.crop_ratio = ""
    player.media_input = media_input

    return player, media_player


def test_cb_stopped_unexpected_non_live_errors():
    player, _ = _make_player()
    player.is_video_initialized = True
    player.media_input.is_live = False
    errors = []
    player.notify_error = lambda error, vlc_lines: errors.append(error)
    player.notify_playback_status_changed = Mock()

    player.cb_stopped(None)

    assert errors == ["Video stopped unexpectedly"]
    player.notify_playback_status_changed.assert_not_called()


def test_cb_vout_defers_and_does_not_reenter_libvlc(monkeypatch):
    """cb_vout schedules the re-apply via the seam and issues NO libvlc setters."""
    monkeypatch.setattr(player_base_mod.env, "IS_MACOS", True)

    player, media_player = _make_player()

    scheduler = Mock()
    player._schedule_view_reapply = scheduler

    player.cb_vout(None)

    assert scheduler.call_count == 1
    assert media_player.calls == []


def test_default_seam_routes_to_apply_media_input_view(monkeypatch):
    """The base _schedule_view_reapply applies directly (issues the setters)."""
    monkeypatch.setattr(player_base_mod.env, "IS_MACOS", True)

    player, media_player = _make_player()

    player._schedule_view_reapply()

    recorded = {name for name, _ in media_player.calls}
    assert recorded == {"aspect_ratio", "crop_geometry", "scale"}


def test_adjust_view_crop_stretch_compensates_override():
    """Pixel crop + Stretch: VLC derives the override SAR from the pre-crop
    dims, so the override must be compensated for the cropped region."""
    player, media_player = _make_player(cell_view_mode=VideoCellViewMode.STRETCH)

    player.adjust_view(
        size=(640, 360),
        view=ViewParams(VideoCellViewMode.STRETCH, 1.0, VideoCrop(160, 0, 160, 0)),
    )

    # Region 320x360 (8:9) must display as 16:9 -> override 32:9.
    assert media_player.calls == [
        ("aspect_ratio", "32:9"),
        ("crop_geometry", "+160+0+160+0"),
        ("scale", 0),
    ]


def test_adjust_view_crop_fill_extends_borders():
    """Pixel crop + Fill: the borders are extended until the visible region
    matches the pane ratio, so VLC's auto-fit fills the pane exactly."""
    player, media_player = _make_player(cell_view_mode=VideoCellViewMode.FILL)

    player.adjust_view(
        size=(640, 360),
        view=ViewParams(VideoCellViewMode.FILL, 1.0, VideoCrop(160, 0, 160, 0)),
    )

    # Region 320x360 -> crop down to 320x180 (16:9) -> 90 top/bottom.
    assert media_player.calls == [
        ("aspect_ratio", "16:9"),
        ("crop_geometry", "+160+90+160+90"),
        ("scale", 0),
    ]


def test_adjust_view_persists_crop_for_vout_reapply():
    """Live unpause stop/play recreates the vout; cb_vout re-applies from
    media_input, so crop/aspect/scale must be written back on each adjust."""
    player, media_player = _make_player(cell_view_mode=VideoCellViewMode.FILL)
    crop = VideoCrop(160, 0, 160, 0)

    player.adjust_view(
        size=(640, 360),
        view=ViewParams(VideoCellViewMode.FILL, 1.0, crop),
    )

    assert player.media_input.video.crop == crop
    assert player.media_input.video.cell_view_mode is VideoCellViewMode.FILL

    media_player.calls.clear()
    player._apply_media_input_view()

    assert media_player.calls == [
        ("aspect_ratio", "16:9"),
        ("crop_geometry", "+160+90+160+90"),
        ("scale", 0),
    ]


def test_apply_media_input_view_uses_cached_size_when_vout_size_missing():
    """After live stop/play, cb_vout can run while video_get_size is still
    0x0. Fill + crop must not fall back to letterbox (Fit)."""
    player, media_player = _make_player(cell_view_mode=VideoCellViewMode.FILL)
    crop = VideoCrop(160, 0, 160, 0)

    player.adjust_view(
        size=(640, 360),
        view=ViewParams(VideoCellViewMode.FILL, 1.0, crop),
    )

    media_player.video_get_size = lambda num=0: (0, 0)
    media_player.calls.clear()

    player._apply_media_input_view()

    assert media_player.calls == [
        ("aspect_ratio", "16:9"),
        ("crop_geometry", "+160+90+160+90"),
        ("scale", 0),
    ]


def test_adjust_view_fills_missing_track_dimensions():
    player, _ = _make_player()
    player.notify_video_dimensions = Mock()
    player.media = Media(
        length=-1,
        video_tracks={
            1: VideoTrack(
                video_dimensions=(0, 0),
                fps=None,
                codec="H264",
                bitrate=0,
                language=None,
                description=None,
            )
        },
        audio_tracks={},
        cur_video_track_id=1,
    )

    player.adjust_view(
        size=(640, 360),
        view=ViewParams(VideoCellViewMode.FILL, 1.0, VideoCrop(0, 0, 0, 0)),
    )

    assert player.media.video_tracks[1].video_dimensions == (640, 360)
    player.notify_video_dimensions.assert_called_once_with(640, 360, None)


class _Tracks:
    """libVLC's track list, read afresh: how wide the pixels are, once said."""

    def __init__(self, sar=(0, 0)):
        self.sar = sar
        self.reads = 0

    def tracks_get(self):
        self.reads += 1
        sar_num, sar_den = self.sar
        content = SimpleNamespace(sar_num=sar_num, sar_den=sar_den)

        return iter(
            [
                SimpleNamespace(
                    id=1,
                    type=vlc.TrackType.video,
                    u=SimpleNamespace(video=SimpleNamespace(contents=content)),
                )
            ]
        )


def _stream_player(tracks: _Tracks):
    """A stream playing 640x360 that has not said how wide its pixels are."""

    player, media_player = _make_player(cell_view_mode=VideoCellViewMode.FIT)
    player.notify_video_dimensions = Mock()
    player.media = Media(
        length=-1,
        video_tracks={
            1: VideoTrack(
                video_dimensions=(640, 360),
                fps=None,
                codec="H264",
                bitrate=0,
                language=None,
                description=None,
            )
        },
        audio_tracks={},
        cur_video_track_id=1,
    )
    player._tracks_manager = SimpleNamespace(current_video_track_id=1)
    player._media_input_vlc = tracks

    return player, media_player


def _none_view():
    return ViewParams(VideoCellViewMode.FIT, 1.0, VideoCrop(0, 0, 0, 0))


def test_adjust_view_reads_how_wide_a_streams_pixels_are():
    """An MPEG-TS stream says only once decoded: 640x360 of pixels 3:2 is
    960x360, which fills 960x360."""

    tracks = _Tracks()
    player, media_player = _stream_player(tracks)

    player.adjust_view(size=(960, 360), view=_none_view())

    assert player._is_view_unsized

    tracks.sar = (3, 2)
    media_player.calls.clear()
    player.adjust_view(size=(960, 360), view=_none_view())

    assert player.media.video_tracks[1].sar == (3, 2)
    player.notify_video_dimensions.assert_called_once_with(640, 360, (3, 2))
    assert ("aspect_ratio", "8:3") in media_player.calls
    assert not player._is_view_unsized


def test_a_player_the_widget_draws_for_keeps_asking_too():
    """The software drivers place the picture in the widget, their player's
    _apply_view doing nothing: it is still asked again as time comes in."""

    tracks = _Tracks()
    player, _ = _stream_player(tracks)
    player._apply_view = lambda size, view: None
    player._schedule_view_reapply = Mock()
    player._schedule_playback_check = Mock()

    player.adjust_view(size=(960, 360), view=_none_view())
    player.cb_time_changed(SimpleNamespace(u=SimpleNamespace(new_time=0)))

    player._schedule_view_reapply.assert_called_once()

    tracks.sar = (3, 2)
    player.adjust_view(size=(960, 360), view=_none_view())

    player.notify_video_dimensions.assert_called_once_with(640, 360, (3, 2))
    assert not player._is_view_unsized


def test_a_video_that_never_says_is_asked_only_so_often():
    tracks = _Tracks()
    player, _ = _stream_player(tracks)

    for _ in range(player_base_mod.SAR_READS + 5):
        player.adjust_view(size=(640, 360), view=_none_view())

    assert tracks.reads == player_base_mod.SAR_READS
    assert not player._is_view_unsized
    player.notify_video_dimensions.assert_not_called()


def test_adjust_view_crop_fit_letterboxes_user_region():
    """Pixel crop + Fit: keep the user borders and native aspect so the
    visible region is letterboxed in the pane."""
    player, media_player = _make_player(cell_view_mode=VideoCellViewMode.FIT)

    player.adjust_view(
        size=(640, 360),
        view=ViewParams(VideoCellViewMode.FIT, 1.0, VideoCrop(160, 0, 160, 0)),
    )

    # Region 320x360 shown in its own shape, letterboxed
    assert media_player.calls == [
        ("aspect_ratio", "16:9"),
        ("crop_geometry", "+160+0+160+0"),
        ("scale", 0),
    ]


def test_adjust_view_puts_the_zoom_in_the_crop():
    """VLC's own zoom only ever zooms about the middle, and its snapshot
    would not see it; the crop does both."""
    player, media_player = _make_player()

    player.adjust_view(
        size=(640, 360),
        view=ViewParams(VideoCellViewMode.FILL, 2.0, VideoCrop(0, 0, 0, 0)),
    )

    assert media_player.calls == [
        ("aspect_ratio", "16:9"),
        ("crop_geometry", "+160+90+160+90"),
        ("scale", 0),
    ]


def test_adjust_view_crops_a_rotated_frame_at_its_own_size():
    """VLC hands a rotated frame over at its unrotated size, the turned
    picture squeezed into it, and crops it there."""
    player, media_player = _make_player()
    player.media_input.video.transform = VideoTransform.ROTATE_90

    player.adjust_view(
        size=(360, 640),
        view=ViewParams(VideoCellViewMode.FILL, 1.0, VideoCrop(160, 0, 160, 0)),
    )

    # 320x360 frame pixels left are 180x640 on screen, so a 9:16 pane
    # takes the middle half of them down
    assert media_player.calls == [
        ("aspect_ratio", "9:16"),
        ("crop_geometry", "+160+90+160+90"),
        ("scale", 0),
    ]


def test_adjust_view_keeps_the_position_for_vout_reapply():
    """A live stream's vout comes back from media_input, anchor and all."""
    player, media_player = _make_player()
    view = ViewParams(
        VideoCellViewMode.FILL, 2.0, VideoCrop(0, 0, 0, 0), VideoAnchor.TOP_LEFT
    )

    player.adjust_view(size=(640, 360), view=view)
    media_player.calls.clear()
    player._apply_media_input_view()

    assert player.media_input.video.anchor is VideoAnchor.TOP_LEFT
    assert media_player.calls == [
        ("aspect_ratio", "16:9"),
        ("crop_geometry", "+0+0+320+180"),
        ("scale", 0),
    ]


@pytest.mark.parametrize("crop", [VideoCrop(0, 0, 0, 0), VideoCrop(60, 0, 60, 0)])
def test_adjust_view_has_vlc_draw_all_of_a_picture_it_turns(crop):
    """VLC crops a picture it turns wrong: it is told to draw all of it,
    in the shape it is shown in but the way it is stored, and not to crop
    it, even where the user does."""
    player, media_player = _make_player()
    player._tracks_manager = Mock(current_video_track_id=1)
    player.media = Media(
        length=-1,
        video_tracks={
            1: VideoTrack(
                video_dimensions=(640, 360),
                fps=None,
                codec="H264",
                bitrate=0,
                language=None,
                description=None,
                orientation=VideoTransform.ROTATE_90,
            )
        },
        audio_tracks={},
        cur_video_track_id=1,
    )

    player.adjust_view(
        size=(400, 500),
        view=ViewParams(VideoCellViewMode.FILL, 2.0, crop),
    )

    # on its side 360x640, covering 400x500 at 400x711, zoomed to 800x1422;
    # cropped, all of it is still drawn, just bigger
    assert media_player.calls == [
        ("aspect_ratio", "711:400"),
        ("crop_geometry", "+0+0+0+0"),
        ("scale", 0),
    ]


def test_cb_vout_noop_when_audio_only(monkeypatch):
    """macOS but audio-only media: cb_vout returns early, no scheduling."""
    monkeypatch.setattr(player_base_mod.env, "IS_MACOS", True)

    player, _ = _make_player(is_audio_only=True)

    scheduler = Mock()
    player._schedule_view_reapply = scheduler

    player.cb_vout(None)

    assert scheduler.call_count == 0


def _time_event(new_time):
    return SimpleNamespace(u=SimpleNamespace(new_time=new_time))


def test_time_applies_a_view_worked_out_without_a_frame_size_again():
    """A stream with no frame size of its own: VLC finds it only after its
    video output is up, when the view is applied. Applied then, a Fill view
    is the whole frame with bars, until something applies it again."""
    player, media_player = _make_player()
    player.media_input.is_live = True
    view = ViewParams(VideoCellViewMode.FILL, 1.0, VideoCrop(0, 0, 0, 0))

    media_player.video_get_size = lambda num=0: (0, 0)
    player.adjust_view(size=(640, 200), view=view)

    assert ("aspect_ratio", "0:0") in media_player.calls

    # still not there at the first time event, at 0
    media_player.calls.clear()
    player.cb_time_changed(_time_event(0))

    assert ("aspect_ratio", "0:0") in media_player.calls

    media_player.video_get_size = lambda num=0: (640, 360)
    media_player.calls.clear()
    player.cb_time_changed(_time_event(0))

    assert media_player.calls == [
        ("aspect_ratio", "16:9"),
        ("crop_geometry", "+0+80+0+80"),
        ("scale", 0),
    ]

    # and left alone after that
    media_player.calls.clear()
    player.cb_time_changed(_time_event(0))

    assert media_player.calls == []


def test_time_leaves_a_view_worked_out_with_a_frame_size_alone():
    player, _ = _make_player()
    player.media_input.is_live = True
    scheduler = Mock()
    player._schedule_view_reapply = scheduler

    player.adjust_view(
        size=(640, 200),
        view=ViewParams(VideoCellViewMode.FILL, 1.0, VideoCrop(0, 0, 0, 0)),
    )
    player.cb_time_changed(_time_event(0))

    scheduler.assert_not_called()


class _CountingMedia:
    """The media as libVLC counts it: how many pictures it has put on screen."""

    def __init__(self, displayed, is_counted=True):
        self.displayed = displayed
        self.is_counted = is_counted

    def get_stats(self, stats):
        stats.displayed_pictures = self.displayed
        return self.is_counted


def _player_counting(displayed, **kwargs):
    player, _ = _make_player(**kwargs)
    player.media_input.is_live = True
    player._media_input_vlc = _CountingMedia(displayed)
    player.notify_playback_started = Mock()
    return player


def test_playback_told_once_vlc_has_a_second_picture_on_screen():
    """VLC keeps a stream's first picture up, frozen, until playback proper
    starts; the one after it is playback under way."""
    player = _player_counting(displayed=1)

    player.cb_time_changed(_time_event(0))
    player.cb_time_changed(_time_event(260))

    player.notify_playback_started.assert_not_called()

    player._media_input_vlc.displayed = 3
    player.cb_time_changed(_time_event(540))
    player.cb_time_changed(_time_event(820))

    player.notify_playback_started.assert_called_once()


def test_the_view_is_told_vlc_again_once_playback_is_under_way():
    """VLC can set up a turned picture's output after the view was last
    applied, leaving out the shape it was told."""
    player = _player_counting(displayed=3)
    player._apply_media_input_view = Mock()

    player.cb_time_changed(_time_event(260))
    player.cb_time_changed(_time_event(540))

    player._apply_media_input_view.assert_called_once()


def test_playback_not_told_without_counts_to_go_by():
    player = _player_counting(displayed=5)
    player._media_input_vlc.is_counted = False

    player.cb_time_changed(_time_event(260))

    player.notify_playback_started.assert_not_called()


def test_playback_not_looked_for_with_audio_only():
    player = _player_counting(displayed=5, is_audio_only=True)

    player.cb_time_changed(_time_event(260))

    player.notify_playback_started.assert_not_called()


def test_vlc_counts_the_pictures_it_shows(tmp_path):
    """The counts are the only sign a stream VLC froze on its first picture
    has started playing, and "--no-stats" stops VLC keeping them."""
    from PyQt5.QtCore import QSettings

    from gridplayer.settings import Settings
    from gridplayer.vlc_player.instance import InstanceVLC

    settings = Settings()
    real_settings = settings.settings
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)
    try:
        instance = InstanceVLC(0, [])
        instance._logger = Mock()

        assert "--no-stats" not in instance.init_options
    finally:
        settings.settings = real_settings


def _view_shaped(aspect_ratio):
    return ViewParams(VideoCellViewMode.FIT, 1.0, VideoCrop(0, 0, 0, 0))._replace(
        aspect_ratio=aspect_ratio
    )


def test_adjust_view_shows_the_aspect_ratio_picked():
    """640x360 shown 4:3 is 480x360 in a 960x360 pane."""

    player, media_player = _stream_player(_Tracks(sar=(1, 1)))

    player.adjust_view(size=(960, 360), view=_view_shaped("4:3"))

    assert ("aspect_ratio", "4:3") in media_player.calls


def test_the_aspect_ratio_picked_is_the_shape_a_turned_file_is_shown_in():
    """A phone file stored 640x360 is shown 360x640, and picked 16:9 is
    shown 16:9 all the same: VLC, which turns it as it places it, is told
    the stored frame's shape, 9:16."""

    player, media_player = _stream_player(_Tracks(sar=(1, 1)))
    track = player.media.video_tracks[1]
    track.orientation = VideoTransform.ROTATE_90
    track.sar = (1, 1)

    player.adjust_view(size=(640, 640), view=_view_shaped(""))
    assert ("aspect_ratio", "16:9") in media_player.calls

    media_player.calls.clear()
    player.adjust_view(size=(640, 640), view=_view_shaped("16:9"))
    assert ("aspect_ratio", "9:16") in media_player.calls


def test_adjust_view_keeps_the_aspect_ratio_for_a_restart():
    player, _ = _make_player()

    player.adjust_view(size=(640, 360), view=_view_shaped("2.35:1"))

    assert player.media_input.video.aspect_ratio == "2.35:1"
