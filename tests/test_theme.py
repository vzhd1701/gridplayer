import pytest
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication

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
    base = palette.color(QPalette.Base)
    text = palette.color(QPalette.Text)
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
    assert "QListWidget#section_index::item:disabled" in style


def test_apply_theme_sets_app_palette():
    app = QApplication.instance() or QApplication([])
    from gridplayer.params.theme import apply_theme

    apply_theme(app)
    assert app.palette().color(QPalette.Base).name() == current_colors()["base"]
    assert "QComboBox QAbstractItemView" in app.styleSheet()


def test_apply_theme_recolors_html_links():
    from PyQt5.QtWidgets import QLabel, QTextBrowser

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
