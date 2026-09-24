"""Where to find a JavaScript engine, beyond the places yt-dlp looks.

YouTube scrambles its stream addresses with a script that has to be run
to undo, and yt-dlp runs it by shelling out to Deno, Node, QuickJS or
Bun. It finds one by looking on PATH, which is fine for a program
started from a shell and wrong for nearly every way GridPlayer ships:

- a snap is strictly confined, so the host's /usr/bin is not merely off
  PATH but absent, and the home interface refuses hidden folders --
  which is where both Deno's installer and nvm put things
- a flatpak has the runtime's own PATH; the host's copy is readable at
  /run/host but nothing searches there
- a macOS app started from Finder inherits launchd's PATH, not the
  shell's, so Homebrew and ~/.deno/bin are both missing

So the ordinary places an engine gets installed are searched by name:
Homebrew on macOS, and the folders Deno's and Bun's own installers use.
What every package can reach besides those is the folder GridPlayer
keeps its own settings in, which is where a snap has to be given one,
and the one instruction that reads the same everywhere. A folder named
on the settings page is tried ahead of all of them, for an engine
somewhere none of this can guess.
"""

from pathlib import Path
from types import MappingProxyType

from yt_dlp.globals import supported_js_runtimes

from gridplayer.params import env
from gridplayer.settings import Settings
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.percent_re import untangle_percent_re

# yt-dlp patches urllib3 as it is imported; see utils/percent_re.py
untangle_percent_re()

# what each engine's binary is called on disk, which is not always what
# yt-dlp calls the engine: quickjs ships as "qjs". Only consulted for
# the folders yt-dlp does not search by itself, so an engine missing
# from here is still found on PATH as it always was.
JS_RUNTIME_BINARIES = MappingProxyType(
    {
        "deno": "deno",
        "node": "node",
        "bun": "bun",
        "quickjs": "qjs",
    }
)

# where a flatpak can see the host's own filesystem. Nothing else has
# this directory, so its presence is what says we are inside one.
FLATPAK_HOST_ROOT = Path("/run/host")

FLATPAK_HOST_DIRS = ("usr/local/bin", "usr/bin")

# where macOS puts things that are not part of the system. An app
# started from Finder gets launchd's PATH, which has none of these on
# it, so a Homebrew install is invisible unless it is looked for.
#
# /usr/local/bin is already found by accident on Intel -- it is where a
# frozen build reports its scripts directory, which yt-dlp searches
# before PATH -- but that is Python's default prefix showing through
# rather than anything meant, and it does nothing for Apple Silicon,
# where Homebrew lives somewhere else entirely.
MACOS_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")

# where the engines' own installers put themselves. Each one adds its
# folder to the shell profile and stops there, which is enough for a
# terminal and nothing at all for a windowed app: a dotted folder in
# $HOME is on no PATH that Finder or a sandbox ever sees.
#
# Node is not among them because nvm keeps a folder per version rather
# than one to look in.
HOME_INSTALL_DIRS = (".deno/bin", ".bun/bin")


def ytdl_js_runtimes(configured: str | None = None) -> dict:
    """Every JavaScript engine yt-dlp can drive, and where to find it.

    Naming all of them is not a vote for any one: yt-dlp ranks them and
    takes the best that answers. Left alone it would look for Deno and
    nothing else, so a machine with Node on it is told there is none.

    An engine is named with a path only where one was actually found,
    because a path yt-dlp is given is a path it looks at instead of
    PATH rather than as well as it. So the ones not found here are
    handed nothing and searched for exactly as before.

    A fresh dict each time, since yt-dlp prunes the one it is handed.
    """

    # the folders are the same for every engine, and working them out
    # reads the settings and asks the filesystem, so it is done once
    # here rather than once per engine on the way to every resolve
    directories = js_runtime_dirs(configured)

    return {
        name: _config_for(_find_js_runtime(name, directories))
        for name in supported_js_runtimes.value
    }


def js_runtime_dirs(configured: str | None = None) -> list[Path]:
    """The folders to search, best answer first.

    The settings page comes before the data folder so that naming one
    engine is enough to override a copy left behind in the other.
    """

    dirs = [configured_dir(configured), get_app_data_dir()]

    # a flatpak sees the host's binaries here and nowhere else, so a
    # system-wide install works without anyone being asked to move it
    if FLATPAK_HOST_ROOT.is_dir():
        dirs += [FLATPAK_HOST_ROOT / subdir for subdir in FLATPAK_HOST_DIRS]

    if env.IS_MACOS:
        dirs += [Path(directory) for directory in MACOS_DIRS]

    # last of the guesses: a folder somebody's package manager owns says
    # more about what they meant than one an installer script made
    dirs += [Path.home() / subdir for subdir in HOME_INSTALL_DIRS]

    return [directory for directory in dirs if directory is not None]


def _find_js_runtime(name: str, directories: list[Path]) -> Path | None:
    """The engine's binary, in the first folder that holds one.

    A stat rather than a run: asking a binary its version costs a
    process, and this happens on the way to every resolve.
    """

    basename = JS_RUNTIME_BINARIES.get(name)

    if basename is None:
        return None

    for directory in directories:
        for filename in _candidate_names(basename):
            candidate = directory / filename

            if candidate.is_file():
                return candidate

    return None


def _candidate_names(basename: str) -> tuple[str, ...]:
    return (f"{basename}.exe", basename) if env.IS_WINDOWS else (basename,)


def configured_dir(configured: str | None = None) -> Path | None:
    """The folder named on the settings page, where one is named.

    A file is taken for the folder holding it, so that pointing at the
    engine itself works as readily as pointing at where it lives.

    None means read what was saved. A string is a folder nobody has
    pressed OK on yet, which is what a checkup run from the page has to
    try: an empty one is a field somebody has just cleared, not an
    instruction to go and look up the old value.
    """

    if configured is None:
        configured = Settings().get("streaming/js_runtime_path")

    configured = str(configured or "").strip()

    if not configured:
        return None

    named = Path(configured).expanduser()

    return named.parent if named.is_file() else named


def _config_for(path: Path | None) -> dict:
    return {"path": str(path)} if path is not None else {}
