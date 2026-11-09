"""The performance settings: what they come to, and dragging along the timeline."""

import dataclasses
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QEvent, QPointF, QSettings, Qt
from PyQt5.QtGui import QColor, QMouseEvent
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.video import Video
from gridplayer.mpv_player.performance import (
    AUTO_BALANCED_FROM_PX,
    AUTO_HIGH_FROM_PX,
    QUALITY_OPTIONS,
    auto_quality,
    hwdec_value,
    is_better,
    is_falling_behind,
    stepped_down,
)
from gridplayer.params.static import (
    GpuChoice,
    HardwareDecoding,
    VideoEndAction,
    VideoInitialState,
    VideoQuality,
)
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.settings import Settings
from gridplayer.utils.gpu_adapters import GpuAdapter, resolve_gpu_adapter
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_overlay_elements import OverlayProgressBar

LENGTH = 20000

WEAK = GpuAdapter("Weak Card", 512)
STRONG = GpuAdapter("Strong Card", 8192)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


class TestQualityPresets:
    def test_every_preset_sets_the_same_options(self):
        names = {frozenset(options) for options in QUALITY_OPTIONS.values()}

        assert len(names) == 1

    def test_auto_is_not_a_preset_of_its_own(self):
        assert set(QUALITY_OPTIONS) == set(VideoQuality) - {VideoQuality.AUTO}

    @pytest.mark.parametrize(
        ("pixels", "expected"),
        [
            (0, VideoQuality.FAST),
            (AUTO_BALANCED_FROM_PX - 1, VideoQuality.FAST),
            (AUTO_BALANCED_FROM_PX, VideoQuality.BALANCED),
            (AUTO_HIGH_FROM_PX - 1, VideoQuality.BALANCED),
            (AUTO_HIGH_FROM_PX, VideoQuality.HIGH),
            (1e9, VideoQuality.HIGH),
        ],
    )
    def test_auto_goes_by_how_big_it_is_shown(self, pixels, expected):
        assert auto_quality(pixels) is expected

    def test_a_grid_of_nine_on_a_1440p_screen_is_fast(self):
        assert auto_quality(853 * 480) is VideoQuality.FAST

    def test_a_grid_of_four_on_a_1440p_screen_is_balanced(self):
        assert auto_quality(1280 * 720) is VideoQuality.BALANCED

    def test_stepping_down_stops_at_the_bottom(self):
        assert stepped_down(VideoQuality.HIGH, 1) is VideoQuality.BALANCED
        assert stepped_down(VideoQuality.HIGH, 9) is VideoQuality.FAST

    def test_better(self):
        assert is_better(VideoQuality.HIGH, VideoQuality.FAST)
        assert not is_better(VideoQuality.FAST, VideoQuality.FAST)


class TestFallingBehind:
    def test_most_frames_lost(self):
        assert is_falling_behind(100, 3, 60, 1, 60)

    def test_a_few_lost_is_nothing(self):
        assert not is_falling_behind(5, 3, 60, 1, 60)

    def test_nothing_lost(self):
        assert not is_falling_behind(0, 3, 60, 1, 60)

    def test_the_count_starting_over_at_a_loop(self):
        assert not is_falling_behind(-400, 3, 60, 1, 60)

    def test_more_frames_than_the_screen_shows(self):
        assert not is_falling_behind(90, 3, 60, 1, 30)

    def test_fast_playback_counts_as_more_frames(self):
        assert not is_falling_behind(180, 3, 60, 2, 60)

    def test_a_video_of_unknown_rate(self):
        assert not is_falling_behind(100, 3, None, 1, 60)

    def test_a_screen_of_unknown_rate(self):
        assert is_falling_behind(100, 3, 60, 1, None)


class TestHwdec:
    @pytest.mark.parametrize(
        ("mode", "needs_memory", "expected"),
        [
            (HardwareDecoding.AUTO, False, "auto-safe"),
            (HardwareDecoding.AUTO, True, "auto-copy-safe"),
            (HardwareDecoding.COPY, False, "auto-copy-safe"),
            (HardwareDecoding.COPY, True, "auto-copy-safe"),
            (HardwareDecoding.OFF, False, "no"),
            (HardwareDecoding.OFF, True, "no"),
        ],
    )
    def test_value(self, mode, needs_memory, expected):
        assert hwdec_value(mode, needs_memory) == expected


class TestGpuChoice:
    ADAPTERS = (WEAK, STRONG)

    @pytest.mark.parametrize(
        ("choice", "expected"),
        [
            (GpuChoice.AUTO, None),
            (GpuChoice.HIGH_PERFORMANCE, "Strong Card"),
            (GpuChoice.POWER_SAVING, "Weak Card"),
            ("Weak Card", "Weak Card"),
            ("Strong Card", "Strong Card"),
        ],
    )
    def test_resolved(self, choice, expected):
        assert resolve_gpu_adapter(choice, self.ADAPTERS) == expected

    def test_a_card_no_longer_there_is_never_asked_for(self):
        assert resolve_gpu_adapter("Gone Card", self.ADAPTERS) is None

    @pytest.mark.parametrize(
        "choice", [GpuChoice.HIGH_PERFORMANCE, GpuChoice.POWER_SAVING, "Weak Card"]
    )
    def test_nothing_to_choose_from(self, choice):
        assert resolve_gpu_adapter(choice, ()) is None

    def test_the_setting_keeps_a_card_by_name(self):
        Settings().set("player/gpu_adapter", "Strong Card")

        assert Settings().get("player/gpu_adapter") == "Strong Card"


class TestSettings:
    @pytest.mark.parametrize(
        ("key", "default"),
        [
            ("player/video_quality", VideoQuality.AUTO),
            ("player/gpu_adapter", GpuChoice.AUTO),
            ("player/hardware_decoding", HardwareDecoding.AUTO),
            ("player/fast_scrubbing", True),
        ],
    )
    def test_defaults(self, key, default):
        assert Settings().get(key) == default

    def test_quality_is_saved(self):
        Settings().set("player/video_quality", VideoQuality.MAXIMUM)

        assert Settings().get("player/video_quality") is VideoQuality.MAXIMUM


def _mouse(kind, x, button, buttons):
    return QMouseEvent(kind, QPointF(x, 5), button, buttons, Qt.NoModifier)


class TestDraggingTheBar:
    @pytest.fixture
    def bar(self, mocker):
        parent = QWidget()

        bar = OverlayProgressBar(parent=parent)
        bar.setAttribute(Qt.WA_DontShowOnScreen)
        bar.resize(200, 23)
        bar.color = QColor(Qt.white)

        mocker.patch(
            "gridplayer.widgets.video_overlay_elements.QGuiApplication.mouseButtons",
            return_value=Qt.LeftButton,
        )

        bar.heard = []
        bar.scrub_changed.connect(lambda on: bar.heard.append(("scrub", on)))
        bar.position_changed.connect(lambda at: bar.heard.append(("at", at)))

        yield bar

        del parent

    @staticmethod
    def _press(bar, x):
        bar.mousePressEvent(
            _mouse(QEvent.MouseButtonPress, x, Qt.LeftButton, Qt.LeftButton)
        )

    @staticmethod
    def _move(bar, x):
        bar.mouseMoveEvent(_mouse(QEvent.MouseMove, x, Qt.NoButton, Qt.LeftButton))

    @staticmethod
    def _release(bar, x):
        bar.mouseReleaseEvent(
            _mouse(QEvent.MouseButtonRelease, x, Qt.LeftButton, Qt.NoButton)
        )

    def test_a_click_is_no_drag(self, bar):
        self._press(bar, 50)
        self._release(bar, 50)

        assert bar.heard == [("at", 0.25)]

    def test_a_drag_says_so_before_it_moves(self, bar):
        self._press(bar, 50)
        self._move(bar, 100)

        assert bar.heard == [("at", 0.25), ("scrub", True), ("at", 0.5)]

    def test_moves_faster_than_the_video_can_follow_come_down_to_the_last(self, bar):
        self._move(bar, 100)
        bar.heard.clear()

        for x in (101, 102, 103, 120):
            self._move(bar, x)

        assert bar.heard == []

        bar._scrub_to_latest()

        assert bar.heard == [("at", 0.6)]

    def test_nothing_new_nothing_said(self, bar):
        self._move(bar, 100)
        bar.heard.clear()

        bar._scrub_to_latest()

        assert bar.heard == []

    def test_held_from_press_to_release(self, bar):
        assert not bar.is_held

        self._press(bar, 50)
        assert bar.is_held

        self._release(bar, 50)
        assert not bar.is_held

    def test_it_ends_before_the_last_position(self, bar):
        self._move(bar, 100)
        bar.heard.clear()

        self._release(bar, 150)

        assert bar.heard == [("scrub", False), ("at", 0.75)]

    def test_let_go_past_the_end_lands_on_the_end(self, bar):
        self._move(bar, 100)
        bar.heard.clear()

        self._release(bar, 900)

        assert bar.heard == [("scrub", False), ("at", 1.0)]

    def test_a_release_that_went_elsewhere_is_made_up_for(self, bar):
        self._move(bar, 100)
        bar.heard.clear()

        self._press(bar, 20)

        assert bar.heard == [("scrub", False), ("at", 0.1)]


class _ShortFrame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=LENGTH
        )


def _context():
    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1
    context.synced_view = None
    context.lists = MediaListsRegistry()

    return context


@pytest.fixture
def block(tmp_path, mocker):
    parent = QWidget()

    video_file = tmp_path / "movie.mp4"
    video_file.touch()

    block = VideoBlock(video_driver=_ShortFrame, context=_context(), parent=parent)

    block.set_video(
        Video(
            uri=video_file,
            playback_state=VideoInitialState.PAUSED,
            end_action=VideoEndAction.STOP,
        )
    )

    assert block.is_video_initialized

    block.exact = mocker.spy(block.video_driver, "set_time")
    block.keyframe = mocker.spy(block.video_driver, "set_time_keyframe")

    yield block

    block.cleanup()
    block.url_resolver.cleanup()


def _reported(block, time_ms):
    block._seek_settle_timer.stop()
    block.video_driver.time_changed.emit(time_ms)
    QApplication.processEvents()


class TestScrubbingABlock:
    def test_a_plain_seek_is_exact(self, block):
        block.seek(5000)

        block.exact.assert_called_once_with(5000)
        block.keyframe.assert_not_called()

    def test_while_dragging_it_goes_by_keyframes(self, block):
        block._on_scrub_changed(True)
        block.seek(5000)

        block.keyframe.assert_called_once_with(5000)
        block.exact.assert_not_called()

    def test_after_the_drag_it_is_exact_again(self, block):
        block._on_scrub_changed(True)
        block.seek(5000)
        block._on_scrub_changed(False)
        block.seek(5200)

        block.exact.assert_called_once_with(5200)

    def test_the_setting_turns_it_off(self, block):
        Settings().set("player/fast_scrubbing", False)

        block._on_scrub_changed(True)
        block.seek(5000)

        block.exact.assert_called_once_with(5000)
        block.keyframe.assert_not_called()

    def test_a_stream_that_turns_seeks_down_stays_exact(self, block):
        block.stream.is_adaptive = True

        block._on_scrub_changed(True)
        block.seek(5000)

        block.exact.assert_called_once_with(5000)

    def test_followers_are_told(self, block):
        heard = []
        block.sync_scrubbing.connect(heard.append)

        block._on_scrub_changed(True)
        block._on_scrub_changed(False)

        assert heard == [True, False]

    def test_landing_short_of_a_loop_is_not_sent_back_mid_drag(self, block):
        block.loop.set_start_time(12000)

        block._on_scrub_changed(True)
        block.seek(12000)
        block.keyframe.reset_mock()
        _reported(block, 9000)
        _reported(block, 9010)

        block.keyframe.assert_not_called()
        block.exact.assert_not_called()

    def test_the_overlay_stays_while_a_bar_is_held(self, block, mocker):
        mocker.patch(
            "gridplayer.widgets.video_block.QApplication.mouseButtons",
            return_value=Qt.LeftButton,
        )
        block._ctx.is_overlay_hide_on_timeout = True
        block.overlay.progress_bar.is_held = True
        hide = mocker.spy(block.overlay, "hide")

        block.hide_overlay()

        hide.assert_not_called()
        assert block.overlay_hide_timer.isActive()

    def test_the_overlay_goes_once_the_bar_is_let_go(self, block, mocker):
        mocker.patch(
            "gridplayer.widgets.video_block.QApplication.mouseButtons",
            return_value=Qt.NoButton,
        )
        block._ctx.is_overlay_hide_on_timeout = True
        block._ctx.is_drag_ui = False
        block.overlay.progress_bar.is_held = True
        hide = mocker.spy(block.overlay, "hide")

        block.hide_overlay()

        hide.assert_called()

    def test_a_keyframe_far_back_is_no_pass_coming_round_mid_drag(self, block):
        block._on_scrub_changed(True)
        block.seek(19500)
        _reported(block, 5000)
        _reported(block, 5010)

        assert not block.is_stopped
