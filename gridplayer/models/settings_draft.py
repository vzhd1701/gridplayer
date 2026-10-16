"""Pending field edits, independent of their widgets and settings store."""

from dataclasses import dataclass
from enum import Enum, auto


class SettingsMode(Enum):
    DEFAULTS = auto()
    OVERRIDES = auto()


class EditIntent(Enum):
    UNCHANGED = auto()
    SET = auto()
    RESET = auto()


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
    intent: EditIntent = EditIntent.UNCHANGED

    @property
    def is_overridden(self) -> bool:
        return self.intent is EditIntent.SET or (
            self.intent is EditIntent.UNCHANGED and self.original_override
        )

    def edit(self):
        self.intent = EditIntent.SET

    def reset(self):
        self.intent = EditIntent.RESET

    def result(
        self,
        value,
        default,
        mode: SettingsMode,
        *,
        is_default: bool,
        preserve: bool,
    ) -> SetValue | ResetValue | None:
        if mode is SettingsMode.OVERRIDES:
            return SetValue(value) if self.is_overridden or value != default else RESET
        if is_default:
            return RESET
        return None if preserve else SetValue(value)
