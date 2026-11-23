"""What a translation must keep of its English.

Errors break the app or its look: a missing `{name}` makes `.format()` raise,
a stray `&` underlines a letter as a shortcut. An AI translation with one is
refused; a shipped one fails tests/test_translation_files.py. Warnings only go
in the report.
"""

import re
from collections import Counter
from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"

# an error that makes the app raise
CRASH = "placeholders-extra"

# {name} for str.format(), %1 / %n / %v for Qt
PLACEHOLDER = re.compile(r"\{[^{}\s]*\}|%(?:\d+|[nv])")
_TAG = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9]*)")
_ACCELERATOR = re.compile(r"&(?![&\s]|[A-Za-z]+;|#\d+;)")
_WORDS = re.compile(r"[A-Za-z]{2,}")

# menu strings, which should stay about as short as the English
SHORT_CONTEXTS = {"Actions"}
LONGER_LIMIT = 1.6
LONGER_MIN_CHARS = 20


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    detail: str

    def __str__(self):
        return f"{self.level}: {self.code}: {self.detail}"


def check(source: str, translation: str, context: str = "") -> list[Issue]:
    if not translation.strip():
        return [Issue(ERROR, "empty", "no text")]

    issues = []

    src_ph = Counter(PLACEHOLDER.findall(source))
    tr_ph = Counter(PLACEHOLDER.findall(translation))
    extra = sorted((tr_ph - src_ph).elements())
    if braced := [p for p in extra if p.startswith("{")]:
        # .format() raises on a name the code doesn't give
        issues.append(Issue(ERROR, CRASH, "not in English: " + " ".join(braced)))
    if src_ph - tr_ph or len(braced) < len(extra):
        issues.append(Issue(ERROR, "placeholders", _diff(src_ph, tr_ph)))

    src_tags = Counter(_tags(source))
    tr_tags = Counter(_tags(translation))
    if src_tags != tr_tags:
        issues.append(Issue(ERROR, "html", _diff(src_tags, tr_tags)))

    src_acc = len(_ACCELERATOR.findall(source))
    tr_acc = len(_ACCELERATOR.findall(translation))
    if tr_acc != src_acc:
        issues.append(
            Issue(
                ERROR, "accelerator", f"{src_acc} '&' shortcut(s) in English, {tr_acc}"
            )
        )

    if _edges(source) != _edges(translation):
        issues.append(Issue(WARNING, "whitespace", "leading or trailing spaces differ"))

    src_lines, tr_lines = source.count("\n") + 1, translation.count("\n") + 1
    if src_lines != tr_lines:
        issues.append(
            Issue(WARNING, "lines", f"{src_lines} line(s) in English, {tr_lines}")
        )

    if (
        context in SHORT_CONTEXTS
        and len(translation) > LONGER_MIN_CHARS
        and len(translation) > LONGER_LIMIT * len(source)
    ):
        issues.append(
            Issue(WARNING, "long", f"{len(translation)} chars for {len(source)}")
        )

    if translation == source and len(_WORDS.findall(source)) >= 2:
        issues.append(Issue(WARNING, "same", "same as the English"))

    return issues


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == ERROR]


def describe(issues: list[Issue]) -> str:
    return "; ".join(f"{i.code}: {i.detail}" for i in issues)


def disagreements(msg, translated: dict, links) -> list[tuple[str, object]]:
    """Where msg says differently what another string says: the same thing
    in other capitals translated with other words ("differs"), or an
    option it names not named by its translation ("names"). Gives
    (code, the other Message); translated: key -> Message, with text."""

    if not msg.translation:
        return []
    found = []
    for key in links.same.get(msg.key, []):
        other = translated.get(key)
        if (
            other
            and other.translation
            and _plain(other.translation) != _plain(msg.translation)
        ):
            found.append(("differs", other))
    for key in links.names.get(msg.key, []):
        other = translated.get(key)
        if other and other.translation:
            name = _plain(other.translation)
            if name and name not in msg.translation.casefold():
                found.append(("names", other))
    return found


def disagreement_text(code: str, other) -> str:
    if code == "differs":
        return (
            f'the same thing as "{other.source}", translated '
            f'"{other.translation}": use the same words'
        )
    return (
        f'it names "{other.source}", translated "{other.translation}": '
        "name it the same way"
    )


def _plain(text: str) -> str:
    text = _ACCELERATOR.sub("", text).strip()
    return text.rstrip("…").rstrip(".:").strip().casefold()


def _tags(text: str) -> list[str]:
    return [f"{slash}{name.lower()}" for slash, name in _TAG.findall(text)]


def _edges(text: str) -> tuple[str, str]:
    return text[: len(text) - len(text.lstrip())], text[len(text.rstrip()) :]


def _diff(want: Counter, got: Counter) -> str:
    missing = sorted((want - got).elements())
    extra = sorted((got - want).elements())
    parts = []
    if missing:
        parts.append("missing " + " ".join(missing))
    if extra:
        parts.append("extra " + " ".join(extra))
    return ", ".join(parts)
