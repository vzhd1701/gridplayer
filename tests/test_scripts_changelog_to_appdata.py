import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "linux_meta"
    / "inject_changelog.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("inject_changelog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inject():
    return _load_script()


def test_strip_markdown_drops_links_and_commit_hashes(inject):
    text = (
        "Restore URI parsing for playlists "
        "([b02b31b](https://github.com/vzhd1701/gridplayer/commit/b02b31b)), "
        "closes [#294](https://github.com/vzhd1701/gridplayer/issues/294) "
        "[#311](https://github.com/vzhd1701/gridplayer/issues/311)"
    )

    assert inject.strip_markdown(text) == (
        "Restore URI parsing for playlists, closes #294 #311"
    )


def test_strip_markdown_cleans_multiple_commit_links(inject):
    text = (
        "Czech translations "
        "([fd35bf2](https://example.com/fd35bf2)), "
        "([c52c5de](https://example.com/c52c5de))"
    )

    assert inject.strip_markdown(text) == "Czech translations"


def test_latest_version_skips_unreleased(inject):
    changes = {
        "unreleased": {"added": ["WIP"]},
        "0.5.5": {"fixed": ["Bug"]},
        "0.5.4": {"fixed": ["Older"]},
    }

    assert inject.latest_version(changes) == "0.5.5"


def test_select_release_uses_requested_version(inject):
    changes = {
        "unreleased": {"added": ["WIP"]},
        "0.5.5": {"fixed": ["Newer"]},
        "0.5.4": {"fixed": ["Older"]},
    }

    version, release = inject.select_release(changes, "0.5.4")

    assert version == "0.5.4"
    assert release == {"fixed": ["Older"]}


def test_select_release_defaults_to_latest_released(inject):
    changes = {
        "unreleased": {"added": ["WIP"]},
        "0.5.5": {"fixed": ["Newer"]},
    }

    version, release = inject.select_release(changes, None)

    assert version == "0.5.5"
    assert release == {"fixed": ["Newer"]}


def test_release_description_xml_groups_sections_and_escapes(inject):
    xml = inject.release_description_xml(
        {
            "added": ["Option to use `code` & more"],
            "fixed": ["Avoid <crash>"],
            "metadata": {"version": "1.0.0"},
        }
    )

    assert xml == (
        "      <description>\n"
        "        <p>Added</p>\n"
        "        <ul>\n"
        "          <li>Option to use code &amp; more</li>\n"
        "        </ul>\n"
        "        <p>Fixed</p>\n"
        "        <ul>\n"
        "          <li>Avoid &lt;crash&gt;</li>\n"
        "        </ul>\n"
        "      </description>"
    )


def test_inject_description_expands_self_closing_release(inject):
    appdata = (
        "<component>\n"
        "  <releases>\n"
        '    <release date="2026-07-24" version="0.5.5"/>\n'
        "  </releases>\n"
        "</component>\n"
    )
    description = "      <description>\n        <p>Fixed</p>\n      </description>"

    result = inject.inject_description(appdata, description)

    assert (
        '    <release date="2026-07-24" version="0.5.5">\n'
        "      <description>\n"
        "        <p>Fixed</p>\n"
        "      </description>\n"
        "    </release>\n"
    ) in result


def test_main_inserts_requested_version(inject, tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n\n"
        "- Unreleased feature\n\n"
        "## [0.5.5] - 2026-07-24\n\n"
        "### Fixed\n\n"
        "- Restore URI parsing "
        "([b02b31b](https://example.com/b02b31b))\n\n"
        "## [0.5.4] - 2025-11-24\n\n"
        "### Added\n\n"
        "- Older feature\n",
        encoding="utf-8",
    )
    appdata = tmp_path / "app.appdata.xml"
    appdata.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<component>\n"
        "  <releases>\n"
        '    <release date="2026-07-24" version="0.5.5"/>\n'
        "  </releases>\n"
        "</component>\n",
        encoding="utf-8",
    )

    assert inject.main([str(appdata), str(changelog), "--version", "0.5.5"]) == 0

    result = appdata.read_text(encoding="utf-8")
    assert "<li>Restore URI parsing</li>" in result
    assert "Unreleased feature" not in result
    assert "Older feature" not in result
    assert 'version="0.5.5"' in result
