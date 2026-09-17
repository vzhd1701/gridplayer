from unittest.mock import Mock

import gridplayer.vlc_player.player_base as player_base_mod
from gridplayer.params.static import VideoAspect, VideoCrop
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import Media, VideoTrack


class _MinimalPlayer(VlcPlayerBase):
    """Concrete VlcPlayerBase with the 9 abstractmethods stubbed as no-ops."""

    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
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


def _make_player(aspect_mode=VideoAspect.FIT, is_audio_only=False):
    player = _MinimalPlayer(vlc_instance=None)

    media_player = _RecordingMediaPlayer()
    player._media_player = media_player

    media = Mock()
    media.is_audio_only = is_audio_only
    player.media = media

    media_input = Mock()
    media_input.size = (640, 360)
    media_input.video.aspect_mode = aspect_mode
    media_input.video.scale = 1.0
    media_input.video.crop = VideoCrop(0, 0, 0, 0)
    media_input.video.transform = None
    player.media_input = media_input

    return player, media_player


def test_cb_stopped_unexpected_non_live_errors():
    player, _ = _make_player()
    player.is_video_initialized = True
    player.media_input.is_live = False
    errors = []
    player.notify_error = errors.append
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
    player, media_player = _make_player(aspect_mode=VideoAspect.STRETCH)

    player.adjust_view(
        size=(640, 360),
        aspect=VideoAspect.STRETCH,
        scale=1.0,
        crop=VideoCrop(160, 0, 160, 0),
    )

    # Region 320x360 (8:9) must display as 16:9 -> override 32:9.
    assert media_player.calls == [
        ("aspect_ratio", "32:9"),
        ("crop_geometry", "+160+0+160+0"),
        ("scale", 0),
    ]


def test_adjust_view_crop_fit_extends_borders():
    """Pixel crop + Fit: the borders are extended until the visible region
    matches the pane ratio, so VLC's auto-fit fills the pane exactly."""
    player, media_player = _make_player(aspect_mode=VideoAspect.FIT)

    player.adjust_view(
        size=(640, 360),
        aspect=VideoAspect.FIT,
        scale=1.0,
        crop=VideoCrop(160, 0, 160, 0),
    )

    # Region 320x360 -> crop down to 320x180 (16:9) -> 90 top/bottom.
    assert media_player.calls == [
        ("aspect_ratio", "640:360"),
        ("crop_geometry", "+160+90+160+90"),
        ("scale", 0),
    ]


def test_adjust_view_persists_crop_for_vout_reapply():
    """Live unpause stop/play recreates the vout; cb_vout re-applies from
    media_input, so crop/aspect/scale must be written back on each adjust."""
    player, media_player = _make_player(aspect_mode=VideoAspect.FIT)
    crop = VideoCrop(160, 0, 160, 0)

    player.adjust_view(
        size=(640, 360),
        aspect=VideoAspect.FIT,
        scale=1.0,
        crop=crop,
    )

    assert player.media_input.video.crop == crop
    assert player.media_input.video.aspect_mode is VideoAspect.FIT

    media_player.calls.clear()
    player._apply_media_input_view()

    assert media_player.calls == [
        ("aspect_ratio", "640:360"),
        ("crop_geometry", "+160+90+160+90"),
        ("scale", 0),
    ]


def test_apply_media_input_view_uses_cached_size_when_vout_size_missing():
    """After live stop/play, cb_vout can run while video_get_size is still
    0x0. FIT+crop must not fall back to letterbox (aspect None)."""
    player, media_player = _make_player(aspect_mode=VideoAspect.FIT)
    crop = VideoCrop(160, 0, 160, 0)

    player.adjust_view(
        size=(640, 360),
        aspect=VideoAspect.FIT,
        scale=1.0,
        crop=crop,
    )

    media_player.video_get_size = lambda num=0: (0, 0)
    media_player.calls.clear()

    player._apply_media_input_view()

    assert media_player.calls == [
        ("aspect_ratio", "640:360"),
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
        aspect=VideoAspect.FIT,
        scale=1.0,
        crop=VideoCrop(0, 0, 0, 0),
    )

    assert player.media.video_tracks[1].video_dimensions == (640, 360)
    player.notify_video_dimensions.assert_called_once_with(640, 360)


def test_adjust_view_crop_none_letterboxes_user_region():
    """Pixel crop + None: keep the user borders and native aspect so the
    visible region is letterboxed in the pane."""
    player, media_player = _make_player(aspect_mode=VideoAspect.NONE)

    player.adjust_view(
        size=(640, 360),
        aspect=VideoAspect.NONE,
        scale=1.0,
        crop=VideoCrop(160, 0, 160, 0),
    )

    assert media_player.calls == [
        ("aspect_ratio", "640:360"),
        ("crop_geometry", "+160+0+160+0"),
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
