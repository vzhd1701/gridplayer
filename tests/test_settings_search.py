"""Searching the Settings dialog: what a search finds, and how the pages
show it."""

import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.paged_dialog import SEARCH_DELAY_MS
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    Indented,
    Section,
    When,
)
from gridplayer.utils.text_search import Query
from gridplayer.widgets.settings_form import SettingsForm, _put_away
from gridplayer.widgets.settings_index import FOUND_ROLE


class TestQuery:
    def test_words_are_found_by_their_start(self):
        query = Query("pau")

        assert query.is_in(["Paused"])
        assert not query.is_in(["Unpaused"])

    def test_case_and_accents_do_not_matter(self):
        assert Query("FUR").is_in(["Für Elise"])
        assert Query("für").is_in(["FUR"])

    def test_every_word_is_found_in_any_order_and_any_text(self):
        query = Query("speed sync")

        assert query.is_in(["Sync speed"])
        assert query.is_in(["Sync", "Playback speed"])
        assert not query.is_in(["Sync play and pause"])

    def test_words_are_split_as_the_texts_are(self):
        assert Query("drag-n-drop").is_in(["Drag-n-Drop"])
        assert Query("yt dlp").is_in(["yt-dlp"])

    def test_a_script_without_spaces_is_found_anywhere(self):
        assert Query("字幕").is_in(["外部字幕ファイル"])

    def test_nothing_typed_is_no_query(self):
        assert not Query("  ")
        assert not Query("-/")

    def test_spans_are_in_the_text_as_written(self):
        assert Query("fur").spans("Über für") == [(5, 8)]
        assert Query("sync syn").spans("Sync speed") == [(0, 4)]

    def test_marked_escapes_plain_text(self):
        marked = Query("a").marked("a < b", "<b>")

        assert marked == "<b>a</b> &lt; b"

    def test_marked_leaves_tags_and_entities_alone(self):
        text = 'VLC Options [<a href="https://vlc.example/a">reference</a>] &amp; a'

        marked = Query("a ref").marked(text, "<b>", is_html=True)

        assert marked == (
            'VLC Options [<a href="https://vlc.example/a"><b>ref</b>erence</a>]'
            " &amp; <b>a</b>"
        )


def _form(*items):
    return SettingsForm(items)


def _shown(form, key):
    row = form._rows[key]
    return not _put_away(row)


def _settle():
    QApplication.processEvents()
    QApplication.processEvents()


class TestTheForm:
    def test_a_setting_out_of_sight_for_good_is_never_found(self):
        form = _form(
            Section(
                "Box",
                CheckboxField(settings_key="a/here", label="Shown thing"),
                CheckboxField(
                    settings_key="a/gone", label="Gone thing", shown_if=lambda: False
                ),
            )
        )

        found = form.find(Query("thing"))

        assert [f.row for f in found] == [form._rows["a/here"]]

    def test_a_long_list_of_options_is_not_searched(self):
        many = {f"v{i}": f"Option {i}" for i in range(30)}
        few = {"x": "Plain", "y": "Fancy"}
        form = _form(
            ComboField(settings_key="a/many", label="Many", choices=lambda: many),
            ComboField(settings_key="a/few", label="Few", choices=lambda: few),
        )

        assert form.find(Query("option 7")) == []
        assert [f.option for f in form.find(Query("fancy"))] == ["Fancy"]

    def test_the_option_picked_is_a_name_and_needs_no_hint(self):
        few = {"x": "Plain", "y": "Fancy"}
        form = _form(ComboField(settings_key="a/few", label="Few", choices=lambda: few))

        found = form.find(Query("plain"))

        assert len(found) == 1
        assert found[0].option is None

    def test_the_page_title_finds_every_row(self):
        form = _form(
            CheckboxField(settings_key="a/one", label="One"),
            CheckboxField(settings_key="a/two", label="Two"),
        )

        assert len(form.find(Query("network"), "Network")) == 2

    def test_a_found_sub_option_brings_what_it_belongs_to(self):
        form = _form(
            CheckboxField(settings_key="a/hide", label="Hide it"),
            Indented(
                CheckboxField(
                    settings_key="a/delay",
                    label="Delay",
                    enabled_when=When("a/hide"),
                )
            ),
            CheckboxField(settings_key="a/other", label="Other"),
        )
        form.set_values({"a/hide": False, "a/delay": False, "a/other": False})

        query = Query("delay")
        form.show_found(query, form.find(query))

        assert _shown(form, "a/delay")
        assert not form.is_enabled("a/delay")
        assert _shown(form, "a/hide")
        assert not _shown(form, "a/other")

    def test_turning_on_what_was_found_shows_its_sub_options(self):
        form = _form(
            CheckboxField(settings_key="a/hide", label="Hide it"),
            Indented(
                CheckboxField(
                    settings_key="a/delay",
                    label="Delay",
                    enabled_when=When("a/hide"),
                )
            ),
        )
        form.set_values({"a/hide": False, "a/delay": False})

        query = Query("hide")
        form.show_found(query, form.find(query))
        assert not _shown(form, "a/delay")

        form.widget("a/hide").setChecked(True)

        assert _shown(form, "a/delay")

    def test_no_query_puts_every_row_and_label_back(self):
        form = _form(
            Section(
                "Box",
                CheckboxField(settings_key="a/one", label="One thing"),
                CheckboxField(settings_key="a/two", label="Two"),
            )
        )
        label = form.editor("a/one").marked

        query = Query("thing")
        form.show_found(query, form.find(query))
        assert "<span" in label.text()
        assert not _shown(form, "a/two")

        form.show_found(None)

        assert label.text() == "One thing"
        assert label.textFormat() == Qt.AutoText
        assert _shown(form, "a/two")


@pytest.fixture
def dialog():
    dialog = SettingsDialog(None)
    dialog.show()
    _settle()

    yield dialog

    dialog.close()
    dialog.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _found_on(dialog, page_id):
    return dialog._index_items[page_id].data(FOUND_ROLE)


def _key(dialog, key):
    QApplication.sendEvent(
        dialog.search_box, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
    )


def _in_view(form, widget):
    viewport = form._scroll_area().viewport()
    top = widget.mapTo(viewport, QPoint(0, 0)).y()
    return 0 <= top and top + widget.height() <= viewport.height()


class TestTheDialog:
    def test_the_pages_say_how_much_was_found_on_them(self, dialog):
        dialog.search("pause")

        assert _found_on(dialog, "playlist") == 3
        assert _found_on(dialog, "video") == 3
        assert _found_on(dialog, "player") == 0

        item = dialog._index_items["player"]
        assert not item.flags() & Qt.ItemIsEnabled

    def test_a_page_with_settings_found_opens_first(self, dialog):
        dialog.show_page("player")

        dialog.search("pause")

        # Shortcuts comes first, but has only the shortcuts its filter found
        assert dialog.section_page.currentWidget() is dialog.pages["playlist"]

    def test_the_page_open_stays_if_anything_is_found_on_it(self, dialog):
        dialog.show_page("video")

        dialog.search("pause")

        assert dialog.section_page.currentWidget() is dialog.pages["video"]

    def test_only_the_rows_found_are_shown(self, dialog):
        dialog.search("pause")
        form = dialog.forms["playlist"]

        assert _shown(form, "playlist/pause_minimized")
        assert _shown(form, "playlist/pause_sync")
        assert not _shown(form, "playlist/view_sync")

    def test_a_row_found_by_an_option_says_which(self, dialog):
        dialog.search("pause")
        row = dialog.forms["video"]._rows["video_defaults/end_action"]

        assert row.hint is not None
        assert row.hint.text() == "Option: Pause at start"

    def test_tooltips_count_only_when_no_name_has_the_words(self, dialog):
        dialog.search("proxy")
        assert _found_on(dialog, "network") == 2
        assert not _shown(dialog.forms["network"], "network/verify_tls")

        dialog.search("recycle")
        assert _found_on(dialog, "playlist") == 1
        assert _shown(dialog.forms["playlist"], "playlist/folder_skip_hidden")

    def test_shortcuts_are_found_by_their_own_filter(self, dialog):
        editor = dialog.widget("player/keymap")
        editor.filter_edit.setText("mine")

        dialog.search("pause")

        assert _found_on(dialog, "shortcuts") == editor.count_matching("pause")
        assert editor.filter_edit.text() == "pause"

        dialog.search("")

        assert editor.filter_edit.text() == "mine"

    def test_a_tooltip_find_stays_beside_what_a_list_finds_in_itself(self, dialog):
        # in a tooltip on Player, and in some shortcuts' names
        dialog.search("picture")

        assert _found_on(dialog, "shortcuts")
        assert _found_on(dialog, "player")

    def test_a_note_goes_with_the_rows_it_is_under(self, dialog):
        form = dialog.forms["cookies"]
        section = dict(form.sections())["Stored cookies"]

        dialog.search("refresh")

        assert _shown(form, "cookies/allow_update")
        assert _put_away(section)

        dialog.search("")

        assert not _put_away(section)
        assert not any(_put_away(note) for note in form._notes)

    def test_a_setting_pointed_at_is_out_of_the_search(self, dialog, mocker):
        mocker.patch.object(settings_dialog.QCustomMessageBox, "warning")
        key = "screenshots/filename_template"
        dialog.widget(key).setText("%Q")
        dialog.search("proxy")

        dialog.accept()

        assert dialog.search_box.text() == ""
        assert _shown(dialog.form_of(key), key)
        assert QApplication.focusWidget() is dialog.widget(key)

    def test_after_a_search_a_page_is_back_where_it_was(self, dialog):
        dialog.show_page("player")
        bar = dialog.forms["player"]._scroll_area().verticalScrollBar()
        bar.setValue(bar.maximum() // 2)
        before = bar.value()
        assert before > 0

        # found elsewhere, so the page is out of sight as the search ends
        dialog.search("pause")
        assert dialog.section_page.currentWidget() is not dialog.pages["player"]
        dialog.search("")
        dialog.show_page("player")

        assert bar.value() == before

    def test_after_a_search_a_page_is_at_the_field_gone_to(self, dialog):
        dialog.show_page("player")
        dialog.search_box.setFocus()
        dialog.search_box.setText("jpg")
        _key(dialog, Qt.Key_Return)
        form = dialog.forms["player"]
        field = QApplication.focusWidget()
        assert form.isAncestorOf(field)

        dialog.search("")

        assert form._scroll_area().verticalScrollBar().value() > 0
        assert _in_view(form, field)

    def test_enter_searches_only_what_is_waiting(self, dialog, mocker):
        dialog.search("pause")
        find = mocker.spy(dialog.forms["playlist"], "find")

        _key(dialog, Qt.Key_Return)
        _key(dialog, Qt.Key_Down)

        assert not find.called

    def test_nothing_found_says_so(self, dialog):
        dialog.search("zzzqqq")

        assert dialog.section_page.currentWidget() is dialog._nothing_found
        assert "zzzqqq" in dialog._nothing_found.text()

        dialog.search("")

        assert dialog.section_page.currentWidget() is not dialog._nothing_found

    def test_reset_links_and_notes_are_away_while_searching(self, dialog):
        dialog.show_page("playlist")
        dialog.widget("playlist/save_window").click()
        assert dialog.resetPage.isVisibleTo(dialog)

        dialog.search("save")

        assert not dialog.resetPage.isVisibleTo(dialog)
        assert not dialog.section_links["playlist"].isVisibleTo(dialog)

        dialog.search("")

        assert dialog.resetPage.isVisibleTo(dialog)
        assert dialog.section_links["playlist"].isVisibleTo(dialog)

    def test_esc_empties_the_box_before_it_closes_the_dialog(self, dialog):
        dialog.search("pause")

        _key(dialog, Qt.Key_Escape)

        assert dialog.search_box.text() == ""
        assert dialog.isVisible()
        assert _found_on(dialog, "playlist") is None

    def test_enter_goes_to_what_was_found_and_not_to_ok(self, dialog):
        dialog.search_box.setFocus()
        dialog.search_box.setText("minimized")

        _key(dialog, Qt.Key_Return)
        _settle()

        assert dialog.isVisible()
        assert dialog.result() == 0
        assert QApplication.focusWidget() is dialog.widget("playlist/pause_minimized")

    def test_typing_searches_once_typing_rests(self, dialog):
        dialog.search_box.setText("pause")

        assert _found_on(dialog, "playlist") is None

        QTest.qWait(SEARCH_DELAY_MS + 100)

        assert _found_on(dialog, "playlist") == 3
