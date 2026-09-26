"""Screenshots: the name a frame is saved under, what of it is kept, and
where it goes.

The title in a file name is whatever the video is called, which is as often
a URL or a site's own name for a stream as it is a file name, so every
platform's idea of what a file can be called gets a say.
"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QEvent, QRect, QSettings, QSize
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS
from gridplayer.params.static import (
    ScreenshotFormat,
    VideoAspect,
    VideoCrop,
    VideoTransform,
    ViewParams,
)
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.settings import _Settings
from gridplayer.utils import screenshots
from gridplayer.utils.app_dir import ENV_USER_DATA_DIR
from gridplayer.utils.cookies import CookieStore
from gridplayer.utils.screenshots import (
    DEFAULT_STEM,
    MAX_STEM_LENGTH,
    ScreenshotJob,
    ScreenshotName,
    ScreenshotView,
    has_counter,
    position_txt,
    render_filename,
    reserve_path,
    sanitize_filename,
    save_screenshot,
    screenshots_dir,
    transformed_image,
    unknown_specifiers,
)
from gridplayer.widgets.video_block import VideoBlock

NOW = datetime(2026, 9, 24, 13, 5, 9, tzinfo=timezone.utc)


def _name(template="shot", title="clip.mkv", position_ms=0) -> ScreenshotName:
    return ScreenshotName(template, title, position_ms, NOW)


def _frame(width=32, height=16) -> QImage:
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor("red"))
    return image


def _frame_file(tmp_path, width=32, height=16) -> str:
    """A PNG where VLC leaves one: alone in a temp folder of its own."""

    folder = tmp_path / "vlc_tmp"
    folder.mkdir()

    path = folder / "snapshot.png"
    assert _frame(width, height).save(str(path), "PNG")

    return str(path)


class TestTheTemplate:
    """In the style of mpv's screenshot-template."""

    @pytest.mark.parametrize(
        ("template", "stem"),
        [
            ("%f", "clip.mkv"),
            ("%F", "clip"),
            ("%p", "01-02-03"),
            ("%P", "01-02-03.456"),
            ("%n", "0001"),
            ("%tY-%tm-%td %tH-%tM-%tS", "2026-09-24 13-05-09"),
            ("%ty", "26"),
            ("%D", "2026-09-24"),
            ("%T", "2026-09-24_13-05-09"),
            ("100%%", "100%"),
        ],
    )
    def test_each_specifier(self, template, stem):
        assert render_filename(template, "clip.mkv", 3_723_456, NOW) == stem

    def test_the_default_one(self):
        assert render_filename("%F_%P", "clip.mkv", 3_723_456, NOW) == (
            "clip_01-02-03.456"
        )

    def test_the_number_is_the_one_asked_for(self):
        assert render_filename("shot%n", "", 0, NOW, number=42) == "shot0042"

    @pytest.mark.parametrize("template", ["%x", "%tQ", "%t", "50%"])
    def test_what_nothing_fills_in_is_left_as_written(self, template):
        assert render_filename(template, "clip", 0, NOW) == template

    def test_a_url_title_can_be_a_file_name(self):
        stem = render_filename("%f", "https://example.com/live?id=1", 0, NOW)

        assert stem == "https___example.com_live_id=1"

    def test_the_extension_of_a_url_is_what_goes(self):
        """Not everything up to the last slash, as a path would have it."""

        stem = render_filename("%F", "https://example.com/v/clip.mp4", 0, NOW)

        assert stem == "https___example.com_v_clip"

    @pytest.mark.parametrize("title", ["My clip", "Part.2 of 3", "clip."])
    def test_what_is_no_extension_stays(self, title):
        assert render_filename("%F", title, 0, NOW) == sanitize_filename(title)

    def test_a_long_title_leaves_room_for_the_number(self):
        stem = render_filename("%f_%n", "x" * 500, 0, NOW, number=7)

        assert stem.endswith("_0007")

    def test_the_position_pads_hours(self):
        assert position_txt(0) == "00-00-00.000"
        assert position_txt(-5) == "00-00-00.000"
        assert position_txt(36_000_001) == "10-00-00.001"
        assert position_txt(36_000_001, with_ms=False) == "10-00-00"


def test_unknown_specifiers_are_found():
    assert unknown_specifiers("%F_%x_%tQ_%t") == ["%x", "%tQ", "%t"]
    assert unknown_specifiers("50%") == ["%"]
    assert unknown_specifiers("%f%F%p%P%n%D%T%tY%ty%tm%td%tH%tM%tS%%") == []


def test_the_counter_is_found():
    assert has_counter("shot%n")
    assert not has_counter("shot")
    assert not has_counter("100%%n")


class TestSanitizing:
    @pytest.mark.parametrize("char", [*'<>:"/\\|?*', "\x00", "\x01", "\x7f"])
    def test_forbidden_characters_are_replaced(self, char):
        assert sanitize_filename(f"a{char}b") == "a_b"

    def test_trailing_dots_and_spaces_go(self):
        """Windows drops them, and the file made is then not the one asked for."""

        assert sanitize_filename("clip. . ") == "clip"

    def test_nothing_left_falls_back_to_a_name(self):
        assert sanitize_filename("   ") == DEFAULT_STEM
        assert sanitize_filename("...") == DEFAULT_STEM

    @pytest.mark.parametrize("name", ["CON", "nul", "com1", "LPT9.old"])
    def test_windows_device_names_are_not_used_as_they_are(self, name):
        assert sanitize_filename(name) == f"_{name}"

    def test_a_long_name_is_cut_short(self):
        assert len(sanitize_filename("x" * 500)) == MAX_STEM_LENGTH

    def test_runs_of_whitespace_are_one_space(self):
        assert sanitize_filename("a \t\n b") == "a b"


class TestTheFolder:
    def test_empty_is_the_data_folder_as_it_is_now(self, tmp_path, monkeypatch):
        """Looked up when used, so a moved data folder takes it along."""

        monkeypatch.setenv(ENV_USER_DATA_DIR, str(tmp_path / "data"))

        assert screenshots_dir("") == tmp_path / "data" / "screenshots"
        assert screenshots_dir("  ") == tmp_path / "data" / "screenshots"

    def test_a_named_folder_is_used(self, tmp_path):
        assert screenshots_dir(str(tmp_path)) == tmp_path

    def test_home_is_expanded(self):
        assert screenshots_dir("~/shots") == Path("~/shots").expanduser()


class TestNamesTaken:
    def test_without_a_counter_a_number_goes_after(self, tmp_path):
        first = reserve_path(tmp_path, _name("shot"), "png")
        second = reserve_path(tmp_path, _name("shot"), "png")

        assert first.is_file()
        assert second.name == "shot (2).png"

    def test_the_counter_takes_the_first_number_free(self, tmp_path):
        (tmp_path / "shot0001.png").write_bytes(b"")
        (tmp_path / "shot0003.png").write_bytes(b"")

        assert reserve_path(tmp_path, _name("shot%n"), "png").name == "shot0002.png"
        assert reserve_path(tmp_path, _name("shot%n"), "png").name == "shot0004.png"

    def test_the_counter_goes_by_the_extension_too(self, tmp_path):
        (tmp_path / "shot0001.png").write_bytes(b"")

        assert reserve_path(tmp_path, _name("shot%n"), "jpg").name == "shot0001.jpg"


class TestTheViewRegion:
    """SW frames are cut the way VLC cuts them on the hardware drivers."""

    def test_nothing_cut_is_nothing_to_do(self):
        fit = ScreenshotView((400, 300), ViewParams(VideoAspect.FIT))
        none = ScreenshotView((100, 100), ViewParams(VideoAspect.NONE))

        assert fit.cut(800, 600) == (None, None)
        assert none.cut(800, 600) == (None, None)

    def test_no_frame_is_nothing_to_do(self):
        view = ScreenshotView((400, 300), ViewParams(crop=VideoCrop(1, 1, 1, 1)))

        assert view.cut(0, 0) == (None, None)

    def test_a_frame_vlc_has_cut_is_left(self):
        view = ScreenshotView((400, 200), None)

        assert view.cut(800, 600) == (None, None)

    def test_it_is_worked_out_for_the_frame_as_it_is(self):
        view = ScreenshotView((400, 200), ViewParams(VideoAspect.FIT))

        assert view.cut(800, 600) == (QRect(0, 100, 800, 400), None)

    def test_the_user_crop_is_in_frame_pixels(self):
        view = ScreenshotView(
            (400, 400), ViewParams(VideoAspect.NONE, crop=VideoCrop(100, 50, 100, 50))
        )

        assert view.cut(788, 576) == (QRect(100, 50, 588, 476), None)

    def test_the_zoom_is_cut_out_too(self):
        """What VLC crops to on the hardware drivers, zoom and all."""

        view = ScreenshotView((400, 300), ViewParams(VideoAspect.FIT, 2.0))

        assert view.cut(800, 600) == (QRect(200, 150, 400, 300), None)

    def test_a_frame_scaled_up_by_the_decoder_is_sized_back(self):
        """640x360 comes drawn from a 640x386 frame, the picture scaled up."""

        view = ScreenshotView(
            (640, 360), ViewParams(VideoAspect.NONE), None, (640, 360)
        )

        assert view.cut(640, 386) == (None, QSize(640, 360))

    def test_a_cut_of_a_frame_scaled_up_is_made_in_its_pixels(self):
        view = ScreenshotView((640, 360), ViewParams(scale=2.0), None, (640, 360))

        # the middle 320x180 of the picture, 96.5 rows down the frame
        assert view.cut(640, 386) == (QRect(160, 96, 320, 193), QSize(320, 180))

    def test_a_rotated_frame_is_shaped_back(self):
        view = ScreenshotView((360, 640), None, VideoTransform.ROTATE_90, (640, 360))

        assert view.cut(640, 360) == (None, QSize(360, 640))

    def test_a_cut_of_a_rotated_frame_is_shaped_back(self):
        # a 640x114 band of the squeezed frame is 360x203 of the picture
        view = ScreenshotView((640, 360), None, VideoTransform.TRANSPOSE, (640, 360))

        assert view.cut(640, 114) == (None, QSize(360, 203))

    def test_a_rotated_frame_drawn_here_is_shaped_back(self):
        view = ScreenshotView(
            (360, 640),
            ViewParams(VideoAspect.NONE),
            VideoTransform.ROTATE_90,
            (640, 360),
        )

        assert view.cut(640, 386) == (None, QSize(360, 640))

    @pytest.mark.parametrize(
        "transform",
        [VideoTransform.NONE, VideoTransform.HFLIP, VideoTransform.ROTATE_180, None],
    )
    def test_an_unrotated_frame_keeps_its_shape(self, transform):
        view = ScreenshotView((640, 360), None, transform, (640, 360))

        assert view.cut(640, 360) == (None, None)

    def test_a_rotation_of_a_frame_of_no_size_is_left(self):
        view = ScreenshotView((640, 360), None, VideoTransform.ROTATE_90)

        assert view.cut(640, 360) == (None, None)


def _marked(width, height) -> QImage:
    """Black, with the top left corner red."""

    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor("black"))
    for x in range(4):
        for y in range(4):
            image.setPixelColor(x, y, QColor("red"))
    return image


class TestTurningAnImage:
    """Where each transform takes a pixel, as VLC's own does."""

    @pytest.mark.parametrize(
        ("transform", "size", "moved"),
        [
            (VideoTransform.NONE, (3, 2), lambda x, y: (x, y)),
            (VideoTransform.HFLIP, (3, 2), lambda x, y: (2 - x, y)),
            (VideoTransform.VFLIP, (3, 2), lambda x, y: (x, 1 - y)),
            (VideoTransform.ROTATE_90, (2, 3), lambda x, y: (1 - y, x)),
            (VideoTransform.ROTATE_180, (3, 2), lambda x, y: (2 - x, 1 - y)),
            (VideoTransform.ROTATE_270, (2, 3), lambda x, y: (y, 2 - x)),
            (VideoTransform.TRANSPOSE, (2, 3), lambda x, y: (y, x)),
            (VideoTransform.ANTITRANSPOSE, (2, 3), lambda x, y: (1 - y, 2 - x)),
        ],
    )
    def test_every_pixel_goes_where_it_should(self, transform, size, moved):
        image = QImage(3, 2, QImage.Format_RGB32)
        for x in range(3):
            for y in range(2):
                image.setPixelColor(x, y, QColor(x * 100, y * 100, 50))

        turned = transformed_image(image, transform)

        assert (turned.width(), turned.height()) == size
        for x in range(3):
            for y in range(2):
                assert turned.pixelColor(*moved(x, y)) == image.pixelColor(x, y)


class TestSaving:
    def test_a_png_is_copied_as_it_is(self, tmp_path):
        source = _frame_file(tmp_path)

        path = save_screenshot(
            source, tmp_path / "out", _name(), ScreenshotFormat.PNG, 90
        )

        assert path == tmp_path / "out" / "shot.png"
        assert path.read_bytes() == Path(source).read_bytes()

    def test_a_jpg_is_made_from_the_png(self, tmp_path):
        path = save_screenshot(
            _frame_file(tmp_path), tmp_path, _name(), ScreenshotFormat.JPG, 90
        )

        assert path.name == "shot.jpg"
        assert path.read_bytes()[:3] == b"\xff\xd8\xff"
        assert QImage(str(path)).size() == _frame().size()

    def test_the_quality_is_what_the_jpg_is_written_at(self, tmp_path):
        frame = _frame(640, 480)

        low = save_screenshot(frame, tmp_path, _name("low"), ScreenshotFormat.JPG, 1)
        high = save_screenshot(
            frame, tmp_path, _name("high"), ScreenshotFormat.JPG, 100
        )

        assert low.stat().st_size < high.stat().st_size

    @pytest.mark.parametrize("image_format", list(ScreenshotFormat))
    def test_the_view_is_cut_out(self, tmp_path, image_format):
        view = ScreenshotView(
            (100, 100), ViewParams(VideoAspect.NONE, crop=VideoCrop(10, 0, 10, 10))
        )

        path = save_screenshot(
            _frame_file(tmp_path, 40, 20), tmp_path, _name(), image_format, 90, view
        )

        assert QImage(str(path)).size().width() == 20
        assert QImage(str(path)).size().height() == 10

    def test_a_view_that_keeps_it_all_copies_the_png(self, tmp_path):
        source = _frame_file(tmp_path)
        view = ScreenshotView((32, 16), ViewParams(VideoAspect.FIT))

        path = save_screenshot(
            source, tmp_path, _name(), ScreenshotFormat.PNG, 90, view
        )

        assert path.read_bytes() == Path(source).read_bytes()

    def test_a_png_vlc_cut_is_copied_as_it_is(self, tmp_path):
        source = _frame_file(tmp_path)
        view = ScreenshotView((32, 16), None, VideoTransform.HFLIP, (32, 16))

        path = save_screenshot(
            source, tmp_path, _name(), ScreenshotFormat.PNG, 90, view
        )

        assert path.read_bytes() == Path(source).read_bytes()

    @pytest.mark.parametrize("image_format", list(ScreenshotFormat))
    def test_a_rotated_frame_is_saved_in_its_shape(self, tmp_path, image_format):
        """VLC's snapshot of a rotated video is squeezed into the unrotated size."""

        view = ScreenshotView((36, 64), None, VideoTransform.ROTATE_90, (64, 36))

        path = save_screenshot(
            _frame_file(tmp_path, 64, 36), tmp_path, _name(), image_format, 90, view
        )

        assert QImage(str(path)).size() == QSize(36, 64)

    @pytest.mark.parametrize("image_format", list(ScreenshotFormat))
    def test_a_frame_vlc_turns_is_saved_the_right_way_up(self, tmp_path, image_format):
        """VLC writes the frame of a phone video the way it is stored."""

        folder = tmp_path / "vlc_tmp"
        folder.mkdir()
        source = folder / "snapshot.png"
        _marked(64, 36).save(str(source), "PNG")
        view = ScreenshotView(
            (36, 64), None, VideoTransform.NONE, (36, 64), VideoTransform.ROTATE_90
        )

        path = save_screenshot(str(source), tmp_path, _name(), image_format, 90, view)

        image = QImage(str(path))
        assert image.size() == QSize(36, 64)
        # the stored top left corner is the top right one turned clockwise
        assert image.pixelColor(34, 1).red() > 200

    def test_a_turned_frame_is_cut_the_way_it_is_shown(self, tmp_path):
        source = _frame_file(tmp_path, 64, 36)
        view = ScreenshotView(
            (36, 64),
            ViewParams(VideoAspect.NONE, crop=VideoCrop(0, 32, 0, 0)),
            VideoTransform.NONE,
            (36, 64),
            VideoTransform.ROTATE_270,
        )

        path = save_screenshot(
            source, tmp_path, _name(), ScreenshotFormat.PNG, 90, view
        )

        assert QImage(str(path)).size() == QSize(36, 32)

    def test_a_frame_in_memory_is_already_the_right_way_up(self, tmp_path):
        view = ScreenshotView(
            (32, 16), None, VideoTransform.NONE, (32, 16), VideoTransform.ROTATE_90
        )

        path = save_screenshot(
            _frame(), tmp_path, _name(), ScreenshotFormat.PNG, 90, view
        )

        assert QImage(str(path)).size() == _frame().size()

    def test_a_frame_in_memory_is_saved_too(self, tmp_path):
        """Where VLC had nothing to give, the frame on show is saved instead."""

        path = save_screenshot(_frame(), tmp_path, _name(), ScreenshotFormat.PNG, 90)

        assert QImage(str(path)).size() == _frame().size()

    def test_the_folder_is_made(self, tmp_path):
        folder = tmp_path / "a" / "b"

        save_screenshot(_frame(), folder, _name(), ScreenshotFormat.PNG, 90)

        assert folder.is_dir()

    def test_a_frame_that_cannot_be_read_leaves_nothing_behind(self, tmp_path):
        broken = tmp_path / "broken.png"
        broken.write_bytes(b"not a png")

        with pytest.raises(OSError, match="Cannot read"):
            save_screenshot(str(broken), tmp_path, _name(), ScreenshotFormat.JPG, 90)

        assert not (tmp_path / "shot.jpg").exists()


class TestTheJob:
    def _run(self, job):
        results = []
        job.saved.connect(lambda path: results.append(("saved", path)))
        job.failed.connect(lambda error: results.append(("failed", error)))

        # run where the test is, the signals are the same either way
        job.run()

        return results

    def test_it_says_where_the_file_went(self, tmp_path):
        job = ScreenshotJob(
            _frame_file(tmp_path), tmp_path / "out", _name(), ScreenshotFormat.PNG, 90
        )

        assert self._run(job) == [("saved", str(tmp_path / "out" / "shot.png"))]

    def test_the_vlc_file_and_its_folder_are_removed(self, tmp_path):
        source = _frame_file(tmp_path)

        self._run(ScreenshotJob(source, tmp_path, _name(), ScreenshotFormat.PNG, 90))

        assert not Path(source).parent.exists()

    def test_they_are_removed_when_saving_fails_too(self, tmp_path, monkeypatch):
        source = _frame_file(tmp_path)

        def _fail(*args):
            raise OSError("disk full")

        monkeypatch.setattr(screenshots, "_write_frame", _fail)

        results = self._run(
            ScreenshotJob(source, tmp_path, _name(), ScreenshotFormat.PNG, 90)
        )

        assert results == [("failed", "disk full")]
        assert not Path(source).parent.exists()
        assert not (tmp_path / "shot.png").exists()


class TestTheAction:
    def test_it_is_the_last_thing_in_the_video_menu(self):
        video_menu = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Video"
        )

        assert video_menu[-2:] == ("---", "Take Screenshot")

    def test_it_asks_the_active_video(self):
        action = ACTIONS["Take Screenshot"]

        assert action["func"] == ("active", "take_screenshot")
        assert action["show_if"] == "is_active_has_video"

    def test_it_is_not_one_of_the_grid_snapshots(self):
        """Those are saved layouts, a different thing with a similar name."""

        assert "Snapshot" not in ACTIONS["Take Screenshot"]["title"]


class TestTheActionForAll:
    def test_it_is_the_last_thing_in_the_all_video_menu(self):
        all_menu = next(
            item
            for item in SECTIONS["video_all"]
            if isinstance(item, tuple) and item[0] == "[ALL]"
        )
        video_menu = next(
            item for item in all_menu if isinstance(item, tuple) and item[0] == "Video"
        )

        assert video_menu[-2:] == ("---", "Take Screenshot [ALL]")

    def test_it_asks_every_video_quietly(self):
        action = ACTIONS["Take Screenshot [ALL]"]

        assert action["func"] == ("all", "take_screenshot", True)
        assert action["show_if"] == "is_any_videos_have_video"

    def test_it_reaches_every_video(self):
        assert VideoBlocksManager.all_take_screenshot is not None

    def test_the_keys_are_one_apart(self):
        assert ACTIONS["Take Screenshot"]["key"] == "Alt+S"
        assert ACTIONS["Take Screenshot [ALL]"]["key"] == "Shift+Alt+S"


class TestHowAFailureIsSaid:
    def _block(self, is_quiet):
        return SimpleNamespace(
            _is_screenshot_quiet=is_quiet,
            show_overlay=MagicMock(),
            info_change=MagicMock(),
            _ctx=SimpleNamespace(commands=SimpleNamespace(warning=MagicMock())),
        )

    def test_one_video_gets_a_warning_with_the_reason(self):
        block = self._block(is_quiet=False)

        VideoBlock._report_screenshot_failure(block, "Could not save", "disk full")

        block._ctx.commands.warning.assert_called_once_with(
            "Could not save\n\ndisk full"
        )
        block.info_change.emit.assert_not_called()

    def test_every_video_at_once_says_so_on_the_overlay(self):
        """Not a warning box per video, one on top of the other."""

        block = self._block(is_quiet=True)

        VideoBlock._report_screenshot_failure(block, "Could not save", "disk full")

        block._ctx.commands.warning.assert_not_called()
        block.show_overlay.assert_called_once()
        block.info_change.emit.assert_called_once_with("Screenshot failed")


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)

    return store


@pytest.fixture
def dialog(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings_dialog, "cookie_store", lambda: CookieStore(tmp_path / "cookies.txt")
    )

    made = SettingsDialog(None)

    yield made

    made.close()
    made.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class TestTheSettings:
    def test_they_are_on_the_player_page(self, dialog):
        for widget in (
            dialog.screenshotsDir,
            dialog.screenshotsFilenameTemplate,
            dialog.screenshotsFilenameTemplateHelpButton,
            dialog.screenshotsFormat,
            dialog.screenshotsJPGQuality,
        ):
            assert dialog.page_general_player.isAncestorOf(widget)

    def test_they_come_back_as_saved(self, dialog, settings, tmp_path):
        dialog.screenshotsDir.setText(str(tmp_path))
        dialog.screenshotsFilenameTemplate.setText("%F-%n")
        dialog.screenshotsFormat.setCurrentIndex(
            dialog.screenshotsFormat.findData(ScreenshotFormat.JPG)
        )
        dialog.screenshotsJPGQuality.setValue(75)

        dialog.save_settings()

        assert settings.get("screenshots/dir") == str(tmp_path)
        assert settings.get("screenshots/filename_template") == "%F-%n"
        assert settings.get("screenshots/format") == ScreenshotFormat.JPG
        assert settings.get("screenshots/jpg_quality") == 75

    def test_the_folder_comes_empty_out_of_the_box(self, dialog):
        """Empty is what follows the data folder wherever it is."""

        assert dialog.screenshotsDir.text() == ""
        assert dialog.screenshotsDir.placeholderText() == "In the data folder"
        assert dialog.screenshotsDir.toolTip().endswith("screenshots")

    def test_the_format_comes_as_the_default(self, dialog):
        assert dialog.screenshotsFilenameTemplate.text() == "%F_%P"

    def test_quality_is_only_for_jpg(self, dialog):
        box = dialog.screenshotsFormat

        box.setCurrentIndex(box.findData(ScreenshotFormat.PNG))
        assert not dialog.screenshotsJPGQuality.isEnabled()

        box.setCurrentIndex(box.findData(ScreenshotFormat.JPG))
        assert dialog.screenshotsJPGQuality.isEnabled()

    def test_quality_is_still_saved_while_png_is_picked(self, dialog, settings):
        """A greyed out widget is skipped on save, so the stored one stays."""

        dialog.save_settings()

        assert settings.get("screenshots/jpg_quality") == 90

    def test_an_empty_format_goes_back_to_the_default(self, dialog, settings):
        dialog.screenshotsFilenameTemplate.setText("  ")

        dialog.save_settings()

        assert settings.get("screenshots/filename_template") == "%F_%P"

    def test_an_unknown_specifier_keeps_the_dialog_open(self, dialog, settings, mocker):
        warned = mocker.patch.object(settings_dialog.QCustomMessageBox, "warning")
        dialog.screenshotsFilenameTemplate.setText("%F_%x")

        dialog.accept()

        assert warned.called
        assert "%x" in warned.call_args.args[2]
        assert settings.get("screenshots/filename_template") != "%F_%x"

    def test_the_help_is_in_a_box_of_its_own(self, dialog, mocker):
        shown = mocker.patch.object(settings_dialog.QCustomMessageBox, "information")

        dialog.screenshotsFilenameTemplateHelpButton.click()

        text = shown.call_args.args[2]
        for specifier in ("%f", "%F", "%p", "%P", "%n", "%D", "%T", "%tY", "%tS", "%%"):
            assert f"<tt>{specifier}</tt>" in text

    def test_there_is_no_help_squeezed_in_beside_the_field(self, dialog):
        assert dialog.screenshotsFilenameTemplate.toolTip() == ""
        assert not hasattr(dialog, "screenshotsFilenameTemplateHelp")

    def test_the_folder_row_is_just_the_field_and_browse(self, dialog):
        """An Open button next to Browse made the row too wide for the page."""

        assert not hasattr(dialog, "screenshotsDirOpen")
        assert dialog.lay_screenshots_dir.count() == 2
