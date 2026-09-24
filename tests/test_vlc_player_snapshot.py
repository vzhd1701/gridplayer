from pathlib import Path

from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.widgets.video_frame_vlc_base import remove_snapshot_file


class _MinimalPlayer(VlcPlayerBase):
    """Concrete VlcPlayerBase with the abstractmethods stubbed as no-ops."""

    def __init__(self, **kwargs):
        super().__init__(vlc_instance=None, **kwargs)

        self.snapshots = []

    def notify_snapshot_taken(self, snapshot_path):
        self.snapshots.append(snapshot_path)

    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class _FakeMediaPlayer:
    def __init__(self, result=0, write_file=True):
        self.result = result
        self.write_file = write_file
        self.requested_paths = []

    def video_take_snapshot(self, num, path, width, height):
        self.requested_paths.append(path)

        if self.write_file:
            Path(path).write_bytes(b"png")

        return self.result


def _make_player(fake_media_player):
    player = _MinimalPlayer()
    player._media_player = fake_media_player

    return player


def test_snapshot_notifies_written_file():
    """Successful snapshot (res == 0, file written) notifies the path."""
    media_player = _FakeMediaPlayer()
    player = _make_player(media_player)

    player.snapshot()

    assert media_player.requested_paths
    assert player.snapshots == media_player.requested_paths

    remove_snapshot_file(player.snapshots[0])
    assert not Path(player.snapshots[0]).parent.exists()


def test_snapshot_reports_failure_when_libvlc_lies():
    """res == 0 but the vout-side grab failed and wrote no file."""
    media_player = _FakeMediaPlayer(result=0, write_file=False)
    player = _make_player(media_player)

    player.snapshot()

    assert player.snapshots == [""]
    assert not Path(media_player.requested_paths[0]).parent.exists()


def test_snapshot_reports_failure_without_vout():
    """res == -1 (no vout) reports failure."""
    media_player = _FakeMediaPlayer(result=-1, write_file=False)
    player = _make_player(media_player)

    player.snapshot()

    assert player.snapshots == [""]


def test_snapshot_noop_without_media_player():
    player = _MinimalPlayer()

    player.snapshot()

    assert player.snapshots == []


def test_remove_snapshot_file_tolerates_missing_file(tmp_path):
    """A vanished file/dir must not raise in a Qt slot."""
    remove_snapshot_file(str(tmp_path / "gone" / "snapshot.png"))


def test_remove_snapshot_file_removes_file_and_dir(tmp_path):
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()

    snapshot = snap_dir / "snapshot.png"
    snapshot.write_bytes(b"png")

    remove_snapshot_file(str(snapshot))

    assert not snap_dir.exists()


class _ScreenshotPlayer(_MinimalPlayer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.screenshots = []

    def notify_screenshot_taken(self, frame_path):
        self.screenshots.append(frame_path)


def test_screenshot_notifies_written_file():
    media_player = _FakeMediaPlayer()
    player = _ScreenshotPlayer()
    player._media_player = media_player

    player.screenshot()

    assert player.screenshots == media_player.requested_paths
    assert player.snapshots == []

    remove_snapshot_file(player.screenshots[0])


def test_screenshot_reports_failure_when_libvlc_lies():
    media_player = _FakeMediaPlayer(result=0, write_file=False)
    player = _ScreenshotPlayer()
    player._media_player = media_player

    player.screenshot()

    assert player.screenshots == [""]
    assert not Path(media_player.requested_paths[0]).parent.exists()


def test_screenshot_answers_without_media_player():
    """Unlike the pause snapshot, somebody is waiting to hear back."""

    player = _ScreenshotPlayer()

    player.screenshot()

    assert player.screenshots == [""]
