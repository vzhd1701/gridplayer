"""What the AI is shown about each string.

Two kinds of things: what is the same for every language (the string, its
notes, the code where it is used, the strings it goes with) and what is a
language's own (its approved translations, the old wording a person
translated, people's unapproved suggestions, what a reviewer deleted, how
the strings it goes with are already translated). Kept apart, so the first
can be sent once and read from a provider's cache for every language.
"""

import difflib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from scripts.translations.pipeline import merge
from scripts.translations.pipeline.ts_file import HUMAN, VANISHED, Message, TsFile

CODE_RADIUS = 8
MAX_PLACES = 2
SIMILAR_RATIO = 0.6
# the longest string that can be the name of something
NAME_MAX_CHARS = 60
MIN_WORDS = 2
# a string this long is prose, which may name an option
PROSE_MIN_WORDS = 8

Key = tuple[str, str, str]

_QUOTED = re.compile(r'"([^"\n]+)"|“([^”\n]+)”|«([^»\n]+)»')


@dataclass
class Links:
    """Strings that are one thing said twice: a menu item and its setting
    differ only in capitals ("Crop Limit", "Crop limit"); a tooltip names an
    option, a button or a page (Tick "Use stored cookies")."""

    same: dict[Key, list[Key]] = field(default_factory=dict)
    names: dict[Key, list[Key]] = field(default_factory=dict)
    order: dict[Key, int] = field(default_factory=dict)

    def related(self, key: Key) -> list[Key]:
        return self.same.get(key, []) + self.names.get(key, [])

    def later(self, a: Key, b: Key) -> bool:
        """a comes after b in en_US.ts: of two strings that disagree,
        the one to change."""
        return self.order.get(a, 0) > self.order.get(b, 0)


def links(source: TsFile) -> Links:
    live = source.live()
    by_fold = defaultdict(list)
    nameable = defaultdict(list)
    for m in live:
        by_fold[m.source.casefold()].append(m)
        if _nameable(m.source):
            nameable[m.source].append(m)

    result = Links(order={m.key: n for n, m in enumerate(live)})
    for m in live:
        same = [
            o.key
            for o in by_fold[m.source.casefold()]
            if o.source != m.source
            # told apart on purpose when they carry a meaning
            and not (o.comment or m.comment)
            # one word can't always be said the same: "Any" ("Любая" crop,
            # "любой" language)
            and len(m.source.split()) >= MIN_WORDS
        ]
        if same:
            result.same[m.key] = same

        quoted = {g for q in _QUOTED.finditer(m.source) for g in q.groups() if g}
        if not quoted and len(m.source.split()) < PROSE_MIN_WORDS:
            continue  # names nothing
        named = []
        for text, msgs in nameable.items():
            if text == m.source or text not in m.source:
                continue
            if text in quoted or _named_in(text, m.source):
                in_context = [o for o in msgs if o.context == m.context]
                named += [o.key for o in in_context or msgs]
        if named:
            result.names[m.key] = named
    return result


def _nameable(text: str) -> bool:
    return (
        len(text) <= NAME_MAX_CHARS
        and "\n" not in text
        and not any(c in text for c in "{%<")
        and not text.rstrip().endswith((".", "?", "!"))
    )


def _named_in(name: str, text: str) -> bool:
    """name, of two words or more and capitalised, whole in a sentence or
    two: "Scale to Fit: the tiles fill the window." (and not "Cell Size" in
    "Reset Cell Size", a name of its own)."""
    if len(name.split()) < MIN_WORDS or not name[0].isupper():
        return False
    if len(text.split()) < PROSE_MIN_WORDS:
        return False
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text) is not None


@dataclass
class Item:
    """A string to translate, the same for every language."""

    id: str
    msg: Message  # from en_US.ts, with its places in the code
    same: list[Key] = field(default_factory=list)
    names: list[Key] = field(default_factory=list)

    @property
    def key(self) -> Key:
        return self.msg.key

    @property
    def places(self) -> list[tuple[str, int]]:
        return self.msg.locations[:MAX_PLACES]

    def as_prompt(self, ids: dict[Key, str] | None = None) -> dict:
        """ids: of the other strings in the same request."""
        data = {"id": self.id, "text": self.msg.source, "qt_context": self.msg.context}
        if self.msg.comment:
            data["meaning"] = self.msg.comment
        if self.msg.extracomment:
            data["note"] = self.msg.extracomment
        if self.places:
            data["where"] = [f"{f}:{line}" for f, line in self.places]
        ids = ids or {}
        if same := [ids[k] for k in self.same if k in ids]:
            data["same_thing_as"] = same
        if names := [ids[k] for k in self.names if k in ids]:
            data["names"] = names
        return data


@dataclass
class Hints:
    """What one language has to say about one string."""

    earlier: list[tuple[str, str]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    related: list[tuple[str, str]] = field(default_factory=list)
    problem: str = ""

    def as_prompt(self) -> dict:
        data = {}
        if self.earlier:
            data["earlier_wording"] = [
                {"english": en, "approved_translation": tr} for en, tr in self.earlier
            ]
        if self.suggestions:
            data["suggested_by_people"] = self.suggestions
        if self.rejected:
            data["rejected_by_reviewer"] = self.rejected
        if self.related:
            data["goes_with"] = [
                {"english": en, "translation": tr} for en, tr in self.related
            ]
        if self.problem:
            data["problem_with_last_try"] = self.problem
        return data


def items(source: TsFile, link: Links | None = None) -> list[Item]:
    """The strings of en_US.ts, numbered by their place there, so a
    string has the same id in every request."""
    link = link or Links()
    return [
        Item(
            id=f"s{n}",
            msg=m,
            same=link.same.get(m.key, []),
            names=link.names.get(m.key, []),
        )
        for n, m in enumerate(source.live(), 1)
    ]


def vanished_by_context(lang: TsFile) -> dict[str, list[Message]]:
    """The language's vanished hints, for hints()."""
    found = defaultdict(list)
    for m in lang.messages:
        if m.origin == VANISHED:
            found[m.context].append(m)
    return found


def hints(
    msg: Message,
    vanished: dict[str, list[Message]],
    suggestions: dict | None,
    related: list[tuple[str, str]] | None = None,
) -> Hints:
    return Hints(
        earlier=similar(msg, vanished.get(msg.context, [])),
        suggestions=(suggestions or {}).get(msg.key, []),
        rejected=merge.rejected(msg),
        related=related or [],
    )


def related_translations(
    key: Key, link: Links, translated: dict[Key, Message], skip=frozenset()
) -> list[tuple[str, str]]:
    """How the language already says the strings this one goes with."""
    seen = {}
    for other in link.related(key):
        m = translated.get(other)
        if m is not None and m.translation and other not in skip:
            seen.setdefault((m.source, m.translation), None)
    return list(seen)


def batches(all_items: list[Item], size: int) -> list[list[Item]]:
    """Strings of one file together, so each sees its neighbours; small files
    packed together, a big one split. Strings that differ only in capitals
    go in the same batch, wherever the other one is used."""

    by_key = {i.key: i for i in all_items}
    placed = set()
    groups = defaultdict(list)  # file -> units kept whole
    for item in all_items:
        if item.key in placed:
            continue
        unit = [item] + [
            by_key[k] for k in item.same if k in by_key and k not in placed
        ]
        placed.update(i.key for i in unit)
        groups[item.places[0][0] if item.places else item.msg.context].append(unit)

    result = []
    current: list[Item] = []
    for units in groups.values():
        if current and len(current) + sum(len(u) for u in units) > size:
            result.append(current)
            current = []
        chunks = list(_chunks(units, size))
        result.extend(chunks[:-1])
        current.extend(chunks[-1])
    if current:
        result.append(current)
    return result


def _chunks(units: list[list[Item]], size: int):
    chunk: list[Item] = []
    for unit in units:
        if chunk and len(chunk) + len(unit) > size:
            yield chunk
            chunk = []
        chunk.extend(unit)
    if chunk:
        yield chunk


def code_excerpts(batch: list[Item], app_dir: Path) -> str:
    """The code around every place a batch's strings are used: each file
    once, the lines around its places merged where they meet, numbered."""

    ranges = defaultdict(list)
    for item in batch:
        for filename, line in item.places:
            ranges[filename].append((max(line - CODE_RADIUS, 1), line + CODE_RADIUS))

    parts = []
    for filename, spans in ranges.items():
        lines = _lines(app_dir / filename)
        if not lines:
            continue
        width = len(str(len(lines)))
        chunks = []
        for start, end in _merged(spans):
            end = min(end, len(lines))
            chunks.append(
                "\n".join(
                    f"{n:>{width}}| {lines[n - 1]}" for n in range(start, end + 1)
                )
            )
        parts.append(f"=== {filename} ===\n" + "\n  …\n".join(chunks))
    return "\n\n".join(parts)


def _merged(spans):
    result = []
    for start, end in sorted(spans):
        if result and start <= result[-1][1] + 1:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def memory(lang: TsFile) -> list[tuple[str, str]]:
    """The language's approved translations, for the AI to follow."""
    return [(m.source, m.translation) for m in lang.live() if m.origin == HUMAN]


def similar(msg: Message, candidates: list[Message]) -> list[tuple[str, str]]:
    scored = []
    for old in candidates:
        ratio = difflib.SequenceMatcher(None, msg.source, old.source).ratio()
        if ratio >= SIMILAR_RATIO:
            scored.append((ratio, old.source, old.translation))
    scored.sort(reverse=True)
    return [(en, tr) for _, en, tr in scored[:2]]


@cache
def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
