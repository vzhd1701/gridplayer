"""A language's file rebuilt against the current English.

What a string ships with, in order: its approved human translation, then the
AI's, then nothing (English). The AI never takes a string a person's approved
translation holds; a changed English text is a new string (Qt keys a message
by context, text and comment), which the AI may translate.
"""

import json
from dataclasses import dataclass, field

from scripts.translations.pipeline.ts_file import (
    AI,
    AI_EXTRA,
    CROWDIN_EXTRA,
    HUMAN,
    REJECTED_EXTRA,
    REVIEWED_EXTRA,
    VANISHED,
    Message,
    TsFile,
)

Key = tuple[str, str, str]

MAX_REJECTIONS = 2


@dataclass
class MergeReport:
    human: int = 0
    ai_kept: int = 0
    ai_replaced_by_human: int = 0
    missing: int = 0
    vanished: int = 0
    dropped_human: list[Key] = field(default_factory=list)


def merge(
    source: TsFile,
    current: TsFile | None,
    approved: dict[Key, str] | None,
    language: str,
) -> tuple[TsFile, MergeReport]:
    """`approved` is everything approved on Crowdin for the language (the keys
    of strings no longer in English too), or None when it wasn't pulled: then
    the human translations the file has are kept as they are."""

    report = MergeReport()
    old = current.by_key() if current else {}
    result = TsFile(language=language, sourcelanguage="en")
    seen: set[Key] = set()

    for src in source.live():
        if src.key in seen:
            continue
        seen.add(src.key)

        msg = Message(
            context=src.context,
            source=src.source,
            comment=src.comment,
            extracomment=src.extracomment,
        )
        prev = old.get(src.key)

        human_text = _human_text(src.key, prev, approved)
        if human_text:
            msg.translation = human_text
            report.human += 1
            if prev is not None and prev.origin == AI:
                report.ai_replaced_by_human += 1
        elif prev is not None and prev.origin == AI:
            msg.translation = prev.translation
            msg.type = "unfinished"
            msg.extras = dict(prev.extras)
            report.ai_kept += 1
        else:
            msg.type = "unfinished"
            if prev is not None and REJECTED_EXTRA in prev.extras:
                msg.extras[REJECTED_EXTRA] = prev.extras[REJECTED_EXTRA]
            report.missing += 1
            if prev is not None and prev.origin == HUMAN:
                report.dropped_human.append(src.key)

        result.messages.append(msg)

    for msg in _vanished(seen, old, approved):
        result.messages.append(msg)
        report.vanished += 1

    return result, report


def _human_text(key: Key, prev: Message | None, approved) -> str:
    if approved is None:
        if prev is not None and prev.origin == HUMAN:
            return prev.translation
        return ""
    return approved.get(key, "")


def _vanished(seen: set[Key], old: dict[Key, Message], approved) -> list[Message]:
    """Human translations of English that is gone: hints for what replaced it."""

    found: dict[Key, Message] = {}

    for key, msg in old.items():
        if key in seen:
            continue
        if msg.origin in {HUMAN, VANISHED} and msg.translation:
            found[key] = _as_vanished(key, msg.translation)

    for key, text in (approved or {}).items():
        if key not in seen and text:
            found[key] = _as_vanished(key, text)

    return list(found.values())


def _as_vanished(key: Key, text: str) -> Message:
    context, source, comment = key
    return Message(
        context=context,
        source=source,
        comment=comment,
        translation=text,
        type="vanished",
    )


def set_ai(msg: Message, text: str, marker: str) -> None:
    msg.translation = text
    msg.type = "unfinished"
    msg.extras[AI_EXTRA] = marker
    # a new text is not reviewed
    msg.extras.pop(REVIEWED_EXTRA, None)


def take_down(msg: Message) -> None:
    """A reviewer deleted the AI text on Crowdin: back to missing, the
    text kept as rejected."""
    add_rejected(msg, msg.translation)
    msg.translation = ""
    for extra in (AI_EXTRA, REVIEWED_EXTRA, CROWDIN_EXTRA):
        msg.extras.pop(extra, None)


def rejected(msg: Message) -> list[str]:
    """AI translations of this English that a proofreader took down."""
    raw = msg.extras.get(REJECTED_EXTRA)
    return json.loads(raw) if raw else []


def add_rejected(msg: Message, text: str) -> None:
    texts = rejected(msg)
    if text not in texts:
        texts.append(text)
    msg.extras[REJECTED_EXTRA] = json.dumps(texts, ensure_ascii=False)


def prune_vanished(ts: TsFile) -> int:
    before = len(ts.messages)
    ts.messages = [m for m in ts.messages if m.origin != VANISHED]
    return before - len(ts.messages)


def todo(ts: TsFile, retranslate_ai: bool = False) -> list[Message]:
    """The strings the AI should translate. One sent to Crowdin is never
    redone: Crowdin would keep the old text, and an approval of it
    would come back over the new one."""

    wanted = []
    for msg in ts.live():
        if msg.origin == AI and (not retranslate_ai or CROWDIN_EXTRA in msg.extras):
            continue
        if msg.origin == HUMAN:
            continue
        if len(rejected(msg)) >= MAX_REJECTIONS:
            # stays English until the English changes
            continue
        wanted.append(msg)
    return wanted
