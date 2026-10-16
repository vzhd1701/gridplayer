from gridplayer.models.settings_draft import (
    RESET,
    EditIntent,
    FieldDraft,
    SettingsMode,
    SetValue,
)


def test_an_edit_supersedes_reset_without_losing_the_original():
    draft = FieldDraft("original", "shown", original_override=True)
    draft.reset()
    draft.edit()

    assert draft.intent is EditIntent.SET
    assert draft.is_overridden
    assert draft.original == "original"
    assert draft.initial_display == "shown"


def test_reset_removes_an_explicit_override_matching_the_default():
    draft = FieldDraft(1, 1, original_override=True)
    assert draft.result(
        1, 1, SettingsMode.OVERRIDES, is_default=True, preserve=False
    ) == SetValue(1)

    draft.reset()

    assert (
        draft.result(1, 1, SettingsMode.OVERRIDES, is_default=True, preserve=False)
        == RESET
    )


def test_a_same_value_edit_creates_an_explicit_override():
    draft = FieldDraft(1, 1)
    draft.edit()

    assert draft.result(
        1, 1, SettingsMode.OVERRIDES, is_default=True, preserve=False
    ) == SetValue(1)


def test_factory_default_is_removed_instead_of_written():
    draft = FieldDraft(1, 1, original_override=True)

    assert (
        draft.result(1, 1, SettingsMode.DEFAULTS, is_default=True, preserve=False)
        == RESET
    )


def test_a_preserved_projection_produces_no_write():
    draft = FieldDraft("hardware", "software")

    assert (
        draft.result(
            "software",
            "hardware",
            SettingsMode.DEFAULTS,
            is_default=False,
            preserve=True,
        )
        is None
    )
