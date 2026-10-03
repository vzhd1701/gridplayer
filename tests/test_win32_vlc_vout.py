from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

import gridplayer.utils.win32_vlc_vout as vlc_vout
from gridplayer.widgets.video_frame_vlc_hw import VideoFrameVLCHW
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP

SURFACE = 1
MAIN = 2
PICTURE = 3


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _Windows:
    """A window tree as VLC leaves it inside the surface, noting moves."""

    def __init__(self, monkeypatch, surface_size, main_size, picture_rect):
        self.client = {SURFACE: surface_size, MAIN: main_size}
        self.tree = {SURFACE: [MAIN], MAIN: [PICTURE], PICTURE: []}
        self.classes = {
            MAIN: "VLC video main 00000186B0EFC8B0",
            PICTURE: "VLC video output 00000186B0EFC8B0",
        }
        self.rects = {PICTURE: picture_rect}
        self.moved = []

        monkeypatch.setattr(vlc_vout, "_client_size", self.client.__getitem__)
        monkeypatch.setattr(vlc_vout, "_children", self.tree.__getitem__)
        monkeypatch.setattr(vlc_vout, "_class_name", self.classes.__getitem__)
        monkeypatch.setattr(vlc_vout, "_rect_in", lambda hwnd, _: self.rects[hwnd])
        monkeypatch.setattr(
            vlc_vout, "_set_rect", lambda hwnd, rect: self.moved.append((hwnd, rect))
        )


def test_vlc_windows_grow_with_the_surface(monkeypatch):
    """A cell going single: VLC's windows are still the size of the cell."""
    windows = _Windows(monkeypatch, (1216, 716), (416, 250), (0, 3, 416, 243))

    vlc_vout._fit_vlc_windows(SURFACE)

    assert windows.moved == [
        (MAIN, (0, 0, 1216, 716)),
        (PICTURE, (0, 9, 1216, 696)),
    ]


def test_vlc_windows_shrink_with_the_surface(monkeypatch):
    windows = _Windows(monkeypatch, (416, 250), (1216, 716), (0, 3, 1216, 709))

    vlc_vout._fit_vlc_windows(SURFACE)

    assert windows.moved == [
        (MAIN, (0, 0, 416, 250)),
        (PICTURE, (0, 1, 416, 248)),
    ]


def test_vlc_windows_left_alone_once_vlc_caught_up(monkeypatch):
    """VLC's own placement of the picture is never second-guessed."""
    windows = _Windows(monkeypatch, (416, 250), (416, 250), (0, 3, 416, 243))

    vlc_vout._fit_vlc_windows(SURFACE)

    assert windows.moved == []


def test_windows_that_are_not_vlc_left_alone(monkeypatch):
    windows = _Windows(monkeypatch, (1216, 716), (416, 250), (0, 3, 416, 243))
    windows.classes[MAIN] = "Qt5152QWindowIcon"

    vlc_vout._fit_vlc_windows(SURFACE)

    assert windows.moved == []


def test_vlc_windows_not_made_yet(monkeypatch):
    windows = _Windows(monkeypatch, (1216, 716), (0, 0), (0, 0, 0, 0))

    vlc_vout._fit_vlc_windows(SURFACE)

    assert windows.moved == []


def test_nothing_done_off_windows(monkeypatch):
    """Tests draw offscreen: there is no native window to look inside."""
    fit = MagicMock()
    monkeypatch.setattr(vlc_vout, "_fit_vlc_windows", fit)
    surface = MagicMock(isVisible=lambda: True)

    vlc_vout.fit_vlc_vout_windows(surface)

    fit.assert_not_called()


def _hw_frame(frame_cls):
    class _Stub(frame_cls):
        def driver_setup(self, vlc_options):
            return MagicMock()

    if frame_cls is VideoFrameVLCHW:
        return _Stub(vlc_options=[], process_manager=MagicMock())
    return _Stub(vlc_options=[])


@pytest.mark.parametrize("frame_cls", [VideoFrameVLCHW, VideoFrameVLCHWSP])
def test_vlc_told_about_the_view_after_its_windows_are_sized(frame_cls):
    """Woken by the view while its windows are being sized, VLC could place
    its picture where they are about to be overruled (see
    fit_vlc_vout_windows)."""
    frame = _hw_frame(frame_cls)
    frame.media = MagicMock(is_audio_only=False)
    calls = MagicMock()
    frame._place_native_surface = calls.place
    frame.video_driver.adjust_view = calls.tell_vlc

    frame.adjust_view()

    assert [c[0] for c in calls.mock_calls] == ["place", "tell_vlc"]
