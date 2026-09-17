import pytest

from gridplayer.utils.track_language import (
    canonical_tag,
    language_name,
    normalize,
    parse_preferences,
    pick_by_language,
)


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("en", ("en",)),
        ("en,ja", ("en", "ja")),
        ("en, ja, fr", ("en", "ja", "fr")),
        ("en; ja / fr | de", ("en", "ja", "fr", "de")),
        ("  EN  ,  Ja  ", ("en", "ja")),
        ("pt_BR", ("pt-br",)),
        ("en, en, EN", ("en",)),
        ("", ()),
        ("   ", ()),
        (",,,", ()),
    ],
)
def test_parse_preferences(written, expected):
    assert parse_preferences(written) == expected


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("en", "en"),
        ("eng", "en"),
        ("English", "en"),
        ("EN", "en"),
        ("en-US", "en"),
        ("en_us", "en"),
        ("jpn", "ja"),
        # bibliographic codes are what a container is most likely to carry
        ("fre", "fr"),
        ("fra", "fr"),
        # no alpha-2 exists for these, so the alpha-3 has to stand in
        ("cop", "cop"),
        ("tlh", "tlh"),
        # nothing to go on
        ("und", None),
        ("zxx", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize(tag, expected):
    assert normalize(tag) == expected


def test_normalize_keeps_unknown_codes_comparable():
    """Two spellings of the same unrecognised tag still have to match."""

    assert normalize("qqq") == normalize("QQQ-XX") == "qqq"


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("en", "English"),
        ("eng", "English"),
        ("cop", "Coptic"),
        ("tlh", "Klingon"),
        ("pt-BR", "Portuguese"),
        ("und", None),
        ("qqq", None),
        (None, None),
    ],
)
def test_language_name(tag, expected):
    assert language_name(tag) == expected


def test_canonical_tag():
    assert canonical_tag("  EN_us  ") == "en-us"
    assert canonical_tag(None) == ""


LADDER = [
    ("cop", "cop"),
    ("klingon", "tlh"),
    ("untagged", None),
    ("english", "en"),
]


@pytest.mark.parametrize(
    ("preferences", "expected"),
    [
        (("en",), "english"),
        (("eng",), "english"),
        (("English",), "english"),
        (("tlh",), "klingon"),
        (("Klingon",), "klingon"),
        # the user's order decides, not the order the source listed them in
        (("cop", "en"), "cop"),
        (("en", "cop"), "english"),
        # a language nobody offers falls through to the next one asked for
        (("de", "tlh"), "klingon"),
        (("de",), None),
        ((), None),
    ],
)
def test_pick_by_language(preferences, expected):
    assert pick_by_language(preferences, LADDER) == expected


def test_pick_by_language_never_answers_with_an_untagged_track():
    """A track with no language is in no language, so it satisfies nothing."""

    assert pick_by_language(("en",), [("untagged", None), ("other", "")]) is None


def test_pick_by_language_prefers_the_full_tag():
    candidates = [("us", "en-US"), ("gb", "en-GB")]

    assert pick_by_language(("en-GB",), candidates) == "gb"
    assert pick_by_language(("en-US",), candidates) == "us"


def test_pick_by_language_falls_back_to_the_bare_language():
    """ "en" is answered with whichever English there is."""

    assert pick_by_language(("en",), [("gb", "en-GB")]) == "gb"


def test_pick_by_language_exact_tag_outranks_the_bare_language():
    """A later candidate spelled out in full beats an earlier loose match."""

    candidates = [("gb", "en-GB"), ("us", "en-US")]

    assert pick_by_language(("en-US",), candidates) == "us"


def test_pick_by_language_takes_the_first_of_equals():
    candidates = [("first", "en"), ("second", "en")]

    assert pick_by_language(("en",), candidates) == "first"
