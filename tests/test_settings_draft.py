from gridplayer.models.settings_draft import (
    RESET,
    EditIntent,
    FieldDraft,
    SettingsMode,
    SetValue,
)


def test_an_edit_supersedes_reset_without_losing_the_original():
    draft = FieldDraft("original", "shown", original_override=True)
    draft.reset("reset display")
    draft.edit()

    assert draft.intent is EditIntent.SET
    assert draft.is_overridden
    assert draft.original == "original"
    assert draft.initial_display == "shown"


def test_reset_removes_an_explicit_override_matching_the_default():
    draft = FieldDraft(1, 1, original_override=True)
    assert draft.result(1, 1, SettingsMode.OVERRIDES) == SetValue(1)

    draft.reset(1)

    assert draft.result(1, 1, SettingsMode.OVERRIDES) == RESET


def test_a_same_value_edit_creates_an_explicit_override():
    draft = FieldDraft(1, 1)
    draft.edit()

    assert draft.result(1, 1, SettingsMode.OVERRIDES) == SetValue(1)


def test_factory_default_is_removed_instead_of_written():
    draft = FieldDraft(1, 1, original_override=True)

    assert draft.result(1, 1, SettingsMode.DEFAULTS) == RESET


def test_a_preserved_projection_saves_the_original_value():
    draft = FieldDraft("hardware", "software")

    value = draft.value_for_save("software", "other")

    assert value == "hardware"
    assert draft.result(value, "other", SettingsMode.DEFAULTS) == SetValue("hardware")


def test_reset_preserves_the_raw_default_behind_a_rounded_display():
    draft = FieldDraft(2.0, 2.0, original_override=True)
    draft.reset(1.1)

    value = draft.value_for_save(1.1, 1.05)

    assert value == 1.05
    assert draft.result(value, 1.05, SettingsMode.OVERRIDES) == RESET


def test_changes_without_signals_are_still_saved():
    draft = FieldDraft(1.05, 1.1)

    value = draft.value_for_save(2.0, 1.05)

    assert draft.result(value, 1.05, SettingsMode.OVERRIDES) == SetValue(2.0)


def test_a_silent_edit_after_reset_supersedes_the_displayed_default():
    draft = FieldDraft(2.0, 2.0, original_override=True)
    draft.reset(1.1)

    value = draft.value_for_save(3.0, 1.05)

    assert draft.result(value, 1.05, SettingsMode.OVERRIDES) == SetValue(3.0)
