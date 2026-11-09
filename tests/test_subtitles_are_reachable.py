"""The two ways subtitles go missing without anything saying so.

Both were true of this player before subtitles were added, and both fail
silently: the track is listed, selecting it reports success, and nothing is
ever drawn. Nothing else in the suite would notice either coming back.
"""

from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.settings import Settings

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _blacklisted(name):
    """The entries a blacklist actually removes; a leading # means keep."""

    blacklist = (SCRIPTS / "_helpers" / name).read_text(encoding="utf-8")

    return [
        line.strip()
        for line in blacklist.splitlines()
        if line.strip() and not line.startswith("#")
    ]


class TestTheBuildsShipWhatDrawsThem:
    """Decoding a subtitle and drawing one are different plugins.

    Each of these was measured by rendering into the software buffer with
    one plugin taken away, against a copy of the tree a build ships -- on
    Windows against what build_win.sh copies, and on Linux against a VLC
    tree run through blacklist_clean.sh with the list below. Both platforms
    gave the same answer:

      no video_filter/libblend  -- nothing draws at all, in any format
      no text_renderer          -- srt, webvtt and ttml draw nothing
      no codec/libass           -- ass and ssa draw nothing, and do NOT
                                   fall back to the text renderer
      no misc (libxml)          -- a ttml track is not even listed

    Every one of them looks the same from the outside: the track is there,
    selecting it reports success, and the picture never changes. The Linux
    builds shipped that way until subtitles were added -- text_renderer was
    on the blacklist, so the snap had no text_renderer directory at all.
    """

    @pytest.mark.parametrize(
        "build_script",
        [
            ("pyinstaller", "build_win.sh"),
            ("windows", "build_mpv.ps1"),
        ],
    )
    def test_the_windows_builds_ship_libmpv(self, build_script):
        """On Windows libmpv draws them itself: it is the one file to ship."""

        script = SCRIPTS.joinpath(*build_script).read_text(encoding="utf-8")

        assert "libmpv-2.dll" in script

    @pytest.mark.parametrize(
        "plugin_dir",
        [
            "plugins/text_renderer",
            "plugins/codec",
            "plugins/misc",
            "plugins/demux",
            "plugins/video_chroma",
            "plugins/video_filter",
        ],
    )
    def test_the_linux_builds_do_not_throw_it_away(self, plugin_dir):
        assert plugin_dir not in _blacklisted("blacklist_vlc_linux.txt")
