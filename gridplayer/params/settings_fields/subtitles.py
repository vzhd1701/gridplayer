from gridplayer.params.settings_fields import choices
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ColorField,
    ComboField,
    SettingField,
    SpinField,
    When,
)
from gridplayer.params.static import SubtitleOutline
from gridplayer.utils.qt import translate

# the outline colour is worth nothing without an outline to draw
_OUTLINE_DRAWN = (
    SubtitleOutline.THIN,
    SubtitleOutline.NORMAL,
    SubtitleOutline.THICK,
)


SUBTITLE_STYLE_FIELDS: tuple[SettingField, ...] = (
    ComboField(
        settings_key="subtitles/font",
        label=translate("SettingsDialog", "Font"),
        choices=choices.font_families,
    ),
    SpinField(
        settings_key="subtitles/size_scale",
        label=translate("SettingsDialog", "Size"),
        minimum=10,
        maximum=500,
        suffix="%",
        tooltip=translate(
            "SettingsDialog",
            "Relative to VLC's size, which already scales with the video.",
        ),
    ),
    ColorField(
        settings_key="subtitles/color",
        label=translate("SettingsDialog", "Color"),
    ),
    CheckboxField(
        settings_key="subtitles/bold",
        label=translate("SettingsDialog", "Bold"),
    ),
    ComboField(
        settings_key="subtitles/outline",
        label=translate("SettingsDialog", "Outline"),
        choices=choices.subtitle_outlines,
        tooltip=translate(
            "SettingsDialog",
            "Outline around the text. Keeps white text readable on bright pictures.",
        ),
    ),
    ColorField(
        settings_key="subtitles/outline_color",
        label=translate("SettingsDialog", "Color"),
        enabled_when=When("subtitles/outline", _OUTLINE_DRAWN),
    ),
    CheckboxField(
        settings_key="subtitles/shadow",
        label=translate("SettingsDialog", "Shadow"),
    ),
    ColorField(
        settings_key="subtitles/shadow_color",
        label=translate("SettingsDialog", "Color"),
        enabled_when=When("subtitles/shadow"),
    ),
    CheckboxField(
        settings_key="subtitles/background",
        label=translate("SettingsDialog", "Background box"),
        tooltip=translate(
            "SettingsDialog",
            "Draw text on a solid box, readable over any picture.",
        ),
    ),
    ColorField(
        settings_key="subtitles/background_color",
        label=translate("SettingsDialog", "Color"),
        enabled_when=When("subtitles/background"),
    ),
    SpinField(
        settings_key="subtitles/margin",
        label=translate("SettingsDialog", "Raise from bottom"),
        minimum=0,
        maximum=500,
        special_text=translate("SettingsDialog", "Default"),
        suffix=translate("SettingsDialog", "px"),
        tooltip=translate(
            "SettingsDialog",
            "Distance from the bottom of the picture. Also applies to ASS and SSA"
            " subtitles.",
        ),
    ),
)
