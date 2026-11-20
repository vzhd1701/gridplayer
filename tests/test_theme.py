from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

from gridplayer.params.static import ColorScheme
from gridplayer.params.theme import (
    THEME_DARK,
    THEME_LIGHT,
    combo_popup_stylesheet,
    current_colors,
    fusion_palette,
    selection_fill,
)
from gridplayer.utils.darkmode import is_dark_mode


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    import gridplayer.settings as settings_mod

    app = QApplication.instance() or QApplication([])
    settings_mod.SETTINGS = None
    return app


def test_current_colors_match_system_theme():
    colors = current_colors()
    expected = THEME_DARK if is_dark_mode() else THEME_LIGHT
    assert colors is expected
    assert colors["base"] != "#000000"
    assert colors["text"] != colors["base"]


def test_fusion_palette_has_readable_contrast():
    palette = fusion_palette()
    base = palette.color(QPalette.ColorRole.Base)
    text = palette.color(QPalette.ColorRole.Text)
    if is_dark_mode():
        assert base.lightness() > 40
        assert text.lightness() > 180
    else:
        assert base.lightness() > 200
        assert text.lightness() < 40


def test_selection_fill_matches_theme_highlight():
    assert selection_fill().name() == current_colors()["highlight"]


def test_combo_popup_stylesheet_uses_theme_base():
    style = combo_popup_stylesheet()
    colors = current_colors()
    assert colors["base"] in style
    assert colors["text"] in style
    assert "QComboBox QAbstractItemView" in style
    # the index lies straight on the dialog
    assert "QListWidget#section_index {background: transparent;" in style
    # a table's header in a round box has no edges but the line under it
    assert "QWidget#rounded_box QHeaderView::section {" in style
    # the settings dialogs' scroll bars are a thin handle alone
    assert "QDialog#settings_dialog QScrollBar::handle {" in style
    assert colors["scroll_handle"] in style


def test_apply_theme_sets_app_palette():
    app = QApplication.instance() or QApplication([])
    from gridplayer.params.theme import apply_theme

    apply_theme(app)
    assert (
        app.palette().color(QPalette.ColorRole.Base).name() == current_colors()["base"]
    )
    assert "QComboBox QAbstractItemView" in app.styleSheet()


def test_apply_theme_recolors_html_links():
    from PyQt6.QtWidgets import QLabel, QTextBrowser

    from gridplayer.params.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    label = QLabel('<a href="https://example.com">link</a>')
    label.show()
    browser = QTextBrowser()
    browser.setHtml('<a href="https://example.com">link</a>')
    browser.show()

    apply_theme(app)
    apply_theme(app)

    assert current_colors()["link"] in browser.document().defaultStyleSheet()
    assert current_colors()["link"] in label.text()
    assert "qrichtext" not in label.text().lower()
    assert "reference" not in label.text() or "<a href=" in label.text().lower()

    vlc = QLabel(
        'VLC Options [<a href="https://wiki.videolan.org/VLC_command-line_help/">'
        "reference</a>]"
    )
    vlc.show()
    apply_theme(app)
    apply_theme(app)
    source = vlc.property("gp_html_src")
    assert source.count("<a href") == 1
    assert "<style" not in source
    assert "reference" in source

    label.hide()
    browser.hide()
    vlc.hide()
    label.deleteLater()
    browser.deleteLater()
    vlc.deleteLater()


def test_dialog_button_icons_stripped_by_proxy_style(mocker):
    mocker.patch("gridplayer.params.theme.env.IS_LINUX", True)

    from PyQt6.QtWidgets import QStyle

    from gridplayer.params import theme as theme_mod
    from gridplayer.params.theme import apply_theme, create_fusion_style

    style = create_fusion_style()

    for standard_icon in theme_mod._DIALOG_ICON_ROLES:
        assert style.standardIcon(standard_icon).isNull()

    # non-dialog icons pass through to the wrapped Fusion style
    assert not style.standardIcon(QStyle.StandardPixmap.SP_DirIcon).isNull()

    # apply_theme wraps the app style; the stripping must survive the
    # QStyleSheetStyle wrapper that app.setStyleSheet() puts on top of it.
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    apply_theme(app)

    assert theme_mod._dialog_button_style_installed
    assert app.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton).isNull()
    assert not app.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon).isNull()


def test_html_set_after_the_theme_still_gets_theme_links():
    """A dialog that fills itself in writes its links long after startup.

    The colour is baked into the label's document as the text is set, so
    text written later would otherwise come out in Qt's own blue, which
    on a dark base is barely there.
    """

    from PyQt6.QtWidgets import QLabel

    from gridplayer.params.theme import apply_theme, set_html_with_links

    app = QApplication.instance() or QApplication([])
    apply_theme(app)

    label = QLabel()
    label.show()

    set_html_with_links(label, 'See <a href="https://example.com">the page</a>')

    assert current_colors()["link"] in label.text()

    # what the theme starts from next time, kept clean so a switch
    # recolours the links rather than layering a rule over the old one
    source = label.property("gp_html_src")
    assert "<style" not in source

    apply_theme(app)

    assert label.property("gp_html_src") == source
    assert label.text().count("<style") == 1

    label.hide()
    label.deleteLater()


@pytest.mark.parametrize(
    "role",
    [
        QPalette.ColorRole.Light,
        QPalette.ColorRole.Midlight,
        QPalette.ColorRole.Mid,
        QPalette.ColorRole.Dark,
        QPalette.ColorRole.Shadow,
        QPalette.ColorRole.LinkVisited,
        QPalette.ColorRole.Accent,
    ],
)
def test_no_shade_is_left_to_the_system(role):
    """Left to the system's palette, Qt 6 makes them dark with the system,
    whatever the app's scheme: black borders (palette(mid)), and the system's
    accent colour in a grey app."""

    palette = fusion_palette()

    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        assert palette.isBrushSet(group, role)


@pytest.mark.parametrize(
    ("is_linux", "setting", "is_dark", "told"),
    [
        (True, ColorScheme.LIGHT, False, Qt.ColorScheme.Light),
        (True, ColorScheme.DARK, True, Qt.ColorScheme.Dark),
        # Linux: the system's as the app's own watcher hears it, not as Qt
        # guesses it
        (True, ColorScheme.SYSTEM, True, Qt.ColorScheme.Dark),
        (True, ColorScheme.SYSTEM, False, Qt.ColorScheme.Light),
        # Windows and macOS: the system's is heard through Qt, which says
        # only the one it's told, once told one
        (False, ColorScheme.SYSTEM, True, Qt.ColorScheme.Unknown),
        (False, ColorScheme.SYSTEM, False, Qt.ColorScheme.Unknown),
        (False, None, False, Qt.ColorScheme.Unknown),
        (False, ColorScheme.DARK, True, Qt.ColorScheme.Dark),
        (False, ColorScheme.LIGHT, False, Qt.ColorScheme.Light),
    ],
)
def test_qt_is_told_the_scheme_of_the_palette(
    monkeypatch, is_linux, setting, is_dark, told
):
    """Fusion draws some things (a check box's outline) by Qt's scheme rather
    than the palette."""

    import gridplayer.params.theme as theme

    monkeypatch.setattr(theme.env, "IS_LINUX", is_linux)
    monkeypatch.setattr(theme, "app_color_scheme", lambda: setting)
    monkeypatch.setattr(theme, "is_dark_mode", lambda: is_dark)
    monkeypatch.setattr(theme, "_told_scheme", [])
    asked = []
    app = SimpleNamespace(
        styleHints=lambda: SimpleNamespace(setColorScheme=asked.append)
    )

    theme._tell_qt_the_scheme(app)
    # again, as each apply_theme does: Qt isn't set off for nothing
    theme._tell_qt_the_scheme(app)

    assert asked == [told]
