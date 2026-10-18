"""Searching the Settings dialog: what a search finds."""

from gridplayer.utils.text_search import Query


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
