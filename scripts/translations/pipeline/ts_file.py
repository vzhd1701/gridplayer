"""Qt .ts files: read any, write a language's the way Crowdin exports them.

A language's file is what ships, and also says where each translation came
from:

* human: `<translation>text</translation>`, approved on Crowdin;
* ai: `<translation type="unfinished">text</translation>` followed by
  `<extra-gp-ai>provider/model date</extra-gp-ai>`, which lrelease compiles
  all the same (only its -nounfinished leaves them out), and
  `<extra-gp-crowdin>id</extra-gp-crowdin>` once sent to Crowdin;
* missing: `<translation type="unfinished"/>`;
* vanished: `<translation type="vanished">text</translation>`, a human one
  whose English is gone, kept as a hint for the string that replaced it.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

AI_EXTRA = "gp-ai"
REJECTED_EXTRA = "gp-rejected"
# who reviewed an AI translation and when (review.py)
REVIEWED_EXTRA = "gp-reviewed"
# the id of the translation sent to Crowdin (sync.py)
CROWDIN_EXTRA = "gp-crowdin"

HUMAN = "human"
AI = "ai"
MISSING = "missing"
VANISHED = "vanished"


@dataclass
class Message:
    context: str
    source: str
    comment: str = ""
    extracomment: str = ""
    locations: list[tuple[str, int]] = field(default_factory=list)
    translation: str = ""
    type: str | None = None
    extras: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.context, self.source, self.comment

    @property
    def origin(self) -> str:
        if self.type in {"vanished", "obsolete"}:
            return VANISHED
        if not self.translation:
            return MISSING
        if AI_EXTRA in self.extras:
            return AI
        if self.type is None:
            return HUMAN
        # unfinished with text, not ours: an unreviewed translation
        return MISSING


@dataclass
class TsFile:
    messages: list[Message] = field(default_factory=list)
    language: str | None = None
    sourcelanguage: str | None = None
    version: str = "2.1"

    def by_key(self, live: bool = False) -> dict[tuple[str, str, str], Message]:
        return {m.key: m for m in (self.live() if live else self.messages)}

    def live(self) -> list[Message]:
        return [m for m in self.messages if m.origin != VANISHED]


def read(path: Path) -> TsFile:
    root = ET.parse(path).getroot()

    ts = TsFile(
        language=root.get("language"),
        sourcelanguage=root.get("sourcelanguage"),
        version=root.get("version", "2.1"),
    )

    for context_el in root.iter("context"):
        context = context_el.findtext("name", "")
        for msg_el in context_el.iter("message"):
            ts.messages.append(_read_message(context, msg_el))

    return ts


def _read_message(context: str, msg_el) -> Message:
    msg = Message(context=context, source=msg_el.findtext("source", ""))

    for el in msg_el:
        if el.tag == "location":
            msg.locations.append((el.get("filename", ""), int(el.get("line", "0"))))
        elif el.tag == "comment":
            msg.comment = el.text or ""
        elif el.tag == "extracomment":
            msg.extracomment = el.text or ""
        elif el.tag == "translation":
            msg.translation = el.text or ""
            msg.type = el.get("type")
        elif el.tag.startswith("extra-"):
            msg.extras[el.tag.removeprefix("extra-")] = el.text or ""

    return msg


def escape(text: str) -> str:
    return _xml_escape(text, {'"': "&quot;"})


def dumps(ts: TsFile) -> str:
    """The text Crowdin's export has: two spaces, no locations."""

    attrs = f' version="{ts.version}"'
    if ts.language:
        attrs += f' language="{escape(ts.language)}"'
    if ts.sourcelanguage:
        attrs += f' sourcelanguage="{escape(ts.sourcelanguage)}"'

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!DOCTYPE TS>",
        f"<TS{attrs}>",
    ]

    for context, messages in _grouped(ts.messages):
        lines.append("  <context>")
        lines.append(f"    <name>{escape(context)}</name>")
        for msg in messages:
            lines.extend(_message_lines(msg))
        lines.append("  </context>")

    lines.append("</TS>")

    return "\n".join(lines) + "\n"


def write(ts: TsFile, path: Path) -> None:
    path.write_text(dumps(ts), encoding="utf-8", newline="\n")


def _grouped(messages: list[Message]):
    groups: dict[str, list[Message]] = {}
    for msg in messages:
        groups.setdefault(msg.context, []).append(msg)
    return groups.items()


def _message_lines(msg: Message) -> list[str]:
    lines = ["    <message>", f"      <source>{escape(msg.source)}</source>"]

    if msg.comment:
        lines.append(f"      <comment>{escape(msg.comment)}</comment>")
    if msg.extracomment:
        lines.append(f"      <extracomment>{escape(msg.extracomment)}</extracomment>")

    type_attr = f' type="{msg.type}"' if msg.type else ""
    if msg.translation:
        lines.append(
            f"      <translation{type_attr}>{escape(msg.translation)}</translation>"
        )
    else:
        lines.append(f"      <translation{type_attr}/>")

    for name, value in msg.extras.items():
        lines.append(f"      <extra-{name}>{escape(value)}</extra-{name}>")

    lines.append("    </message>")

    return lines
