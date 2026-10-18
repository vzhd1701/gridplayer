"""Searching the Settings dialog: what a search finds, and how a page
shows it."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ComboField,
    Indented,
    Section,
    When,
)
from gridplayer.utils.text_search import Query
from gridplayer.widgets.settings_form import SettingsForm, _put_away


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
