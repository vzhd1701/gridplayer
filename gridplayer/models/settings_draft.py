"""Pending field edits, independent of their widgets and settings store."""

from dataclasses import dataclass
from enum import Enum, auto


class SettingsMode(Enum):
    DEFAULTS = auto()
    OVERRIDES = auto()


class EditIntent(Enum):
    UNCHANGED = auto()
    SET = auto()


@dataclass(frozen=True)
class ResetIntent:
    displayed: object


@dataclass(frozen=True)
class SetValue:
    value: object


@dataclass(frozen=True)
class ResetValue:
    """Remove the stored value or playlist override."""


RESET = ResetValue()


@dataclass
class FieldDraft:
    original: object = None
    initial_display: object = None
    original_override: bool = False
    intent: EditIntent | ResetIntent = EditIntent.UNCHANGED

    @property
    def is_reset(self) -> bool:
        return isinstance(self.intent, ResetIntent)

    @property
    def is_overridden(self) -> bool:
        return self.intent is EditIntent.SET or (
            self.intent is EditIntent.UNCHANGED and self.original_override
        )

    def edit(self):
        self.intent = EditIntent.SET

    def reset(self, displayed):
        self.intent = ResetIntent(displayed)

    def value_for_save(self, displayed, default, *, preserve_original: bool = True):
        if isinstance(self.intent, ResetIntent) and displayed == self.intent.displayed:
            return default
        if (
            preserve_original
            and self.intent is EditIntent.UNCHANGED
            and displayed == self.initial_display
        ):
            return self.original
        return displayed

    def result(
        self,
        value,
        default,
        mode: SettingsMode,
    ) -> SetValue | ResetValue:
        if mode is SettingsMode.OVERRIDES:
            return SetValue(value) if self.is_overridden or value != default else RESET
        if value == default:
            return RESET
        return SetValue(value)
