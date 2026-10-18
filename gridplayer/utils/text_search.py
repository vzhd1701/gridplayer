"""Words typed into a search box, and where they are found in a text.

A word is found where a word of the text starts with it, whatever the case
and the accents: "pau" in "Paused", "fur" in "Für". Scripts written without
spaces have no words to start, so there a word is found anywhere in the
text. Every word typed has to be found, in any order.
"""

import functools
import html
import re
import unicodedata
from collections.abc import Iterable

_TAG = re.compile(r"<[^>]*>")


# the same labels are searched on every key typed
@functools.lru_cache(maxsize=4096)
def _fold(text: str) -> tuple[str, tuple[int, ...]]:
    """The text in lower case and without accents, and where each of its
    characters came from in the text as it was."""

    folded, origin = [], []
    for at, char in enumerate(text):
        for base in unicodedata.normalize("NFKD", char):
            if unicodedata.combining(base):
                continue
            for lower in base.casefold():
                folded.append(lower)
                origin.append(at)
    return "".join(folded), tuple(origin)


def _is_spaceless(word: str) -> bool:
    # Chinese, Japanese and the like
    return any(unicodedata.east_asian_width(char) in "WF" for char in word)


def plain_text(text: str) -> str:
    """What a label written in HTML reads as."""

    return html.unescape(_TAG.sub("", text))


class Query:
    """What is typed, as words to find."""

    def __init__(self, text: str):
        self.text = text.strip()
        folded, _ = _fold(self.text)
        self.words = tuple(dict.fromkeys(re.findall(r"\w+", folded)))
        # None for a word of a script without spaces, found anywhere
        self._patterns = {
            word: None if _is_spaceless(word) else re.compile(re.escape(word))
            for word in self.words
        }

    def __bool__(self):
        return bool(self.words)

    def _starts(self, folded: str, word: str):
        pattern = self._patterns[word]
        if pattern is None:
            start = folded.find(word)
            while start >= 0:
                yield start
                start = folded.find(word, start + 1)
            return

        for found in pattern.finditer(folded):
            start = found.start()
            if start == 0 or not folded[start - 1].isalnum():
                yield start

    def found_words(self, text: str) -> set[str]:
        """The words found in the text."""

        folded, _ = _fold(text)
        return {
            word
            for word in self.words
            if next(self._starts(folded, word), None) is not None
        }

    def found_in(self, texts: Iterable[str]) -> set[str]:
        """The words found, each in any of the texts."""

        return set().union(*(self.found_words(text) for text in texts))

    def is_in(self, texts: Iterable[str]) -> bool:
        """Every word found, each in any of the texts."""

        left = set(self.words)
        for text in texts:
            left -= self.found_words(text)
            if not left:
                return True
        return not left

    def spans(self, text: str) -> list[tuple[int, int]]:
        """Where in the text the words are found, start and end, in order
        and joined where they overlap."""

        folded, origin = _fold(text)

        spans = []
        for word in self.words:
            for start in self._starts(folded, word):
                end = start + len(word)
                spans.append((origin[start], origin[end - 1] + 1))

        joined = []
        for start, end in sorted(spans):
            if joined and start <= joined[-1][1]:
                joined[-1] = (joined[-1][0], max(end, joined[-1][1]))
            else:
                joined.append((start, end))
        return joined

    def marked(self, text: str, mark: str, *, is_html: bool = False) -> str:
        """The text as HTML, with what is found in it inside the mark's tag
        (mark is its opening tag, as "<span style=...>").

        In HTML, only the words are marked: never a tag or an entity."""

        close = "</" + re.match(r"<(\w+)", mark).group(1) + ">"

        def mark_plain(plain):
            out, at = [], 0
            for start, end in self.spans(plain):
                out.append(html.escape(plain[at:start]))
                out.append(mark + html.escape(plain[start:end]) + close)
                at = end
            out.append(html.escape(plain[at:]))
            return "".join(out)

        if not is_html:
            return mark_plain(text)

        out = []
        for part in re.split(r"(<[^>]*>|&#?\w+;)", text):
            if part.startswith("<") or (part.startswith("&") and part.endswith(";")):
                out.append(part)
            else:
                out.append(mark_plain(part))
        return "".join(out)
