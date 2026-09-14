from threading import Lock as ThreadLock
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication, QGraphicsPixmapItem

from gridplayer.params.static import VideoDriver
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.settings import Settings
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP
from gridplayer.widgets.video_frame_vlc_sw_sp import (
    VideoDriverVLCSWSP,
    VideoFrameVLCSWSP,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_vlc_sw_sp_enum_value():
    assert VideoDriver.VLC_SW_SP.value == "vlc_sw_sp"


def test_sw_sp_frame_is_not_opengl():
    assert VideoFrameVLCSWSP.is_opengl is False


def test_manager_returns_sw_sp_without_process_manager(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_SW_SP)
    ctx = SimpleNamespace()
    manager = VideoDriverManager(context=ctx)

    driver = manager.video_driver()

    assert driver is VideoFrameVLCSWSP
    assert manager._process_manager is None


def test_manager_returns_hw_sp_without_process_manager(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_HW_SP)
    ctx = SimpleNamespace()
    manager = VideoDriverManager(context=ctx)

    driver = manager.video_driver()

    assert driver is VideoFrameVLCHWSP
    assert manager._process_manager is None


def test_set_log_level_vlc_forwards_to_sw_sp_frames(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_SW_SP)
    frame = SimpleNamespace(set_log_level_vlc=MagicMock())
    ctx = SimpleNamespace(video_blocks=[SimpleNamespace(video_driver=frame)])
    manager = VideoDriverManager(context=ctx)

    manager.set_log_level_vlc(10)

    frame.set_log_level_vlc.assert_called_once_with(10)


def test_set_log_level_vlc_forwards_to_hw_sp_frames(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_HW_SP)
    frame = SimpleNamespace(set_log_level_vlc=MagicMock())
    ctx = SimpleNamespace(video_blocks=[SimpleNamespace(video_driver=frame)])
    manager = VideoDriverManager(context=ctx)

    manager.set_log_level_vlc(20)

    frame.set_log_level_vlc.assert_called_once_with(20)


def test_set_log_level_vlc_skips_missing_sw_sp_driver(mocker):
    mocker.patch.object(Settings(), "get", return_value=VideoDriver.VLC_SW_SP)
    ctx = SimpleNamespace(video_blocks=[SimpleNamespace(video_driver=None)])
    manager = VideoDriverManager(context=ctx)

    manager.set_log_level_vlc(10)


class _StubSWSPFrame(VideoFrameVLCSWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def test_sw_sp_frame_surface_and_snapshot():
    frame = _StubSWSPFrame(vlc_options=[])

    assert frame._videoitem is not None
    assert frame.video_surface is not None

    frame.take_snapshot()
    frame.video_driver.set_pause.assert_called_once_with(True)

    frame.cleanup()
    frame.video_driver.cleanup.assert_called_once()


def _driver_with_mocked_player(mocker):
    player = MagicMock()
    mocker.patch(
        "gridplayer.widgets.video_frame_vlc_sw_sp.PlayerProcessSingleVLCSWSP",
        return_value=player,
    )
    item = QGraphicsPixmapItem()
    driver = VideoDriverVLCSWSP(image_dest=item, vlc_options=[])
    return driver, item


def test_sw_sp_driver_uses_threading_lock(mocker):
    driver, _item = _driver_with_mocked_player(mocker)
    try:
        assert isinstance(driver._shared_memory.lock, type(ThreadLock()))
    finally:
        driver.cleanup()


def test_process_image_noop_without_frame_size(mocker):
    driver, item = _driver_with_mocked_player(mocker)
    try:
        driver.process_image()
        assert item.pixmap().isNull()
    finally:
        driver.cleanup()


def test_init_frame_sets_dummy_pixmap(mocker):
    driver, item = _driver_with_mocked_player(mocker)
    try:
        driver.init_frame(4, 6)
        pix = item.pixmap()
        assert pix.width() == 4
        assert pix.height() == 6
    finally:
        driver.cleanup()


def test_process_image_copies_shared_memory_into_pixmap(mocker):
    driver, item = _driver_with_mocked_player(mocker)
    try:
        driver.init_frame(2, 2)
        driver._shared_memory.allocate(2 * 2 * 4)
        driver._shared_memory.memory.buf[:] = b"\x00\x00\xff\xff" * 4
        driver.process_image()
        pix = item.pixmap()
        assert pix.width() == 2
        assert pix.height() == 2
        assert not pix.isNull()
    finally:
        driver.cleanup()


def test_process_image_noop_after_cleanup(mocker):
    driver, item = _driver_with_mocked_player(mocker)
    driver.init_frame(2, 2)
    driver.cleanup()
    driver.process_image()
    assert item.pixmap().width() == 2


def test_process_image_handles_closed_mapping(mocker):
    driver, item = _driver_with_mocked_player(mocker)
    try:
        driver.init_frame(2, 2)
        driver._shared_memory.allocate(2 * 2 * 4)
        driver._shared_memory.close()
        driver.process_image()
        assert item.pixmap().width() == 2
    finally:
        driver.cleanup()


def _combo_data(combo):
    return [combo.itemData(i) for i in range(combo.count())]


def test_settings_combo_includes_software_sp(mocker):
    from PyQt5.QtWidgets import QComboBox, QSpinBox, QWidget

    from gridplayer.dialogs.settings import SettingsDialog

    parent = QWidget()
    dialog = SimpleNamespace(
        playerVideoDriver=QComboBox(parent),
        playerVideoDriverPlayers=QSpinBox(parent),
        tr=lambda s: s,
    )

    mocker.patch("gridplayer.dialogs.settings.env.IS_MACOS", False)
    SettingsDialog.fill_playerVideoDriver(dialog)
    non_mac = _combo_data(dialog.playerVideoDriver)
    assert VideoDriver.VLC_SW_SP in non_mac
    assert VideoDriver.VLC_SW in non_mac
    assert VideoDriver.VLC_HW in non_mac

    mocker.patch("gridplayer.dialogs.settings.env.IS_MACOS", True)
    dialog.playerVideoDriver.clear()
    SettingsDialog.fill_playerVideoDriver(dialog)
    mac = _combo_data(dialog.playerVideoDriver)
    assert VideoDriver.VLC_SW_SP in mac
    assert VideoDriver.VLC_SW in mac
    assert VideoDriver.VLC_HW_SP in mac
    assert VideoDriver.VLC_HW not in mac

    idx = dialog.playerVideoDriver.findData(VideoDriver.VLC_SW_SP)
    dialog.playerVideoDriverPlayers.setEnabled(True)
    SettingsDialog.driver_selected(dialog, idx)
    assert not dialog.playerVideoDriverPlayers.isEnabled()
