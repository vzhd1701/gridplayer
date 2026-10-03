"""The overlay of a hardware video as a child window of its cell, Windows 8+.

A translucent window of its own, put inside the cell's: in the cell's
coordinates, never following the player window around, and stacked above
the frame VLC draws into. Being a window, what Qt does for a widget inside
another one is left to it: the mouse events nothing on it takes going on
to the cell, and the mouse being over a button of it. Up to Windows 7, and
everywhere else, the overlay stays floating.
"""

from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSettings, Qt
from PyQt5.QtGui import QEnterEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.video import Video
from gridplayer.params.static import VideoInitialState
from gridplayer.settings import Settings
from gridplayer.widgets import video_block as video_block_module
from gridplayer.widgets import video_overlay
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_overlay import (
    OverlayBlock,
    OverlayBlockChild,
    OverlayBlockFloating,
    is_layered_child_supported,
)

WINDOWS_7 = (6, 1)
WINDOWS_8 = (6, 2)
WINDOWS_8_1 = (6, 3)
WINDOWS_10 = (10, 0)


class _HardwareFrame(VideoFrameDummy):
    """Stands in for a hardware frame: the surface VLC draws into is native."""

    is_native_surface = True

    def ui_video_surface(self):
        return QWidget(self.video_clip)

    def driver_setup(self, vlc_options):
        # as the hardware frame does, handing VLC its window
        self.video_surface.winId()

        return super().driver_setup(vlc_options)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _context():
    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1

    return context


@pytest.fixture
def make_block(monkeypatch):
    made = []

    def make(frame, is_supported):
        monkeypatch.setattr(
            video_block_module, "is_layered_child_supported", lambda: is_supported
        )

        # held on to: a parent collected out from under it takes the block
        window = QWidget()
        window.resize(640, 360)

        block = VideoBlock(video_driver=frame, context=_context(), parent=window)
        block.setGeometry(0, 0, 640, 360)
        made.append((window, block))

        return window, block

    yield make

    for window, block in made:
        block.url_resolver.cleanup()
        block.overlay.close()
        window.close()


class TestWhichWindows:
    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            (WINDOWS_7, False),
            (WINDOWS_8, True),
            (WINDOWS_8_1, True),
            (WINDOWS_10, True),
        ],
        ids=["7", "8", "8.1", "10+"],
    )
    def test_windows_8_is_the_first_to_layer_a_child_window(
        self, monkeypatch, version, expected
    ):
        monkeypatch.setattr(video_overlay.env, "IS_WINDOWS", True)
        # only the major and minor of it are read
        monkeypatch.setattr(
            video_overlay.sys, "getwindowsversion", lambda: version, raising=False
        )

        assert is_layered_child_supported() is expected

    def test_nowhere_but_windows(self, monkeypatch):
        monkeypatch.setattr(video_overlay.env, "IS_WINDOWS", False)

        assert is_layered_child_supported() is False


class TestWhichOverlay:
    def test_a_hardware_video_gets_a_child_one_where_it_can(self, make_block):
        _, block = make_block(_HardwareFrame, is_supported=True)

        assert type(block.overlay) is OverlayBlockChild

    def test_and_a_floating_one_where_it_cannot(self, make_block):
        _, block = make_block(_HardwareFrame, is_supported=False)

        assert type(block.overlay) is OverlayBlockFloating

    @pytest.mark.parametrize("is_supported", [True, False])
    def test_a_software_video_paints_its_own(self, make_block, is_supported):
        _, block = make_block(VideoFrameDummy, is_supported=is_supported)

        assert type(block.overlay) is OverlayBlock


class TestChildWindow:
    def test_its_window_is_inside_the_cells(self, make_block):
        _, block = make_block(_HardwareFrame, is_supported=True)
        overlay = block.overlay

        assert overlay.isWindow()
        assert overlay.windowHandle().parent() is block.windowHandle()

    def test_it_covers_the_cell_in_the_cells_coordinates(self, make_block):
        window, block = make_block(_HardwareFrame, is_supported=True)
        window.show()
        block.show()
        block.setGeometry(40, 30, 320, 180)
        block.layout().activate()

        assert block.overlay.geometry() == QRect(0, 0, 320, 180)

    def test_it_stays_put_when_the_player_window_moves(self, make_block):
        window, block = make_block(_HardwareFrame, is_supported=True)
        window.move(200, 150)
        window.show()
        block.show()
        block.layout().activate()

        window.move(500, 400)

        assert block.overlay.pos() == QPoint(0, 0)

    def test_it_goes_above_the_frame_made_after_it(self, make_block, tmp_path):
        _, block = make_block(_HardwareFrame, is_supported=True)
        raised = []
        block.overlay.raise_ = lambda: raised.append(block.video_driver)

        video_file = tmp_path / "movie.mkv"
        video_file.touch()
        block.set_video(Video(uri=video_file, playback_state=VideoInitialState.PAUSED))

        assert raised == [block.video_driver]
        assert block.video_driver is not None


class _MouseMoves(QObject):
    def __init__(self):
        super().__init__()

        self.seen = []

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseMove:
            self.seen.append(event.pos())

        return False


class TestBeingAWindow:
    @pytest.fixture
    def block(self, make_block):
        window, block = make_block(_HardwareFrame, is_supported=True)
        window.show()
        block.show()
        block.overlay.show()
        block.layout().activate()
        block.overlay.layout().activate()

        return block

    def test_mouse_events_nothing_on_it_takes_go_on_to_the_cell(self, block):
        moves = _MouseMoves()
        block.installEventFilter(moves)

        move = QMouseEvent(
            QEvent.MouseMove, QPointF(5, 7), Qt.NoButton, Qt.NoButton, Qt.NoModifier
        )
        QApplication.sendEvent(block.overlay, move)

        assert moves.seen == [QPoint(5, 7)]

    def test_a_button_is_under_the_mouse_once_the_mouse_is_in(self, block):
        """QApplication.widgetAt only looks into top-level windows.

        The player's is the one under the mouse, and the overlay's window is
        inside it, so nothing on the overlay is ever found there.
        """

        overlay = block.overlay
        button = overlay.exit_button
        pos = QPointF(button.mapTo(overlay, button.rect().center()))
        global_pos = QPointF(overlay.mapToGlobal(pos.toPoint()))

        QApplication.sendEvent(
            overlay.windowHandle(), QEnterEvent(pos, pos, global_pos)
        )

        assert button.underMouse()

        QApplication.sendEvent(overlay.windowHandle(), QEvent(QEvent.Leave))

        assert not button.underMouse()
