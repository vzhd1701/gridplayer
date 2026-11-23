"""The words every provider gets, the same for each.

A request is a fixed part, which providers cache, and a varying one:

* many languages: fixed = instructions, glossary, a batch's strings and its
  code; varying = a language's approved translations and what to do. The
  batch is read from cache for every language after the first.
* one language: fixed = instructions, glossary, the language's approved
  translations; varying = the batch and what to do. Those are read from
  cache for every batch after the first.
"""

import json
from pathlib import Path

from scripts.translations.pipeline.context import Hints, Item

SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}

# what the translator and the reviewer are told the app is
APP = """\
GridPlayer, a desktop app that plays many videos side by side in one \
window, each video in a cell of a grid. It plays local files, folders, \
playlists and online streams, with VLC or MPV."""

SYSTEM = f"""\
You translate the user interface of {APP}

You get a glossary; strings of the app, each with an id and where the code \
uses it ("where", file:line); the code around those places, lines numbered; \
the translations people already made and approved for the target language; \
and which ids to translate, with notes. Translate exactly those ids. Reply \
with JSON only: {{"translations": [{{"id": "...", "text": "..."}}]}}, one entry \
per id asked for.

How to translate:
- Plain, short, everyday words, the way the app's other strings in this \
language already say things. Menu items and buttons about as short as the \
English; a long one gets cut off.
- Follow the approved translations: same terms, same tone, same way of \
addressing the user (formal or informal), same capitalisation style for \
menu items. They were made and checked by people.
- Use the code to see what a string is: a menu item, a button, a tooltip, \
a setting's name, an error message, a unit.
- Keep exactly: {{placeholders}} with their names, %1 %n %v, HTML tags and \
attributes, line breaks, leading and trailing spaces, and the names in the \
glossary's "keep" list. Do not add & to a string that has none.
- "meaning" tells which sense of the English is meant; "note" is from the \
developer.
- Say one thing one way. "same_thing_as": ids of strings that differ from \
this one only in capitals (a menu item and the same setting in the \
Settings dialog): use the same words, each in its own capitals. "names": \
ids of strings this one names (an option, a button, a page): name them \
exactly as those are translated.
- Notes per id: "earlier_wording": the English used to say that and a \
person translated it so; keep their wording where the meaning didn't \
change. "suggested_by_people": translations people offered that no one \
approved yet; prefer them when they are right. "rejected_by_reviewer": a \
reviewer took these down; write something different. "goes_with": \
strings already translated that this one is the same as or names; use \
those words. "problem_with_last_try": your last answer broke a rule; fix \
that.
"""


def glossary_part(terms: dict[str, str], keep: list[str]) -> str:
    glossary = {"keep": keep, "terms": terms}
    return f"Glossary:\n{json.dumps(glossary, ensure_ascii=False, indent=1)}\n"


def strings_part(batch: list[Item], code: str) -> str:
    ids = {i.key: i.id for i in batch}
    return (
        f"Strings ({len(batch)}):\n"
        + json.dumps([i.as_prompt(ids) for i in batch], ensure_ascii=False, indent=1)
        + f"\n\nCode:\n{code}\n"
    )


def memory_part(language_name: str, memory: list[tuple[str, str]]) -> str:
    approved = [{"en": en, "tr": tr} for en, tr in memory]
    return (
        f"Approved {language_name} translations ({len(approved)}):\n"
        + "\n".join(json.dumps(a, ensure_ascii=False) for a in approved)
        + "\n"
    )


def ask_part(language_name: str, wanted: list[tuple[Item, Hints]]) -> str:
    notes = {item.id: h.as_prompt() for item, h in wanted if h.as_prompt()}
    text = (
        f"Translate into {language_name} the strings with these ids: "
        + ", ".join(item.id for item, _ in wanted)
        + "\n"
    )
    if notes:
        text += f"Notes per id:\n{json.dumps(notes, ensure_ascii=False, indent=1)}\n"
    return text


def request(
    glossary: str,
    strings: str,
    memory: str,
    ask: str,
    many_languages: bool,
) -> tuple[str, str]:
    """(fixed, varying): what a provider caches, and what changes."""
    if many_languages:
        return f"{SYSTEM}\n{glossary}\n{strings}", f"{memory}\n{ask}"
    return f"{SYSTEM}\n{glossary}\n{memory}", f"{strings}\n{ask}"


def dump(path: Path, fixed: str, varying: str) -> None:
    """A request as a file, for --dry-run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{fixed}\n===== varying =====\n{varying}", encoding="utf-8")
