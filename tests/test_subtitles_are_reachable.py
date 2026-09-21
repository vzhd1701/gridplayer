"""The two ways subtitles go missing without anything saying so.

Both were true of this player before subtitles were added, and both fail
silently: the track is listed, selecting it reports success, and nothing is
ever drawn. Nothing else in the suite would notice either coming back.
"""

import logging
from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.settings import Settings
from gridplayer.vlc_player.instance import InstanceVLC

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _init_options(vlc_options=()):
    instance = InstanceVLC(0, list(vlc_options))
    instance._logger = logging.getLogger("test")

    return instance.init_options


class TestTheInstanceDoesNotRefuseSubtitlesOutright:
    def test_no_spu_is_never_passed(self):
        """It is settled when the input opens and cannot be undone after.

        libvlc_video_set_spu then returns success and libvlc_video_get_spu
        reports the track, while nothing is decoded or drawn -- so a video
        looks as though it is showing subtitles and is not.
        """

        assert "--no-spu" not in _init_options()

    def test_files_beside_the_video_are_still_ours_to_find(self):
        """We offer them ourselves, so VLC must not go looking as well."""

        assert "--no-sub-autodetect-file" in _init_options()

    def test_what_the_user_asked_for_is_still_passed_through(self):
        options = _init_options(["--freetype-rel-fontsize=20"])

        assert "--freetype-rel-fontsize=20" in options


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
        "plugin",
        [
            "text_renderer",
            "libblend_plugin.dll",
            "libscale_plugin.dll",
            # libass lives in codec, and ass/ssa have no fallback without it
            "plugins/codec",
            # libxml, which ttml and usf are parsed with
            "plugins/misc",
            # yuvp, which the bitmap ones are unpacked to rgba by
            "plugins/video_chroma",
            # the demuxer that opens a subtitle file on its own
            "plugins/demux",
        ],
    )
    def test_the_windows_build_copies_it(self, plugin):
        build_win = (SCRIPTS / "pyinstaller" / "build_win.sh").read_text(
            encoding="utf-8"
        )

        assert plugin in build_win

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
