from unittest.mock import Mock

import pytest

import gridplayer.vlc_player.player_base as player_base_mod
from gridplayer.params.static import VideoAspect, VideoCrop
from gridplayer.vlc_player.player_base import VlcPlayerBase


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


def test_cb_vout_noop_when_audio_only(monkeypatch):
    """macOS but audio-only media: cb_vout returns early, no scheduling."""
    monkeypatch.setattr(player_base_mod.env, "IS_MACOS", True)

    player, _ = _make_player(is_audio_only=True)

    scheduler = Mock()
    player._schedule_view_reapply = scheduler

    player.cb_vout(None)

    assert scheduler.call_count == 0
