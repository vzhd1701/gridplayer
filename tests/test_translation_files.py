"""The translations that ship: nothing in them may break the app."""

from pathlib import Path

import pytest

from scripts.translations.pipeline import qa, ts_file

# this checkout's, whatever GP_TRANSLATIONS_ROOT says
ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "resources" / "translations"
LANGUAGE_FILES = [p for p in sorted(TRANSLATIONS.glob("*.ts")) if p.stem != "en_US"]


@pytest.mark.parametrize("path", LANGUAGE_FILES, ids=lambda p: p.stem)
def test_translations_name_only_placeholders_the_english_has(path):
    found = [
        f"{m.context}: {m.source!r} -> {m.translation!r}: {issue.detail}"
        for m in ts_file.read(path).live()
        if m.translation
        for issue in qa.check(m.source, m.translation, m.context)
        if issue.code == qa.CRASH
    ]

    assert found == []


@pytest.mark.parametrize("path", LANGUAGE_FILES, ids=lambda p: p.stem)
def test_ai_translations_pass_every_check(path):
    found = [
        f"{m.context}: {m.source!r} -> {m.translation!r}: {issue}"
        for m in ts_file.read(path).live()
        if m.origin == ts_file.AI
        for issue in qa.errors(qa.check(m.source, m.translation, m.context))
    ]

    assert found == []


def test_unfinished_translations_are_compiled():
    """AI translations are marked unfinished: lrelease must keep them."""

    build = (ROOT / "scripts/qt_resources/build_resources.py").read_text(
        encoding="utf-8"
    )

    assert "nounfinished" not in build
