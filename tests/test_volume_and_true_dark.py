"""Volume past 100%, and the dark theme in black."""

import dataclasses
import itertools
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QPoint, QSettings, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPalette
from PyQt5.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from gridplayer.models.media_list import MediaList
from gridplayer.models.video import Video
from gridplayer.params import theme
from gridplayer.params.menu import SECTIONS
from gridplayer.params.static import (
    ColorScheme,
    VideoEndAction,
    VideoInitialState,
)
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.settings import Settings
from gridplayer.utils import darkmode
from gridplayer.utils.drop_zone import DropZone
from gridplayer.widgets.settings_controls import FIELD_MIN_LIGHTNESS, fit_fields
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_audio import VOLUME_FULL_SNAP
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_overlay_elements import (
    BAR_PROGRESS_COLOR,
    VOLUME_PAST_FULL_COLOR,
    OverlayBorder,
    OverlayVolumeBar,
    OverlayVolumeLabel,
)

PAST_FULL = QColor(VOLUME_PAST_FULL_COLOR)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


class _Frame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=20000
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

    block = VideoBlock(video_driver=_Frame, context=_context(), parent=parent)

    block.set_video(
        Video(
            uri=video_file,
            playback_state=VideoInitialState.PAUSED,
            end_action=VideoEndAction.STOP,
        )
    )

    block.sent = mocker.spy(block.video_driver, "audio_set_volume")

    yield block

    block.cleanup()
    block.url_resolver.cleanup()


class TestVolume:
    def test_the_default_limit_is_past_100(self):
        assert Settings().get("player/max_volume") > 100

    def test_set_past_100(self, block):
        block.audio.set_volume(1.25)

        block.sent.assert_called_with(1.25)
        assert block.video_params.volume == 1.25

    def test_stops_at_the_limit(self, block):
        Settings().set("player/max_volume", 120)

        block.audio.set_volume(3.0)

        assert block.video_params.volume == 1.2

    def test_a_limit_lowered_since_is_kept_to(self, block):
        block.audio.set_volume(1.5)

        Settings().set("player/max_volume", 100)
        block.audio.set_volume(block.video_params.volume)

        assert block.video_params.volume == 1.0

    def test_never_below_nothing(self, block):
        block.audio.set_volume(-1)

        assert block.video_params.volume == 0

    def test_the_top_of_the_bar_is_the_limit(self, block):
        block.audio.set_volume_from_bar(1.0)

        assert block.video_params.volume == 1.5

    def test_the_bar_is_shown_against_the_limit(self, block):
        heard = []
        block.volume_change.connect(heard.append)

        block.audio.set_volume(0.75)

        assert heard == [0.5]

    def test_the_bar_is_told_where_100_is(self, block):
        heard = []
        block.volume_full_mark_change.connect(heard.append)

        block.audio.set_volume(1.0)

        assert heard == [pytest.approx(1 / 1.5)]

    def test_near_the_mark_is_on_it(self, block):
        block.audio.set_volume_from_bar(1.01 / 1.5)

        assert block.video_params.volume == 1.0

    def test_a_step_up_goes_past_100(self, block):
        block.audio.set_volume(1.0)

        block.audio.volume_increase()

        assert block.video_params.volume == 1.05

    def test_a_step_up_stops_at_the_limit(self, block):
        block.audio.set_volume(1.5)

        block.audio.volume_increase()

        assert block.video_params.volume == 1.5

    def test_100_as_the_limit_is_as_it_always_was(self, block):
        Settings().set("player/max_volume", 100)

        block.audio.set_volume_from_bar(1.0)

        assert block.video_params.volume == 1.0


def _bar_image(bar):
    image = QImage(bar.size(), QImage.Format_RGB32)
    image.fill(QColor("#101010"))

    painter = QPainter(image)
    bar.render(painter, QPoint(0, 0))
    painter.end()

    return image


class TestVolumeBarMark:
    @pytest.fixture
    def bar(self):
        bar = OverlayVolumeBar()
        bar.setAttribute(Qt.WA_DontShowOnScreen)
        bar.resize(23, 90)
        bar.color = QColor(Qt.white)

        yield bar

    @staticmethod
    def _row(image, y):
        return image.pixel(image.width() // 2, y)

    def test_marked_where_it_goes_past_100(self, bar):
        bar.full_mark = 2 / 3

        image = _bar_image(bar)

        assert self._row(image, 30) != self._row(image, 20)

    def test_not_marked_where_100_is_the_top(self, bar):
        image = _bar_image(bar)

        assert self._row(image, 30) == self._row(image, 20)


class TestVolumeBarPast100:
    @pytest.fixture
    def bar(self):
        bar = OverlayVolumeBar()
        bar.setAttribute(Qt.WA_DontShowOnScreen)
        bar.resize(23, 90)
        bar.color = QColor(Qt.white)
        bar.full_mark = 2 / 3

        yield bar

    @staticmethod
    def _is_past_full_color(color):
        return abs(color.red() - PAST_FULL.red()) < 8 and abs(
            color.green() - PAST_FULL.green()
        ) < 8

    def test_filled_past_100_in_its_own_colour(self, bar):
        bar.position = 1.0

        image = _bar_image(bar)

        assert self._is_past_full_color(QColor(image.pixel(11, 15)))
        assert not self._is_past_full_color(QColor(image.pixel(11, 60)))

    def test_the_part_past_100_shows_with_nothing_there_yet(self, bar):
        bar.position = 0.3

        image = _bar_image(bar)

        assert image.pixel(11, 15) != image.pixel(11, 45)

    def test_no_colour_where_100_is_the_top(self, bar):
        bar.full_mark = 1.0
        bar.position = 1.0

        assert not self._is_past_full_color(QColor(_bar_image(bar).pixel(11, 15)))

    def test_parts_cover_the_bar_once(self, bar):
        bar.position = 0.8

        parts = [rect for rect, _ in bar._filled_parts(is_hovered=False)]
        rows = sorted((r.top(), r.top() + r.height()) for r in parts)

        assert rows[0][0] == 0
        assert rows[-1][1] == bar.height()
        assert all(a[1] == b[0] for a, b in itertools.pairwise(rows))


class TestVolumeNumber:
    def test_said_in_percent_against_the_limit(self, block):
        block.audio.set_volume(1.2)

        assert block.overlay.label_volume.text == "120%"

    def test_at_100(self, block):
        block.audio.set_volume(1.0)

        assert block.overlay.label_volume.text == "100%"

    def test_snap_is_light(self, block):
        block.audio.set_volume_from_bar(1 / 1.5 + VOLUME_FULL_SNAP * 0.9)

        assert block.video_params.volume == 1.0

    def test_past_the_snap_it_goes_where_it_is_put(self, block):
        block.audio.set_volume_from_bar(1 / 1.5 + VOLUME_FULL_SNAP * 1.5)

        assert block.video_params.volume > 1.0

    def test_keeps_its_width_whatever_it_says(self):
        label = OverlayVolumeLabel()

        label.text = "5%"
        label.update_visuals()
        narrow = label.minimumWidth()

        label.text = "150%"
        label.update_visuals()

        assert label.minimumWidth() == narrow


class TestOverlayFollowsTheme:
    @pytest.fixture
    def palette(self):
        application = QApplication.instance()
        real = application.palette()

        def use(base, text):
            palette = QPalette(real)
            palette.setColor(QPalette.Base, QColor(base))
            palette.setColor(QPalette.Text, QColor(text))
            application.setPalette(palette)

        yield use

        application.setPalette(real)

    @pytest.fixture
    def bar(self):
        bar = OverlayVolumeBar()
        bar.color = QColor("#ffffff")

        return bar

    def test_default_colour_takes_the_dark_themes(self, bar, palette):
        palette("#000000", "#eeeeee")

        assert bar.color.name() == "#000000"
        assert bar.color_progress.name() == "#eeeeee"

    def test_grey_theme_too(self, bar, palette):
        palette("#3a3a3a", "#eeeeee")

        assert bar.color.name() == "#3a3a3a"

    def test_light_theme_is_as_it_was(self, bar, palette):
        palette("#ffffff", "#000000")

        assert bar.color.name() == "#ffffff"
        assert bar.color_progress.name() == BAR_PROGRESS_COLOR

    def test_a_colour_picked_stays(self, bar, palette):
        palette("#000000", "#eeeeee")
        bar.color = QColor("#336699")

        assert bar.color.name() == "#336699"
        assert bar.color_progress.name() == BAR_PROGRESS_COLOR

    def test_the_active_ring_shows_on_black(self, palette):
        palette("#000000", "#eeeeee")
        ring = OverlayBorder()
        ring.color = QColor("#ffffff")

        assert ring.color.name() == "#eeeeee"


class TestDuplicate:
    @pytest.fixture
    def setup(self, tmp_path):
        video_file = tmp_path / "movie.mp4"
        video_file.touch()

        video = Video(uri=video_file, is_muted=False, current_position=100)

        block = SimpleNamespace(
            video_params=video, time=7000, bookmarks=("mark",)
        )

        context = MagicMock()
        context.active_block = block
        context.lists.get.return_value = None

        manager = SimpleNamespace(_ctx=context)

        return manager, block, context

    @staticmethod
    def _copy(context) -> Video:
        return context.commands.layout_drop.call_args.args[0][0]

    def test_goes_right_after_the_original(self, setup):
        manager, block, context = setup

        VideoBlocksManager.cmd_duplicate_video(manager)

        args = context.commands.layout_drop.call_args.args

        assert args[1:] == (None, block, DropZone.AFTER, False)

    def test_is_a_video_of_its_own(self, setup):
        manager, block, context = setup

        VideoBlocksManager.cmd_duplicate_video(manager)

        assert self._copy(context).id != block.video_params.id
        assert self._copy(context).uri == block.video_params.uri

    def test_from_where_the_original_is_now(self, setup):
        manager, _block, context = setup

        VideoBlocksManager.cmd_duplicate_video(manager)

        assert self._copy(context).current_position == 7000

    def test_muted_so_they_do_not_play_over_each_other(self, setup):
        manager, block, context = setup

        VideoBlocksManager.cmd_duplicate_video(manager)

        assert self._copy(context).is_muted is True
        assert block.video_params.is_muted is False

    def test_a_list_of_its_own(self, setup):
        manager, block, context = setup
        media_list = MediaList()
        block.video_params.list_id = media_list.id
        context.lists.get.return_value = media_list
        context.lists.add.side_effect = lambda item: item

        VideoBlocksManager.cmd_duplicate_video(manager)

        assert self._copy(context).list_id != media_list.id

    def test_nothing_without_a_video(self, setup):
        manager, _block, context = setup
        context.active_block = None

        VideoBlocksManager.cmd_duplicate_video(manager)

        context.commands.layout_drop.assert_not_called()

    def test_not_while_its_list_is_still_being_read(self, setup):
        manager, block, context = setup
        block.video_params.read_as_list = True

        VideoBlocksManager.cmd_duplicate_video(manager)

        context.commands.layout_drop.assert_not_called()

    def test_in_the_menu_right_after_rename(self):
        section = next(s for s in SECTIONS.values() if "Rename" in s)

        assert section.index("Duplicate") == section.index("Rename") + 1


class _FakeSettings:
    def __init__(self, scheme):
        self.scheme = scheme

    def get(self, _key):
        return self.scheme


class TestTrueDark:
    @pytest.fixture
    def scheme(self, monkeypatch):
        def choose(picked):
            monkeypatch.setattr(darkmode, "Settings", lambda: _FakeSettings(picked))

        monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: False)

        return choose

    def test_it_is_a_dark_mode(self, scheme):
        scheme(ColorScheme.TRUE_DARK)

        assert darkmode.is_dark_mode() is True

    def test_it_is_black(self, scheme):
        scheme(ColorScheme.TRUE_DARK)

        colors = theme.current_colors()

        assert colors["window"] == "#000000"
        assert colors["base"] == "#000000"
        assert colors["background"] == "#000000"

    def test_grey_is_still_there(self, scheme):
        scheme(ColorScheme.DARK)

        assert theme.current_colors() is theme.THEME_DARK
        assert theme.current_colors()["window"] != "#000000"

    def test_light_is_still_there(self, scheme):
        scheme(ColorScheme.LIGHT)

        assert theme.current_colors() is theme.THEME_LIGHT

    def test_it_has_every_colour_the_others_have(self):
        assert set(theme.THEME_TRUE_DARK) == set(theme.THEME_DARK)

    def test_text_can_be_read_on_it(self):
        text = QColor(theme.THEME_TRUE_DARK["text"])

        assert text.lightness() > 200

    def test_it_is_remembered(self):
        Settings().set("player/color_scheme", ColorScheme.TRUE_DARK)

        assert Settings().get("player/color_scheme") is ColorScheme.TRUE_DARK

    def test_a_field_stands_out_on_a_black_card(self, scheme):
        card = QWidget()
        palette = card.palette()
        palette.setColor(palette.Active, palette.Base, QColor("#000000"))
        card.setPalette(palette)

        layout = QVBoxLayout(card)
        field = QLineEdit()
        layout.addWidget(field)

        fit_fields(card)

        assert field.palette().color(palette.Base).lightness() == FIELD_MIN_LIGHTNESS
