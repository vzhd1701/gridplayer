"""Crowdin and the language files: people's work comes in, the AI's goes out.

pull: approved translations (what ships before the AI's), the leading
unapproved suggestion of each string (a hint for the AI), and which of the
AI translations sent earlier a reviewer took down.

push: AI translations Crowdin has nothing for yet, marked as AI so
translators see them as suggestions to check.
"""

from dataclasses import dataclass, field

from scripts.translations.pipeline import merge
from scripts.translations.pipeline.ts_file import AI, CROWDIN_EXTRA, Message, TsFile


def crowdin_id(msg: Message) -> int | None:
    found = msg.extras.get(CROWDIN_EXTRA)
    return int(found) if found else None


def set_crowdin_id(msg: Message, translation_id: int) -> None:
    msg.extras[CROWDIN_EXTRA] = str(translation_id)


@dataclass
class Pulled:
    approved: dict = field(default_factory=dict)
    suggestions: dict = field(default_factory=dict)
    rejected: list = field(default_factory=list)


def pull(client, file_id: int, strings, language: str, lang: TsFile) -> Pulled:
    """`lang` loses the AI translations a reviewer took down (each is kept
    as rejected, for the AI to try something else once)."""

    key_of = {s.id: s.key for s in strings}
    id_of = {s.key: s.id for s in strings}
    result = Pulled()

    for t in client.top_translations(language, file_id, approved_only=True):
        if t.string_id in key_of:
            result.approved[key_of[t.string_id]] = t.text

    top = {}
    for t in client.top_translations(language, file_id, approved_only=False):
        top[t.string_id] = t
        key = key_of.get(t.string_id)
        if key and key not in result.approved and t.provider != "ai":
            result.suggestions[key] = [t.text]

    for msg in lang.live():
        if msg.origin != AI or msg.key in result.approved:
            continue
        ours = crowdin_id(msg)
        string_id = id_of.get(msg.key)
        if ours is None or string_id is None:
            continue
        leading = top.get(string_id)
        if leading is not None and leading.id == ours:
            continue
        if ours in client.translation_ids(string_id, language):
            continue
        result.rejected.append(msg.key)
        merge.take_down(msg)

    return result


def to_push(client, file_id: int, strings, language: str, lang: TsFile):
    """(message, string id) of the AI translations to send: not sent yet,
    and nothing on Crowdin for the string, not even a suggestion."""

    id_of = {s.key: s.id for s in strings}
    translated = {
        t.string_id
        for t in client.top_translations(language, file_id, approved_only=False)
    }
    return [
        (msg, id_of[msg.key])
        for msg in lang.live()
        if msg.origin == AI
        and crowdin_id(msg) is None
        and msg.key in id_of
        and id_of[msg.key] not in translated
    ]
