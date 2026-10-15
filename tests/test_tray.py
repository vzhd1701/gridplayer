"""The tray: minimize and close there, quit from it, the window back as it
was, the pictures off while away, and what keeps the system awake then."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QEvent, QSettings
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.models.video import Video
from gridplayer.params.settings_fields import general as general_fields
from gridplayer.params.static import VideoInitialState
from gridplayer.player.managers import screensaver as screensaver_module
from gridplayer.player.managers import tray as tray_module
from gridplayer.player.managers import window_state as window_state_module
from gridplayer.player.managers.screensaver import ScreensaverManager
from gridplayer.player.managers.tray import TrayManager
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.settings import _Settings
from gridplayer.utils import taskbar as taskbar_module
from gridplayer.utils.keepawake import KeepAwakeMode
from gridplayer.utils.single_instance import Listener
from gridplayer.utils.taskbar import TaskbarHidingBlocker
from gridplayer.vlc_player.static import DISABLED_TRACK
from gridplayer.widgets.video_block import VideoBlock

URI = "http://example.com/a.mp4"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    for module in (window_state_module, tray_module, screensaver_module):
        monkeypatch.setattr(module, "Settings", lambda: store)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)

    return store


class FakeVideo:
    def __init__(self, is_paused=False):
        self.video_params = SimpleNamespace(is_paused=is_paused)
        self.unpaused_by = []

    def set_pause(self, is_paused):
        self.unpaused_by.append(is_paused)


class FakeBlocks(list):
    @property
    def unpaused(self):
        return [v for v in self if not v.video_params.is_paused]


class Player:
    """A window with the manager on it, and what it asked of the others."""

    def __init__(self, monkeypatch):
        self.terminated = 0
        self.taskbar = []
        self.notes = 0
        self.decoding = []
        self.save_answer = True

        monkeypatch.setattr(window_state_module, "force_terminate", self._terminate)
        monkeypatch.setattr(
            window_state_module, "set_hidden_from_taskbar", self._set_taskbar
        )
        monkeypatch.setattr(
            window_state_module, "is_taskbar_hiding_available", lambda: True
        )

        self.window = QWidget()

        self.ctx = SimpleNamespace(
            is_tray_shown=True,
            video_blocks=FakeBlocks(),
            is_video_decoding_stopped=False,
            commands=SimpleNamespace(
                check_playlist_save=lambda: self.save_answer,
                remember_last_playlist=lambda: None,
                force_close_playlist=lambda: None,
                show_tray_note=self._note,
                set_video_decoding_stopped=self._set_decoding,
            ),
        )

        self.manager = WindowStateManager(context=self.ctx, parent=self.window)
        self.window.installEventFilter(self.manager)
        self.manager.init()

        self.paused = 0
        self.manager.pause_on_minimize.connect(self._pause)

        self.away = []
        self.manager.away_changed.connect(self.away.append)

    @property
    def commands(self):
        return self.manager.commands

    @property
    def is_in_tray(self):
        return self.manager._is_in_tray

    def _terminate(self):
        self.terminated += 1

    def _set_taskbar(self, widget, is_hidden, is_showing=False):
        self.taskbar.append((is_hidden, is_showing))

    def _note(self):
        self.notes += 1

    def _set_decoding(self, is_stopped):
        self.ctx.is_video_decoding_stopped = is_stopped
        self.decoding.append(is_stopped)

    def _pause(self):
        self.paused += 1


@pytest.fixture
def player(settings, monkeypatch):
    made = Player(monkeypatch)

    yield made

    made.window.removeEventFilter(made.manager)
    made.window.hide()
    made.window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    QApplication.instance().setQuitOnLastWindowClosed(True)


def _settle():
    QTest.qWait(20)


class TestClose:
    def test_quits_with_the_tray_left_alone(self, player):
        player.window.show()

        player.window.close()

        assert player.terminated == 1
        assert not player.is_in_tray

    def test_goes_to_the_tray(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()

        assert player.window.close() is False

        assert player.is_in_tray
        assert not player.window.isVisible()
        assert player.terminated == 0
        assert player.notes == 1

    def test_quits_with_no_tray_icon_up(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.ctx.is_tray_shown = False
        player.window.show()

        player.window.close()

        assert player.terminated == 1

    def test_quits_with_the_icon_turned_off(self, settings, player):
        """Close to the tray is greyed out and kept; without the icon it
        has nowhere to go."""

        settings.set("player/close_to_tray", True)
        player.window.show()

        player.window.close()

        assert player.terminated == 1

    def test_stays_up_under_a_dialog(self, settings, player, monkeypatch):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        monkeypatch.setattr(
            QApplication, "activeModalWidget", staticmethod(lambda: QWidget())
        )
        player.window.show()

        player.window.close()

        assert not player.is_in_tray
        assert player.terminated == 1


class TestQuit:
    def test_quits_past_close_to_the_tray(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()

        player.commands["quit"]()

        assert player.terminated == 1
        assert not player.is_in_tray

    def test_from_the_tray(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()
        player.window.close()

        player.commands["quit"]()

        assert player.terminated == 1

    def test_kept_from_by_the_playlist_question_closes_to_the_tray_again(
        self, settings, player
    ):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()
        player.save_answer = False

        player.commands["quit"]()

        assert player.terminated == 0
        assert player.window.isVisible()

        player.window.close()

        assert player.is_in_tray

    def test_logging_off_quits(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()

        player.manager._set_quitting(None)
        player.window.close()

        assert player.terminated == 1


class TestMinimize:
    def test_stays_minimized_with_the_tray_left_alone(self, player):
        player.window.show()

        player.window.showMinimized()
        _settle()

        assert not player.is_in_tray
        assert player.window.isVisible()

    def test_goes_to_the_tray(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/minimize_to_tray", True)
        player.window.show()

        player.window.showMinimized()
        _settle()

        assert player.is_in_tray
        assert not player.window.isVisible()

    def test_with_no_taskbar_button_goes_to_the_tray(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/hide_taskbar", True)
        player.window.show()

        player.window.showMinimized()
        _settle()

        assert player.is_in_tray

    def test_comes_back_maximized_as_it_went(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/minimize_to_tray", True)
        player.window.showMaximized()

        player.window.showMinimized()
        _settle()

        player.commands["activate_window"]()

        assert player.window.isVisible()
        assert player.window.isMaximized()
        assert not player.window.isMinimized()


class TestBack:
    @pytest.fixture
    def in_tray(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()
        player.window.close()

        return player

    def test_the_icon_clicked(self, in_tray):
        in_tray.commands["toggle_window"]()

        assert in_tray.window.isVisible()
        assert not in_tray.is_in_tray

        in_tray.commands["toggle_window"]()

        assert in_tray.is_in_tray

    def test_comes_back_full_screen_as_it_went(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.showFullScreen()
        player.window.close()

        player.commands["activate_window"]()

        assert player.window.isFullScreen()

    def test_other_windows_go_and_come_back_with_it(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()

        other = QWidget()
        other.show()

        player.window.close()

        assert not other.isVisible()

        player.commands["activate_window"]()

        assert other.isVisible()

        other.close()
        other.deleteLater()

    def test_a_playlist_opened_meanwhile_waits_for_it(self, in_tray):
        state = window_state_module.WindowState(
            is_maximized=True, is_fullscreen=False, geometry=""
        )

        in_tray.manager.restore_window_state(state)

        assert not in_tray.window.isVisible()

        in_tray.commands["activate_window"]()

        assert in_tray.window.isMaximized()


class TestAway:
    @pytest.fixture
    def tray_player(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/close_to_tray", True)
        player.window.show()

        return player

    def test_said_both_ways(self, tray_player):
        tray_player.window.close()
        tray_player.commands["activate_window"]()

        assert tray_player.away == [True, False]

    def test_videos_paused_and_played_again(self, tray_player):
        playing = FakeVideo()
        paused = FakeVideo(is_paused=True)
        tray_player.ctx.video_blocks.extend((playing, paused))

        tray_player.window.close()

        assert tray_player.paused == 1

        tray_player.commands["activate_window"]()

        assert playing.unpaused_by == [False]
        assert paused.unpaused_by == []

    def test_videos_left_playing(self, tray_player):
        tray_player.manager.set_pause_minimized(False)

        tray_player.window.close()

        assert tray_player.paused == 0

    def test_pictures_off_and_back_on(self, settings, tray_player):
        settings.set("player/tray_stop_video", True)

        tray_player.window.close()

        assert tray_player.decoding == [True]

        tray_player.commands["activate_window"]()

        assert tray_player.decoding == [True, False]

    def test_pictures_left_on(self, tray_player):
        tray_player.window.close()
        tray_player.commands["activate_window"]()

        assert tray_player.decoding == []


class TestTaskbar:
    def test_button_kept(self, player):
        player.manager.apply_taskbar()

        assert player.taskbar[-1] == (False, False)

    def test_button_gone_before_every_show(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/hide_taskbar", True)

        player.window.show()

        assert player.taskbar[-1] == (True, True)

    def test_button_kept_with_no_tray_to_come_back_from(self, settings, player):
        settings.set("player/tray_icon", True)
        settings.set("player/hide_taskbar", True)
        player.ctx.is_tray_shown = False

        player.manager.apply_taskbar()

        assert player.taskbar[-1] == (False, False)


class FakeKeepAwake:
    def __init__(self):
        self.mode = KeepAwakeMode.NONE

    def set_mode(self, mode):
        self.mode = mode


class TestKeepAwake:
    @pytest.fixture
    def screensaver(self, settings, monkeypatch):
        monkeypatch.setattr(screensaver_module, "KeepAwake", FakeKeepAwake)

        return ScreensaverManager(context=SimpleNamespace(), parent=None)

    def test_nothing_playing(self, screensaver):
        screensaver.screensaver_check(0)

        assert screensaver.keepawake.mode is KeepAwakeMode.NONE

    def test_playing_on_screen(self, screensaver):
        screensaver.screensaver_check(2)

        assert screensaver.keepawake.mode is KeepAwakeMode.SCREEN

    def test_playing_away_keeps_only_the_system_awake(self, screensaver):
        screensaver.screensaver_check(2)
        screensaver.set_away(True)

        assert screensaver.keepawake.mode is KeepAwakeMode.SLEEP

        screensaver.set_away(False)

        assert screensaver.keepawake.mode is KeepAwakeMode.SCREEN

    def test_turned_off(self, settings, screensaver):
        settings.set("player/inhibit_screensaver", False)

        screensaver.screensaver_check(2)

        assert screensaver.keepawake.mode is KeepAwakeMode.NONE

    def test_the_setting_is_no_count_of_videos(self, screensaver):
        """The setting changed says nothing of what plays."""

        screensaver.refresh(1)

        assert screensaver.keepawake.mode is KeepAwakeMode.NONE


class TestStartedAgain:
    def _listener(self):
        listener = Listener()

        said = []
        listener.activate.connect(lambda: said.append("activate"))
        listener.open_files.connect(lambda files: said.append(files))

        return listener, said

    def test_with_no_files_shows_the_window(self):
        listener, said = self._listener()

        listener._handle_input_data([])

        assert said == ["activate"]

    def test_with_files_shows_the_window_first(self):
        listener, said = self._listener()

        listener._handle_input_data(["a.mp4"])

        assert said == ["activate", ["a.mp4"]]

    def test_a_ping_is_not_a_launch(self):
        listener, said = self._listener()

        listener._handle_input_data("ping")

        assert said == []


class TestTrayIcon:
    @pytest.fixture
    def tray(self, settings):
        calls = []

        ctx = SimpleNamespace(
            commands=SimpleNamespace(
                is_window_away=lambda: ctx.is_away,
                toggle_window=lambda: calls.append("toggle"),
                quit=lambda: calls.append("quit"),
                activate_window=lambda: calls.append("activate"),
            ),
            is_away=False,
        )

        manager = TrayManager(context=ctx, parent=None)
        manager.calls = calls

        yield manager

        manager.cleanup()

    def test_none_out_of_the_box(self, tray):
        tray.apply_settings()

        assert tray._icon is None
        assert not tray.is_shown()

    def test_put_up_and_taken_down(self, settings, tray):
        changed = []
        tray.changed.connect(lambda: changed.append(True))

        settings.set("player/tray_icon", True)
        tray.apply_settings()

        assert tray._icon is not None
        assert tray._icon.isVisible()

        settings.set("player/tray_icon", False)
        tray.apply_settings()

        assert tray._icon is None
        assert changed == [True, True]

    def test_menu_says_show_or_hide(self, settings, tray):
        settings.set("player/tray_icon", True)
        tray.apply_settings()

        tray._update_menu()
        assert tray._show_action.text() == "Hide"

        tray._ctx.is_away = True
        tray._update_menu()
        assert tray._show_action.text() == "Show"

    def test_menu_waits_for_a_dialog(self, settings, tray, monkeypatch):
        settings.set("player/tray_icon", True)
        tray.apply_settings()
        monkeypatch.setattr(
            QApplication, "activeModalWidget", staticmethod(lambda: QWidget())
        )

        tray._update_menu()

        assert not tray._show_action.isEnabled()
        assert not tray._quit_action.isEnabled()

        tray._quit()

        assert tray.calls == []

    @pytest.mark.skipif(
        tray_module.env.IS_MACOS, reason="macOS opens the menu on a click"
    )
    def test_clicked(self, settings, tray):
        settings.set("player/tray_icon", True)
        tray.apply_settings()

        tray._on_activated(QSystemTrayIcon.Trigger)
        tray._on_activated(QSystemTrayIcon.Context)

        assert tray.calls == ["toggle"]

    def test_note_said_once(self, settings, tray, monkeypatch):
        settings.set("player/tray_icon", True)
        tray.apply_settings()

        monkeypatch.setattr(
            QSystemTrayIcon, "supportsMessages", staticmethod(lambda: True)
        )
        said = []
        tray._icon.showMessage = lambda *args: said.append(args)

        tray.show_note()
        tray.show_note()

        assert len(said) == 1
        assert settings.get("player/tray_note_shown") is True


def _block(is_paused=False, track_id=0, audio=True, tracks=(0,)):
    block = Mock()
    block.is_video_initialized = True
    block.is_live = False
    block.time = 5000
    block._is_video_stopped_in_tray = False
    block.video_params = Video(uri=URI, is_paused=is_paused, video_track_id=track_id)
    block.video_tracks = dict.fromkeys(tracks)
    block.audio.tracks = {1: None} if audio else {}

    return block


class TestPictureOff:
    def test_off_and_back_on(self):
        block = _block(track_id=3, tracks=(3,))

        VideoBlock.set_video_decoding_stopped(block, True)

        block.video_driver.set_video_track.assert_called_once_with(DISABLED_TRACK)
        # what is saved stays as it was
        assert block.video_params.video_track_id == 3

        VideoBlock.set_video_decoding_stopped(block, False)

        block.video_driver.set_video_track.assert_called_with(3)
        # from a key frame, which 10-bit HEVC on D3D11 needs to come back
        block.video_driver.set_time.assert_called_once_with(5000)

    def test_live_back_on_with_no_seek(self):
        block = _block()
        block.is_live = True

        VideoBlock.set_video_decoding_stopped(block, True)
        VideoBlock.set_video_decoding_stopped(block, False)

        block.video_driver.set_video_track.assert_called_with(0)
        block.video_driver.set_time.assert_not_called()

    def test_paused_left_alone(self):
        block = _block(is_paused=True)

        VideoBlock.set_video_decoding_stopped(block, True)

        block.video_driver.set_video_track.assert_not_called()

    def test_with_no_sound_left_alone(self):
        block = _block(audio=False)

        VideoBlock.set_video_decoding_stopped(block, True)

        block.video_driver.set_video_track.assert_not_called()

    def test_switched_off_by_hand_stays_off(self):
        block = _block(track_id=DISABLED_TRACK)

        VideoBlock.set_video_decoding_stopped(block, True)
        VideoBlock.set_video_decoding_stopped(block, False)

        block.video_driver.set_video_track.assert_not_called()

    def test_no_track_read_back_takes_the_first(self):
        block = _block(track_id=None, tracks=(4, 2))

        VideoBlock.set_video_decoding_stopped(block, True)
        VideoBlock.set_video_decoding_stopped(block, False)

        block.video_driver.set_video_track.assert_called_with(2)

    def test_paused_meanwhile_shows_where_it_is(self):
        block = _block()

        VideoBlock.set_video_decoding_stopped(block, True)
        block.video_params.playback_state = VideoInitialState.PAUSED
        VideoBlock.set_video_decoding_stopped(block, False)

        block.video_driver.set_time.assert_called_once_with(5000)


@pytest.fixture
def make_dialog(settings, _no_real_cache, monkeypatch):
    monkeypatch.setattr(
        settings_dialog.QSystemTrayIcon,
        "isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(general_fields, "taskbar_hiding_blocker", lambda: None)

    made = []

    def _make():
        dialog = SettingsDialog(None)
        made.append(dialog)

        return dialog

    yield _make

    for dialog in made:
        dialog.close()
        dialog.deleteLater()

    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class TestSettings:
    def test_greyed_out_with_no_icon(self, make_dialog):
        dialog = make_dialog()

        assert dialog.widget("player/tray_icon").isEnabled()
        assert not dialog.widget("player/close_to_tray").isEnabled()

        dialog.widget("player/tray_icon").setChecked(True)

        assert dialog.widget("player/close_to_tray").isEnabled()
        assert dialog.widget("player/tray_stop_video").isEnabled()

    def test_no_taskbar_button_minimizes_to_the_tray(self, settings, make_dialog):
        dialog = make_dialog()
        dialog.widget("player/tray_icon").setChecked(True)

        dialog.widget("player/hide_taskbar").setChecked(True)

        assert dialog.widget("player/minimize_to_tray").isChecked()
        assert not dialog.widget("player/minimize_to_tray").isEnabled()

        dialog.save_settings()

        # ticked for it, not by the user
        assert settings.get("player/minimize_to_tray") is False
        assert settings.get("player/hide_taskbar") is True

        dialog.widget("player/hide_taskbar").setChecked(False)

        assert not dialog.widget("player/minimize_to_tray").isChecked()
        assert dialog.widget("player/minimize_to_tray").isEnabled()

    def test_saved(self, settings, make_dialog):
        dialog = make_dialog()

        dialog.widget("player/tray_icon").setChecked(True)
        dialog.widget("player/close_to_tray").setChecked(True)
        dialog.widget("player/tray_stop_video").setChecked(True)
        dialog.save_settings()

        assert settings.get("player/tray_icon") is True
        assert settings.get("player/close_to_tray") is True
        assert settings.get("player/tray_stop_video") is True

    def test_no_tray_on_the_desktop(self, settings, make_dialog, monkeypatch):
        settings.set("player/tray_icon", True)
        monkeypatch.setattr(
            settings_dialog.QSystemTrayIcon,
            "isSystemTrayAvailable",
            staticmethod(lambda: False),
        )

        dialog = make_dialog()

        assert not dialog.widget("player/tray_icon").isEnabled()
        assert not dialog.widget("player/close_to_tray").isEnabled()
        assert not dialog.playerTrayUnavailable.isHidden()

    @pytest.mark.parametrize(
        ("blocker", "said"),
        [
            (TaskbarHidingBlocker.WAYLAND, "Wayland"),
            (TaskbarHidingBlocker.GNOME, "GNOME"),
        ],
    )
    def test_no_taskbar_hiding(self, settings, make_dialog, monkeypatch, blocker, said):
        settings.set("player/tray_icon", True)
        monkeypatch.setattr(general_fields, "taskbar_hiding_blocker", lambda: blocker)

        dialog = make_dialog()

        assert dialog.widget("player/close_to_tray").isEnabled()
        assert not dialog.widget("player/hide_taskbar").isEnabled()
        assert said in dialog.widget("player/hide_taskbar").toolTip()

    def test_no_taskbar_hiding_leaves_minimize_alone(
        self, settings, make_dialog, monkeypatch
    ):
        """Turned on where it was possible, it no longer ticks minimize."""

        settings.set("player/tray_icon", True)
        settings.set("player/hide_taskbar", True)
        monkeypatch.setattr(
            general_fields,
            "taskbar_hiding_blocker",
            lambda: TaskbarHidingBlocker.GNOME,
        )

        dialog = make_dialog()

        assert not dialog.widget("player/minimize_to_tray").isChecked()
        assert dialog.widget("player/minimize_to_tray").isEnabled()


class TestTaskbarHidingBlocker:
    @pytest.fixture
    def on_linux(self, monkeypatch):
        monkeypatch.setattr(taskbar_module.env, "IS_WINDOWS", False)
        monkeypatch.setattr(taskbar_module.env, "IS_MACOS", False)

    def _platform(self, monkeypatch, name):
        monkeypatch.setattr(
            taskbar_module.QGuiApplication, "platformName", staticmethod(lambda: name)
        )

    def _wm(self, monkeypatch, name):
        monkeypatch.setattr(taskbar_module, "_x11_wm_name", lambda: name)

    def test_wayland(self, on_linux, monkeypatch):
        self._platform(monkeypatch, "wayland")

        assert taskbar_module.taskbar_hiding_blocker() is TaskbarHidingBlocker.WAYLAND

    @pytest.mark.parametrize("wm", ["gnome shell", "mutter (muffin)", "mutter"])
    def test_gnome_and_its_mutter(self, on_linux, monkeypatch, wm):
        self._platform(monkeypatch, "xcb")
        self._wm(monkeypatch, wm)

        assert taskbar_module.taskbar_hiding_blocker() is TaskbarHidingBlocker.GNOME

    @pytest.mark.parametrize("wm", ["kwin", "xfwm4", ""])
    def test_others(self, on_linux, monkeypatch, wm):
        self._platform(monkeypatch, "xcb")
        self._wm(monkeypatch, wm)

        assert taskbar_module.taskbar_hiding_blocker() is None
        assert taskbar_module.is_taskbar_hiding_available()


def test_window_state_keeps_maximized_while_in_the_tray(settings, player):
    settings.set("player/tray_icon", True)
    settings.set("player/close_to_tray", True)
    player.window.showMaximized()
    player.window.close()

    assert player.manager.window_state().is_maximized
    assert not player.manager.window_state().is_fullscreen


def test_asked_to_quit_as_macos_asks_on_cmd_q():
    """Cmd+Q comes as the application's Quit event, before any close."""

    said = []
    watcher = window_state_module._QuitWatcher(lambda: said.append(True))

    watcher.eventFilter(None, QEvent(QEvent.Type(window_state_module.QUIT_EVENT)))
    watcher.eventFilter(None, QEvent(QEvent.Close))

    assert said == [True]
