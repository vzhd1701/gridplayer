from types import SimpleNamespace

import pytest

from gridplayer.mpv_player import conf
from gridplayer.mpv_player.conf import ConfLine, Skip, Skipped, parse_conf, resolve

_KNOWN = {"deband", "hwdec", "scale", "vo", "gpu-api", "sub-use-margins", "wid"}


def _option_info(name):
    return {"type": "String"} if name in _KNOWN else None


def test_lines_are_read_as_mpv_reads_them():
    lines, skipped = parse_conf(
        '# a comment\n\ndeband\n--scale = spline36\nhwdec="nvdec"\nnot an option\n'
    )

    assert lines == [
        ConfLine(3, "deband", "deband", "yes"),
        ConfLine(4, "--scale = spline36", "scale", "spline36"),
        ConfLine(5, 'hwdec="nvdec"', "hwdec", "nvdec"),
    ]
    assert skipped == [Skipped(6, "not an option", Skip.NOT_AN_OPTION)]


def test_profiles_are_left_out():
    lines, skipped = parse_conf("deband=yes\n[big]\nscale=spline36\n")

    assert [line.name for line in lines] == ["deband"]
    assert [line.why for line in skipped] == [Skip.PROFILE, Skip.PROFILE]


def test_a_name_with_no_in_front_turns_its_flag_off():
    lines, _ = parse_conf("no-deband")

    kept, skipped = resolve(lines, _option_info, is_direct=False)

    assert [(line.name, line.value) for line in kept] == [("deband", "no")]
    assert skipped == []


def test_a_name_mpv_does_not_know_is_skipped():
    lines, _ = parse_conf("scael=spline36")

    kept, skipped = resolve(lines, _option_info, is_direct=False)

    assert kept == []
    assert skipped == [Skipped(1, "scael=spline36", Skip.UNKNOWN)]


@pytest.mark.parametrize(
    "line", ["wid=5", "input-ipc-server=x", "load-scripts=yes", "video-zoom=1"]
)
def test_what_the_app_sets_itself_is_skipped(line):
    lines, _ = parse_conf(line)

    _, skipped = resolve(lines, _option_info, is_direct=True)

    assert [line.why for line in skipped] == [Skip.APP_OWN]


@pytest.mark.parametrize(
    ("line", "on_direct", "elsewhere"),
    [
        ("vo=gpu-next", None, Skip.DIRECT_ONLY),
        ("gpu-api=vulkan", None, Skip.DIRECT_ONLY),
        ("sub-use-margins=yes", Skip.APP_OWN, None),
    ],
)
def test_some_go_by_the_output(line, on_direct, elsewhere):
    lines, _ = parse_conf(line)

    for is_direct, why in ((True, on_direct), (False, elsewhere)):
        _, skipped = resolve(lines, _option_info, is_direct=is_direct)
        assert [line.why for line in skipped] == ([why] if why else [])


def test_no_file_is_no_options(tmp_path):
    assert conf.read_conf(tmp_path / "mpv.conf") == ""


class _CheckingMpv:
    def __init__(self, **_options):
        self.is_terminated = False

    @staticmethod
    def option_info(name):
        return _option_info(name)

    @staticmethod
    def command(*args):
        if args == ("set", "deband", "maybe"):
            raise ValueError("invalid value")

    def terminate(self):
        self.is_terminated = True


def test_check_says_what_a_video_would_take_and_skip(tmp_path, monkeypatch):
    path = tmp_path / "mpv.conf"
    path.write_text("scale=spline36\ndeband=maybe\nscael=x\nvo=gpu-next\n")
    monkeypatch.setattr(conf, "conf_path", lambda: path)

    taken, skipped = conf.check_conf(SimpleNamespace(MPV=_CheckingMpv), False)

    assert taken == 1
    assert [(line.number, line.why) for line in skipped] == [
        (2, Skip.BAD_VALUE),
        (3, Skip.UNKNOWN),
        (4, Skip.DIRECT_ONLY),
    ]


def test_check_with_an_mpv_that_will_not_start(tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "conf_path", lambda: tmp_path / "mpv.conf")

    def broken(**_options):
        raise OSError("no")

    assert conf.check_conf(SimpleNamespace(MPV=broken), False) is None


def test_a_new_file_says_how_it_is_read():
    lines, skipped = parse_conf(conf.TEMPLATE)

    assert lines == []
    assert skipped == []
