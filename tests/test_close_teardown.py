from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.video import Video
from gridplayer.params.static import VideoInitialState
from gridplayer.player.manager import Commands, Context
from gridplayer.player.managers.bookmarks import BookmarksRegistry
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolver
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_frame_vlc_sw import VideoFrameVLCSW
from gridplayer.widgets.video_overlay import OverlayMode
from gridplayer.widgets.video_status import LoadStage, StepState


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubSWFrame(VideoFrameVLCSW):
    def driver_setup(self, vlc_options):
        return MagicMock()


class _StubBlock:
    def __init__(self, events, name):
        self._events = events
        self.id = name
        self.video_id = name
        self.video_params = MagicMock()

    def hide(self):
        self._events.append(("hide", self.id))

    def isVisible(self):
        return True

    def show_reloading(self):
        self._events.append(("reloading", self.id))

    def cleanup_start(self):
        self._events.append(("start", self.id))

    def release_player(self):
        self._events.append(("release", self.id))

    def close_silently(self):
        self._events.append(("close", self.id))


@pytest.fixture
def blocks_manager():
    """The manager, and a way to give it blocks to close.

    The parent is held for the length of the test rather than returned
    with the manager: dropped, Qt takes the manager down with it, and
    every use of it raises about a deleted C++ object.
    """

    parent = QWidget()
    manager = VideoBlocksManager(context=Context(), parent=parent)
    events = []
    parent.repaint = lambda: events.append(("repaint",))

    def _with_blocks(*names):
        for name in names:
            block = _StubBlock(events, name)
            manager._ctx.video_blocks.append(block)
            manager.close_all_signal.connect(block.close_silently)
        return events

    yield manager, _with_blocks

    parent.deleteLater()


def test_frame_cleanup_start_does_not_wait():
    frame = _StubSWFrame(process_manager=MagicMock(), vlc_options=[])

    frame.cleanup_start()

    frame.video_driver.cleanup_start.assert_called_once()
    frame.video_driver.cleanup_wait.assert_not_called()


def test_frame_cleanup_start_is_idempotent():
    frame = _StubSWFrame(process_manager=MagicMock(), vlc_options=[])

    frame.cleanup_start()
    frame.cleanup()

    frame.video_driver.cleanup_start.assert_called_once()
    frame.video_driver.cleanup_wait.assert_called_once()


def test_close_all_starts_every_player_before_closing_any(blocks_manager):
    manager, with_blocks = blocks_manager
    events = with_blocks("a", "b", "c")

    manager.close_all()

    assert [e for e in events if e[0] in ("start", "close")] == [
        ("start", "a"),
        ("start", "b"),
        ("start", "c"),
        ("close", "a"),
        ("close", "b"),
        ("close", "c"),
    ]


def test_close_all_takes_every_video_off_screen_before_any_is_waited_on(
    blocks_manager,
):
    """The window is not painted while the players let go, one by one:
    whatever was still on show played on and went black in turn, and the
    grid's empty cell came up only after the last of them, the window blank
    until then."""
    manager, with_blocks = blocks_manager
    events = with_blocks("a", "b", "c")
    manager.video_count_changed.connect(lambda count: events.append(("count", count)))

    manager.close_all()

    assert events[:6] == [
        ("hide", "a"),
        ("hide", "b"),
        ("hide", "c"),
        # the grid lays itself out without them on this, empty cell and all
        ("count", 0),
        ("repaint",),
        ("start", "a"),
    ]


def test_remove_videos_starts_every_player_before_closing_any(blocks_manager):
    """And off screen, the grid laid out and painted without them, before
    any wait, as close_all does it."""
    manager, with_blocks = blocks_manager
    events = with_blocks("a", "b")
    manager.video_count_changed.connect(lambda count: events.append(("count", count)))

    manager.remove_videos(["a", "b"])

    assert events == [
        ("hide", "a"),
        ("hide", "b"),
        ("count", 0),
        ("repaint",),
        ("start", "a"),
        ("start", "b"),
        ("close", "a"),
        ("close", "b"),
    ]


def test_reload_keeps_the_cells_until_new_ones_take_their_places(blocks_manager):
    """Closed first, the grid was shown empty, its empty cell and all, until
    the players were started again and the new cells came."""
    manager, with_blocks = blocks_manager
    events = with_blocks("a", "b")
    manager.video_count_changed.connect(lambda count: events.append(("count", count)))
    manager.reload_all_closed.connect(lambda: events.append(("restart",)))

    names = {id(block.video_params): block.id for block in manager._ctx.video_blocks}

    def _add(video):
        block = _StubBlock(events, names[id(video)] + "'")
        manager._ctx.video_blocks.append(block)
        events.append(("add", block.id))
        return block

    manager._add_video_block = _add

    manager.reload_videos()

    assert events == [
        # said by all before any player lets go, and those started at once
        ("reloading", "a"),
        ("reloading", "b"),
        ("start", "a"),
        ("start", "b"),
        ("release", "a"),
        ("release", "b"),
        ("restart",),
        # swapped for the new ones in one go, the window not painted between
        ("hide", "a"),
        ("hide", "b"),
        ("close", "a"),
        ("close", "b"),
        ("add", "a'"),
        ("add", "b'"),
        ("count", 2),
    ]
    assert [block.id for block in manager._ctx.video_blocks] == ["a'", "b'"]


def test_reload_with_no_cells_restarts_the_players(blocks_manager):
    manager, _ = blocks_manager
    restarts = []
    manager.reload_all_closed.connect(lambda: restarts.append(True))

    manager.reload_videos()

    assert restarts == [True]


@pytest.fixture
def cell(mocker, tmp_path):
    """A cell on show in a window, on a player that is not there."""

    mocker.patch.object(VideoURLResolver, "resolve")

    settings = Settings()
    real_settings = settings.settings
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1
    context.synced_view = None
    context.lists = MediaListsRegistry()
    context.bookmarks = BookmarksRegistry()
    context.video_blocks = []

    window = QWidget()
    window.resize(640, 360)
    block = VideoBlock(video_driver=VideoFrameDummy, context=context, parent=window)
    block.resize(640, 360)
    window.show()
    block.show()

    yield block, window

    if not block._is_closing:
        block.close_silently()
    VideoBlock.cleanup(block)
    window.deleteLater()

    settings.settings = real_settings
    PlaylistSettings().clear()


def test_a_cell_closed_is_off_screen_before_its_player_is_waited_on(cell):
    """A hardware video's cell, once its player lets go, shows what was
    painted there before its picture came, the loading status, and the
    window is not painted while the player is waited on."""
    block, window = cell
    seen = []
    window.repaint = lambda: seen.append("painted")
    block.cleanup = lambda: seen.append(
        "waited off screen" if block.isHidden() else "waited on show"
    )

    block.close()

    assert seen == ["painted", "waited off screen"]


def test_a_cell_closed_off_screen_leaves_the_window_be(cell):
    """Closing them all takes them off screen and paints the window once,
    rather than once for each."""
    block, window = cell
    seen = []
    window.repaint = lambda: seen.append("painted")
    block.cleanup = lambda: seen.append("waited")
    block.hide()

    block.close_silently()

    assert seen == ["waited"]


@pytest.mark.parametrize(
    ("uri", "said", "steps"),
    [
        ("file", "Opening…", ()),
        (
            "https://example.com/v.m3u8",
            "Resolving the link…",
            (StepState.CURRENT, StepState.TODO),
        ),
    ],
)
def test_reloading_says_so_over_the_video_as_a_new_cell_does(
    cell, tmp_path, uri, said, steps
):
    block, _ = cell

    if uri == "file":
        uri = tmp_path / "a.mp4"
        uri.touch()

    block.set_video(Video(uri=uri))
    block._show_stage(LoadStage.VIDEO, "Buffering 100%")
    block.video_status.hide()

    block.show_reloading()

    assert not block.video_status.isHidden()
    assert block.video_status.status_text == said
    assert tuple(state for _, state in block.video_status.steps) == steps
    assert block.overlay.mode is OverlayMode.LOADING
    assert block.video_driver is not None

    block.release_player()

    assert block.video_driver is None


def test_reloading_leaves_a_stopped_cell_stopped(cell, tmp_path):
    block, _ = cell
    path = tmp_path / "a.mp4"
    path.touch()
    block.set_video(Video(uri=path, playback_state=VideoInitialState.STOPPED))

    block.show_reloading()

    assert block.video_status.isHidden()
    assert block.overlay.mode is OverlayMode.STOPPED


def _playing(block, path):
    block.set_video(Video(uri=path))
    block._show_stage(LoadStage.VIDEO, "Buffering 100%")
    block.video_status.hide()


def test_a_cell_stopped_is_painted_stopped_before_its_player_is_waited_on(
    cell, tmp_path
):
    """A hardware video's window, gone, shows what was painted under it
    before its picture came, the loading status, until the cell is painted
    again; the window is not painted while the player is waited on."""
    block, _ = cell
    path = tmp_path / "a.mp4"
    path.touch()
    _playing(block, path)

    seen = []
    block.repaint = lambda: seen.append(
        "painted" if block.video_status.isHidden() else "painted with status"
    )
    block.video_driver.cleanup = lambda: seen.append("waited")

    block.stop_playback()

    assert seen == ["painted", "waited"]


@pytest.mark.parametrize("how", ["reload", "next"])
def test_a_load_begun_again_says_so_while_the_old_player_is_waited_on(
    cell, tmp_path, how
):
    """Not how far the load before it got, painted over the video as the
    old player lets go."""
    block, _ = cell
    path = tmp_path / "a.mp4"
    other = tmp_path / "b.mp4"
    path.touch()
    other.touch()
    _playing(block, path)

    seen = []
    block.video_driver.cleanup = lambda: seen.append(
        (block.video_status.isHidden(), block.video_status.status_text)
    )

    if how == "reload":
        block.reload()
    else:
        block._switch_to(other)

    assert seen == [(False, "Opening…")]


def _window_state_manager(commands):
    window = QWidget()
    ctx = Context()
    ctx.commands = Commands()
    ctx.commands.update(commands)

    return WindowStateManager(context=ctx, parent=window), window, ctx


def test_close_event_hides_window_before_tearing_players_down(mocker):
    mocker.patch("gridplayer.player.managers.window_state.force_terminate")

    events = []
    manager, window, _ = _window_state_manager(
        {
            "check_playlist_save": lambda: (events.append("ask"), True)[1],
            "remember_last_playlist": lambda: events.append("remember"),
            "force_close_playlist": lambda: events.append("close"),
        }
    )
    mocker.patch.object(window, "hide", side_effect=lambda: events.append("hide"))

    manager.closeEvent(MagicMock())

    assert events == ["ask", "remember", "hide", "close"]


def test_close_event_keeps_window_when_save_is_cancelled(mocker):
    terminate = mocker.patch("gridplayer.player.managers.window_state.force_terminate")

    manager, _, ctx = _window_state_manager(
        {
            "check_playlist_save": lambda: False,
            "remember_last_playlist": MagicMock(),
            "force_close_playlist": MagicMock(),
        }
    )
    event = MagicMock()

    assert manager.closeEvent(event) is True

    event.ignore.assert_called_once()
    ctx.commands.remember_last_playlist.assert_not_called()
    ctx.commands.force_close_playlist.assert_not_called()
    terminate.assert_not_called()
