"""The texts the screenshots show, matched to en_US.ts strings, as Crowdin
screenshot tags."""

import html
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from scripts.translations.pipeline.qa import PLACEHOLDER

_TAG = re.compile(r"<[^>]+>")
# long enough that finding it inside a bigger text is not chance
INSIDE_MIN_CHARS = 16


def normalize(text: str) -> str:
    if "<" in text:
        text = _TAG.sub(" ", text)
    text = html.unescape(text)
    return " ".join(text.split()).casefold()


@dataclass
class Matcher:
    exact: dict[str, list] = field(default_factory=dict)
    patterns: list[tuple[re.Pattern, tuple]] = field(default_factory=list)
    long_ones: list[tuple[str, tuple]] = field(default_factory=list)

    @classmethod
    def of(cls, keys) -> "Matcher":
        m = cls()
        for key in keys:
            source = key[1]
            plain = normalize(source)
            if not plain:
                continue
            if PLACEHOLDER.search(plain):
                parts = [re.escape(p) for p in PLACEHOLDER.split(plain)]
                m.patterns.append((re.compile(".+?".join(parts)), key))
            else:
                m.exact.setdefault(plain, []).append(key)
                if len(plain) >= INSIDE_MIN_CHARS:
                    m.long_ones.append((plain, key))
        return m

    def find(self, text: str) -> list:
        plain = normalize(text)
        if plain in self.exact:
            return list(self.exact[plain])
        found = [key for pattern, key in self.patterns if pattern.fullmatch(plain)]
        if found:
            return found
        if len(plain) >= INSIDE_MIN_CHARS:
            return [key for long, key in self.long_ones if long in plain]
        return []


@dataclass
class Shot:
    path: Path
    tags: list[tuple[tuple, list[int]]]  # key, [x, y, w, h] in the picture


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def match(shots_dir: Path, tags_json: dict, keys) -> tuple[list[Shot], set]:
    """The shots with their tags, and the keys no shot shows."""

    matcher = Matcher.of(keys)
    result, covered = [], set()

    for name, data in tags_json.items():
        path = shots_dir / f"{name}.png"
        if not path.exists():
            continue
        width, _ = png_size(path)
        scale = width / data["size"][0] if data["size"][0] else 1

        tags = []
        for item in data["texts"]:
            rect = [round(v * scale) for v in item["rect"]]
            for key in matcher.find(item["text"]):
                tags.append((key, rect))
                covered.add(key)
        result.append(Shot(path, tags))

    return result, set(keys) - covered
