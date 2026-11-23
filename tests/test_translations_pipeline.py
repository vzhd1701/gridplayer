from pathlib import Path

import pytest

from scripts.translations.pipeline import merge, qa, stats, ts_file
from scripts.translations.pipeline.ts_file import (
    AI,
    HUMAN,
    MISSING,
    VANISHED,
    Message,
    TsFile,
)

TRANSLATIONS = Path(__file__).resolve().parents[1] / "resources" / "translations"


def _source(*texts, context="Ctx"):
    return TsFile(messages=[Message(context=context, source=t) for t in texts])


def _lang(*messages):
    return TsFile(language="de", sourcelanguage="en", messages=list(messages))


def _ai(source, text, context="Ctx"):
    msg = Message(context=context, source=source)
    merge.set_ai(msg, text, "fake/model 2026-11-23")
    return msg


def _human(source, text, context="Ctx"):
    return Message(context=context, source=source, translation=text)


@pytest.mark.parametrize(
    "path",
    [p for p in sorted(TRANSLATIONS.glob("*.ts")) if p.stem != "en_US"],
    ids=lambda p: p.stem,
)
def test_language_file_reads_back_the_same(path, tmp_path):
    ts = ts_file.read(path)

    out = tmp_path / path.name
    ts_file.write(ts, out)

    assert ts_file.read(out) == ts
    assert ts_file.dumps(ts_file.read(out)) == out.read_text(encoding="utf-8")


def test_ai_translation_is_written_unfinished_with_its_mark(tmp_path):
    ts = _lang(_ai("Play", "Abspielen"), Message(context="Ctx", source="Stop"))

    text = ts_file.dumps(ts)

    assert '<translation type="unfinished">Abspielen</translation>' in text
    assert "<extra-gp-ai>fake/model 2026-11-23</extra-gp-ai>" in text
    assert "<translation/>" in text

    out = tmp_path / "de_DE.ts"
    ts_file.write(ts, out)
    back = ts_file.read(out)
    assert [m.origin for m in back.messages] == [AI, MISSING]


def test_approved_human_translation_takes_the_place_of_the_ai():
    current = _lang(_ai("Play", "Abspielen (KI)"))

    result, report = merge.merge(
        _source("Play"), current, {("Ctx", "Play", ""): "Abspielen"}, "de"
    )

    (msg,) = result.live()
    assert msg.origin == HUMAN
    assert msg.translation == "Abspielen"
    assert msg.extras == {}
    assert report.ai_replaced_by_human == 1


def test_ai_translation_stays_while_no_one_approved_another():
    current = _lang(_ai("Play", "Abspielen"))

    result, report = merge.merge(_source("Play"), current, {}, "de")

    (msg,) = result.live()
    assert msg.origin == AI
    assert msg.translation == "Abspielen"
    assert report.ai_kept == 1
    assert merge.todo(result) == []


def test_reworded_english_is_new_work_with_the_old_human_text_as_a_hint():
    current = _lang(_human("Open file", "Datei öffnen"))
    approved = {("Ctx", "Open file", ""): "Datei öffnen"}

    result, report = merge.merge(_source("Open a file"), current, approved, "de")

    (new,) = result.live()
    assert new.origin == MISSING
    assert merge.todo(result) == [new]
    (hint,) = [m for m in result.messages if m.origin == VANISHED]
    assert (hint.source, hint.translation) == ("Open file", "Datei öffnen")
    assert report.vanished == 1


def test_without_a_pull_human_translations_are_kept():
    current = _lang(_human("Play", "Abspielen"))

    result, _ = merge.merge(_source("Play"), current, None, "de")

    assert result.live()[0].origin == HUMAN


def test_a_withdrawn_approval_leaves_the_string_to_do():
    current = _lang(_human("Play", "Abspielen"))

    result, report = merge.merge(_source("Play"), current, {}, "de")

    assert result.live()[0].origin == MISSING
    assert report.dropped_human == [("Ctx", "Play", "")]


def test_a_string_rejected_twice_stays_english():
    current = _lang(Message(context="Ctx", source="Play"))
    merge.add_rejected(current.messages[0], "Spielen")

    result, _ = merge.merge(_source("Play"), current, {}, "de")
    (msg,) = result.live()
    assert merge.todo(result) == [msg]
    assert merge.rejected(msg) == ["Spielen"]

    merge.set_ai(msg, "Abspielen", "fake/model")
    merge.add_rejected(msg, "Abspielen")
    msg.translation = ""
    msg.extras.pop(ts_file.AI_EXTRA)

    assert merge.todo(result) == []


def test_retranslate_takes_ai_strings_but_never_human_ones():
    current = _lang(_ai("Play", "Abspielen"), _human("Stop", "Stopp"))
    approved = {("Ctx", "Stop", ""): "Stopp"}

    result, _ = merge.merge(_source("Play", "Stop"), current, approved, "de")

    assert [m.source for m in merge.todo(result, retranslate_ai=True)] == ["Play"]


def test_retranslate_leaves_what_crowdin_has():
    """Crowdin would keep the old text, and its approval would come back."""
    sent = _ai("Play", "Abspielen")
    sent.extras[ts_file.CROWDIN_EXTRA] = "77"
    current = _lang(sent, _ai("Stop", "Stoppen"))

    result, _ = merge.merge(_source("Play", "Stop"), current, None, "de")

    assert [m.source for m in merge.todo(result, retranslate_ai=True)] == ["Stop"]


def test_progress_counts_checked_and_ai():
    ts = _lang(
        _human("A", "a"),
        _human("B", "b"),
        _ai("C", "c"),
        Message(context="Ctx", source="D"),
        Message(context="Ctx", source="Old", translation="x", type="vanished"),
    )

    source = _lang(*[Message(context="Ctx", source=s) for s in "ABCD"])
    p = stats.progress(ts, source)

    assert (p.total, p.human, p.ai) == (4, 2, 1)
    assert p.as_dict() == {"checked": 50, "ai": 25}


def test_progress_is_of_the_english_now():
    """A file not merged since en_US.ts grew is not complete."""
    ts = _lang(_human("A", "a"), _human("Gone", "g"))
    source = _lang(*[Message(context="Ctx", source=s) for s in "ABCD"])

    assert stats.progress(ts, source).as_dict() == {"checked": 25, "ai": 0}


@pytest.mark.parametrize("humans", [999, 223])
def test_one_ai_string_in_many_still_shows(humans):
    names = [str(i) for i in range(1801)]
    ts = _lang(*[_human(n, "x") for n in names[:humans]], _ai("last", "x"))
    source = _lang(*[Message(context="Ctx", source=n) for n in [*names, "last"]])

    assert stats.progress(ts, source).as_dict()["ai"] == 1


@pytest.mark.parametrize(
    ("source", "translation", "code"),
    [
        ("Open {name}", "Öffnen {nom}", qa.CRASH),
        ("Open {name}", "Öffnen", "placeholders"),
        ("<b>Bold</b> text", "<b>Fett Text", "html"),
        ("Paste", "&Einfügen", "accelerator"),
        ("Play", " ", "empty"),
    ],
)
def test_qa_errors(source, translation, code):
    issues = qa.check(source, translation)

    assert code in {i.code for i in qa.errors(issues)}


@pytest.mark.parametrize(
    ("source", "translation"),
    [
        ("Open {name}", "{name} öffnen"),
        ("Video & audio", "Video & Audio"),
        ('<a href="{url}">here</a>', '<a href="{url}">hier</a>'),
        ("Speed 5%", "Geschwindigkeit 5%"),
    ],
)
def test_qa_passes(source, translation):
    assert qa.errors(qa.check(source, translation)) == []


def _ai_setup(tmp_path, languages):
    """An app of one file, its en_US.ts, and a language file each with only
    "Stop" translated by a person."""
    from scripts.translations.pipeline import ai

    app = tmp_path / "app"
    app.mkdir()
    code = "\n".join(f"line{n} = None" for n in range(1, 40))
    (app / "menu.py").write_text(code, encoding="utf-8")
    source = TsFile(
        messages=[
            Message(context="Ctx", source="Play {name}", locations=[("menu.py", 10)]),
            Message(context="Ctx", source="Stop", locations=[("menu.py", 12)]),
            Message(context="Ctx", source="Pause", locations=[("menu.py", 30)]),
        ]
    )
    jobs = []
    for code_, name in languages:
        path = tmp_path / f"{code_}.ts"
        ts_file.write(
            _lang(
                Message(context="Ctx", source="Play {name}"),
                _human("Stop", "Stopp"),
                Message(context="Ctx", source="Pause"),
            ),
            path,
        )
        jobs.append(ai.Job(code_, name, path))
    return ai.Common(source, app, ""), jobs


def test_ai_fills_what_is_missing_and_marks_it(tmp_path):
    from scripts.translations.pipeline import ai
    from scripts.translations.pipeline.providers import Fake

    common, jobs = _ai_setup(tmp_path, [("de_DE", "German")])

    report = ai.translate(
        jobs, common, Fake(), batch_size=10, parallel=1, log=lambda *_: None
    )

    assert report.languages["de_DE"].translated == 2
    play, stop, pause = ts_file.read(jobs[0].lang_path).live()
    assert play.origin == AI
    assert play.translation == "[German] Play {name}"
    assert play.extras[ts_file.AI_EXTRA].startswith("fake/default ")
    assert (stop.origin, stop.translation) == (HUMAN, "Stopp")
    assert pause.translation == "[German] Pause"


def test_languages_share_a_batch_the_provider_can_cache(tmp_path):
    from scripts.translations.pipeline import ai
    from scripts.translations.pipeline.providers import Fake

    common, jobs = _ai_setup(tmp_path, [("de_DE", "German"), ("cs_CZ", "Czech")])
    # Czech misses "Stop" too
    ts_file.write(
        _lang(
            *[
                Message(context="Ctx", source=t)
                for t in ("Play {name}", "Stop", "Pause")
            ]
        ),
        jobs[1].lang_path,
    )
    fake = Fake()

    ai.translate(jobs, common, fake, batch_size=10, parallel=2, log=lambda *_: None)

    (de_fixed, de_varying), (cs_fixed, cs_varying) = fake.requests
    # the strings and code first, the same for both languages
    assert de_fixed == cs_fixed
    assert "Play {name}" in de_fixed
    assert "line10 = None" in de_fixed
    assert "Approved German" in de_varying
    assert "Approved Czech" in cs_varying
    # only what each one misses
    assert "these ids: s1, s3" in de_varying
    assert "these ids: s1, s2, s3" in cs_varying
    assert ts_file.read(jobs[1].lang_path).live()[1].translation == "[Czech] Stop"


def test_one_language_caches_its_approved_translations_instead(tmp_path):
    from scripts.translations.pipeline import ai
    from scripts.translations.pipeline.providers import Fake

    common, jobs = _ai_setup(tmp_path, [("de_DE", "German")])
    fake = Fake()

    ai.translate(jobs, common, fake, batch_size=1, parallel=1, log=lambda *_: None)

    (first, _), (second, _) = fake.requests
    assert first == second
    assert "Approved German" in first
    assert "Play {name}" not in first


def test_a_broken_answer_is_asked_again_with_what_was_wrong(tmp_path):
    from scripts.translations.pipeline import ai
    from scripts.translations.pipeline.providers import Fake

    class LosesPlaceholders(Fake):
        def run(self, fixed, varying, schema):
            answer = super().run(fixed, varying, schema)
            if len(self.requests) == 1:
                for a in answer:
                    a["text"] = a["text"].replace("{name}", "{nom}")
            return answer

    common, jobs = _ai_setup(tmp_path, [("de_DE", "German")])
    fake = LosesPlaceholders()

    report = ai.translate(
        jobs, common, fake, batch_size=10, parallel=1, log=lambda *_: None
    )

    assert report.languages["de_DE"].translated == 2
    assert "problem_with_last_try" in fake.requests[1][1]
    assert (
        ts_file.read(jobs[0].lang_path).live()[0].translation == "[German] Play {name}"
    )


def test_batches_keep_a_file_together_and_pack_small_ones():
    from scripts.translations.pipeline import context

    source = TsFile(
        messages=[
            Message(context="C", source=f"{f}{n}", locations=[(f, n + 1)])
            for f, count in (("a.py", 3), ("b.py", 2), ("c.py", 4))
            for n in range(count)
        ]
    )
    items = context.items(source)

    files = [[i.places[0][0] for i in b] for b in context.batches(items, 5)]

    assert files == [["a.py"] * 3 + ["b.py"] * 2, ["c.py"] * 4]


def _linked_source(*more):
    return TsFile(
        messages=[
            Message(context="Actions", source="Crop Limit", locations=[("a.py", 1)]),
            Message(context="Actions", source="Stop", locations=[("a.py", 2)]),
            Message(context="Set", source="Any", locations=[("b.py", 1)]),
            Message(context="Set", source="any", locations=[("b.py", 2)]),
            Message(
                context="Set",
                source="Crop limit",
                comment="",
                locations=[("b.py", 3)],
            ),
            Message(context="Set", source="Scale to Fit", locations=[("b.py", 4)]),
            Message(
                context="Set",
                source="Scale to Fit: the tiles fill the window, the gaps go.",
                locations=[("b.py", 5)],
            ),
            Message(
                context="Set", source="Reset Scale to Fit", locations=[("b.py", 7)]
            ),
            *more,
        ]
    )


def test_links_find_one_thing_said_twice():
    from scripts.translations.pipeline import context

    tick = Message(context="Set", source='Tick "Stop" to stop.')
    link = context.links(_linked_source(tick))

    assert link.same[("Actions", "Crop Limit", "")] == [("Set", "Crop limit", "")]
    # one word can need another form ("Любая", "любой")
    assert ("Set", "Any", "") not in link.same
    tooltip = ("Set", "Scale to Fit: the tiles fill the window, the gaps go.", "")
    assert link.names[tooltip] == [("Set", "Scale to Fit", "")]
    assert link.names[tick.key] == [("Actions", "Stop", "")]
    # a name of its own, not a sentence naming another
    assert ("Set", "Reset Scale to Fit", "") not in link.names


def test_batches_put_a_menu_item_with_its_setting():
    from scripts.translations.pipeline import context, prompt

    source = _linked_source()
    link = context.links(source)
    items = context.items(source, link)

    batches = context.batches(items, 2)

    first = [i.msg.source for i in batches[0]]
    assert first == ["Crop Limit", "Crop limit"]
    assert '"same_thing_as": [\n   "s5"\n  ]' in prompt.strings_part(batches[0], "")


def test_qa_disagreements():
    from scripts.translations.pipeline import context

    source = _linked_source()
    link = context.links(source)
    menu = _ai("Crop Limit", "Предел обрезки", context="Actions")
    setting = _ai("Crop limit", "Лимит обрезки", context="Set")
    name = _ai("Scale to Fit", "Вписать в окно", context="Set")
    tooltip = _ai(
        "Scale to Fit: the tiles fill the window, the gaps go.",
        "«По размеру окна»: плитки заполняют окно.",
        context="Set",
    )
    by_key = {m.key: m for m in (menu, setting, name, tooltip)}

    assert qa.disagreements(setting, by_key, link) == [("differs", menu)]
    assert qa.disagreements(tooltip, by_key, link) == [("names", name)]
    setting.translation = "предел обрезки…"
    tooltip.translation = "«Вписать в окно»: плитки заполняют окно."
    assert qa.disagreements(setting, by_key, link) == []
    assert qa.disagreements(tooltip, by_key, link) == []


def test_strings_that_disagree_are_asked_again_with_the_other(tmp_path):
    from scripts.translations.pipeline import ai
    from scripts.translations.pipeline.providers import Fake

    class SaysItTwoWays(Fake):
        """First time round, the setting in other words than its menu item."""

        def run(self, fixed, varying, schema):
            answer = super().run(fixed, varying, schema)
            if len(self.requests) == 1:
                for a in answer:
                    if a["text"].endswith("Crop limit"):
                        a["text"] = "[German] Zuschnittgrenze"
            return answer

    source = _linked_source()
    path = tmp_path / "de_DE.ts"
    ts_file.write(
        _lang(*[Message(context=m.context, source=m.source) for m in source.messages]),
        path,
    )
    fake = SaysItTwoWays()

    report = ai.translate(
        [ai.Job("de_DE", "German", path)],
        ai.Common(source, tmp_path, ""),
        fake,
        batch_size=50,
        parallel=1,
        log=lambda *_: None,
    )

    assert report.languages["de_DE"].translated == 8
    assert report.languages["de_DE"].aligned == 1
    _, again = fake.requests[1]
    assert "these ids: s5\n" in again
    assert '"goes_with"' in again
    assert "[German] Crop Limit" in again
    setting = ts_file.read(path).by_key()[("Set", "Crop limit", "")]
    assert setting.translation == "[German] Crop limit"


def test_old_ai_strings_agree_only_when_asked(tmp_path):
    from scripts.translations.pipeline import ai
    from scripts.translations.pipeline.providers import Fake

    source = _linked_source()
    path = tmp_path / "de_DE.ts"
    ts_file.write(
        _lang(
            *[_ai(m.source, f"[German] {m.source}", m.context) for m in source.messages]
        ),
        path,
    )
    ts = ts_file.read(path)
    ts.by_key()[("Set", "Crop limit", "")].translation = "Zuschnittgrenze"
    ts_file.write(ts, path)

    def run(**kw):
        fake = Fake()
        ai.translate(
            [ai.Job("de_DE", "German", path)],
            ai.Common(source, tmp_path, ""),
            fake,
            batch_size=50,
            parallel=1,
            log=lambda *_: None,
            **kw,
        )
        return fake

    assert run().requests == []
    assert len(run(fix_consistency=True).requests) == 1
    fixed = ts_file.read(path).by_key()[("Set", "Crop limit", "")]
    assert fixed.translation == "[German] Crop limit"


def test_code_is_shown_once_where_places_meet(tmp_path):
    from scripts.translations.pipeline import context

    (tmp_path / "menu.py").write_text(
        "\n".join(f"line{n}" for n in range(1, 101)), encoding="utf-8"
    )
    source = TsFile(
        messages=[
            Message(context="C", source=s, locations=[("menu.py", line)])
            for s, line in (("A", 20), ("B", 25), ("C", 80))
        ]
    )
    batch = context.items(source)

    code = context.code_excerpts(batch, tmp_path)

    assert code.count("=== menu.py ===") == 1
    assert code.count(" line20\n") == 1
    assert " 12| line12" in code
    assert " 33| line33" in code
    assert " 34| line34" not in code
    assert "\n  …\n" in code
    assert " 88| line88" in code


class _FakeCrowdin:
    def __init__(self, approved=(), top=(), all_ids=None):
        self.approved = list(approved)
        self.top = list(top)
        self.all_ids = all_ids or {}

    def top_translations(self, language, file_id, approved_only):
        return self.approved if approved_only else self.top

    def translation_ids(self, string_id, language):
        return self.all_ids.get(string_id, set())


def _crowdin_strings(*sources):
    from scripts.translations.pipeline.crowdin_api import CrowdinString

    return [CrowdinString(n, ("Ctx", s, "")) for n, s in enumerate(sources, 1)]


def _tr(tid, sid, text, provider=None):
    from scripts.translations.pipeline.crowdin_api import Translation

    return Translation(tid, sid, text, provider)


def test_crowdin_key_reads_comment_and_unescapes():
    from scripts.translations.pipeline.crowdin_api import escape, string_key

    assert string_key(
        "&lt;b&gt;Media&lt;/b&gt;", "Dialog - Add Files\nFile formats\nplayer/x.py:64"
    ) == ("Dialog - Add Files", "<b>Media</b>", "File formats")
    assert string_key("Play", "Actions\nparams/actions.py:7") == ("Actions", "Play", "")
    # a translator note comes first
    assert string_key(
        "{PERCENT}% AI",
        "share translated by AI\nLanguageList\nwidgets/language_list.py:76",
        "LanguageList['{PERCENT}% AI']",
    ) == ("LanguageList", "{PERCENT}% AI", "")
    assert escape('<a href="{URL}">') == "&lt;a href=&quot;{URL}&quot;&gt;"


def test_pull_gives_approved_and_people_suggestions_not_ai_ones():
    from scripts.translations.pipeline import sync

    client = _FakeCrowdin(
        approved=[_tr(10, 1, "Abspielen")],
        top=[_tr(10, 1, "Abspielen"), _tr(11, 2, "Stoppen"), _tr(12, 3, "KI", "ai")],
    )

    pulled = sync.pull(
        client, 19, _crowdin_strings("Play", "Stop", "Pause"), "de", _lang()
    )

    assert pulled.approved == {("Ctx", "Play", ""): "Abspielen"}
    assert pulled.suggestions == {("Ctx", "Stop", ""): ["Stoppen"]}


def test_pull_takes_down_an_ai_translation_a_reviewer_deleted():
    from scripts.translations.pipeline import sync

    kept, gone = _ai("Play", "Abspielen"), _ai("Stop", "Halt")
    sync.set_crowdin_id(kept, 21)
    sync.set_crowdin_id(gone, 22)
    lang = _lang(kept, gone)
    client = _FakeCrowdin(top=[_tr(21, 1, "Abspielen", "ai")], all_ids={2: {30}})

    pulled = sync.pull(client, 19, _crowdin_strings("Play", "Stop"), "de", lang)

    assert pulled.rejected == [("Ctx", "Stop", "")]
    assert kept.origin == AI
    assert gone.origin == MISSING
    assert merge.rejected(gone) == ["Halt"]
    assert merge.todo(lang) == [gone]


def test_push_sends_only_ai_strings_crowdin_has_nothing_for():
    from scripts.translations.pipeline import sync

    sent_before = _ai("Pause", "Pause")
    sync.set_crowdin_id(sent_before, 5)
    lang = _lang(
        _ai("Play", "Abspielen"),
        _ai("Stop", "Halt"),
        sent_before,
        _human("Next", "Weiter"),
    )
    client = _FakeCrowdin(top=[_tr(40, 2, "Stoppen")])

    todo = sync.to_push(
        client, 19, _crowdin_strings("Play", "Stop", "Pause", "Next"), "de", lang
    )

    assert [(m.source, sid) for m, sid in todo] == [("Play", 1)]
    sync.set_crowdin_id(todo[0][0], 77)
    assert sync.crowdin_id(todo[0][0]) == 77
    assert todo[0][0].extras[ts_file.AI_EXTRA] == "fake/model 2026-11-23"


def test_screenshot_texts_find_their_strings():
    from scripts.translations.pipeline.shots import Matcher

    keys = [
        ("Ctx", "General", ""),
        ("Ctx", "Open {name}?", ""),
        ("Ctx", "<b>Fit</b> keeps the whole picture", ""),
        ("Other", "General", ""),
    ]
    m = Matcher.of(keys)

    assert m.find("GENERAL") == [("Ctx", "General", ""), ("Other", "General", "")]
    assert m.find("Open a.mp4?") == [("Ctx", "Open {name}?", "")]
    assert m.find("Help: Fit keeps the whole picture. More…") == [
        ("Ctx", "<b>Fit</b> keeps the whole picture", "")
    ]
    assert m.find("Nothing like it") == []


def _review_file():
    return _lang(
        _human("Stop", "Стоп"),
        _ai("Seek", "Поиск"),
        _ai("Fill gaps", "Заполнять пробелы"),
        _ai("Show {name}", "Показать {name}"),
    )


def test_review_shows_the_whole_file_and_fixes_what_it_finds():
    from scripts.translations.pipeline import review
    from scripts.translations.pipeline.providers import Fake

    ts = _review_file()
    fake = Fake()
    fake.findings = [
        {"id": "r2", "kind": "meaning", "problem": "search", "fix": "Перемотка"},
        # breaks a placeholder: refused
        {"id": "r4", "kind": "grammar", "problem": "x", "fix": "Показать {nom}"},
        # a person's translation is not the review's to change
        {"id": "r1", "kind": "meaning", "problem": "x", "fix": "Остановить"},
    ]

    report = review.review(ts, review.targets(ts), "Russian", "", fake)

    fixed, ask = fake.requests[0]
    assert '"approved": true' in fixed
    assert '"en": "Fill gaps"' in fixed
    assert "all the 3 AI drafts" in ask
    stop, seek, gaps, show = ts.live()
    assert (stop.translation, seek.translation) == ("Стоп", "Перемотка")
    assert show.translation == "Показать {name}"
    assert [f.applied for f in report.findings] == [True, False]
    assert "placeholders" in report.findings[1].refused
    assert seek.origin == AI
    assert all(ts_file.REVIEWED_EXTRA in m.extras for m in (seek, gaps, show))


def test_a_later_review_asks_only_about_what_is_new():
    from scripts.translations.pipeline import review
    from scripts.translations.pipeline.providers import Fake

    ts = _review_file()
    review.review(ts, review.targets(ts), "Russian", "", Fake())
    gaps = ts.live()[2]
    merge.set_ai(gaps, "Заполнять промежутки", "fake/model 2026-11-24")

    assert review.targets(ts) == [gaps]
    fake = Fake()
    review.review(ts, review.targets(ts), "Russian", "", fake)
    assert "only these ids: r3\n" in fake.requests[0][1]


def test_review_leaves_out_what_crowdin_has():
    from scripts.translations.pipeline import review, sync

    ts = _review_file()
    sync.set_crowdin_id(ts.live()[1], 77)

    assert [m.source for m in review.targets(ts)] == ["Fill gaps", "Show {name}"]
