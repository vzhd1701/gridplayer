# Translations

What ships for each string: its translation approved on Crowdin, else an AI
translation, else the English. People always win: an approved translation
replaces the AI's at the next update.

## Updating the translations, step by step

Once, before the first update:

1. Install the [Crowdin CLI](https://crowdin.github.io/crowdin-cli/) and
   `lrelease` (Qt Linguist tools).
2. Put the Crowdin credentials in `.local/crowdin.yml` (`project_id`,
   `api_token`, `base_url`); the token needs the project's source files and
   strings, translations, screenshots and storage.
3. Have at least one AI provider working:
   * `claude`: the Claude Code CLI, logged in;
   * `codex`: the Codex CLI, logged in;
   * `openrouter`: a key in `.local/openrouter.yml` (`api_key: ...`) or in
     `OPENROUTER_API_KEY`.

Each time:

1. Commit or stash your other work: the update is a commit of its own.
2. Run everything:

   ```bash
   just translations-all
   ```

   or with options for the AI step, e.g.
   `just translations-all --provider codex`. It stops at the first step that
   fails; run the steps from there by hand (below).
3. If the AI step stopped (a used-up quota, Ctrl+C), go on where it stopped,
   with the same or another provider, then run the rest:

   ```bash
   just translations-ai --provider openrouter
   just translations-check
   just translations-push
   just translations-stats
   just generate-resources
   ```

4. Read `build/translations/report.md`. A line marked **must fix** breaks
   the app (a `{placeholder}` the English lacks): fix that translation on
   Crowdin, then `just translations-pull`, `just translations-merge`.
5. Look at the diff of `resources/translations/` and
   `gridplayer/params/languages_progress.py`, try a language or two in the
   app, and commit: `fix: update translations`.
6. The first time only, once the run has put up the new screenshots: delete
   the ones put up by hand before, which show old screens.

   ```bash
   just translations-screenshots --no-run --upload --delete-others
   ```

## Trying one language first

Before a whole update, a test with one language you can read. It sends
nothing to Crowdin, only reads from it, and changes only that language's
file (and the shares in Settings). Czech, for example:

```bash
just translations-extract                   # en_US.ts from the code
just translations-pull --lang cs_CZ         # only reads from Crowdin
just translations-merge --lang cs_CZ
just translations-ai --lang cs_CZ           # add --limit 100 for a smaller first go
just translations-check --lang cs_CZ        # report in build/translations/report.md
just translations-stats
just generate-resources
uv run gridplayer                           # Settings → Language → Čeština
```

Then look at:

* the app in that language: menus, Settings pages, messages, and the
  shares in its language list ("· 12% checked · 88% AI");
* `build/translations/report.md`, for what the checks found;
* `git diff resources/translations/cs_CZ.ts`, each AI translation beside
  its English.

`--limit` stops after that many strings; running the AI step again goes on
from there. `--provider` tries another provider on the same language.

A few wrong AI strings can be fixed in the `.ts` file by hand: change the
text and leave its `type="unfinished"` and `<extra-gp-ai>` as they are, so
it still goes to Crowdin for review. To redo all the language's AI strings
instead, `just translations-ai --lang cs_CZ --retranslate-ai`; a person's
translation is never touched, nor one already sent to Crowdin, which is
its reviewers' to change there.

To undo it:

```bash
git restore resources/translations gridplayer/params/languages_progress.py
just generate-resources
```

## The steps

| Recipe | What it does |
| --- | --- |
| `translations-extract` | `en_US.ts` from the code (pylupdate6) |
| `translations-upload` | `en_US.ts` to Crowdin (Crowdin CLI) |
| `translations-pull` | from Crowdin: approved translations, the leading unapproved suggestion of each string, AI translations a reviewer deleted |
| `translations-merge` | each language's `.ts` rebuilt against `en_US.ts` |
| `translations-ai` | AI translations for what is missing |
| `translations-ai-review` | a second look at the new AI translations, the whole file in view; fixes errors, report in `build/translations/review.md` |
| `translations-check` | QA of every translation, into `build/translations/report.md` |
| `translations-push` | AI translations to Crowdin, marked as AI, for people to check |
| `translations-stats` | `languages_progress.py`: the shares in Settings, "· 72% checked · 28% AI" |
| `translations-update-contributors` | translators' names, from Crowdin's report |
| `translations-screenshots` | context screenshots; `--upload` sends them, `--delete-others` also deletes those put up by hand |
| `translations-all` | all of the above, then `generate-resources` |

Each runs `scripts/translations/tr.py`; `tr.py <step> --help` lists its
options (`--lang de_DE cs_CZ` for some languages only, `--limit` and
`--dry-run` for a look first).

## How it works

### The language files

`resources/translations/<lang>.ts` is what ships and also says where each
translation came from:

* approved on Crowdin: a plain `<translation>`;
* AI: `<translation type="unfinished">` followed by
  `<extra-gp-ai>provider/model date</extra-gp-ai>`, and once sent to
  Crowdin `<extra-gp-crowdin>id</extra-gp-crowdin>`. lrelease
  compiles unfinished translations unless given `-nounfinished`, which it
  must never be (`tests/test_translation_files.py` checks);
* missing: an empty `<translation type="unfinished"/>`: the English shows;
* vanished: `type="vanished"`, a person's translation of English that
  changed or went away, kept as a hint for the AI translating the new text.
  `tr.py merge --prune` drops them.

Qt knows a string by its context, text and comment: rewording the English
makes a new string. So the AI never overwrites a person's translation, and
a reworded string is translated anew, with the old translation as a hint.

### The AI step

The strings any of the run's languages miss go in batches (50 by default,
three requests at a time), those of one source file together. Each request
gives the model:

* how to translate: short plain words like the app's others, the same terms,
  tone and way of addressing the user as the approved translations;
* `scripts/translations/glossary.toml`: what the app's words mean, and the
  names to keep as they are;
* the batch's strings, each with its Qt context, a translator note (`#: ...`
  above the call in the code) and where the code uses it;
* the code around those places, 8 lines each way, each file once with its
  lines numbered: strings close together share their lines;
* every translation approved for the language;
* which ids to translate, with what the language has to say of each: the
  old wording and its approved translation, people's unapproved suggestion,
  the translations a reviewer deleted.

A request is a fixed part the provider caches, and a varying one. With
several languages, the batch is the fixed part: it goes to one language
first, then to the others, which read it from the cache at a tenth of the
price. With one language, its approved translations are, read from the
cache for every batch. All three providers cache it: Claude Code its system
prompt, OpenRouter the part marked for it, OpenAI a start it has seen.

An answer that breaks a check (a placeholder, an HTML tag, a `&` shortcut
lost or added) is asked again once; then the string stays English and is
listed. Every answer is saved as it comes, so a stopped run loses nothing.

One thing is said one way. A menu item and the same setting differ only in
capitals ("Crop Limit", "Crop limit"): they go in the same batch, marked as
the same thing. A tooltip that names an option ("Tick "Use stored cookies"")
is told how the option is translated. After the run, an AI translation that
still disagrees is asked again once with the other one's words: of two AI
strings the later in `en_US.ts`, never a person's. `check --warnings` lists
what disagrees; a name in another grammatical case shows there too, which is
fine. `ai --fix-consistency` does the same to the AI strings of earlier
runs not yet sent to Crowdin, a few requests a language.
At the end the run says what it used: tokens in, written to and read from
the cache, out, and what that would cost at API prices (Codex says none).

Providers, with each one's model and effort, and the batch size are in
`scripts/translations/config.toml`. All providers get the same prompt and
answer the same JSON, so any can continue another's work; each translation
records the provider, model and effort that made it.

What it takes, measured: the whole backlog of 2026-11 (about 1,700 strings
missing in each of 18 languages, 750 requests) is about 13 million tokens
in, most of them read from the cache, and 3 million out, half of that the
model's thinking. With Claude Opus at high effort that is about $100 at
Claude Code's API prices, $85 through OpenRouter, and two hours. The output
is most of it. A later update, a few dozen strings, costs cents.

### The review

The AI step's batches can't see each other. `review` gives the model one
language's whole file, approved translations marked, and asks only for
errors a native speaker would fix: a word in the wrong sense, grammar, one
thing said two ways, and English strings that stand for two things the
language must tell apart (those need a split in the code, and are only
reported). Taste is left alone. A fix that passes QA replaces the AI text,
which stays an AI draft for Crowdin; approved translations are never
touched. Reviewed strings are marked (`<extra-gp-reviewed>`), so the next
review asks only about new or changed ones; strings already on Crowdin are
left out, so it runs before `push`. `--report-only` changes nothing.

Tried on Russian (1,578 AI strings, before any hand fixes): Claude Opus
found 52 errors in 2.5 minutes for $1.26, all real, most of a person's list
and some the person missed; it missed a few wrong senses that an approved
string seemed to back. Codex found 133 in 7 minutes, more wrong senses
but also many rewrites for taste that made labels longer, so Claude is the
reviewer to use. Roughly $25 for all 18 languages the first time, cents
after.

### Crowdin

* `push` adds a translation with `provider: "ai"` and `isPreTranslated`, out
  of the translation memory, only for strings with no translation at all on
  Crowdin. Crowdin shows it as an AI suggestion; it counts as translated,
  not approved.
* A reviewer approving it (or another) makes it a person's: the next pull
  ships it as such. Deleting it makes the AI try once more with the deleted
  text in mind; deleted twice, the string stays English.
* People's unapproved suggestions don't ship; the AI reads them as hints.
* Crowdin keeps a `.ts` string's text escaped as in the file (`&lt;p&gt;`),
  and its context as "Qt context, comment, file:line".
* Leave Crowdin's own pre-translation and auto-approval off, or they would
  fill and approve strings without a person.

### Screenshots

Each run of `translations-all` shoots them all again and sends Crowdin only
those that changed, so they follow the app's screens:

1. `scripts/translations/screenshots/scenario.py` runs the app offscreen in
   English (`tests/real_app`, with its test clips served from
   `http://127.0.0.1:47811`, so no path of this computer shows). It opens:
   * the main window, every menu and submenu, Edit Grid;
   * every page of Settings and of the Playlist window, each long page also
     whole as one tall picture, and the list of choices of each drop-down;
   * the dialogs of a cell's menu (Rename, Timecode, Position, Crop, Delay,
     Attempts, Next After, grid size, bookmarks, lists, Add URLs), the List
     window, the network and YouTube checkups, a cell's error and its
     details, the crash window and About.

   For each screen it saves a picture and every text on it with its
   rectangle: labels, buttons, menu items, list rows, tabs. Videos are
   paused on the same frame and the text cursor doesn't blink, so a screen
   that didn't change comes out the same, byte for byte.
2. `tr.py screenshots` matches those texts to the strings of `en_US.ts`:
   whatever the case, without the markup, with a `{placeholder}` matching
   any text, and a long string also inside a bigger text.
3. With `--upload`, each picture goes up as `gp-<screen>.png` with a tag on
   each string it shows, at its place, after the source upload, so the tags
   find this update's strings. `build/translations/screenshots_sent.json`
   keeps what was sent:
   * a picture the same as the one sent, with the same tags: left alone;
   * the same picture, other tags (strings added or reworded): only its
     tags are replaced;
   * a new or changed picture: sent, keeping the screenshot's id on Crowdin
     when one by that name is there;
   * a `gp-` picture no longer made: deleted.

   Without that file (a clean `build/`), everything is sent again.
4. In Crowdin's editor, a string's screenshots show beside it, its place
   highlighted.

Pictures not named `gp-` are left alone, unless `--delete-others`.

How long it takes: shooting about 135 screens, about 70 s. Sending one
picture with its tags, about 2 s, so 4–5 minutes the first time (2 MB in
all); re-tagging one, about 1 s. On a later run usually only the error
screens, whose text carries a time, and the screens that really changed
go up.

The strings no screen shows are listed in
`build/translations/not_in_screenshots.txt`; to cover more, add screens to
the scenario.

### Trying it out

`GP_TRANSLATIONS_ROOT=<a copy of the checkout>` makes every step read and
write that copy instead (the credentials still come from this one), e.g. to
see what a provider makes of one language:

```bash
GP_TRANSLATIONS_ROOT=/tmp/gp-copy uv run python scripts/translations/tr.py ai --lang de_DE --limit 50
```

`--dry-run` writes the prompts to `build/translations/prompts/` and asks no
one.

## Known gaps

* No string has plural forms: the code fakes them ("+{count} other(s)"),
  which is wrong in Czech, Polish, Russian or Arabic. Qt's `%n` forms would
  fix it.
* The same English with two meanings in one context ("Open", "Fit") is one
  string unless the code gives a disambiguation.
* The screenshots show over 40% of the strings. Most of the rest only
  show in some states (a stream, a failing download, a checkup's results)
  or as tooltips and messages.
