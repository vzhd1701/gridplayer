import pytest
from types import SimpleNamespace

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication

from pydantic import ValidationError

from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.defaults_fields import VIDEO_FIELDS
from gridplayer.params.static import VideoCrop
from gridplayer.playlist_settings import (
    PlaylistSettings,
    overrides_from_playlist,
    playlist_kwargs_from_overrides,
)
from gridplayer.settings import Settings, _default_settings
from gridplayer.widgets.defaults_form import DefaultsForm


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, mocker):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def test_settings_crop_round_trip():
    Settings().set("video_defaults/crop", VideoCrop(1, 2, 3, 4))

    assert Settings().get("video_defaults/crop") == VideoCrop(1, 2, 3, 4)


def test_settings_crop_falls_back_to_default_on_garbage():
    Settings().settings.setValue("video_defaults/crop", "not,a,crop,at,all")

    assert (
        Settings().get("video_defaults/crop")
        == _default_settings["video_defaults/crop"]
    )


def test_video_uses_session_defaults():
    PlaylistSettings().replace(
        {
            "video_defaults/rate": 2.0,
            "video_defaults/scale": 1.5,
            "video_defaults/volume": 0.5,
            "video_defaults/color": "#ff0000",
            "video_defaults/crop": VideoCrop(1, 2, 3, 4),
        }
    )

    video = Video(uri="http://example.com/a.mp4")

    assert video.rate == 2.0
    assert video.scale == 1.5
    assert video.volume == 0.5
    assert video.color.as_rgb_tuple() == (255, 0, 0)
    assert video.crop == VideoCrop(1, 2, 3, 4)


def test_video_accepts_session_color_object():
    from pydantic_extra_types.color import Color as PydColor

    PlaylistSettings().replace({"video_defaults/color": PydColor("#5724c2")})

    video = Video(uri="http://example.com/a.mp4")

    assert video.color.as_rgb_tuple() == (87, 36, 194)


def test_video_keeps_rate_constraints():
    with pytest.raises(ValidationError):
        Video(rate=100)


def test_playlist_video_defaults_seed_session():
    PlaylistSettings().replace(
        {
            "video_defaults/rate": 2.0,
            "video_defaults/crop": VideoCrop(1, 2, 3, 4),
        }
    )
    playlist = Playlist(
        videos=[], **playlist_kwargs_from_overrides(PlaylistSettings().as_dict())
    )

    seeded = overrides_from_playlist(playlist)

    assert seeded["video_defaults/rate"] == 2.0
    assert seeded["video_defaults/crop"] == VideoCrop(1, 2, 3, 4)


def test_playlist_dumps_video_defaults_round_trip():
    PlaylistSettings().replace(
        {
            "video_defaults/color": "#5724c2",
            "video_defaults/crop": VideoCrop(1, 2, 3, 4),
        }
    )
    playlist = Playlist(
        videos=[Video(uri="http://example.com/a.mp4")],
        **playlist_kwargs_from_overrides(PlaylistSettings().as_dict()),
    )

    parsed = Playlist.parse(playlist.dumps())
    seeded = overrides_from_playlist(parsed)

    assert seeded["video_defaults/color"].as_rgb_tuple() == (87, 36, 194)
    assert seeded["video_defaults/crop"] == VideoCrop(1, 2, 3, 4)


def test_defaults_form_crop_kind():
    form = DefaultsForm(VIDEO_FIELDS)
    crop_widget = form._widgets["video_defaults/crop"]

    crop_widget.value = VideoCrop(1, 2, 3, 4)

    assert form.values()["video_defaults/crop"] == VideoCrop(1, 2, 3, 4)


def test_defaults_form_color_kind():
    form = DefaultsForm(VIDEO_FIELDS)
    color_widget = form._widgets["video_defaults/color"]

    color_widget.color = QColor("#ff0000").getRgb()[:3]

    assert form.values()["video_defaults/color"] == "#ff0000"


def test_defaults_form_float_spin_kind():
    form = DefaultsForm(VIDEO_FIELDS)
    rate_widget = form._widgets["video_defaults/rate"]

    rate_widget.setValue(2.5)

    assert form.values()["video_defaults/rate"] == 2.5


def test_defaults_form_color_marks_row_edited():
    form = DefaultsForm(VIDEO_FIELDS)

    form._widgets["video_defaults/color"].color = QColor("#ff0000").getRgb()[:3]

    assert "video_defaults/color" in form.overridden_keys()


def test_color_popup_forwards_selection():
    from gridplayer.widgets.color_palette import _QColorPopup

    popup = _QColorPopup((255, 255, 255))
    selected = []
    popup.color_changed.connect(lambda: selected.append(popup.color.getRgb()[:3]))

    popup._palette.color = QColor("#ff0000").getRgb()[:3]

    assert selected == [(255, 0, 0)]


def test_compact_picker_opens_popup_on_click(mocker):
    from gridplayer.widgets import color_palette as cp

    swatch = cp.QCompactColorPicker()
    exec_mock = mocker.patch.object(cp._QColorPopup, "exec_", return_value=None)

    swatch.click()

    assert exec_mock.called


def test_compact_picker_applies_popup_selection(mocker):
    from gridplayer.widgets import color_palette as cp

    swatch = cp.QCompactColorPicker()
    emitted = []
    swatch.color_changed.connect(lambda: emitted.append(swatch.color.getRgb()[:3]))

    def fake_exec(self):
        self._palette.color = QColor("#0000ff").getRgb()[:3]
        self._on_selected()

    mocker.patch.object(cp._QColorPopup, "exec_", fake_exec)
    swatch.click()

    assert swatch.color.getRgb()[:3] == (0, 0, 255)
    assert emitted == [(0, 0, 255)]


def test_settings_get_all_includes_new_defaults():
    values = Settings().get_all()

    assert values["video_defaults/rate"] == _default_settings["video_defaults/rate"]
    assert values["video_defaults/crop"] == VideoCrop(0, 0, 0, 0)
    assert values["video_defaults/color"] == "#ffffff"
