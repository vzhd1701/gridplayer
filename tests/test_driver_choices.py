"""The Decoder setting: every driver listed, what can't run greyed out and why,
and a note saying what's missing and what plays instead."""

from pathlib import Path

import pytest
from PyQt5.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QComboBox

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.params import env
from gridplayer.params.settings_fields import advanced, choices
from gridplayer.params.static import DisplayServer, MpvOutput, VideoDriver
from gridplayer.settings import _Settings
from gridplayer.utils import media_libs, video_driver
from gridplayer.utils.cookies import CookieStore
from gridplayer.utils.media_libs import LibProblem, MediaLib
from gridplayer.widgets.combo_box import ReasonComboBox

DRIVER = "player/video_driver"

ALL_DECODERS = [
    VideoDriver.VLC_HW,
    VideoDriver.VLC_SW,
    VideoDriver.MPV_HW,
    VideoDriver.MPV_SW,
    VideoDriver.DUMMY,
]


@pytest.fixture
def libs(monkeypatch):
    """Both there, and what a test takes away."""

    problems = {}

    def lib_problem(lib):
        return problems.get(lib)

    for module in (media_libs, video_driver):
        monkeypatch.setattr(module, "lib_problem", lib_problem)

    monkeypatch.setattr(env, "IS_MACOS", False)
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "windows")

    return problems


@pytest.fixture
def wayland(libs, monkeypatch):
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "wayland")
    monkeypatch.delenv("DISPLAY", raising=False)


@pytest.fixture
def wayland_with_xwayland(libs, monkeypatch):
    monkeypatch.setattr(video_driver, "_qt_platform_name", lambda: "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", True)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)
    monkeypatch.setattr(
        settings_dialog, "cookie_store", lambda: CookieStore(tmp_path / "cookies.txt")
    )

    return store


@pytest.fixture
def make_dialog(settings):
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


def _note(dialog):
    bubble = dialog.driverNotice
    if bubble.isHidden():
        return None
    lines = bubble.lines.property("gp_html_src")
    return f"{bubble.title.text()}\n{lines}"


# -- what's listed


def test_every_decoder_is_listed_in_order(libs):
    assert list(choices.video_drivers()) == ALL_DECODERS


def test_the_names_say_which_library(libs):
    names = choices.video_drivers()

    assert names[VideoDriver.VLC_HW] == "Hardware <VLC>"
    assert names[VideoDriver.VLC_SW] == "Software <VLC>"
    assert names[VideoDriver.MPV_HW] == "Hardware <MPV>"
    assert names[VideoDriver.MPV_SW] == "Software <MPV>"


@pytest.mark.usefixtures("wayland")
def test_all_of_them_are_listed_on_wayland_too(libs):
    assert list(choices.video_drivers()) == ALL_DECODERS


# -- why not


def test_nothing_unavailable_with_both_libraries(libs):
    assert choices.unavailable_video_drivers() == {}


def test_libmpv_missing_greys_both_mpv_drivers(libs):
    libs[MediaLib.MPV] = LibProblem.MISSING

    assert choices.unavailable_video_drivers() == {
        VideoDriver.MPV_HW: "libmpv not found",
        VideoDriver.MPV_SW: "libmpv not found",
    }


def test_vlc_missing_greys_both_vlc_drivers(libs):
    libs[MediaLib.VLC] = LibProblem.MISSING

    reasons = choices.unavailable_video_drivers()

    assert set(reasons) == {VideoDriver.VLC_HW, VideoDriver.VLC_SW}
    assert set(reasons.values()) == {"VLC not found"}


@pytest.mark.parametrize(
    ("problem", "said"),
    [
        (LibProblem.WONT_LOAD, "libmpv won't load"),
        (LibProblem.TOO_OLD, "libmpv is too old"),
    ],
)
def test_each_problem_says_its_own(libs, problem, said):
    libs[MediaLib.MPV] = problem

    assert choices.unavailable_video_drivers()[VideoDriver.MPV_HW] == said


@pytest.mark.usefixtures("wayland")
def test_wayland_greys_vlc_hardware_only(libs):
    assert choices.unavailable_video_drivers() == {
        VideoDriver.VLC_HW: "Needs X11",
    }


@pytest.mark.usefixtures("wayland")
def test_x11_goes_over_the_library_since_installing_wont_help(libs):
    libs[MediaLib.VLC] = LibProblem.MISSING

    reasons = choices.unavailable_video_drivers()

    assert reasons[VideoDriver.VLC_HW] == "Needs X11"
    assert reasons[VideoDriver.VLC_SW] == "VLC not found"


def test_macos_keeps_vlc_hardware_as_a_single_process(libs, monkeypatch):
    monkeypatch.setattr(env, "IS_MACOS", True)

    assert choices.unavailable_video_drivers() == {}
    assert video_driver.is_single_process_only(VideoDriver.VLC_HW)
    assert not video_driver.is_single_process_only(VideoDriver.VLC_SW)


# -- the combo


def _combo_with_mpv_greyed():
    combo = ReasonComboBox()
    for value, name in (("a", "First"), ("mpv", "Greyed"), ("b", "Last")):
        combo.addItem(name, value)
    combo.set_unavailable({"mpv": "libmpv not found"})
    return combo


def test_a_greyed_choice_says_why_and_cant_be_clicked():
    combo = _combo_with_mpv_greyed()

    assert combo.reason_of("mpv") == "libmpv not found"
    assert combo.reason_of("a") is None
    assert not combo.model().item(1).isEnabled()
    assert combo.model().item(0).isEnabled()


def test_the_arrow_keys_step_over_a_greyed_choice():
    combo = _combo_with_mpv_greyed()
    combo.setCurrentIndex(0)

    QTest.keyClick(combo, Qt.Key_Down)
    assert combo.currentData() == "b"

    QTest.keyClick(combo, Qt.Key_Up)
    assert combo.currentData() == "a"


def test_the_wheel_steps_over_a_greyed_choice():
    combo = _combo_with_mpv_greyed()
    combo.setCurrentIndex(0)

    down = QWheelEvent(
        QPointF(1, 1),
        QPointF(combo.mapToGlobal(QPoint(1, 1))),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(combo, down)

    assert combo.currentData() == "b"


def test_the_list_opens_wide_enough_for_the_reason(monkeypatch):
    monkeypatch.setattr(QComboBox, "showPopup", lambda _: None)

    combo = _combo_with_mpv_greyed()
    combo.setFixedWidth(40)
    metrics = combo.view().fontMetrics()

    combo.showPopup()

    needs = metrics.horizontalAdvance("Greyed") + metrics.horizontalAdvance(
        "libmpv not found"
    )
    assert combo.view().minimumWidth() > needs


# -- the dialog


def test_the_dialog_greys_what_cant_run(libs, make_dialog):
    libs[MediaLib.MPV] = LibProblem.MISSING

    combo = make_dialog().widget(DRIVER)

    assert combo.reason_of(VideoDriver.MPV_SW) == "libmpv not found"
    assert not combo.model().item(combo.findData(VideoDriver.MPV_HW)).isEnabled()
    assert combo.model().item(combo.findData(VideoDriver.VLC_HW)).isEnabled()


def test_a_search_finds_a_greyed_name(libs, make_dialog):
    libs[MediaLib.MPV] = LibProblem.MISSING

    dialog = make_dialog()
    dialog.search("Software <MPV>")

    assert dialog.section_page.currentWidget() is dialog.pages["decoder"]


@pytest.mark.parametrize("text", ["Processes", "Single process"])
def test_a_search_finds_the_processes_choice(libs, make_dialog, text):
    dialog = make_dialog()
    dialog.search(text)

    assert dialog.section_page.currentWidget() is dialog.pages["decoder"]


def test_a_pick_that_cant_run_is_kept(libs, make_dialog, settings):
    libs[MediaLib.MPV] = LibProblem.MISSING
    settings.set(DRIVER, VideoDriver.MPV_SW)

    dialog = make_dialog()

    assert dialog.value(DRIVER) == VideoDriver.VLC_SW

    dialog.save_settings()

    assert settings.get(DRIVER) == VideoDriver.MPV_SW


# -- the bubble under the block


HOW_TO_FIX = f'<a href="{advanced.DECODER_HELP_URL}">How to fix</a>'


def test_no_bubble_with_both_libraries(libs, make_dialog):
    assert _note(make_dialog()) is None


def test_the_bubble_is_out_of_the_card_under_it(libs, make_dialog):
    libs[MediaLib.MPV] = LibProblem.MISSING

    dialog = make_dialog()
    row = dialog.forms["decoder"]._rows[DRIVER]

    assert not row.isAncestorOf(dialog.driverNotice)
    assert row.parentWidget() is not dialog.driverNotice.parentWidget()


def test_a_library_not_installed_is_only_not_available(libs, make_dialog, settings):
    libs[MediaLib.MPV] = LibProblem.MISSING
    settings.set(DRIVER, VideoDriver.VLC_HW)

    assert _note(make_dialog()) == (
        f"Some modes aren't available\nMPV: libmpv not found. {HOW_TO_FIX}"
    )


def test_a_pick_that_cant_run_says_what_plays_instead(libs, make_dialog, settings):
    libs[MediaLib.MPV] = LibProblem.MISSING
    settings.set(DRIVER, VideoDriver.MPV_HW)

    assert _note(make_dialog()) == (
        f"MPV can't run. Playing with VLC for now.\nlibmpv not found. {HOW_TO_FIX}"
    )


def test_a_vlc_pick_that_cant_run(libs, make_dialog, settings):
    libs[MediaLib.VLC] = LibProblem.MISSING
    settings.set(DRIVER, VideoDriver.VLC_SW)

    assert _note(make_dialog()) == (
        f"VLC can't run. Playing with MPV for now.\nVLC not found. {HOW_TO_FIX}"
    )


@pytest.mark.parametrize(
    ("problem", "said"),
    [
        (LibProblem.WONT_LOAD, "MPV: libmpv won't load."),
        (LibProblem.TOO_OLD, "MPV: libmpv is too old."),
    ],
)
def test_each_problem_says_its_own_in_the_bubble(
    libs, make_dialog, settings, problem, said
):
    libs[MediaLib.MPV] = problem
    settings.set(DRIVER, VideoDriver.VLC_HW)

    assert said in _note(make_dialog())


@pytest.mark.parametrize(
    ("picked", "is_warning"),
    [(VideoDriver.VLC_HW, False), (VideoDriver.MPV_HW, True)],
)
def test_the_warning_sign_is_for_a_pick_that_cant_run(
    libs, settings, picked, is_warning
):
    libs[MediaLib.MPV] = LibProblem.MISSING

    notice = advanced.driver_notice(picked, video_driver.session_video_driver(picked))

    assert notice.is_problem is is_warning


def test_the_bubble_calms_down_once_something_else_is_picked(
    libs, make_dialog, settings
):
    libs[MediaLib.MPV] = LibProblem.MISSING
    settings.set(DRIVER, VideoDriver.MPV_HW)

    dialog = make_dialog()
    combo = dialog.widget(DRIVER)
    combo.setCurrentIndex(combo.findData(VideoDriver.VLC_SW))

    assert _note(dialog) == (
        f"Some modes aren't available\nMPV: libmpv not found. {HOW_TO_FIX}"
    )


@pytest.mark.usefixtures("wayland")
def test_hardware_picked_on_wayland(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.VLC_HW)

    assert _note(make_dialog()) == (
        "VLC Hardware can't run. Playing with VLC Software for now.\n"
        f"VLC Hardware: needs X11. {HOW_TO_FIX}"
    )


@pytest.mark.usefixtures("wayland")
def test_wayland_says_it_even_if_the_pick_is_fine(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.MPV_HW)

    assert _note(make_dialog()) == (
        f"Some modes aren't available\nVLC Hardware: needs X11. {HOW_TO_FIX}"
    )


@pytest.mark.usefixtures("wayland")
def test_every_reason_gets_a_line(libs, make_dialog, settings):
    libs[MediaLib.MPV] = LibProblem.MISSING
    settings.set(DRIVER, VideoDriver.VLC_SW)

    note = _note(make_dialog())

    assert "MPV: libmpv not found." in note
    assert "VLC Hardware: needs X11." in note
    assert note.count("How to fix") == 2


def test_both_missing_says_both(libs, make_dialog):
    libs[MediaLib.VLC] = LibProblem.MISSING
    libs[MediaLib.MPV] = LibProblem.MISSING

    note = _note(make_dialog())

    assert "VLC not found." in note
    assert "MPV: libmpv not found." in note
    assert "<br>" in note


def test_the_bubble_goes_away_when_nothing_is_left_to_say(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.VLC_SW)
    dialog = make_dialog()
    assert _note(dialog) is None

    libs[MediaLib.MPV] = LibProblem.MISSING
    combo = dialog.widget(DRIVER)
    combo.setCurrentIndex(combo.findData(VideoDriver.VLC_HW))
    assert _note(dialog) is not None

    libs.clear()
    combo.setCurrentIndex(combo.findData(VideoDriver.VLC_SW))
    assert _note(dialog) is None


def test_how_to_fix_goes_to_the_readme_section():
    readme = Path(__file__).parent.parent / "README.md"

    assert advanced.DECODER_HELP_URL.endswith("#when-a-mode-isnt-available")
    assert "### When a mode isn't available" in readme.read_text(encoding="utf-8")


# -- what only VLC listens to


VLC_ONLY = ("misc/vlc_options", "internal/hw_crop_border_offset")


@pytest.mark.parametrize("key", VLC_ONLY)
@pytest.mark.parametrize("driver", [VideoDriver.MPV_HW, VideoDriver.MPV_SW])
def test_vlc_options_grey_out_on_mpv(libs, make_dialog, settings, key, driver):
    settings.set(DRIVER, driver)

    assert not make_dialog().widget(key).isEnabled()


@pytest.mark.parametrize("key", VLC_ONLY)
def test_vlc_options_stay_on_vlc(libs, make_dialog, settings, key):
    settings.set(DRIVER, VideoDriver.VLC_HW_SP)

    assert make_dialog().widget(key).isEnabled()


def test_vlc_options_stay_on_software_vlc(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.VLC_SW_SP)

    assert make_dialog().widget("misc/vlc_options").isEnabled()


@pytest.mark.parametrize(
    ("key", "is_vlc"),
    [("logging/log_level_vlc", True), ("logging/log_level_mpv", False)],
)
def test_a_log_level_on_its_other_page_follows_the_driver(
    libs, make_dialog, settings, key, is_vlc
):
    settings.set(DRIVER, VideoDriver.VLC_HW)
    dialog = make_dialog()
    level = dialog.widget(key)
    combo = dialog.widget(DRIVER)

    assert level.isEnabled() == is_vlc

    combo.setCurrentIndex(combo.findData(VideoDriver.MPV_SW))
    assert level.isEnabled() != is_vlc

    combo.setCurrentIndex(combo.findData(VideoDriver.VLC_SW))
    assert level.isEnabled() == is_vlc


def test_vlc_log_level_starts_grey_on_mpv(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.MPV_HW)

    assert not make_dialog().widget("logging/log_level_vlc").isEnabled()


def _section_of(dialog, key):
    card = dialog.forms["decoder"]._rows[key].parentWidget()
    return card.parentWidget()


def test_vlc_options_section_goes_on_mpv_and_comes_back_on_vlc(libs, make_dialog):
    dialog = make_dialog()
    section = _section_of(dialog, "misc/vlc_options")
    assert "VLC Options" in section.header.text()

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    assert section.isHidden()

    _pick_decoder(dialog, VideoDriver.VLC_SW)
    assert not section.isHidden()


def _row_hidden(dialog, key):
    return dialog.forms["decoder"]._rows[key].isHidden()


def test_vlc_only_experiments_go_on_mpv(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.VLC_HW)
    dialog = make_dialog()
    key = "internal/hw_crop_border_offset"

    assert not _row_hidden(dialog, key)

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    assert _row_hidden(dialog, key)

    _pick_decoder(dialog, VideoDriver.VLC_HW)
    assert not _row_hidden(dialog, key)


# what's there for VLC's own window for the picture, over which the overlay floats
VLC_HW_ONLY = (
    "internal/hw_crop_border_offset",
    "internal/opaque_hw_overlay",
    "internal/fake_overlay_invisibility",
)


@pytest.mark.parametrize("key", VLC_HW_ONLY)
def test_hardware_vlc_workarounds_go_on_software_vlc(
    libs, make_dialog, monkeypatch, key
):
    # where all three are there to show
    monkeypatch.setattr(env, "IS_LINUX", True)
    dialog = make_dialog()

    _pick_decoder(dialog, VideoDriver.VLC_HW)
    _pick_single(dialog, True)
    assert not _row_hidden(dialog, key)

    _pick_decoder(dialog, VideoDriver.VLC_SW)
    assert _row_hidden(dialog, key)

    _pick_single(dialog, False)
    assert _row_hidden(dialog, key)


# what Direct's window has over it on Linux too: the overlay floats there as well
FLOATING_OVERLAY = (
    "internal/opaque_hw_overlay",
    "internal/fake_overlay_invisibility",
)


@pytest.mark.parametrize("key", FLOATING_OVERLAY)
def test_floating_overlay_workarounds_with_direct_output(
    libs, make_dialog, monkeypatch, key
):
    monkeypatch.setattr(env, "IS_LINUX", True)
    monkeypatch.setattr(env, "IS_WINDOWS", False)
    # Direct is offered on Linux only with an X server to put its window on
    monkeypatch.setenv("DISPLAY", ":0")
    dialog = make_dialog()
    output = dialog.widget("player/mpv_output")

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    output.setCurrentIndex(output.findData(MpvOutput.WINDOW))
    assert not _row_hidden(dialog, key)

    for other in (MpvOutput.READBACK, MpvOutput.GL):
        output.setCurrentIndex(output.findData(other))
        assert _row_hidden(dialog, key)

    # Direct stays picked, for a Software MPV that has no window of its own
    output.setCurrentIndex(output.findData(MpvOutput.WINDOW))
    _pick_decoder(dialog, VideoDriver.MPV_SW)
    assert _row_hidden(dialog, key)

    _pick_decoder(dialog, VideoDriver.VLC_HW)
    assert not _row_hidden(dialog, key)


def test_border_fix_stays_vlc_s_with_direct_output(libs, make_dialog, monkeypatch):
    # mpv places the picture on whole pixels: no edges to crop
    monkeypatch.setattr(env, "IS_LINUX", True)
    dialog = make_dialog()
    output = dialog.widget("player/mpv_output")

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    output.setCurrentIndex(output.findData(MpvOutput.WINDOW))

    assert _row_hidden(dialog, "internal/hw_crop_border_offset")


def test_native_drag_events_stay_whatever_the_driver(libs, make_dialog, monkeypatch):
    # dragging cells in the window, which has nothing to do with the driver
    monkeypatch.setattr(env, "IS_LINUX", True)
    dialog = make_dialog()
    key = "internal/force_native_drag_events"

    for decoder in (VideoDriver.VLC_SW, VideoDriver.MPV_SW, VideoDriver.VLC_HW):
        _pick_decoder(dialog, decoder)
        assert not _row_hidden(dialog, key)


def test_black_line_fix_only_with_fast_output(libs, make_dialog, monkeypatch):
    monkeypatch.setattr(env, "IS_WINDOWS", True)
    dialog = make_dialog()
    key = "internal/gl_line_fix"
    output = dialog.widget("player/mpv_output")

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    output.setCurrentIndex(output.findData(MpvOutput.READBACK))
    assert _row_hidden(dialog, key)

    output.setCurrentIndex(output.findData(MpvOutput.GL))
    assert not _row_hidden(dialog, key)

    # Shared stays picked, for a Software MPV that has no GL
    _pick_decoder(dialog, VideoDriver.MPV_SW)
    assert _row_hidden(dialog, key)


def test_experiments_go_altogether_when_none_apply(libs, make_dialog, monkeypatch):
    # Windows: no Linux ones, and Black line fix only with Shared output
    monkeypatch.setattr(env, "IS_WINDOWS", True)
    monkeypatch.setattr(env, "IS_LINUX", False)
    dialog = make_dialog()
    section = _section_of(dialog, "internal/hw_crop_border_offset")

    _pick_decoder(dialog, VideoDriver.VLC_SW)
    assert section.isHidden()

    _pick_decoder(dialog, VideoDriver.VLC_HW)
    assert not section.isHidden()

    # Use mpv.conf
    _pick_decoder(dialog, VideoDriver.MPV_SW)
    assert not section.isHidden()


def test_mpv_conf_is_there_only_for_mpv(libs, make_dialog):
    dialog = make_dialog()

    _pick_decoder(dialog, VideoDriver.VLC_HW)
    assert _row_hidden(dialog, "player/mpv_conf")

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    assert not _row_hidden(dialog, "player/mpv_conf")


def test_mpv_conf_buttons_are_there_while_it_is_on(libs, make_dialog):
    dialog = make_dialog()
    buttons = (dialog.mpvConfOpenButton, dialog.mpvConfCheckButton)

    assert all(button.isHidden() for button in buttons)

    dialog.widget("player/mpv_conf").setChecked(True)
    assert not any(button.isHidden() for button in buttons)

    dialog.widget("player/mpv_conf").setChecked(False)
    assert all(button.isHidden() for button in buttons)


def test_mpv_conf_buttons_go_before_the_switch(libs, make_dialog):
    dialog = make_dialog()
    switch = dialog.widget("player/mpv_conf")
    line = dialog.forms["decoder"]._rows["player/mpv_conf"].line
    place = [
        line.indexOf(widget)
        for widget in (dialog.mpvConfOpenButton, dialog.mpvConfCheckButton, switch)
    ]

    assert place == sorted(place)
    assert place[0] >= 1


def test_vlc_options_section_starts_hidden_on_mpv(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.MPV_SW)

    assert _section_of(make_dialog(), "misc/vlc_options").isHidden()


def test_a_saved_vlc_option_survives_mpv(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.MPV_HW)
    settings.set("misc/vlc_options", "--no-audio")

    dialog = make_dialog()
    dialog.save_settings()

    assert settings.get("misc/vlc_options") == "--no-audio"


# -- decoder and processes, one stored value


def _editor(dialog):
    return dialog.forms["decoder"]._editors[DRIVER]


def _pick_decoder(dialog, decoder):
    combo = dialog.widget(DRIVER)
    combo.setCurrentIndex(combo.findData(decoder))


def _pick_single(dialog, is_single):
    processes = _editor(dialog).processes
    processes.setCurrentIndex(processes.findData(is_single))


@pytest.mark.parametrize(
    ("driver", "decoder", "is_single"),
    [
        (VideoDriver.VLC_HW, VideoDriver.VLC_HW, False),
        (VideoDriver.VLC_HW_SP, VideoDriver.VLC_HW, True),
        (VideoDriver.VLC_SW, VideoDriver.VLC_SW, False),
        (VideoDriver.VLC_SW_SP, VideoDriver.VLC_SW, True),
        (VideoDriver.MPV_HW, VideoDriver.MPV_HW, True),
        (VideoDriver.MPV_SW, VideoDriver.MPV_SW, True),
        (VideoDriver.DUMMY, VideoDriver.DUMMY, True),
    ],
)
def test_a_driver_comes_apart_and_back(driver, decoder, is_single):
    assert video_driver.driver_parts(driver) == (decoder, is_single)
    assert video_driver.driver_of_parts(decoder, is_single) == driver


@pytest.mark.parametrize(
    ("stored", "decoder", "single"),
    [
        (VideoDriver.VLC_HW, VideoDriver.VLC_HW, False),
        (VideoDriver.VLC_HW_SP, VideoDriver.VLC_HW, True),
        (VideoDriver.VLC_SW_SP, VideoDriver.VLC_SW, True),
    ],
)
def test_the_two_choices_show_a_saved_driver(
    libs, make_dialog, settings, stored, decoder, single
):
    settings.set(DRIVER, stored)

    dialog = make_dialog()

    assert dialog.widget(DRIVER).currentData() == decoder
    assert _editor(dialog).processes.currentData() is single
    assert dialog.value(DRIVER) == stored


def test_a_saved_setting_stays_untouched_if_nothing_is_changed(
    libs, make_dialog, settings
):
    settings.set(DRIVER, VideoDriver.VLC_HW_SP)

    dialog = make_dialog()

    result = dialog.forms["decoder"].persistence_result()

    assert result[DRIVER].value == VideoDriver.VLC_HW_SP


def test_the_processes_choice_saves_the_twin(libs, make_dialog, settings):
    dialog = make_dialog()

    _pick_decoder(dialog, VideoDriver.VLC_SW)
    _pick_single(dialog, True)
    dialog.save_settings()

    assert settings.get(DRIVER) == VideoDriver.VLC_SW_SP


def _processes_line(dialog):
    return _editor(dialog)._processes_line


@pytest.mark.parametrize("decoder", [VideoDriver.MPV_HW, VideoDriver.MPV_SW])
def test_mpv_has_no_processes_choice_to_show(libs, make_dialog, decoder):
    dialog = make_dialog()

    _pick_decoder(dialog, decoder)

    assert _processes_line(dialog).isHidden()
    assert _editor(dialog).processes.currentData() is True
    assert dialog.value(DRIVER) == decoder


def test_mpv_saved_opens_with_no_processes_choice(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.MPV_SW)

    dialog = make_dialog()

    assert _processes_line(dialog).isHidden()


def test_going_back_to_vlc_brings_back_the_choice(libs, make_dialog):
    dialog = make_dialog()
    processes = _editor(dialog).processes

    _pick_decoder(dialog, VideoDriver.VLC_SW)
    assert processes.currentData() is False

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    _pick_decoder(dialog, VideoDriver.VLC_SW)

    assert not _processes_line(dialog).isHidden()
    assert processes.currentData() is False
    assert processes.isEnabled()
    assert dialog.value(DRIVER) == VideoDriver.VLC_SW


def test_macos_vlc_hardware_is_locked_software_is_not(libs, make_dialog, monkeypatch):
    monkeypatch.setattr(env, "IS_MACOS", True)

    dialog = make_dialog()
    processes = _editor(dialog).processes

    _pick_decoder(dialog, VideoDriver.VLC_HW)
    # shown, greyed out: it can be chosen with the other VLC
    assert not _processes_line(dialog).isHidden()
    assert not processes.isEnabled()
    assert dialog.value(DRIVER) == VideoDriver.VLC_HW_SP

    _pick_decoder(dialog, VideoDriver.VLC_SW)
    assert processes.isEnabled()
    assert dialog.value(DRIVER) == VideoDriver.VLC_SW


def test_videos_per_process_only_with_multi_process(libs, make_dialog):
    dialog = make_dialog()
    row = dialog.forms["decoder"]._rows["player/video_driver_players"]

    _pick_decoder(dialog, VideoDriver.VLC_HW)
    assert not row.isHidden()

    _pick_single(dialog, True)
    assert row.isHidden()

    _pick_single(dialog, False)
    assert not row.isHidden()

    _pick_decoder(dialog, VideoDriver.MPV_HW)
    assert row.isHidden()


def test_reset_goes_back_to_the_default_of_both(libs, make_dialog, settings):
    settings.set(DRIVER, VideoDriver.VLC_SW_SP)

    dialog = make_dialog()
    dialog.forms["decoder"].reset(DRIVER)

    assert dialog.value(DRIVER) == VideoDriver.MPV_HW
    # MPV plays in a single process
    assert _editor(dialog).processes.currentData() is True


@pytest.mark.usefixtures("wayland_with_xwayland")
@pytest.mark.parametrize(
    ("display", "said"),
    [
        (
            DisplayServer.AUTO,
            "VLC Hardware needs X11. Works after you restart GridPlayer.",
        ),
        (
            DisplayServer.X11,
            "VLC Hardware needs X11. Works after you restart GridPlayer.",
        ),
        (
            DisplayServer.WAYLAND,
            "VLC Hardware needs X11. Set Window system to Auto or X11.",
        ),
    ],
)
def test_hardware_picked_on_wayland_with_xwayland(
    libs, make_dialog, settings, display, said
):
    settings.set(DRIVER, VideoDriver.VLC_HW)
    settings.set("player/display_server", display)

    assert _note(make_dialog()) == (
        f"VLC Hardware can't run. Playing with VLC Software for now.\n{said}"
    )


@pytest.mark.usefixtures("wayland_with_xwayland")
def test_wayland_with_xwayland_says_nothing_if_hardware_isnt_picked(
    libs, make_dialog, settings
):
    settings.set(DRIVER, VideoDriver.MPV_HW)

    assert _note(make_dialog()) is None


@pytest.mark.usefixtures("wayland_with_xwayland")
def test_hardware_picked_with_platform_given(libs, make_dialog, settings, monkeypatch):
    monkeypatch.setattr(env, "IS_QT_PLATFORM_PICKED", False)
    settings.set(DRIVER, VideoDriver.VLC_HW)

    assert _note(make_dialog()) == (
        "VLC Hardware can't run. Playing with VLC Software for now.\n"
        "VLC Hardware needs X11. GridPlayer was started with --platform wayland."
    )


@pytest.mark.usefixtures("wayland_with_xwayland")
def test_the_notice_follows_the_window_system_on_the_page(
    libs, make_dialog, settings, monkeypatch
):
    monkeypatch.setattr(env, "IS_LINUX", True)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    settings.set(DRIVER, VideoDriver.VLC_HW)
    settings.set("player/display_server", DisplayServer.WAYLAND)

    dialog = make_dialog()
    assert "Set Window system to Auto or X11" in _note(dialog)

    buttons = dialog.widget("player/display_server")
    buttons.setCurrentIndex(buttons.findData(DisplayServer.AUTO))

    assert "Works after you restart GridPlayer" in _note(dialog)
